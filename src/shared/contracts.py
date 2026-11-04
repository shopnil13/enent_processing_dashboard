from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class ValidatedEvent:
    source_id: str
    event_id: str
    type: Literal["COUNT", "VOID"]
    quantity: int | None
    target_event_id: str | None
    event_time: datetime


@dataclass(frozen=True)
class EventValidationError:
    error: str
    raw: dict
    source_id: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class ItemResult:
    status: Literal["ACCEPTED", "DUPLICATE", "CONFLICT", "PENDING_REFERENCE", "REJECTED"]
    event_id: str | None
    source_id: str | None
    reason: str | None = None


@dataclass(frozen=True)
class Summary:
    net_total: int
    processed_events: int
    pending_ack: int
    unresolved: int
    duplicates: int
    conflicts: int
    rejected_submissions: int = 0


@dataclass(frozen=True)
class AckResult:
    event_id: str
    status: Literal["ACKED", "ALREADY_ACKED", "NOT_READY", "NOT_FOUND"]
