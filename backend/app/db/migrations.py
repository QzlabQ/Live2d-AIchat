from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings


async def ensure_session_updated_at_column(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(sessions)'))
        existing = {row._mapping['name'] for row in result}
        if not existing or 'updated_at' in existing:
            return

        await connection.execute(
            text('ALTER TABLE sessions ADD COLUMN updated_at DATETIME')
        )
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ')
        await connection.execute(
            text(
                'UPDATE sessions '
                'SET updated_at = COALESCE(updated_at, created_at, :now)'
            ),
            {'now': now},
        )


async def ensure_message_analysis_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(messages)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'emotion': 'ALTER TABLE messages ADD COLUMN emotion VARCHAR(20)',
            'latency_ms': 'ALTER TABLE messages ADD COLUMN latency_ms INTEGER',
        }
        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))


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


async def ensure_avatar_config_admin_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        if 'voice_profile_id' not in existing:
            await connection.execute(
                text('ALTER TABLE avatar_config ADD COLUMN voice_profile_id VARCHAR(36)')
            )


async def ensure_avatar_config_profile_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'name': 'ALTER TABLE avatar_config ADD COLUMN name VARCHAR(120)',
            'slug': 'ALTER TABLE avatar_config ADD COLUMN slug VARCHAR(120)',
            'is_active': 'ALTER TABLE avatar_config ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 0',
            'created_at': 'ALTER TABLE avatar_config ADD COLUMN created_at DATETIME',
        }
        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))

        await connection.execute(
            text(
                "UPDATE avatar_config "
                "SET name = COALESCE(NULLIF(name, ''), '默认数字人') "
                "WHERE name IS NULL OR length(name) = 0"
            )
        )
        await connection.execute(
            text(
                "UPDATE avatar_config "
                "SET slug = COALESCE(NULLIF(slug, ''), 'avatar-' || id) "
                "WHERE slug IS NULL OR length(slug) = 0"
            )
        )
        await connection.execute(
            text(
                'UPDATE avatar_config '
                'SET created_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP) '
                'WHERE created_at IS NULL'
            )
        )

        first_active = (
            await connection.execute(
                text(
                    'SELECT id FROM avatar_config '
                    'WHERE is_active = 1 '
                    'ORDER BY updated_at DESC, id DESC '
                    'LIMIT 1'
                )
            )
        ).scalar_one_or_none()
        if first_active is None:
            first_active = (
                await connection.execute(
                    text('SELECT id FROM avatar_config ORDER BY updated_at DESC, id DESC LIMIT 1')
                )
            ).scalar_one_or_none()

        if first_active is not None:
            await connection.execute(text('UPDATE avatar_config SET is_active = 0'))
            await connection.execute(
                text('UPDATE avatar_config SET is_active = 1 WHERE id = :id'),
                {'id': first_active},
            )


async def ensure_avatar_config_response_language_column(engine: AsyncEngine, settings: Settings) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        if 'response_language' not in existing:
            await connection.execute(
                text("ALTER TABLE avatar_config ADD COLUMN response_language VARCHAR(12) NOT NULL DEFAULT 'zh'")
            )

        await connection.execute(
            text(
                'UPDATE avatar_config '
                'SET response_language = :response_language '
                'WHERE response_language IS NULL OR length(response_language) = 0'
            ),
            {'response_language': settings.default_avatar_response_language},
        )


async def ensure_avatar_config_display_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(avatar_config)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'display_scale': 'ALTER TABLE avatar_config ADD COLUMN display_scale FLOAT NOT NULL DEFAULT 1.0',
            'display_offset_x': 'ALTER TABLE avatar_config ADD COLUMN display_offset_x FLOAT NOT NULL DEFAULT 0.0',
            'display_offset_y': 'ALTER TABLE avatar_config ADD COLUMN display_offset_y FLOAT NOT NULL DEFAULT 0.0',
            'stage_height': 'ALTER TABLE avatar_config ADD COLUMN stage_height INTEGER NOT NULL DEFAULT 420',
        }
        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))

        defaults = {
            'display_scale': 1.0,
            'display_offset_x': 0.0,
            'display_offset_y': 0.0,
            'stage_height': 420,
        }
        for column, default in defaults.items():
            await connection.execute(
                text(f'UPDATE avatar_config SET {column} = :default WHERE {column} IS NULL'),
                {'default': default},
            )


async def ensure_knowledge_doc_admin_columns(engine: AsyncEngine) -> None:
    if not engine.url.get_backend_name().startswith('sqlite'):
        return

    async with engine.begin() as connection:
        result = await connection.execute(text('PRAGMA table_info(knowledge_docs)'))
        existing = {row._mapping['name'] for row in result}
        if not existing:
            return

        column_sql = {
            'stored_path': 'ALTER TABLE knowledge_docs ADD COLUMN stored_path VARCHAR(500)',
            'error_message': "ALTER TABLE knowledge_docs ADD COLUMN error_message TEXT NOT NULL DEFAULT ''",
        }
        for column, statement in column_sql.items():
            if column not in existing:
                await connection.execute(text(statement))

        await connection.execute(
            text("UPDATE knowledge_docs SET stored_path = '' WHERE stored_path IS NULL")
        )
        await connection.execute(
            text("UPDATE knowledge_docs SET error_message = '' WHERE error_message IS NULL")
        )
