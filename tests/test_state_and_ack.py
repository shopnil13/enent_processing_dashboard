from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_repeated_ack_and_statuses():
    """Test 4: Repeated ack, NOT_FOUND, NOT_READY, ALREADY_ACKED."""
    # 1. Create an ACCEPTED COUNT
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "evt_ack_1",
        "type": "COUNT",
        "quantity": 10,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # 2. Create a PENDING_REFERENCE VOID
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "void_pending",
        "type": "VOID",
        "target_event_id": "non_existent_target",
        "event_time": "2026-11-04T10:00:00Z"
    })

    # Test ACK with mixed conditions:
    res = client.post("/api/ack", json={
        "event_ids": ["evt_ack_1", "evt_ack_1", "void_pending", "totally_missing"]
    })
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 4
    assert results[0] == {"event_id": "evt_ack_1", "status": "ACKED"}
    assert results[1] == {"event_id": "evt_ack_1", "status": "ALREADY_ACKED"}
    assert results[2] == {"event_id": "void_pending", "status": "NOT_READY"}
    assert results[3] == {"event_id": "totally_missing", "status": "NOT_FOUND"}

    # Subsequent request for evt_ack_1 is now ALREADY_ACKED
    res2 = client.post("/api/ack", json={"event_ids": ["evt_ack_1"]})
    assert res2.json()["results"][0]["status"] == "ALREADY_ACKED"


def test_summary_metrics_and_source_filter():
    """Verify all 7 summary metrics accurately calculated on durable data."""
    # 1. Accepted COUNT (qty 20) on line_1
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c1",
        "type": "COUNT",
        "quantity": 20,
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 2. Accepted COUNT (qty 30) on line_1, then VOIDed by v1
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c2",
        "type": "COUNT",
        "quantity": 30,
        "event_time": "2026-11-04T10:01:00Z"
    })
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "v1",
        "type": "VOID",
        "target_event_id": "c2",
        "event_time": "2026-11-04T10:02:00Z"
    })

    # 3. Accepted COUNT (qty 50) on line_2
    client.post("/api/events", json={
        "source_id": "line_2",
        "event_id": "c3",
        "type": "COUNT",
        "quantity": 50,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # 4. A PENDING_REFERENCE VOID
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "v_pending",
        "type": "VOID",
        "target_event_id": "c_missing",
        "event_time": "2026-11-04T10:05:00Z"
    })

    # 5. Duplicate attempt on line_1
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c1",
        "type": "COUNT",
        "quantity": 20,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # 6. Conflict attempt on line_1 (different valid quantity <= 500)
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c1",
        "type": "COUNT",
        "quantity": 300,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # 7. Rejected submission (quantity > 500 ceiling)
    client.post("/api/events", json={
        "source_id": "line_1",
        "event_id": "c_exceed",
        "type": "COUNT",
        "quantity": 501,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # Acknowledge c1
    client.post("/api/ack", json={"event_ids": ["c1"]})

    # Global summary check:
    # net_total: c1(20) + c3(50) = 70 (c2 was voided by v1)
    # processed_events: c1, c2, v1, c3 = 4
    # pending_ack: c2, c3 = 2
    # unresolved: v_pending = 1
    # duplicates: 1
    # conflicts: 1
    # rejected_submissions: 1
    res_global = client.get("/api/state?view=summary")
    assert res_global.status_code == 200
    s_global = res_global.json()
    assert s_global["net_total"] == 70
    assert s_global["processed_events"] == 4
    assert s_global["pending_ack"] == 2
    assert s_global["unresolved"] == 1
    assert s_global["duplicates"] == 1
    assert s_global["conflicts"] == 1
    assert s_global["rejected_submissions"] == 1

    # Filtered summary for line_1:
    res_l1 = client.get("/api/state?view=summary&source_id=line_1")
    s_l1 = res_l1.json()
    assert s_l1["net_total"] == 20
    assert s_l1["processed_events"] == 3
    assert s_l1["pending_ack"] == 1
    assert s_l1["unresolved"] == 1
    assert s_l1["duplicates"] == 1
    assert s_l1["conflicts"] == 1
    assert s_l1["rejected_submissions"] == 1

    # Filtered summary for line_2 (no rejected submissions on line_2 -> 0):
    res_l2 = client.get("/api/state?view=summary&source_id=line_2")
    s_l2 = res_l2.json()
    assert s_l2["rejected_submissions"] == 0


def test_pending_and_exceptions_views():
    """Verify pending view returns unacked counts and exceptions view returns issues."""
    client.post("/api/events", json={
        "source_id": "line_test",
        "event_id": "count_pending",
        "type": "COUNT",
        "quantity": 10,
        "event_time": "2026-11-04T10:00:00Z"
    })
    client.post("/api/events", json={
        "source_id": "line_test",
        "event_id": "count_bad",
        "type": "COUNT",
        "quantity": -5,
        "event_time": "2026-11-04T10:00:00Z"
    })

    # Pending view
    res_pending = client.get("/api/state?view=pending&source_id=line_test")
    assert res_pending.status_code == 200
    events = res_pending.json()["events"]
    assert len(events) == 1
    assert events[0]["event_id"] == "count_pending"

    # Exceptions view
    res_exc = client.get("/api/state?view=exceptions&source_id=line_test")
    assert res_exc.status_code == 200
    exceptions = res_exc.json()["exceptions"]
    assert any("quantity must be a positive integer" in ex.get("reason", "") for ex in exceptions)

    # Invalid view
    res_bad = client.get("/api/state?view=invalid_view")
    assert res_bad.status_code == 400
