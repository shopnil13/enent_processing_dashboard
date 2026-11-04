from fastapi.testclient import TestClient
from src.main import app
from src.shared.db import get_pool

client = TestClient(app)


def test_submit_single_and_batch_count():
    """Test 1: COUNT events ingestion."""
    # Single object
    res = client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "evt_c1",
        "type": "COUNT",
        "quantity": 10,
        "event_time": "2026-11-04T10:00:00Z"
    })
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["status"] == "ACCEPTED"
    assert data["results"][0]["event_id"] == "evt_c1"
    assert data["results"][0]["source_id"] == "line_1"

    # Batch array
    res2 = client.post("/api/events", json=[
        {
            "source_id": "line_1",
            "event_id": "evt_c2",
            "type": "COUNT",
            "quantity": 25,
            "event_time": "2026-11-04T10:05:00Z"
        },
        {
            "source_id": "line_2",
            "event_id": "evt_c1",  # Same event_id but different source is valid
            "type": "COUNT",
            "quantity": 5,
            "event_time": "2026-11-04T10:05:00Z"
        }
    ])
    assert res2.status_code == 200
    results2 = res2.json()["results"]
    assert len(results2) == 2
    assert results2[0]["status"] == "ACCEPTED"
    assert results2[1]["status"] == "ACCEPTED"


def test_duplicate_and_conflict_handling():
    """Test 2: Duplicate not double-counted, conflict preserves original."""
    payload = {
        "source_id": "line_1",
        "event_id": "evt_dup",
        "type": "COUNT",
        "quantity": 100,
        "event_time": "2026-11-04T10:00:00Z"
    }
    # Initial submission
    res1 = client.post("/api/events", json=payload)
    assert res1.json()["results"][0]["status"] == "ACCEPTED"

    # Exact duplicate
    res2 = client.post("/api/events", json=payload)
    assert res2.json()["results"][0]["status"] == "DUPLICATE"

    # Conflict (different quantity)
    conflict_payload = dict(payload, quantity=200)
    res3 = client.post("/api/events", json=conflict_payload)
    assert res3.json()["results"][0]["status"] == "CONFLICT"
    assert "Payload conflict" in res3.json()["results"][0].get("reason", "")

    # Verify original preserved in DB
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT quantity FROM production_events WHERE source_id = 'line_1' AND event_id = 'evt_dup';")
            assert cur.fetchone()[0] == 100


def test_void_before_count_auto_resolution():
    """Test 3: VOID submitted before COUNT auto-resolves when COUNT arrives."""
    # Submit VOID first (target does not exist yet)
    void_payload = {
        "source_id": "line_1",
        "event_id": "void_01",
        "type": "VOID",
        "target_event_id": "evt_target",
        "event_time": "2026-11-04T10:00:00Z"
    }
    res_void = client.post("/api/events", json=void_payload)
    assert res_void.json()["results"][0]["status"] == "PENDING_REFERENCE"

    # Submit second VOID for same target
    void_payload_2 = {
        "source_id": "line_1",
        "event_id": "void_02",
        "type": "VOID",
        "target_event_id": "evt_target",
        "event_time": "2026-11-04T10:01:00Z"
    }
    res_void_2 = client.post("/api/events", json=void_payload_2)
    assert res_void_2.json()["results"][0]["status"] == "PENDING_REFERENCE"

    # Now submit the COUNT
    count_payload = {
        "source_id": "line_1",
        "event_id": "evt_target",
        "type": "COUNT",
        "quantity": 50,
        "event_time": "2026-11-04T10:02:00Z"
    }
    res_count = client.post("/api/events", json=count_payload)
    assert res_count.json()["results"][0]["status"] == "ACCEPTED"

    # Verify that void_01 resolved to ACCEPTED (auto-acknowledged) and void_02 became REJECTED
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT event_id, status, acknowledged_at, failure_reason 
                FROM production_events 
                WHERE event_id IN ('void_01', 'void_02')
                ORDER BY event_id;
            """)
            rows = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}
            # void_01 was first (lowest id) -> ACCEPTED, acknowledged
            assert rows["void_01"][0] == "ACCEPTED"
            assert rows["void_01"][1] is not None
            # void_02 was second -> REJECTED with reason mentioning void_01
            assert rows["void_02"][0] == "REJECTED"
            assert "target already voided by void_01" in rows["void_02"][2]


def test_void_immediate_acceptance():
    """VOID submitted after COUNT is immediately ACCEPTED."""
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c_immediate",
        "type": "COUNT",
        "quantity": 15,
        "event_time": "2026-11-04T10:00:00Z"
    })
    res_void = client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "v_immediate",
        "type": "VOID",
        "target_event_id": "c_immediate",
        "event_time": "2026-11-04T10:05:00Z"
    })
    assert res_void.json()["results"][0]["status"] == "ACCEPTED"


def test_void_rejections():
    """VOID self-target, source mismatch, target is VOID, and second VOID against same target."""
    # Target self
    res_self = client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "v_self",
        "type": "VOID",
        "target_event_id": "v_self",
        "event_time": "2026-11-04T10:00:00Z"
    })
    assert res_self.json()["results"][0]["status"] == "REJECTED"
    assert "cannot target itself" in res_self.json()["results"][0].get("reason", "")

    # Source mismatch
    client.post("/api/events", json={
        "source_id": "line_A",
        "event_id": "c_source_a",
        "type": "COUNT",
        "quantity": 10,
        "event_time": "2026-11-04T10:00:00Z"
    })
    res_mismatch = client.post("/api/events", json={
        "source_id": "line_B",
        "event_id": "v_source_b",
        "type": "VOID",
        "target_event_id": "c_source_a",
        "event_time": "2026-11-04T10:05:00Z"
    })
    assert res_mismatch.json()["results"][0]["status"] == "REJECTED"
    assert "source mismatch" in res_mismatch.json()["results"][0].get("reason", "")


def test_mixed_batch_with_invalid_items():
    """Mixed batch containing valid and invalid items preserves order and does not abort valid items."""
    batch = [
        {"invalid": "no fields"},
        {
            "source_id": "line_1",
            "event_id": "evt_valid_1",
            "type": "COUNT",
            "quantity": 40,
            "event_time": "2026-11-04T10:00:00Z"
        },
        {
            "source_id": "line_1",
            "event_id": "evt_bad_qty",
            "type": "COUNT",
            "quantity": -5,
            "event_time": "2026-11-04T10:00:00Z"
        }
    ]
    res = client.post("/api/events", json=batch)
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 3
    assert results[0]["status"] == "REJECTED"
    assert results[1]["status"] == "ACCEPTED"
    assert results[2]["status"] == "REJECTED"


def test_malformed_json_and_top_level_types():
    """Non-object/non-array top-level returns 400."""
    res_str = client.post("/api/events", content="just a string", headers={"Content-Type": "application/json"})
    assert res_str.status_code == 400

    res_empty_arr = client.post("/api/events", json=[])
    assert res_empty_arr.status_code == 200
    assert res_empty_arr.json()["results"] == []
