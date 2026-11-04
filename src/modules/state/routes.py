import os
from typing import Optional
from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse
from src.modules.state import service as state_service

router = APIRouter(prefix="/api/state", tags=["state"])


@router.get("", status_code=status.HTTP_200_OK)
def get_state(
    view: Optional[str] = Query(None),
    source_id: Optional[str] = Query(None)
):
    if not view or view not in ("summary", "pending", "exceptions", "sources", "mqtt"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid or missing 'view' parameter. Must be one of: summary, pending, exceptions"}
        )

    clean_source_id = source_id.strip() if source_id and source_id.strip() else None

    if view == "summary":
        summary = state_service.get_summary(source_id=clean_source_id)
        return {
            "net_total": summary.net_total,
            "processed_events": summary.processed_events,
            "pending_ack": summary.pending_ack,
            "unresolved": summary.unresolved,
            "duplicates": summary.duplicates,
            "conflicts": summary.conflicts,
            "rejected_submissions": summary.rejected_submissions,
        }

    if view == "pending":
        pending_events = state_service.get_pending(source_id=clean_source_id)
        return {"events": pending_events}

    if view == "exceptions":
        exceptions_list = state_service.get_exceptions(source_id=clean_source_id)
        return {"exceptions": exceptions_list}

    if view == "sources":
        sources_list = state_service.get_sources()
        return {"sources": sources_list}

    if view == "mqtt":
        from src.modules.mqtt.service import tracker, get_challenge_counts, get_latest_challenge_info
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
