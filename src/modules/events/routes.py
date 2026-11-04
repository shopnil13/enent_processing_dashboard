import logging
from typing import Any
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from src.shared.db import transaction
from src.modules.events.service import process_events

logger = logging.getLogger("events.routes")
router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", status_code=status.HTTP_200_OK)
async def submit_events(request: Request):
    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON body"}
        )

    if not isinstance(raw_body, (dict, list)):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Request body must be a JSON object or an array of objects"}
        )

    raw_items = [raw_body] if isinstance(raw_body, dict) else raw_body

    if not raw_items:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"results": []}
        )

    try:
        with transaction() as conn:
            results = process_events(conn, raw_items, channel="REST")
    except Exception as e:
        logger.error(f"Unexpected error processing event batch: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "INTERNAL_ERROR"}
        )

    response_items = []
    for r in results:
        entry: dict[str, Any] = {
            "status": r.status,
            "event_id": r.event_id,
            "source_id": r.source_id,
        }
        if r.reason is not None:
            entry["reason"] = r.reason
        response_items.append(entry)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"results": response_items}
    )
