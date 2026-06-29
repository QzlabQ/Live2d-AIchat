from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.ws_router import websocket_router
from app.core.config import get_settings
from app.db.seed import ensure_default_avatar_config
from app.db.session import init_db, shutdown_db

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await init_db()
        await ensure_default_avatar_config()
        logger.info("Database initialization finished.")
    except Exception:  # pragma: no cover - startup should remain resilient
        logger.exception("Backend startup finished with degraded database state.")
    yield
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
