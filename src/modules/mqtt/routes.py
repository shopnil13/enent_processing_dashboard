import os
from fastapi import APIRouter, status
from src.modules.mqtt.service import tracker, get_challenge_counts, get_latest_challenge_info

router = APIRouter(prefix="/api/mqtt", tags=["mqtt"])


@router.get("/status", status_code=status.HTTP_200_OK)
def get_mqtt_status():
    completed, failed = get_challenge_counts()
    last_info = get_latest_challenge_info()

    return {
        "connected": tracker.connected,
        "candidate_id": tracker.candidate_id or os.getenv("CANDIDATE_ID", "shopnil13"),
        "broker": tracker.broker or f"{os.getenv('MQTT_BROKER_HOST', '152.42.238.142')}:{os.getenv('MQTT_BROKER_PORT', '1883')}",
        "last_challenge_id": tracker.last_challenge_id or (last_info["challenge_id"] if last_info else None),
        "last_challenge_time": tracker.last_challenge_time or (last_info["responded_at"] if last_info else None),
        "last_response_status": tracker.last_response_status or (last_info["status"] if last_info else None),
        "last_error": tracker.last_error,
        "completed_challenges": completed,
        "failed_challenges": failed,
    }
