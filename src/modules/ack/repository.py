from typing import Any
import psycopg
from psycopg.rows import dict_row


def get_events_for_ack(conn: psycopg.Connection, event_id: str) -> list[dict[str, Any]]:
    """Retrieve all rows matching an event_id across sources."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT id, source_id, event_id, status, acknowledged_at
            FROM production_events
            WHERE event_id = %s;
        """, (event_id,))
        return cur.fetchall()


def set_events_acknowledged(conn: psycopg.Connection, event_id: str) -> int:
    """Set acknowledged_at timestamp for accepted rows of this event_id."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE production_events
            SET acknowledged_at = now()
            WHERE event_id = %s AND status = 'ACCEPTED' AND acknowledged_at IS NULL;
        """, (event_id,))
        return cur.rowcount
