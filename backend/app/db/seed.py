from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AvatarConfig, VoiceProfile
from app.db.session import AsyncSessionFactory

settings = get_settings()
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_backend_path(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return str(candidate.resolve())

    backend_candidate = BACKEND_ROOT / candidate
    if backend_candidate.exists():
        return str(backend_candidate.resolve())
    return str(backend_candidate)


async def ensure_default_avatar_config() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(AvatarConfig).limit(1))
        avatar_config = result.scalar_one_or_none()
        if avatar_config is not None:
            return

        session.add(
            AvatarConfig(
                name="默认数字人",
                slug="default-avatar",
                is_active=True,
                model_path=settings.default_avatar_model_path,
                voice_id=settings.default_avatar_voice_id,
                voice_profile_id=None,
                response_language=settings.default_avatar_response_language,
                persona=settings.default_avatar_persona,
                tts_reference_audio_path=settings.default_tts_reference_audio_path,
                tts_reference_text=settings.default_tts_reference_text,
                tts_speed=settings.default_tts_speed,
                tts_emotion_enabled=settings.default_tts_emotion_enabled,
            )
        )
        await session.commit()


async def ensure_default_voice_profile() -> None:
    reference_audio = _resolve_backend_path(settings.default_tts_reference_audio_path)
    reference_audio_path = Path(reference_audio)
    if not reference_audio_path.exists():
        return

    async with AsyncSessionFactory() as session:
        result = await session.execute(select(VoiceProfile).where(VoiceProfile.is_default.is_(True)).limit(1))
        profile = result.scalar_one_or_none()
        if profile is None:
            profile = VoiceProfile(
                name="默认导览音色",
                description="系统初始化的默认参考音频。",
                source_filename=reference_audio_path.name,
                audio_path=str(reference_audio_path),
                reference_text=settings.default_tts_reference_text,
                duration_ms=0,
                mime_type="audio/wav",
                is_default=True,
            )
            session.add(profile)
            await session.commit()
            await session.refresh(profile)

        avatar_result = await session.execute(
            select(AvatarConfig).where(AvatarConfig.is_active.is_(True)).limit(1)
        )
        avatar = avatar_result.scalar_one_or_none()
        if avatar is None:
            avatar_result = await session.execute(select(AvatarConfig).order_by(AvatarConfig.id.asc()).limit(1))
            avatar = avatar_result.scalar_one_or_none()
        if avatar is None:
            return

        if avatar.voice_profile_id:
            return

        avatar.voice_profile_id = profile.id
        if not avatar.tts_reference_audio_path:
            avatar.tts_reference_audio_path = str(reference_audio_path)
        if not avatar.tts_reference_text:
            avatar.tts_reference_text = settings.default_tts_reference_text
        if not avatar.voice_id:
            avatar.voice_id = profile.name
        await session.commit()
