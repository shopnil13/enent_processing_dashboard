import json
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from src.main import app
from src.shared.db import get_pool
from src.modules.mqtt.service import handle_mqtt_challenge
from src.modules.mqtt.protocol import compute_canonical_digest

client = TestClient(app)
CANDIDATE_ID = "shopnil13"


def test_mqtt_challenge_success_and_idempotency():
    """Test 5: Valid challenge processes events, second call returns stored response without re-processing."""
    challenge_payload = {
        "protocol_version": "1.0",
        "candidate_id": CANDIDATE_ID,
        "challenge_id": "chal_001",
        "command": "PROCESS_EVENTS",
        "events": [
            {
                "source_id": "line_mqtt",
                "event_id": "m_c1",
                "type": "COUNT",
                "quantity": 100,
                "event_time": "2026-11-04T10:00:00Z"
            }
        ],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    }

    # 1. First execution
    resp1 = handle_mqtt_challenge(json.dumps(challenge_payload), candidate_id=CANDIDATE_ID)
    assert resp1["status"] == "COMPLETED"
    assert resp1["challenge_id"] == "chal_001"
    assert len(resp1["results"]) == 1
    assert resp1["results"][0]["status"] == "ACCEPTED"
    assert resp1["state"]["net_total"] == 100

    # 2. Repeated execution with identical payload (idempotency)
    resp2 = handle_mqtt_challenge(json.dumps(challenge_payload), candidate_id=CANDIDATE_ID)
    assert resp2["status"] == "COMPLETED"
    assert resp2["challenge_id"] == "chal_001"
    assert resp2["results"][0]["status"] == "ACCEPTED"
    assert resp2["state"]["net_total"] == 100

    # Verify that the event was NOT double-counted in the database
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM production_events WHERE event_id = 'm_c1';")
            assert cur.fetchone()[0] == 1


def test_mqtt_challenge_conflict():
    """Challenge with same ID but different payload digest returns CHALLENGE_CONFLICT."""
    initial_payload = {
        "protocol_version": "1.0",
        "candidate_id": CANDIDATE_ID,
        "challenge_id": "chal_conflict_test",
        "command": "PROCESS_EVENTS",
        "events": [
            {
                "source_id": "line_mqtt",
                "event_id": "m_c2",
                "type": "COUNT",
                "quantity": 50,
                "event_time": "2026-11-04T10:00:00Z"
            }
        ]
    }
    resp1 = handle_mqtt_challenge(json.dumps(initial_payload), candidate_id=CANDIDATE_ID)
    assert resp1["status"] == "COMPLETED"

    # Conflicting payload under same challenge_id
    conflict_payload = dict(initial_payload, events=[
        {
            "source_id": "line_mqtt",
            "event_id": "m_c2_diff",
            "type": "COUNT",
            "quantity": 999,
            "event_time": "2026-11-04T10:00:00Z"
        }
    ])
    resp2 = handle_mqtt_challenge(json.dumps(conflict_payload), candidate_id=CANDIDATE_ID)
    assert resp2["status"] == "FAILED"
    assert resp2["error"] == "CHALLENGE_CONFLICT"


def test_mqtt_protocol_errors():
    """Test protocol validation errors: version, candidate mismatch, expired, bad JSON."""
    # 1. Bad JSON
    r_bad_json = handle_mqtt_challenge("not valid json", candidate_id=CANDIDATE_ID)
    assert r_bad_json["status"] == "FAILED"
    assert r_bad_json["error"] == "VALIDATION_ERROR"

    # 2. Unsupported protocol version
    r_version = handle_mqtt_challenge(json.dumps({
        "protocol_version": "2.0",
        "candidate_id": CANDIDATE_ID,
        "challenge_id": "c_v",
        "command": "PROCESS_EVENTS",
        "events": []
    }), candidate_id=CANDIDATE_ID)
    assert r_version["status"] == "FAILED"
    assert r_version["error"] == "UNSUPPORTED_PROTOCOL"

    # 3. Candidate mismatch
    r_mismatch = handle_mqtt_challenge(json.dumps({
        "protocol_version": "1.0",
        "candidate_id": "someone_else",
        "challenge_id": "c_m",
        "command": "PROCESS_EVENTS",
        "events": []
    }), candidate_id=CANDIDATE_ID)
    assert r_mismatch["status"] == "FAILED"
    assert r_mismatch["error"] == "CANDIDATE_MISMATCH"

    # 4. Expired challenge
    expired_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    r_expired = handle_mqtt_challenge(json.dumps({
        "protocol_version": "1.0",
        "candidate_id": CANDIDATE_ID,
        "challenge_id": "c_exp",
        "command": "PROCESS_EVENTS",
        "events": [],
        "expires_at": expired_time
    }), candidate_id=CANDIDATE_ID)
    assert r_expired["status"] == "FAILED"
    assert r_expired["error"] == "CHALLENGE_EXPIRED"


def test_mqtt_status_endpoint():
    """Verify GET /api/mqtt/status returns valid status and challenge counts."""
    res = client.get("/api/mqtt/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert "candidate_id" in data
    assert "completed_challenges" in data
    assert "failed_challenges" in data
    assert data["completed_challenges"] >= 0
