import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.avatar import get_avatar_config, update_avatar_config
from app.core.config import Settings
from app.db.base import Base
from app.db.migrations import ensure_avatar_config_tts_columns
from app.db.models import AvatarConfig
from app.schemas.avatar import AvatarConfigUpdate


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
            await engine.dispose()


class AvatarConfigApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_avatar_config_api_reads_and_updates_tts_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(__file__).resolve().parents[1] / 'storage' / 'vendor' / 'CosyVoice' / 'asset' / 'zero_shot_prompt.wav'

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

                await update_avatar_config(
                    AvatarConfigUpdate(
                        tts_reference_audio_path=str(prompt_wav),
                        tts_reference_text='new text',
                        tts_speed=1.2,
                        tts_emotion_enabled=False,
                    ),
                    db=session,
                )

                after = await get_avatar_config(session)
                self.assertEqual(after.tts_reference_text, 'new text')
                self.assertEqual(after.tts_speed, 1.2)
                self.assertFalse(after.tts_emotion_enabled)

            await engine.dispose()

    async def test_avatar_config_api_rejects_missing_reference_audio(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'api.db'
            engine = create_async_engine(f'sqlite+aiosqlite:///{db_path}')
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            prompt_wav = Path(__file__).resolve().parents[1] / 'storage' / 'vendor' / 'CosyVoice' / 'asset' / 'zero_shot_prompt.wav'

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

            await engine.dispose()

    def test_avatar_config_update_rejects_out_of_range_tts_speed(self) -> None:
        with self.assertRaises(ValidationError):
            AvatarConfigUpdate(tts_speed=2.0)


if __name__ == '__main__':
    unittest.main()
