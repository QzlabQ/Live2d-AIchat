import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.avatar import get_avatar_config, list_avatar_models, update_avatar_config
from app.core.config import Settings
from app.db.base import Base
from app.db.seed import ensure_avatar_model_paths
from app.db.migrations import (
    ensure_avatar_config_admin_columns,
    ensure_avatar_config_display_columns,
    ensure_avatar_config_profile_columns,
    ensure_avatar_config_response_language_column,
    ensure_avatar_config_tts_columns,
)
from app.db.models import AvatarConfig, VoiceProfile
from app.schemas.avatar import AvatarConfigUpdate, AvatarProfileCreate
from app.services.live2d_models import PREFERRED_LIVE2D_MODEL_PATH

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class AvatarConfigMigrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_migration_adds_tts_columns_to_old_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            settings = Settings(
                default_tts_reference_audio_path='./storage/vendor/CosyVoice/asset/zero_shot_prompt.wav',
                default_tts_reference_text='\u5e0c\u671b\u4f60\u4ee5\u540e\u80fd\u591f\u505a\u5f97\u6bd4\u6211\u8fd8\u597d\u3002',
                default_tts_speed=1.0,
                default_tts_emotion_enabled=True,
            )
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_tts_columns(engine, settings)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}
                    row = (await connection.execute(text('SELECT * FROM avatar_config LIMIT 1'))).mappings().one()

                self.assertIn('tts_reference_audio_path', names)
                self.assertIn('tts_reference_text', names)
                self.assertIn('tts_speed', names)
                self.assertIn('tts_emotion_enabled', names)
                self.assertEqual(row['tts_speed'], 1.0)
                self.assertEqual(row['tts_emotion_enabled'], 1)
            finally:
                await engine.dispose()

    async def test_sqlite_migration_adds_voice_profile_id_column(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_admin_columns(engine)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}

                self.assertIn('voice_profile_id', names)
            finally:
                await engine.dispose()

    async def test_sqlite_migration_adds_avatar_profile_columns(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_profile_columns(engine)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}
                    row = (await connection.execute(text('SELECT * FROM avatar_config LIMIT 1'))).mappings().one()

                self.assertIn('name', names)
                self.assertIn('slug', names)
                self.assertIn('is_active', names)
                self.assertIn('created_at', names)
                self.assertEqual(row['name'], '默认数字人')
                self.assertEqual(row['is_active'], 1)
            finally:
                await engine.dispose()

    async def test_sqlite_migration_adds_response_language_column(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            settings = Settings(default_avatar_response_language='zh')
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_response_language_column(engine, settings)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}
                    row = (await connection.execute(text('SELECT response_language FROM avatar_config LIMIT 1'))).mappings().one()

                self.assertIn('response_language', names)
                self.assertEqual(row['response_language'], 'zh')
            finally:
                await engine.dispose()

    async def test_sqlite_migration_adds_display_columns_to_old_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'old.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            try:
                async with engine.begin() as connection:
                    await connection.execute(text('''CREATE TABLE avatar_config (id INTEGER PRIMARY KEY AUTOINCREMENT, model_path VARCHAR(255) NOT NULL, voice_id VARCHAR(100) NOT NULL, persona TEXT NOT NULL, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)'''))
                    await connection.execute(text('''INSERT INTO avatar_config (model_path, voice_id, persona) VALUES ('model', 'voice', 'persona')'''))

                await ensure_avatar_config_display_columns(engine)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text('PRAGMA table_info(avatar_config)'))).mappings().all()
                    names = {column['name'] for column in columns}
                    row = (
                        await connection.execute(
                            text(
                                'SELECT display_scale, display_offset_x, display_offset_y, stage_height '
                                'FROM avatar_config LIMIT 1'
                            )
                        )
                    ).mappings().one()

                self.assertIn('display_scale', names)
                self.assertIn('display_offset_x', names)
                self.assertIn('display_offset_y', names)
                self.assertIn('stage_height', names)
                self.assertEqual(row['display_scale'], 1.0)
                self.assertEqual(row['display_offset_x'], 0.0)
                self.assertEqual(row['display_offset_y'], 0.0)
                self.assertEqual(row['stage_height'], 420)
            finally:
                await engine.dispose()


class AvatarConfigApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_config_api_reads_and_updates_tts_fields(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()

                    before = await get_avatar_config(session)
                    self.assertEqual(before.tts_speed, 1.0)
                    self.assertEqual(before.response_language, 'zh')

                    await update_avatar_config(
                        AvatarConfigUpdate(
                            response_language='en',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='new text',
                            tts_speed=1.2,
                            tts_emotion_enabled=False,
                        ),
                        db=session,
                    )

                    after = await get_avatar_config(session)
                    self.assertEqual(after.response_language, 'en')
                    self.assertEqual(after.tts_reference_text, 'new text')
                    self.assertEqual(after.tts_speed, 1.2)
                    self.assertFalse(after.tts_emotion_enabled)
            finally:
                await engine.dispose()

    async def test_avatar_config_api_rejects_missing_reference_audio(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()

                    with self.assertRaises(HTTPException) as raised:
                        await update_avatar_config(
                            AvatarConfigUpdate(tts_reference_audio_path='./storage/vendor/CosyVoice/asset/missing.wav'),
                            db=session,
                        )

                    self.assertEqual(raised.exception.status_code, 400)
            finally:
                await engine.dispose()

    async def test_avatar_config_api_rejects_reference_audio_outside_backend_workspace(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir, TemporaryDirectory() as outside_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')
            outside_wav = Path(outside_dir) / 'outside.wav'
            outside_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()

                    with self.assertRaises(HTTPException) as raised:
                        await update_avatar_config(
                            AvatarConfigUpdate(tts_reference_audio_path=str(outside_wav)),
                            db=session,
                        )

                    self.assertEqual(raised.exception.status_code, 400)
                    self.assertEqual(
                        raised.exception.detail,
                        'TTS reference audio must be inside the backend workspace or approved shared storage.',
                    )
            finally:
                await engine.dispose()

    async def test_avatar_config_update_applies_voice_profile_fields(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    profile = VoiceProfile(
                        name='Warm Guide',
                        description='default',
                        source_filename='prompt.wav',
                        audio_path=str(prompt_wav),
                        reference_text='新的参考文本',
                        duration_ms=1200,
                        mime_type='audio/wav',
                        is_default=False,
                    )
                    session.add(profile)
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()
                    await session.refresh(profile)

                    await update_avatar_config(
                        AvatarConfigUpdate(voice_profile_id=profile.id),
                        db=session,
                    )

                    after = await get_avatar_config(session)
                    self.assertEqual(after.voice_profile_id, profile.id)
                    self.assertEqual(after.voice_id, 'Warm Guide')
                    self.assertEqual(after.tts_reference_text, '新的参考文本')
                    self.assertEqual(Path(after.tts_reference_audio_path).resolve(), prompt_wav.resolve())
            finally:
                await engine.dispose()

    async def test_avatar_config_update_rejects_unknown_model_path(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()

                    with self.assertRaises(HTTPException) as raised:
                        await update_avatar_config(
                            AvatarConfigUpdate(model_path='/live2d/models/guide/guide.model3.json'),
                            db=session,
                        )

                    self.assertEqual(raised.exception.status_code, 400)
                    self.assertEqual(
                        raised.exception.detail,
                        'Avatar model path is not available in frontend/public/live2d.',
                    )
            finally:
                await engine.dispose()

    def test_avatar_config_update_rejects_out_of_range_tts_speed(self) -> None:
        with self.assertRaises(ValidationError):
            AvatarConfigUpdate(tts_speed=2.0)

    async def test_avatar_config_api_reads_and_updates_display_fields(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    session.add(
                        AvatarConfig(
                            model_path='model',
                            voice_id='voice',
                            persona='persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='old text',
                            tts_speed=1.0,
                            tts_emotion_enabled=True,
                        )
                    )
                    await session.commit()

                    before = await get_avatar_config(session)
                    self.assertEqual(before.display_scale, 1.0)
                    self.assertEqual(before.display_offset_x, 0.0)
                    self.assertEqual(before.display_offset_y, 0.0)
                    self.assertEqual(before.stage_height, 420)

                    await update_avatar_config(
                        AvatarConfigUpdate(
                            display_scale=1.24,
                            display_offset_x=0.08,
                            display_offset_y=-0.12,
                            stage_height=560,
                        ),
                        db=session,
                    )

                    after = await get_avatar_config(session)
                    self.assertEqual(after.display_scale, 1.24)
                    self.assertEqual(after.display_offset_x, 0.08)
                    self.assertEqual(after.display_offset_y, -0.12)
                    self.assertEqual(after.stage_height, 560)
            finally:
                await engine.dispose()

    def test_avatar_config_update_rejects_out_of_range_display_fields(self) -> None:
        invalid_payloads = [
            {'display_scale': 0.59},
            {'display_scale': 1.81},
            {'display_offset_x': -0.51},
            {'display_offset_x': 0.51},
            {'display_offset_y': -0.51},
            {'display_offset_y': 0.51},
            {'stage_height': 319},
            {'stage_height': 761},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    AvatarConfigUpdate(**payload)

    async def test_avatar_profiles_can_be_isolated_by_active_profile(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'profiles.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            from app.api.routes.avatar import create_avatar_profile, set_active_avatar_profile

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    haru = AvatarConfig(
                        name='Haru',
                        slug='haru',
                        is_active=True,
                        model_path=PREFERRED_LIVE2D_MODEL_PATH,
                        voice_id='haru-voice',
                        persona='haru persona',
                        tts_reference_audio_path=str(prompt_wav),
                        tts_reference_text='haru text',
                        tts_speed=1.0,
                        tts_emotion_enabled=True,
                    )
                    session.add(haru)
                    await session.commit()
                    await session.refresh(haru)

                    neuro = await create_avatar_profile(
                        AvatarProfileCreate(
                            name='Neuro',
                            model_path=PREFERRED_LIVE2D_MODEL_PATH,
                            voice_id='neuro-voice',
                            response_language='en',
                            persona='neuro persona',
                            tts_reference_audio_path=str(prompt_wav),
                            tts_reference_text='neuro text',
                            tts_speed=1.05,
                            tts_emotion_enabled=True,
                            activate=False,
                        ),
                        db=session,
                    )

                    await update_avatar_config(
                        AvatarConfigUpdate(persona='neuro persona updated', tts_speed=1.1),
                        profile_id=neuro.id,
                        db=session,
                    )

                    active_before = await get_avatar_config(session)
                    self.assertEqual(active_before.name, 'Haru')
                    self.assertEqual(active_before.persona, 'haru persona')

                    await set_active_avatar_profile(session, neuro.id)
                    active_after = await get_avatar_config(session)
                    self.assertEqual(active_after.name, 'Neuro')
                    self.assertEqual(active_after.persona, 'neuro persona updated')
                    self.assertEqual(active_after.tts_speed, 1.1)

                    haru_after = await get_avatar_config(session, profile_id=haru.id)
                    self.assertEqual(haru_after.persona, 'haru persona')
                    self.assertEqual(haru_after.tts_speed, 1.0)
            finally:
                await engine.dispose()

    async def test_ensure_avatar_model_paths_repairs_invalid_stored_profile(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory(dir=BACKEND_ROOT) as prompt_dir:
            db_path = Path(temp_dir) / 'repair.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(prompt_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as session:
                    invalid_profile = AvatarConfig(
                        name='Guide',
                        slug='guide',
                        is_active=True,
                        model_path='/live2d/models/guide/guide.model3.json',
                        voice_id='guide-voice',
                        persona='guide persona',
                        tts_reference_audio_path=str(prompt_wav),
                        tts_reference_text='guide text',
                        tts_speed=1.0,
                        tts_emotion_enabled=True,
                    )
                    session.add(invalid_profile)
                    await session.commit()
                    await session.refresh(invalid_profile)
                    profile_id = invalid_profile.id

                with (
                    patch('app.db.seed.AsyncSessionFactory', session_factory),
                    patch('app.db.seed.discover_live2d_model_paths', return_value=[PREFERRED_LIVE2D_MODEL_PATH]),
                ):
                    await ensure_avatar_model_paths()

                async with session_factory() as session:
                    repaired = await get_avatar_config(session, profile_id=profile_id)

                self.assertEqual(repaired.model_path, PREFERRED_LIVE2D_MODEL_PATH)
            finally:
                await engine.dispose()

    async def test_list_avatar_models_returns_existing_public_model(self) -> None:
        response = await list_avatar_models()
        self.assertTrue(any(item.path.endswith('haru_greeter_t03.model3.json') for item in response.items))


if __name__ == '__main__':
    unittest.main()
