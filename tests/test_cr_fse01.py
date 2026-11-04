import json
from fastapi.testclient import TestClient
from src.main import app
from src.modules.mqtt.service import handle_mqtt_challenge

client = TestClient(app)
CANDIDATE_ID = "shopnil13"


def test_cr01_quantity_validation_ceiling():
    """
    CR-01: A single COUNT cannot exceed 500. Valid quantities are 1 to 500 inclusive.
    Examples: COUNT 450 -> ACCEPTED, COUNT 501 -> REJECTED.
    """
    # 1. Valid COUNT: 450 -> ACCEPTED
    res_450 = client.post("/api/events", json={
        "source_id": "line_cr1",
        "event_id": "c_450",
        "type": "COUNT",
        "quantity": 450,
        "event_time": "2026-11-04T10:00:00Z"
    })
    assert res_450.status_code == 200
    r_450 = res_450.json()["results"][0]
    assert r_450["status"] == "ACCEPTED"
    assert r_450["event_id"] == "c_450"

    # 2. Invalid COUNT: 501 -> REJECTED with clear reason
    res_501 = client.post("/api/events", json={
        "source_id": "line_cr1",
        "event_id": "c_501",
        "type": "COUNT",
        "quantity": 501,
        "event_time": "2026-11-04T10:00:00Z"
    })
    assert res_501.status_code == 200
    r_501 = res_501.json()["results"][0]
    assert r_501["status"] == "REJECTED"
    assert "quantity exceeds maximum of 500" in r_501.get("reason", "")

    # Verify total increased only by 450, not by 501
    summary = client.get("/api/state?view=summary&source_id=line_cr1").json()
    assert summary["net_total"] == 450
    assert summary["processed_events"] == 1
    assert summary["rejected_submissions"] == 1

    # Boundary tests: 1 and 500 are valid
    res_bound = client.post("/api/events", json=[
        {"source_id": "line_cr1", "event_id": "c_min", "type": "COUNT", "quantity": 1, "event_time": "2026-11-04T10:01:00Z"},
        {"source_id": "line_cr1", "event_id": "c_max", "type": "COUNT", "quantity": 500, "event_time": "2026-11-04T10:02:00Z"}
    ])
    for item in res_bound.json()["results"]:
        assert item["status"] == "ACCEPTED"


def test_cr01_mqtt_quantity_validation():
    """Verify max quantity ceiling applies equally to MQTT challenge ingestion."""
    challenge_payload = {
        "protocol_version": "1.0",
        "candidate_id": CANDIDATE_ID,
        "challenge_id": "chal_qty_test",
        "command": "PROCESS_EVENTS",
        "events": [
            {
                "source_id": "line_mqtt_cr",
                "event_id": "m_c_valid",
                "type": "COUNT",
                "quantity": 450,
                "event_time": "2026-11-04T10:00:00Z"
            },
            {
                "source_id": "line_mqtt_cr",
                "event_id": "m_c_exceed",
                "type": "COUNT",
                "quantity": 501,
                "event_time": "2026-11-04T10:01:00Z"
            }
        ]
    }
    resp = handle_mqtt_challenge(json.dumps(challenge_payload), candidate_id=CANDIDATE_ID)
    assert resp["status"] == "COMPLETED"
    results = resp["results"]
    assert results[0]["status"] == "ACCEPTED"
    assert results[1]["status"] == "REJECTED"
    assert "quantity exceeds maximum of 500" in results[1].get("reason", "")
    assert resp["state"]["net_total"] == 450
    assert resp["state"]["rejected_submissions"] == 1


def test_cr02_rejected_submissions_in_summary_and_source_filter():
    """
    CR-02: rejected_submissions counts stored submission attempts with status REJECTED only.
    DUPLICATE, CONFLICT and PENDING_REFERENCE are excluded.
    Optional source_id filter returns 0 when none.
    """
    # Clean initial state for source LINE_CR_A
    s_init = client.get("/api/state?view=summary&source_id=LINE_CR_A").json()
    assert s_init["rejected_submissions"] == 0

    # 1. Successful event
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "evt_a_1",
        "type": "COUNT",
        "quantity": 100,
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 2. Duplicate attempt (must NOT be counted in rejected_submissions)
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "evt_a_1",
        "type": "COUNT",
        "quantity": 100,
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 3. Conflict attempt (must NOT be counted in rejected_submissions)
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "evt_a_1",
        "type": "COUNT",
        "quantity": 200,
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 4. Pending reference VOID (must NOT be counted in rejected_submissions)
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "void_pending",
        "type": "VOID",
        "target_event_id": "missing_evt",
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 5. Rejected attempt: quantity > 500
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "evt_rej_1",
        "type": "COUNT",
        "quantity": 550,
        "event_time": "2026-11-04T10:00:00Z"
    })
    # 6. Rejected attempt: malformed type
    client.post("/api/events", json={
        "source_id": "LINE_CR_A",
        "event_id": "evt_rej_2",
        "type": "UNKNOWN_TYPE",
        "event_time": "2026-11-04T10:00:00Z"
    })

    # Summary for LINE_CR_A: exactly 2 rejected submissions
    s_a = client.get("/api/state?view=summary&source_id=LINE_CR_A").json()
    assert s_a["net_total"] == 100
    assert s_a["duplicates"] == 1
    assert s_a["conflicts"] == 1
    assert s_a["unresolved"] == 1
    assert s_a["rejected_submissions"] == 2

    # Summary for LINE_CR_B: returns 0 when there are none
    s_b = client.get("/api/state?view=summary&source_id=LINE_CR_B").json()
    assert s_b["rejected_submissions"] == 0
