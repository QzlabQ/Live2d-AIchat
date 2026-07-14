from fastapi import APIRouter

from app.api.routes import (
    admin_auth,
    admin_sessions,
    avatar,
    dashboard,
    health,
    knowledge,
    knowledge_gaps,
    reports,
    sessions,
    visitor,
    voice_profiles,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(admin_auth.router, tags=["admin-auth"])
api_router.include_router(admin_sessions.router, tags=["admin-sessions"])
api_router.include_router(avatar.router, tags=["avatar"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(knowledge.router, tags=["knowledge"])
api_router.include_router(knowledge_gaps.router, tags=["knowledge-gaps"])
api_router.include_router(voice_profiles.router, tags=["voice-profiles"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(visitor.router, tags=["visitor"])
