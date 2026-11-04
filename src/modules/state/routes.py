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
    if not view or view not in ("summary", "pending", "exceptions", "sources"):
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
