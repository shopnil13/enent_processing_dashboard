import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional


def compute_canonical_digest(data: Any) -> str:
    """Computes SHA-256 hex digest of canonically formatted JSON (sorted keys, compact separators)."""
    canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def parse_envelope(raw_input: bytes | str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Parses raw MQTT message payload into JSON dict. Returns (parsed_dict, error_code)."""
    try:
        if isinstance(raw_input, bytes):
            raw_str = raw_input.decode("utf-8")
        else:
            raw_str = str(raw_input)
        parsed = json.loads(raw_str)
        if not isinstance(parsed, dict):
            return None, "VALIDATION_ERROR"
        return parsed, None
    except Exception:
        return None, "VALIDATION_ERROR"


def validate_challenge_envelope(
    payload: dict[str, Any],
    expected_candidate_id: str
) -> Optional[str]:
    """
    Validates challenge envelope rules according to Section 6.
    Returns error code if invalid, or None if valid.
    """
    if payload.get("protocol_version") != "1.0":
        return "UNSUPPORTED_PROTOCOL"

    if payload.get("candidate_id") != expected_candidate_id:
        return "CANDIDATE_MISMATCH"

    if payload.get("command") != "PROCESS_EVENTS" or not isinstance(payload.get("events"), list):
        return "VALIDATION_ERROR"

    challenge_id = payload.get("challenge_id")
    if not challenge_id or not isinstance(challenge_id, str):
        return "VALIDATION_ERROR"

    expires_at_raw = payload.get("expires_at")
    if expires_at_raw:
        try:
            clean_ts = expires_at_raw.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(clean_ts)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp_dt:
                return "CHALLENGE_EXPIRED"
        except Exception:
            return "VALIDATION_ERROR"

    return None


def build_success_response(
    req: dict[str, Any],
    results: list[dict[str, Any]],
    state_summary: dict[str, Any]
) -> dict[str, Any]:
    return {
        "protocol_version": req.get("protocol_version", "1.0"),
        "candidate_id": req.get("candidate_id"),
        "challenge_id": req.get("challenge_id"),
        "status": "COMPLETED",
        "results": results,
        "state": state_summary
    }


def build_failure_response(
    req: Optional[dict[str, Any]],
    error_code: str
) -> dict[str, Any]:
    resp: dict[str, Any] = {
        "protocol_version": (req or {}).get("protocol_version", "1.0"),
        "status": "FAILED",
        "error": error_code
    }
    if req and "candidate_id" in req:
        resp["candidate_id"] = req["candidate_id"]
    if req and "challenge_id" in req:
        resp["challenge_id"] = req["challenge_id"]
    return resp
