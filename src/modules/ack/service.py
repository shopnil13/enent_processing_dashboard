import logging
import psycopg
from src.shared.contracts import AckResult
from src.shared.domain_events import queue_event, EVENT_ACKNOWLEDGED
from src.modules.ack import repository as repo

logger = logging.getLogger("ack.service")


def acknowledge_events(conn: psycopg.Connection, event_ids: list[str]) -> list[AckResult]:
    """
    Acknowledges events in request order inside one transaction.
    - no rows -> NOT_FOUND
    - no ACCEPTED rows -> NOT_READY
    - an ACCEPTED row with acknowledged_at IS NULL -> set it -> ACKED
    - otherwise -> ALREADY_ACKED
    """
    results: list[AckResult] = []

    for eid in event_ids:
        rows = repo.get_events_for_ack(conn, eid)
        if not rows:
            results.append(AckResult(event_id=eid, status="NOT_FOUND"))
            continue

        accepted_rows = [r for r in rows if r["status"] == "ACCEPTED"]
        if not accepted_rows:
            results.append(AckResult(event_id=eid, status="NOT_READY"))
            continue

        unacknowledged = [r for r in accepted_rows if r["acknowledged_at"] is None]
        if unacknowledged:
            repo.set_events_acknowledged(conn, eid)
            queue_event(EVENT_ACKNOWLEDGED, {"event_id": eid})
            results.append(AckResult(event_id=eid, status="ACKED"))
        else:
            results.append(AckResult(event_id=eid, status="ALREADY_ACKED"))

    return results
