import os
import json
import random
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from src.shared.db import transaction, init_pool, close_pool
from src.modules.events.service import process_events
from src.modules.ack.service import acknowledge_events
from src.modules.mqtt.service import handle_mqtt_challenge, tracker
from src.modules.state.service import get_summary

load_dotenv()


def populate_rich_demo():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set.")

    print("Connecting to database...")
    init_pool(db_url)

    now = datetime.now(timezone.utc)

    # 1. Simulate production lines across factory floor
    lines = [
        "stamping-press-A",
        "welding-robotics-01",
        "paint-shop-line",
        "final-assembly-line",
        "quality-inspection-gate",
    ]

    events_batch = []
    
    # Generate realistic historical counts over past 6 hours
    for i, line in enumerate(lines):
        for seq in range(1, 6):
            event_id = f"evt_{line[:4]}_{seq:03d}"
            qty = random.choice([25, 50, 75, 100, 120, 150, 200])
            mins_ago = (len(lines) - i) * 60 - seq * 10
            evt_time = now - timedelta(minutes=max(mins_ago, 5))
            
            events_batch.append({
                "source_id": line,
                "event_id": event_id,
                "type": "COUNT",
                "quantity": qty,
                "event_time": evt_time.isoformat()
            })

    # Add specific VOIDs that target known earlier counts
    events_batch.append({
        "source_id": "stamping-press-A",
        "event_id": "void_stamp_002",
        "type": "VOID",
        "target_event_id": "evt_stam_002",
        "event_time": (now - timedelta(minutes=15)).isoformat()
    })
    events_batch.append({
        "source_id": "paint-shop-line",
        "event_id": "void_paint_004",
        "type": "VOID",
        "target_event_id": "evt_pain_004",
        "event_time": (now - timedelta(minutes=8)).isoformat()
    })

    # Add pending VOIDs waiting for future counts
    events_batch.append({
        "source_id": "final-assembly-line",
        "event_id": "void_asm_future_01",
        "type": "VOID",
        "target_event_id": "evt_asm_upcoming_101",
        "event_time": (now - timedelta(minutes=4)).isoformat()
    })
    events_batch.append({
        "source_id": "welding-robotics-01",
        "event_id": "void_weld_future_02",
        "type": "VOID",
        "target_event_id": "evt_weld_upcoming_202",
        "event_time": (now - timedelta(minutes=2)).isoformat()
    })

    # Add some duplicate attempts
    events_batch.append({
        "source_id": "stamping-press-A",
        "event_id": "evt_stam_001",
        "type": "COUNT",
        "quantity": events_batch[0]["quantity"],
        "event_time": events_batch[0]["event_time"]
    })

    # Add conflict attempt
    events_batch.append({
        "source_id": "final-assembly-line",
        "event_id": "evt_fina_001",
        "type": "COUNT",
        "quantity": 9999,
        "event_time": now.isoformat()
    })

    # Ingest event batch
    print(f"Ingesting {len(events_batch)} events across factory lines...")
    with transaction() as conn:
        res = process_events(conn, events_batch, channel="REST")
        print(f"Ingested {len(res)} results.")

    # Acknowledge half of the counts so there is a healthy balance of acknowledged & pending
    to_ack = [
        "evt_stam_001",
        "evt_stam_003",
        "evt_weld_001",
        "evt_weld_002",
        "evt_pain_001",
        "evt_fina_002",
        "evt_qual_001",
        "evt_qual_002",
        "evt_qual_003",
    ]
    print(f"Acknowledging {len(to_ack)} completed items...")
    with transaction() as conn:
        acknowledge_events(conn, to_ack)

    # 2. Ingest 4 MQTT Challenges to populate the MQTT Panel
    candidate_id = os.getenv("CANDIDATE_ID", "shopnil13")
    print(f"Simulating MQTT challenges for candidate: {candidate_id}...")

    for c_idx in range(1, 5):
        chal_payload = {
            "protocol_version": "1.0",
            "candidate_id": candidate_id,
            "challenge_id": f"chal_prod_{c_idx:03d}",
            "command": "PROCESS_EVENTS",
            "events": [
                {
                    "source_id": "mqtt-gateway-edge",
                    "event_id": f"m_evt_{c_idx}_1",
                    "type": "COUNT",
                    "quantity": c_idx * 35,
                    "event_time": (now - timedelta(minutes=20 - c_idx * 4)).isoformat()
                }
            ],
            "expires_at": (now + timedelta(hours=1)).isoformat()
        }
        resp = handle_mqtt_challenge(json.dumps(chal_payload), candidate_id=candidate_id)
        print(f"MQTT Challenge {chal_payload['challenge_id']} -> {resp.get('status')}")

    # Set tracker status
    tracker.connected = True
    tracker.candidate_id = candidate_id
    tracker.broker = f"{os.getenv('MQTT_BROKER_HOST', '152.42.238.142')}:{os.getenv('MQTT_BROKER_PORT', '1883')}"
    tracker.last_challenge_id = "chal_prod_004"
    tracker.last_challenge_time = now.isoformat()
    tracker.last_response_status = "COMPLETED"
    tracker.last_error = None

    summary = get_summary()
    print("\n=== Rich Demo Population Complete ===")
    print(f"Net Total:         {summary.net_total}")
    print(f"Processed Events:  {summary.processed_events}")
    print(f"Pending Ack:       {summary.pending_ack}")
    print(f"Unresolved Voids:  {summary.unresolved}")
    print(f"Duplicates:        {summary.duplicates}")
    print(f"Conflicts:         {summary.conflicts}")

    close_pool()


if __name__ == "__main__":
    populate_rich_demo()

