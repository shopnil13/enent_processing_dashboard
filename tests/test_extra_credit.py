import concurrent.futures
from fastapi.testclient import TestClient
from src.main import app
from src.shared.db import get_pool, close_pool, init_pool
from src.modules.state.service import get_summary

client = TestClient(app)


def test_concurrent_submissions_threads():
    """Verify concurrent submissions of the same event_id result in exactly 1 ACCEPTED and others DUPLICATE."""
    event_payload = {
        "source_id": "thread_src",
        "event_id": "c_threaded_01",
        "type": "COUNT",
        "quantity": 50,
        "event_time": "2026-11-04T10:00:00Z"
    }

    num_threads = 8

    def submit_event():
        return client.post("/api/events", json=event_payload).json()["results"][0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(submit_event) for _ in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    statuses = [r["status"] for r in results]
    accepted_count = statuses.count("ACCEPTED")
    duplicate_count = statuses.count("DUPLICATE")

    assert accepted_count == 1
    assert duplicate_count == num_threads - 1

    # Verify DB has exactly 1 row
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM production_events WHERE source_id = 'thread_src' AND event_id = 'c_threaded_01';")
            assert cur.fetchone()[0] == 1


def test_concurrent_count_and_void_race():
    """Advisory locking serializes COUNT and VOID race condition regardless of thread interleaving."""
    count_payload = {
        "source_id": "race_src",
        "event_id": "c_race",
        "type": "COUNT",
        "quantity": 100,
        "event_time": "2026-11-04T10:00:00Z"
    }
    void_payload = {
        "source_id": "race_src",
        "event_id": "v_race",
        "type": "VOID",
        "target_event_id": "c_race",
        "event_time": "2026-11-04T10:01:00Z"
    }

    def submit(payload):
        return client.post("/api/events", json=payload).json()["results"][0]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_count = executor.submit(submit, count_payload)
        f_void = executor.submit(submit, void_payload)
        r_count = f_count.result()
        r_void = f_void.result()

    # Both must succeed
    assert r_count["status"] == "ACCEPTED"
    assert r_void["status"] in ("ACCEPTED", "PENDING_REFERENCE")

    # Final DB check: Both must be ACCEPTED, net total must be 0
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, status 
                FROM production_events 
                WHERE source_id = 'race_src' AND event_id IN ('c_race', 'v_race');
            """)
            status_map = dict(cur.fetchall())
            assert status_map["c_race"] == "ACCEPTED"
            assert status_map["v_race"] == "ACCEPTED"

    summary = client.get("/api/state?view=summary&source_id=race_src").json()
    assert summary["net_total"] == 0
    assert summary["processed_events"] == 2


def test_multiple_pending_voids_resolution_order():
    """Lowest ID pending VOID becomes ACCEPTED; remaining pending VOIDs become REJECTED."""
    # Submit 3 pending VOIDs
    for i in (1, 2, 3):
        res = client.post("/api/events", json={
            "source_id": "fifo_src",
            "event_id": f"v_fifo_{i}",
            "type": "VOID",
            "target_event_id": "c_fifo",
            "event_time": f"2026-11-04T10:0{i}:00Z"
        })
        assert res.json()["results"][0]["status"] == "PENDING_REFERENCE"

    # Submit the target COUNT
    res_c = client.post("/api/events", json={
        "source_id": "fifo_src",
        "event_id": "c_fifo",
        "type": "COUNT",
        "quantity": 77,
        "event_time": "2026-11-04T10:10:00Z"
    })
    assert res_c.json()["results"][0]["status"] == "ACCEPTED"

    # Verify v_fifo_1 won, v_fifo_2 and v_fifo_3 were rejected
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, status, failure_reason 
                FROM production_events 
                WHERE source_id = 'fifo_src' AND event_id LIKE 'v_fifo_%'
                ORDER BY id ASC;
            """)
            rows = cur.fetchall()
            assert rows[0] == ("v_fifo_1", "ACCEPTED", None)
            assert rows[1] == ("v_fifo_2", "REJECTED", "target already voided by v_fifo_1")
            assert rows[2] == ("v_fifo_3", "REJECTED", "target already voided by v_fifo_1")


def test_restart_recovery():
    """Verify durable state is unaffected by pool teardown and restart."""
    import os
    test_db_url = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:Shopnil13@localhost:5432/fse01_test")

    client.post("/api/events", json={
        "source_id": "restart_src",
        "event_id": "c_durable",
        "type": "COUNT",
        "quantity": 120,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # Close and reopen connection pool against test database (simulating service restart)
    close_pool()
    init_pool(test_db_url)

    summary = get_summary(source_id="restart_src")
    assert summary.net_total == 120
    assert summary.processed_events == 1


def test_source_mismatch_void_rejected():
    """VOID targeting event belonging to another source is rejected with 'source mismatch'."""
    client.post("/api/events", json={
        "source_id": "alpha_source",
        "event_id": "count_alpha",
        "type": "COUNT",
        "quantity": 30,
        "event_time": "2026-11-04T10:00:00Z"
    })

    res = client.post("/api/events", json={
        "source_id": "beta_source",
        "event_id": "void_beta",
        "type": "VOID",
        "target_event_id": "count_alpha",
        "event_time": "2026-11-04T10:05:00Z"
    })
    assert res.json()["results"][0]["status"] == "REJECTED"
    assert "source mismatch" in res.json()["results"][0]["reason"]
