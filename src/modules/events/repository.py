import json
from typing import Any, Optional
import psycopg
from psycopg.rows import dict_row
from src.shared.contracts import ValidatedEvent


def lock_key(conn: psycopg.Connection, source_id: str, count_event_id: str) -> None:
    """Acquire transaction-scoped advisory lock for concurrency control between COUNT and VOID."""
    lock_str = f"{source_id}:{count_event_id}"
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", (lock_str,))


def ensure_source(conn: psycopg.Connection, source_id: str, display_name: Optional[str] = None) -> None:
    """Insert unknown source_id into production_sources on the first valid event."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO production_sources (source_id, display_name)
            VALUES (%s, %s)
            ON CONFLICT (source_id) DO NOTHING;
        """, (source_id, display_name or source_id))


def insert_attempt(
    conn: psycopg.Connection,
    raw_payload: Any,
    source_id: Optional[str],
    event_id: Optional[str],
    classification: str,
    error: Optional[str],
    channel: str
) -> int:
    """Record an audit entry into submission_attempts."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO submission_attempts (raw_payload, source_id, event_id, classification, error, channel)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            json.dumps(raw_payload),
            source_id,
            event_id,
            classification,
            error,
            channel
        ))
        return cur.fetchone()[0]


def insert_event_on_conflict(
    conn: psycopg.Connection,
    ev: ValidatedEvent,
    status: str,
    failure_reason: Optional[str] = None,
    auto_ack: bool = False
) -> tuple[Optional[int], bool]:
    """
    Attempt to insert the event. If (source_id, event_id) exists, does nothing.
    Returns (event_id_pk, inserted).
    """
    with conn.cursor() as cur:
        ack_sql = "now()" if auto_ack else "NULL"
        cur.execute(f"""
            INSERT INTO production_events (
                source_id, event_id, type, quantity, target_event_id,
                event_time, status, failure_reason, acknowledged_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {ack_sql})
            ON CONFLICT (source_id, event_id) DO NOTHING
            RETURNING id;
        """, (
            ev.source_id,
            ev.event_id,
            ev.type,
            ev.quantity,
            ev.target_event_id,
            ev.event_time,
            status,
            failure_reason
        ))
        row = cur.fetchone()
        if row:
            return row[0], True
        return None, False


def get_event(conn: psycopg.Connection, source_id: str, event_id: str) -> Optional[dict]:
    """Fetch existing event by primary source_id + event_id key."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, source_id, event_id, type, quantity, target_event_id,
                   event_time, received_at, status, failure_reason, acknowledged_at
            FROM production_events
            WHERE source_id = %s AND event_id = %s;
        """, (source_id, event_id))
        return cur.fetchone()


def find_events_by_id_any_source(conn: psycopg.Connection, event_id: str) -> list[dict]:
    """Check across all sources for the given event_id."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, source_id, event_id, type, quantity, target_event_id,
                   event_time, received_at, status, failure_reason, acknowledged_at
            FROM production_events
            WHERE event_id = %s;
        """, (event_id,))
        return cur.fetchall()


def get_accepted_void_for_target(conn: psycopg.Connection, source_id: str, target_event_id: str) -> Optional[dict]:
    """Find if an accepted VOID already targets this event within the source."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, source_id, event_id, type, quantity, target_event_id, status
            FROM production_events
            WHERE source_id = %s AND target_event_id = %s AND type = 'VOID' AND status = 'ACCEPTED'
            LIMIT 1;
        """, (source_id, target_event_id))
        return cur.fetchone()


def list_pending_voids(conn: psycopg.Connection, source_id: str, target_event_id: str) -> list[dict]:
    """Fetch pending VOIDs in FIFO (id ASC) order for a resolved COUNT event."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, source_id, event_id, type, target_event_id, status
            FROM production_events
            WHERE source_id = %s AND target_event_id = %s AND type = 'VOID' AND status = 'PENDING_REFERENCE'
            ORDER BY id ASC;
        """, (source_id, target_event_id))
        return cur.fetchall()


def mark_void_accepted(conn: psycopg.Connection, void_row_id: int) -> Optional[str]:
    """Transition a pending VOID to ACCEPTED with auto-acknowledgment."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE production_events
            SET status = 'ACCEPTED', acknowledged_at = now()
            WHERE id = %s
            RETURNING event_id;
        """, (void_row_id,))
        row = cur.fetchone()
        return row[0] if row else None


def mark_void_rejected(conn: psycopg.Connection, void_row_id: int, reason: str) -> None:
    """Transition losing pending VOIDs to REJECTED."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE production_events
            SET status = 'REJECTED', failure_reason = %s, acknowledged_at = now()
            WHERE id = %s;
        """, (reason, void_row_id))
