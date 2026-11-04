from datetime import datetime, timezone
from typing import Any
from src.shared.contracts import ValidatedEvent, EventValidationError

MAX_COUNT_QUANTITY = 500


def validate_event(raw: Any) -> ValidatedEvent | EventValidationError:
    if not isinstance(raw, dict):
        return EventValidationError(
            error="Item must be a JSON object",
            raw={"value": str(raw)} if not isinstance(raw, (dict, list)) else raw
        )

    source_id = raw.get("source_id")
    event_id = raw.get("event_id")

    # Extract strings if present for metadata in error
    s_id_str = str(source_id) if source_id is not None and isinstance(source_id, str) else None
    e_id_str = str(event_id) if event_id is not None and isinstance(event_id, str) else None

    if not source_id or not isinstance(source_id, str) or not source_id.strip():
        return EventValidationError(
            error="source_id is required and must be a non-empty string",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    if not event_id or not isinstance(event_id, str) or not event_id.strip():
        return EventValidationError(
            error="event_id is required and must be a non-empty string",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    event_type = raw.get("type")
    if event_type not in ("COUNT", "VOID"):
        return EventValidationError(
            error=f"type must be 'COUNT' or 'VOID', got {event_type!r}",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    event_time_raw = raw.get("event_time")
    if not event_time_raw:
        return EventValidationError(
            error="event_time is required",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    if isinstance(event_time_raw, str):
        try:
            # Handle ISO timestamp (e.g., 2026-11-04T10:00:00Z or +00:00)
            clean_time_str = event_time_raw.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(clean_time_str)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            else:
                parsed_dt = parsed_dt.astimezone(timezone.utc)
        except Exception as e:
            return EventValidationError(
                error=f"Invalid event_time ISO-8601 format: {e}",
                raw=raw,
                source_id=s_id_str,
                event_id=e_id_str
            )
    elif isinstance(event_time_raw, datetime):
        if event_time_raw.tzinfo is None:
            parsed_dt = event_time_raw.replace(tzinfo=timezone.utc)
        else:
            parsed_dt = event_time_raw.astimezone(timezone.utc)
    else:
        return EventValidationError(
            error="event_time must be a valid ISO-8601 timestamp string",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    quantity = raw.get("quantity")
    target_event_id = raw.get("target_event_id")

    if event_type == "COUNT":
        if quantity is None:
            return EventValidationError(
                error="quantity is required for COUNT event",
                raw=raw,
                source_id=s_id_str,
                event_id=e_id_str
            )
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            return EventValidationError(
                error=f"quantity must be a positive integer, got {quantity!r}",
                raw=raw,
                source_id=s_id_str,
                event_id=e_id_str
            )
        if quantity > MAX_COUNT_QUANTITY:
            return EventValidationError(
                error=f"quantity exceeds maximum of {MAX_COUNT_QUANTITY}",
                raw=raw,
                source_id=s_id_str,
                event_id=e_id_str
            )
        if target_event_id is not None:
            return EventValidationError(
                error="target_event_id must not be present for COUNT event",
                raw=raw,
                source_id=s_id_str,
                event_id=e_id_str
            )
        return ValidatedEvent(
            source_id=source_id.strip(),
            event_id=event_id.strip(),
            type="COUNT",
            quantity=quantity,
            target_event_id=None,
            event_time=parsed_dt
        )

    # event_type == "VOID"
    if quantity is not None:
        return EventValidationError(
            error="quantity must not be present for VOID event",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )
    if not target_event_id or not isinstance(target_event_id, str) or not target_event_id.strip():
        return EventValidationError(
            error="target_event_id is required and must be a non-empty string for VOID event",
            raw=raw,
            source_id=s_id_str,
            event_id=e_id_str
        )

    return ValidatedEvent(
        source_id=source_id.strip(),
        event_id=event_id.strip(),
        type="VOID",
        quantity=None,
        target_event_id=target_event_id.strip(),
        event_time=parsed_dt
    )
