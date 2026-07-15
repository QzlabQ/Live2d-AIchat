from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.ws_router import websocket_router
from app.core.config import get_settings
from app.db.seed import ensure_default_avatar_config, ensure_default_voice_profile
from app.db.session import init_db, shutdown_db
from app.services.asr import get_asr_service
from app.services.avatar_trace import get_avatar_trace_service
from app.services.reports import get_report_service
from app.services.tts import TTSRuntimeValidationError, get_tts_service

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    trace_service = get_avatar_trace_service()
    report_service = get_report_service()
    try:
        await init_db()
        await ensure_default_avatar_config()
        await ensure_default_voice_profile()
        await asyncio.to_thread(get_tts_service().warmup)
        await get_asr_service().warmup()
        await trace_service.start()
        await report_service.start()
        logger.info("Database initialization finished.")
    except TTSRuntimeValidationError:
        await report_service.stop()
        await trace_service.stop()
        await shutdown_db()
        logger.exception("Backend startup failed due to invalid TTS runtime configuration.")
        raise
    except Exception:  # pragma: no cover - startup should remain resilient
        logger.exception("Backend startup finished with degraded database state.")
    yield
    await report_service.stop()
    await trace_service.stop()
    await shutdown_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "status": "ok",
            "docs": "/docs",
            "api_prefix": settings.api_v1_prefix,
            "websocket": "/ws/chat/{session_id}",
        }

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.include_router(websocket_router)
    return app


app = create_app()
