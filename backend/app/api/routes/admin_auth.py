from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.admin import AdminLoginRequest, AdminLoginResponse, AdminMeResponse
from app.services.admin_auth import AdminAuthService, get_admin_auth_service, require_admin_auth

router = APIRouter(prefix="/admin/auth")


@router.post("/login", response_model=AdminLoginResponse)
async def login_admin(
    payload: AdminLoginRequest,
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminLoginResponse:
    token, expires_in = service.authenticate(payload.username, payload.password)
    return AdminLoginResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=AdminMeResponse)
async def get_admin_me(claims=Depends(require_admin_auth)) -> AdminMeResponse:
    return AdminMeResponse(username=claims.sub)
