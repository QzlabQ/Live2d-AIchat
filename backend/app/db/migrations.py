from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings


async def ensure_avatar_config_tts_columns(engine: AsyncEngine, settings: Settings) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'tts_reference_audio_path': 'ALTER TABLE avatar_config ADD COLUMN tts_reference_audio_path VARCHAR(500)',
            'tts_reference_text': 'ALTER TABLE avatar_config ADD COLUMN tts_reference_text TEXT',
            'tts_speed': 'ALTER TABLE avatar_config ADD COLUMN tts_speed FLOAT NOT NULL DEFAULT 1.0',
            'tts_emotion_enabled': 'ALTER TABLE avatar_config ADD COLUMN tts_emotion_enabled BOOLEAN NOT NULL DEFAULT 1',
        }

        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))

        await connection.execute(
            text(
                'UPDATE avatar_config '
                'SET tts_reference_audio_path = :path '
                'WHERE tts_reference_audio_path IS NULL OR length(tts_reference_audio_path) = 0'
            ),
            {'path': settings.default_tts_reference_audio_path},
        )
        await connection.execute(
            text(
                'UPDATE avatar_config '
                'SET tts_reference_text = :text '
                'WHERE tts_reference_text IS NULL OR length(tts_reference_text) = 0'
            ),
            {'text': settings.default_tts_reference_text},
        )
        await connection.execute(
            text('UPDATE avatar_config SET tts_speed = :speed WHERE tts_speed IS NULL'),
            {'speed': settings.default_tts_speed},
        )
        await connection.execute(
            text('UPDATE avatar_config SET tts_emotion_enabled = :enabled WHERE tts_emotion_enabled IS NULL'),
            {'enabled': 1 if settings.default_tts_emotion_enabled else 0},
        )
