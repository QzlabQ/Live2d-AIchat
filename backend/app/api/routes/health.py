from __future__ import annotations

from fastapi import APIRouter

from app.db.session import ping_db
from app.schemas.health import HealthResponse
from app.services.asr import get_asr_service
from app.services.tts import get_tts_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    database_ok = await ping_db()
    database_status = "ready" if database_ok else "degraded"
    overall_status = "ok" if database_ok else "degraded"

    return HealthResponse(
        status=overall_status,
        database=database_status,
        asr=get_asr_service().status(),
        tts=get_tts_service().status(),
    )
