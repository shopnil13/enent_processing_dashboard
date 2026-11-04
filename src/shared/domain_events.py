import logging
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("domain_events")

# Domain event names
EVENT_ACCEPTED = "EVENT_ACCEPTED"
VOID_RESOLVED = "VOID_RESOLVED"
EVENT_ACKNOWLEDGED = "EVENT_ACKNOWLEDGED"

_subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)
_event_queue: list[tuple[str, dict[str, Any]]] = []


def subscribe(event_name: str, fn: Callable[[dict[str, Any]], None]) -> None:
    _subscribers[event_name].append(fn)


def queue_event(event_name: str, payload: dict[str, Any]) -> None:
    """Queue an event to be published only after transaction commit."""
    _event_queue.append((event_name, payload))


def flush_events() -> None:
    """Publish all queued events after transaction commit."""
    global _event_queue
    events = list(_event_queue)
    _event_queue.clear()
    for name, payload in events:
        for fn in _subscribers.get(name, []):
            try:
                fn(payload)
            except Exception as e:
                logger.error(f"Error handling domain event {name}: {e}", exc_info=True)


def clear_events() -> None:
    """Clear queued events if transaction rolls back."""
    _event_queue.clear()


@contextmanager
def transaction_events():
    """Context manager to queue events during transaction and flush upon commit."""
    try:
        yield
        flush_events()
    except Exception:
        clear_events()
        raise
