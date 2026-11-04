import os
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from src.shared.db import transaction, init_pool, close_pool
from src.modules.events.service import process_events
from src.modules.ack.service import acknowledge_events
from src.modules.state.service import get_summary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed")

load_dotenv()


def seed_demo_events():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL is not set.")

    logger.info(f"Connecting to dev database...")
    init_pool(db_url)

    now = datetime.now(timezone.utc)

    demo_events = [
        # Assembly Line 1
        {
            "source_id": "assembly-line-1",
            "event_id": "c_asm1_001",
            "type": "COUNT",
            "quantity": 40,
            "event_time": (now - timedelta(minutes=45)).isoformat(),
        },
        {
            "source_id": "assembly-line-1",
            "event_id": "c_asm1_002",
            "type": "COUNT",
            "quantity": 60,
            "event_time": (now - timedelta(minutes=30)).isoformat(),
        },
        {
            "source_id": "assembly-line-1",
            "event_id": "c_asm1_003",
            "type": "COUNT",
            "quantity": 25,
            "event_time": (now - timedelta(minutes=20)).isoformat(),
        },
        {
            "source_id": "assembly-line-1",
            "event_id": "v_asm1_001",
            "type": "VOID",
            "target_event_id": "c_asm1_003",
            "event_time": (now - timedelta(minutes=15)).isoformat(),
        },
        # Assembly Line 2
        {
            "source_id": "assembly-line-2",
            "event_id": "c_asm2_001",
            "type": "COUNT",
            "quantity": 100,
            "event_time": (now - timedelta(minutes=50)).isoformat(),
        },
        {
            "source_id": "assembly-line-2",
            "event_id": "c_asm2_002",
            "type": "COUNT",
            "quantity": 80,
            "event_time": (now - timedelta(minutes=25)).isoformat(),
        },
        {
            "source_id": "assembly-line-2",
            "event_id": "v_asm2_pending",
            "type": "VOID",
            "target_event_id": "c_asm2_future_target",
            "event_time": (now - timedelta(minutes=10)).isoformat(),
        },
        # Packaging Line 1
        {
            "source_id": "packaging-line-1",
            "event_id": "c_pkg_001",
            "type": "COUNT",
            "quantity": 150,
            "event_time": (now - timedelta(minutes=5)).isoformat(),
        },
        # Duplicate submission attempt
        {
            "source_id": "assembly-line-1",
            "event_id": "c_asm1_001",
            "type": "COUNT",
            "quantity": 40,
            "event_time": (now - timedelta(minutes=45)).isoformat(),
        },
        # Conflict submission attempt (different quantity)
        {
            "source_id": "assembly-line-2",
            "event_id": "c_asm2_001",
            "type": "COUNT",
            "quantity": 999,
            "event_time": (now - timedelta(minutes=50)).isoformat(),
        },
        # Invalid item to demonstrate rejected exception logging
        {
            "source_id": "assembly-line-1",
            "invalid_field": "corrupted payload",
        },
    ]

    logger.info(f"Ingesting {len(demo_events)} demo events...")
    with transaction() as conn:
        results = process_events(conn, demo_events, channel="REST")
        for r in results:
            logger.info(f" -> {r.status} (event_id={r.event_id}, source={r.source_id})")

    # Acknowledge some of the completed counts to show a mixed pending / acknowledged state
    ack_ids = ["c_asm1_001", "c_asm2_002"]
    logger.info(f"Acknowledging events: {ack_ids}...")
    with transaction() as conn:
        ack_results = acknowledge_events(conn, ack_ids)
        for ar in ack_results:
            logger.info(f" -> ACK result: {ar.event_id}: {ar.status}")

    # Print summary
    summary = get_summary()
    logger.info("=== Demo Seed Complete ===")
    logger.info(f"Net Total:         {summary.net_total}")
    logger.info(f"Processed Events:  {summary.processed_events}")
    logger.info(f"Pending Ack:       {summary.pending_ack}")
    logger.info(f"Unresolved Voids:  {summary.unresolved}")
    logger.info(f"Duplicates:        {summary.duplicates}")
    logger.info(f"Conflicts:         {summary.conflicts}")

    close_pool()


if __name__ == "__main__":
    seed_demo_events()

