import logging
from typing import Any
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from src.shared.db import transaction
from src.modules.ack.service import acknowledge_events

logger = logging.getLogger("ack.routes")
router = APIRouter(prefix="/api/ack", tags=["ack"])


@router.post("", status_code=status.HTTP_200_OK)
async def post_ack(request: Request):
    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Invalid JSON body"}
        )

    if not isinstance(raw_body, dict) or "event_ids" not in raw_body:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Body must be a JSON object containing 'event_ids' list"}
        )

    event_ids = raw_body.get("event_ids")
    if not isinstance(event_ids, list):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "'event_ids' must be a list of strings"}
        )

    if not event_ids:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"results": []}
        )

    # Convert all items to strings
    clean_ids = [str(eid) for eid in event_ids]

    try:
        with transaction() as conn:
            results = acknowledge_events(conn, clean_ids)
    except Exception as e:
        logger.error(f"Unexpected error during acknowledgment: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "INTERNAL_ERROR"}
        )

    response_items = [{"event_id": r.event_id, "status": r.status} for r in results]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"results": response_items}
    )
