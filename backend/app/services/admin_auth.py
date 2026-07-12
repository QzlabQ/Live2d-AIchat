from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings


def _b64url_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode((payload + padding).encode("ascii"))


@dataclass(slots=True)
class AdminClaims:
    sub: str
    exp: int
    iat: int


class AdminAuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authenticate(self, username: str, password: str) -> tuple[str, int]:
        if not (
            hmac.compare_digest(username, self.settings.admin_username)
            and hmac.compare_digest(password, self.settings.admin_password)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误。",
            )

        expires_in = int(self.settings.admin_token_ttl_seconds)
        return self.create_access_token(self.settings.admin_username, ttl_seconds=expires_in), expires_in

    def create_access_token(self, subject: str, *, ttl_seconds: int) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        issued_at = int(time.time())
        payload = {
            "sub": subject,
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
        }
        encoded_header = _b64url_encode(
            json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        encoded_payload = _b64url_encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        signature = hmac.new(
            self.settings.admin_jwt_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        return f"{encoded_header}.{encoded_payload}.{_b64url_encode(signature)}"

    def decode_access_token(self, token: str) -> AdminClaims:
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="管理员令牌格式无效。",
            ) from exc

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            self.settings.admin_jwt_secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64url_decode(encoded_signature)):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="管理员令牌签名无效。",
            )

        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
        claims = AdminClaims(
            sub=str(payload.get("sub", "")),
            exp=int(payload.get("exp", 0)),
            iat=int(payload.get("iat", 0)),
        )
        if not claims.sub or claims.exp <= int(time.time()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="管理员令牌已过期或无效。",
            )
        return claims


@lru_cache
def get_admin_auth_service() -> AdminAuthService:
    return AdminAuthService(get_settings())


bearer_scheme = HTTPBearer(auto_error=False)


async def require_admin_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: AdminAuthService = Depends(get_admin_auth_service),
) -> AdminClaims:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少管理员认证信息。",
        )
    return service.decode_access_token(credentials.credentials)
