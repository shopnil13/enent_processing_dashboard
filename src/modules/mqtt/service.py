import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Optional
import psycopg
from psycopg.rows import dict_row
from src.shared.db import get_connection, transaction
from src.modules.events.service import process_events
from src.modules.state.service import get_summary
from src.modules.mqtt.protocol import (
    compute_canonical_digest,
    parse_envelope,
    validate_challenge_envelope,
    build_success_response,
    build_failure_response
)

logger = logging.getLogger("mqtt.service")


class MqttRuntimeState:
    def __init__(self):
        self.connected: bool = False
        self.candidate_id: str = ""
        self.broker: str = ""
        self.last_challenge_id: Optional[str] = None
        self.last_challenge_time: Optional[str] = None
        self.last_response_status: Optional[str] = None
        self.last_error: Optional[str] = None

    def update_challenge(self, challenge_id: Optional[str], status: str, error: Optional[str] = None):
        self.last_challenge_id = challenge_id
        self.last_challenge_time = datetime.now(timezone.utc).isoformat()
        self.last_response_status = status
        self.last_error = error


tracker = MqttRuntimeState()


def get_stored_challenge(conn: psycopg.Connection, challenge_id: str) -> Optional[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT challenge_id, request_digest, request_body, response, status, received_at, responded_at
            FROM mqtt_challenges
            WHERE challenge_id = %s;
        """, (challenge_id,))
        return cur.fetchone()


def insert_challenge_record(
    conn: psycopg.Connection,
    challenge_id: str,
    request_digest: str,
    request_body: dict[str, Any],
    response: dict[str, Any],
    status: str
) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO mqtt_challenges (
                challenge_id, request_digest, request_body, response, status, received_at, responded_at
            )
            VALUES (%s, %s, %s, %s, %s, now(), now());
        """, (
            challenge_id,
            request_digest,
            json.dumps(request_body),
            json.dumps(response),
            status
        ))


def get_challenge_counts(conn: Optional[psycopg.Connection] = None) -> tuple[int, int]:
    """Returns (completed_count, failed_count) from durable storage."""
    with get_connection(conn) as c:
        with c.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed,
                    COUNT(*) FILTER (WHERE status = 'FAILED') AS failed
                FROM mqtt_challenges;
            """)
            row = cur.fetchone()
            if row:
                return int(row[0]), int(row[1])
            return 0, 0


def handle_mqtt_challenge(
    raw_payload: bytes | str,
    candidate_id: str,
    conn: Optional[psycopg.Connection] = None
) -> dict[str, Any]:
    """
    Core challenge evaluation pipeline.
    Maintains idempotency, transaction isolation, and durable challenge history.
    """
    req, parse_err = parse_envelope(raw_payload)
    if parse_err:
        resp = build_failure_response(None, parse_err)
        tracker.update_challenge(None, "FAILED", parse_err)
        return resp

    challenge_id = req.get("challenge_id")

    # Envelope verification
    validation_err = validate_challenge_envelope(req, expected_candidate_id=candidate_id)
    if validation_err:
        resp = build_failure_response(req, validation_err)
        tracker.update_challenge(challenge_id, "FAILED", validation_err)
        return resp

    request_digest = compute_canonical_digest(req)

    # Check for existing challenge
    with get_connection(conn) as c:
        stored = get_stored_challenge(c, challenge_id)
        if stored:
            if stored["request_digest"] == request_digest:
                logger.info(f"Challenge {challenge_id} already processed. Returning stored response.")
                stored_resp = stored["response"]
                tracker.update_challenge(challenge_id, stored.get("status", "COMPLETED"), None)
                return stored_resp if isinstance(stored_resp, dict) else json.loads(stored_resp)
            else:
                logger.warning(f"Challenge {challenge_id} conflict with different digest.")
                resp = build_failure_response(req, "CHALLENGE_CONFLICT")
                tracker.update_challenge(challenge_id, "FAILED", "CHALLENGE_CONFLICT")
                return resp

    # Process events and summary inside ONE transaction
    try:
        with transaction(conn) as tx_conn:
            events_list = req.get("events", [])
            item_results = process_events(tx_conn, events_list, channel="MQTT")
            summary = get_summary(tx_conn)

            formatted_results = []
            for r in item_results:
                entry: dict[str, Any] = {
                    "status": r.status,
                    "event_id": r.event_id,
                    "source_id": r.source_id,
                }
                if r.reason:
                    entry["reason"] = r.reason
                formatted_results.append(entry)

            resp_payload = build_success_response(
                req,
                formatted_results,
                asdict(summary)
            )

            insert_challenge_record(
                tx_conn,
                challenge_id=challenge_id,
                request_digest=request_digest,
                request_body=req,
                response=resp_payload,
                status="COMPLETED"
            )

        tracker.update_challenge(challenge_id, "COMPLETED", None)
        return resp_payload

    except Exception as e:
        logger.error(f"Error executing MQTT challenge {challenge_id}: {e}", exc_info=True)
        resp = build_failure_response(req, "INTERNAL_ERROR")
        tracker.update_challenge(challenge_id, "FAILED", "INTERNAL_ERROR")
        return resp
