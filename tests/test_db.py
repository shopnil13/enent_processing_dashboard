import pytest
from src.shared.db import get_pool, transaction
from src.shared.domain_events import subscribe, queue_event, transaction_events


def test_db_connection_and_tables(db_conn):
    """Verify tables exist in the test database."""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        tables = {row[0] for row in cur.fetchall()}
        assert "production_sources" in tables
        assert "production_events" in tables
        assert "submission_attempts" in tables
        assert "mqtt_challenges" in tables
        assert "schema_migrations" in tables


def test_transaction_commit_and_rollback(db_conn):
    """Verify transaction commits on success and rolls back on exception."""
    # Test commit
    with transaction(db_conn):
        with db_conn.cursor() as cur:
            cur.execute("INSERT INTO production_sources (source_id, display_name) VALUES ('src_1', 'Source 1');")

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM production_sources WHERE source_id = 'src_1';")
        assert cur.fetchone()[0] == 1

    # Test rollback
    with pytest.raises(RuntimeError):
        with transaction(db_conn):
            with db_conn.cursor() as cur:
                cur.execute("INSERT INTO production_sources (source_id, display_name) VALUES ('src_2', 'Source 2');")
            raise RuntimeError("Forced rollback")

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM production_sources WHERE source_id = 'src_2';")
        assert cur.fetchone()[0] == 0


def test_domain_events_queue_and_flush():
    """Verify domain events are only dispatched upon successful transaction commit."""
    published = []

    def on_event(payload):
        published.append(payload)

    subscribe("TEST_EVENT", on_event)

    # Success case
    with transaction_events():
        queue_event("TEST_EVENT", {"status": "ok"})
        assert len(published) == 0  # not yet dispatched

    assert len(published) == 1
    assert published[0] == {"status": "ok"}

    # Rollback case
    with pytest.raises(RuntimeError):
        with transaction_events():
            queue_event("TEST_EVENT", {"status": "failed"})
            raise RuntimeError("Rollback")

    assert len(published) == 1  # unchanged
