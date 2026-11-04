from typing import Optional, Any
import psycopg
from psycopg.rows import dict_row
from src.shared.contracts import Summary


def query_summary(conn: psycopg.Connection, source_id: Optional[str] = None) -> Summary:
    """Calculates all summary metrics directly from durable database tables."""
    sql = """
    WITH count_totals AS (
        SELECT COALESCE(SUM(pe.quantity), 0) AS net_total
        FROM production_events pe
        WHERE pe.type = 'COUNT'
          AND pe.status = 'ACCEPTED'
          AND NOT EXISTS (
              SELECT 1 FROM production_events pv
              WHERE pv.source_id = pe.source_id
                AND pv.target_event_id = pe.event_id
                AND pv.type = 'VOID'
                AND pv.status = 'ACCEPTED'
          )
          AND (%(source_id)s::text IS NULL OR pe.source_id = %(source_id)s)
    ),
    event_counts AS (
        SELECT
            COUNT(*) FILTER (WHERE status = 'ACCEPTED') AS processed_events,
            COUNT(*) FILTER (WHERE status = 'ACCEPTED' AND acknowledged_at IS NULL) AS pending_ack,
            COUNT(*) FILTER (WHERE status = 'PENDING_REFERENCE') AS unresolved
        FROM production_events
        WHERE (%(source_id)s::text IS NULL OR source_id = %(source_id)s)
    ),
    attempt_counts AS (
        SELECT
            COUNT(*) FILTER (WHERE classification = 'DUPLICATE') AS duplicates,
            COUNT(*) FILTER (WHERE classification = 'CONFLICT') AS conflicts,
            COUNT(*) FILTER (WHERE classification = 'REJECTED') AS rejected_submissions
        FROM submission_attempts
        WHERE (%(source_id)s::text IS NULL OR source_id = %(source_id)s)
    )
    SELECT 
        ct.net_total,
        ec.processed_events,
        ec.pending_ack,
        ec.unresolved,
        ac.duplicates,
        ac.conflicts,
        ac.rejected_submissions
    FROM count_totals ct
    CROSS JOIN event_counts ec
    CROSS JOIN attempt_counts ac;
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"source_id": source_id})
        row = cur.fetchone()
        assert row is not None
        return Summary(
            net_total=int(row["net_total"]),
            processed_events=int(row["processed_events"]),
            pending_ack=int(row["pending_ack"]),
            unresolved=int(row["unresolved"]),
            duplicates=int(row["duplicates"]),
            conflicts=int(row["conflicts"]),
            rejected_submissions=int(row["rejected_submissions"])
        )


def query_pending(conn: psycopg.Connection, source_id: Optional[str] = None) -> list[dict[str, Any]]:
    """Returns ACCEPTED COUNTs not yet acknowledged."""
    sql = """
        SELECT 
            id,
            source_id,
            event_id,
            type,
            quantity,
            target_event_id,
            event_time,
            received_at,
            status,
            acknowledged_at
        FROM production_events
        WHERE type = 'COUNT'
          AND status = 'ACCEPTED'
          AND acknowledged_at IS NULL
          AND (%(source_id)s::text IS NULL OR source_id = %(source_id)s)
        ORDER BY id ASC;
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, {"source_id": source_id})
        rows = cur.fetchall()
        for r in rows:
            if r.get("event_time"):
                r["event_time"] = r["event_time"].isoformat()
            if r.get("received_at"):
                r["received_at"] = r["received_at"].isoformat()
        return rows


def query_exceptions(conn: psycopg.Connection, source_id: Optional[str] = None) -> list[dict[str, Any]]:
    """
    Exceptions = PENDING_REFERENCE events, REJECTED events/attempts (with reason), and CONFLICT attempts.
    Attempts without a usable source_id appear only when unfiltered.
    """
    events_sql = """
        SELECT 
            id::text AS entry_id,
            source_id,
            event_id,
            type,
            status,
            failure_reason AS reason,
            received_at,
            'EVENT' AS source_kind
        FROM production_events
        WHERE (status = 'PENDING_REFERENCE' OR (status = 'REJECTED' AND failure_reason IS NOT NULL))
          AND (%(source_id)s::text IS NULL OR source_id = %(source_id)s)
    """

    attempts_sql = """
        SELECT 
            ('att_' || id)::text AS entry_id,
            source_id,
            event_id,
            channel AS type,
            classification AS status,
            error AS reason,
            received_at,
            'ATTEMPT' AS source_kind
        FROM submission_attempts
        WHERE classification IN ('REJECTED', 'CONFLICT')
          AND (
              (%(source_id)s::text IS NULL)
              OR (source_id = %(source_id)s)
          )
    """

    unified_sql = f"""
        {events_sql}
        UNION ALL
        {attempts_sql}
        ORDER BY received_at DESC;
    """

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(unified_sql, {"source_id": source_id})
        rows = cur.fetchall()
        for r in rows:
            if r.get("received_at"):
                r["received_at"] = r["received_at"].isoformat()
        return rows


def query_sources(conn: psycopg.Connection) -> list[str]:
    """Returns list of all known source IDs."""
    with conn.cursor() as cur:
        cur.execute("SELECT source_id FROM production_sources ORDER BY source_id ASC;")
        return [row[0] for row in cur.fetchall()]
