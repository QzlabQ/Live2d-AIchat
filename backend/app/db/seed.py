from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AvatarConfig
from app.db.session import AsyncSessionFactory

settings = get_settings()


async def ensure_default_avatar_config() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(AvatarConfig).limit(1))
        avatar_config = result.scalar_one_or_none()
        if avatar_config is not None:
            return

        session.add(
            AvatarConfig(
                model_path=settings.default_avatar_model_path,
                voice_id=settings.default_avatar_voice_id,
                persona=settings.default_avatar_persona,
            )
        )
        await session.commit()
