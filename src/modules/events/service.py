import logging
from typing import Any, Optional
import psycopg
from src.shared.contracts import ValidatedEvent, EventValidationError, ItemResult
from src.shared.domain_events import queue_event, EVENT_ACCEPTED, VOID_RESOLVED
from src.modules.events.validation import validate_event
from src.modules.events import repository as repo

logger = logging.getLogger("events.service")


def resolve_pending_voids(conn: psycopg.Connection, source_id: str, count_event_id: str) -> None:
    """
    When a COUNT is accepted, resolve any VOIDs that arrived earlier targeting this COUNT.
    Lowest ID pending VOID becomes ACCEPTED (auto-acknowledged).
    Any other pending VOIDs become REJECTED with reason 'target already voided by <winning_event_id>'.
    """
    pending = repo.list_pending_voids(conn, source_id, count_event_id)
    if not pending:
        return

    # First one wins
    winner = pending[0]
    winning_event_id = repo.mark_void_accepted(conn, winner["id"]) or winner["event_id"]
    queue_event(VOID_RESOLVED, {
        "event_id": winning_event_id,
        "source_id": source_id,
        "target_event_id": count_event_id
    })

    # Subsequent ones lose
    rejection_reason = f"target already voided by {winning_event_id}"
    for loser in pending[1:]:
        repo.mark_void_rejected(conn, loser["id"], rejection_reason)


def _check_duplicate_or_conflict(
    conn: psycopg.Connection,
    ev: ValidatedEvent,
    raw: Any,
    channel: str
) -> ItemResult:
    existing = repo.get_event(conn, ev.source_id, ev.event_id)
    if not existing:
        # Fallback if somehow row wasn't retrieved
        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "CONFLICT", "Unknown conflict", channel)
        return ItemResult(
            status="CONFLICT",
            event_id=ev.event_id,
            source_id=ev.source_id,
            reason="Unknown conflict"
        )

    # Normalize fields for comparison
    types_match = existing["type"] == ev.type
    quantities_match = existing["quantity"] == ev.quantity
    targets_match = (existing["target_event_id"] or None) == (ev.target_event_id or None)
    times_match = abs((existing["event_time"] - ev.event_time).total_seconds()) < 0.001

    if types_match and quantities_match and targets_match and times_match:
        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "DUPLICATE", None, channel)
        return ItemResult(
            status="DUPLICATE",
            event_id=ev.event_id,
            source_id=ev.source_id
        )
    else:
        err_msg = "Payload conflict with existing event"
        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "CONFLICT", err_msg, channel)
        return ItemResult(
            status="CONFLICT",
            event_id=ev.event_id,
            source_id=ev.source_id,
            reason=err_msg
        )


def process_count(
    conn: psycopg.Connection,
    ev: ValidatedEvent,
    raw: Any,
    channel: str
) -> ItemResult:
    # Serialize with concurrent VOIDs for this event
    repo.lock_key(conn, ev.source_id, ev.event_id)

    row_id, inserted = repo.insert_event_on_conflict(conn, ev, status="ACCEPTED", auto_ack=False)
    if not inserted:
        return _check_duplicate_or_conflict(conn, ev, raw, channel)

    # Log successful attempt
    repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "ACCEPTED", None, channel)
    queue_event(EVENT_ACCEPTED, {
        "event_id": ev.event_id,
        "source_id": ev.source_id,
        "type": "COUNT"
    })

    # Resolve any pre-existing pending VOIDs for this COUNT
    resolve_pending_voids(conn, ev.source_id, ev.event_id)

    return ItemResult(
        status="ACCEPTED",
        event_id=ev.event_id,
        source_id=ev.source_id
    )


def process_void(
    conn: psycopg.Connection,
    ev: ValidatedEvent,
    raw: Any,
    channel: str
) -> ItemResult:
    assert ev.target_event_id is not None
    # Concurrency: serialize with COUNT and other VOIDs targeting the same count event
    repo.lock_key(conn, ev.source_id, ev.target_event_id)

    # Check if this VOID event itself was already submitted
    existing = repo.get_event(conn, ev.source_id, ev.event_id)
    if existing:
        return _check_duplicate_or_conflict(conn, ev, raw, channel)

    # Rule: VOID cannot target itself
    if ev.target_event_id == ev.event_id:
        reason = "VOID cannot target itself"
        repo.insert_event_on_conflict(conn, ev, status="REJECTED", failure_reason=reason, auto_ack=True)
        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "REJECTED", reason, channel)
        return ItemResult(
            status="REJECTED",
            event_id=ev.event_id,
            source_id=ev.source_id,
            reason=reason
        )

    # Check target within the same source
    target = repo.get_event(conn, ev.source_id, ev.target_event_id)

    if target is not None:
        if target["type"] == "VOID":
            reason = "Cannot VOID a VOID event"
            repo.insert_event_on_conflict(conn, ev, status="REJECTED", failure_reason=reason, auto_ack=True)
            repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "REJECTED", reason, channel)
            return ItemResult(status="REJECTED", event_id=ev.event_id, source_id=ev.source_id, reason=reason)

        if target["status"] != "ACCEPTED":
            reason = f"Target event has status {target['status']}"
            repo.insert_event_on_conflict(conn, ev, status="REJECTED", failure_reason=reason, auto_ack=True)
            repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "REJECTED", reason, channel)
            return ItemResult(status="REJECTED", event_id=ev.event_id, source_id=ev.source_id, reason=reason)

        already_voided = repo.get_accepted_void_for_target(conn, ev.source_id, ev.target_event_id)
        if already_voided:
            reason = f"Target already voided by {already_voided['event_id']}"
            repo.insert_event_on_conflict(conn, ev, status="REJECTED", failure_reason=reason, auto_ack=True)
            repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "REJECTED", reason, channel)
            return ItemResult(status="REJECTED", event_id=ev.event_id, source_id=ev.source_id, reason=reason)

        # Target is an ACCEPTED COUNT and not voided -> ACCEPTED!
        row_id, inserted = repo.insert_event_on_conflict(conn, ev, status="ACCEPTED", auto_ack=True)
        if not inserted:
            return _check_duplicate_or_conflict(conn, ev, raw, channel)

        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "ACCEPTED", None, channel)
        queue_event(EVENT_ACCEPTED, {
            "event_id": ev.event_id,
            "source_id": ev.source_id,
            "type": "VOID"
        })
        return ItemResult(
            status="ACCEPTED",
            event_id=ev.event_id,
            source_id=ev.source_id
        )

    # Target does not exist in this source. Check across all sources.
    target_in_other_sources = repo.find_events_by_id_any_source(conn, ev.target_event_id)
    if target_in_other_sources:
        reason = "source mismatch"
        repo.insert_event_on_conflict(conn, ev, status="REJECTED", failure_reason=reason, auto_ack=True)
        repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "REJECTED", reason, channel)
        return ItemResult(
            status="REJECTED",
            event_id=ev.event_id,
            source_id=ev.source_id,
            reason=reason
        )

    # Target does not exist anywhere -> PENDING_REFERENCE
    row_id, inserted = repo.insert_event_on_conflict(conn, ev, status="PENDING_REFERENCE", auto_ack=False)
    if not inserted:
        return _check_duplicate_or_conflict(conn, ev, raw, channel)

    repo.insert_attempt(conn, raw, ev.source_id, ev.event_id, "PENDING_REFERENCE", None, channel)
    return ItemResult(
        status="PENDING_REFERENCE",
        event_id=ev.event_id,
        source_id=ev.source_id
    )


def process_event(
    conn: psycopg.Connection,
    raw: Any,
    channel: str = "REST"
) -> ItemResult:
    """Validate, record attempt, and dispatch to process_count or process_void."""
    validation = validate_event(raw)
    if isinstance(validation, EventValidationError):
        repo.insert_attempt(
            conn,
            raw,
            validation.source_id,
            validation.event_id,
            "REJECTED",
            validation.error,
            channel
        )
        return ItemResult(
            status="REJECTED",
            event_id=validation.event_id,
            source_id=validation.source_id,
            reason=validation.error
        )

    # Ensure source is recorded
    repo.ensure_source(conn, validation.source_id)

    if validation.type == "COUNT":
        return process_count(conn, validation, raw, channel)
    else:
        return process_void(conn, validation, raw, channel)


def process_events(
    conn: psycopg.Connection,
    raw_items: list[Any],
    channel: str = "REST"
) -> list[ItemResult]:
    """
    Processes a list of raw event items inside savepoints.
    Business failures never abort the transaction.
    """
    results: list[ItemResult] = []
    for item in raw_items:
        # Each item executes in its own savepoint
        with conn.transaction():
            res = process_event(conn, item, channel=channel)
            results.append(res)
    return results
