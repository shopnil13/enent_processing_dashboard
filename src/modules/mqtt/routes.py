from fastapi import APIRouter, status
from src.modules.mqtt.service import tracker, get_challenge_counts

router = APIRouter(prefix="/api/mqtt", tags=["mqtt"])


@router.get("/status", status_code=status.HTTP_200_OK)
def get_mqtt_status():
    completed, failed = get_challenge_counts()
    return {
        "connected": tracker.connected,
        "candidate_id": tracker.candidate_id,
        "broker": tracker.broker,
        "last_challenge_id": tracker.last_challenge_id,
        "last_challenge_time": tracker.last_challenge_time,
        "last_response_status": tracker.last_response_status,
        "last_error": tracker.last_error,
        "completed_challenges": completed,
        "failed_challenges": failed,
    }
