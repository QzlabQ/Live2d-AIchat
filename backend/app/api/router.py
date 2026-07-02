from fastapi import APIRouter

from app.api.routes import avatar, health, knowledge, sessions

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(avatar.router, tags=["avatar"])
api_router.include_router(knowledge.router, tags=["knowledge"])
