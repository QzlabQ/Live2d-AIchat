import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.sessions import (
    create_session,
    get_session_messages,
    list_sessions,
    update_session_interest_tags,
)
from app.db.base import Base
from app.db.migrations import ensure_session_updated_at_column
from app.db.models import Message, Session
from app.schemas.session import SessionCreateRequest, SessionInterestTagsUpdate
from app.services import visitor_sessions
from app.services.visitor_sessions import (
    list_visitor_sessions,
    load_session_messages,
    update_session_interest_tags as update_session_interest_tags_service,
)


class SessionMigrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_migration_adds_updated_at_to_old_sessions_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            expected_created_at = "2026-07-07 10:00:00"

            try:
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            """
                            CREATE TABLE sessions (
                                id VARCHAR(36) PRIMARY KEY NOT NULL,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                                interest_tags JSON NOT NULL,
                                device_type VARCHAR(20) NOT NULL
                            )
                            """
                        )
                    )
                    await connection.execute(
                        text(
                            """
                            INSERT INTO sessions (id, created_at, interest_tags, device_type)
                            VALUES (:id, :created_at, :interest_tags, :device_type)
                            """
                        ),
                        {
                            "id": "legacy-session",
                            "created_at": expected_created_at,
                            "interest_tags": "[]",
                            "device_type": "mobile",
                        },
                    )

                await ensure_session_updated_at_column(engine)

                async with engine.connect() as connection:
                    columns = (await connection.execute(text("PRAGMA table_info(sessions)"))).mappings().all()
                    row = (
                        await connection.execute(
                            text("SELECT created_at, updated_at FROM sessions WHERE id = :id"),
                            {"id": "legacy-session"},
                        )
                    ).mappings().one()

                self.assertIn("updated_at", {column["name"] for column in columns})
                self.assertEqual(row["updated_at"], row["created_at"])
                self.assertEqual(str(row["updated_at"]), expected_created_at)
            finally:
                await engine.dispose()

    async def test_init_db_triggers_session_updated_at_migration(self) -> None:
        with (
            patch("app.db.session.ensure_session_updated_at_column", new=AsyncMock()) as ensure_session_mock,
            patch("app.db.session.ensure_avatar_config_tts_columns", new=AsyncMock()) as ensure_avatar_mock,
            patch("app.db.session.engine") as engine_mock,
        ):
            connection = AsyncMock()
            begin_context = AsyncMock()
            begin_context.__aenter__.return_value = connection
            engine_mock.begin.return_value = begin_context

            from app.db.session import init_db

            await init_db()

            connection.run_sync.assert_awaited_once()
            ensure_session_mock.assert_awaited_once_with(engine_mock)
            ensure_avatar_mock.assert_awaited_once()


class VisitorSessionsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_list_sessions_uses_latest_message_time_as_updated_at(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'activity.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            older_time = datetime(2026, 7, 7, 10, 0, 0)
            newer_time = datetime(2026, 7, 7, 10, 5, 0)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(
                    interest_tags=["history"],
                    device_type="mobile",
                    created_at=older_time,
                    updated_at=older_time,
                )
                db.add(session_obj)
                await db.flush()
                db.add(
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="Night tour starts at 19:30.",
                        created_at=newer_time,
                    )
                )
                await db.commit()

                items = await list_visitor_sessions(db, limit=10)

            self.assertEqual(items[0].updated_at, newer_time)
            await engine.dispose()

    async def test_list_sessions_returns_latest_preview_sorted_by_activity(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'sessions.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            older_session_at = datetime(2026, 7, 7, 8, 0, 0)
            newer_session_at = datetime(2026, 7, 7, 9, 0, 0)
            older_message_at = datetime(2026, 7, 7, 10, 1, 0)
            newer_message_at = datetime(2026, 7, 7, 10, 5, 0)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                newer = Session(
                    interest_tags=["night-tour"],
                    device_type="mobile",
                    created_at=newer_session_at,
                    updated_at=newer_session_at,
                )
                older = Session(
                    interest_tags=["history"],
                    device_type="mobile",
                    created_at=older_session_at,
                    updated_at=older_session_at,
                )
                db.add_all([older, newer])
                await db.flush()
                db.add_all(
                    [
                        Message(
                            session_id=older.id,
                            role="user",
                            content="Tell me a history story first.",
                            created_at=older_message_at,
                        ),
                        Message(
                            session_id=newer.id,
                            role="user",
                            content="What time does the night tour start?",
                            created_at=newer_message_at,
                        ),
                    ]
                )
                await db.commit()

                items = await list_visitor_sessions(db, limit=10)

            self.assertEqual([item.session_id for item in items], [newer.id, older.id])
            self.assertEqual(items[0].last_message_preview, "What time does the night tour start?")
            self.assertEqual(items[0].interest_tags, ["night-tour"])
            self.assertEqual(items[0].updated_at, newer_message_at)
            self.assertEqual(items[1].updated_at, older_message_at)
            await engine.dispose()

    async def test_load_session_messages_returns_chat_timeline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'timeline.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.flush()
                db.add_all(
                    [
                        Message(session_id=session_obj.id, role="user", content="When is the park open?"),
                        Message(session_id=session_obj.id, role="assistant", content="The park is usually open from 9:00 to 21:30."),
                    ]
                )
                await db.commit()

                items = await load_session_messages(db, session_obj.id)

            self.assertEqual([item.role for item in items], ["user", "assistant"])
            self.assertEqual(items[1].content, "The park is usually open from 9:00 to 21:30.")
            await engine.dispose()

    async def test_save_session_message_refreshes_session_updated_at(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'save-message.db'}")
            try:
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                original_updated_at = datetime(2026, 7, 7, 10, 0, 0)
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as db:
                    session_obj = Session(
                        interest_tags=["history"],
                        device_type="mobile",
                        created_at=original_updated_at,
                        updated_at=original_updated_at,
                    )
                    db.add(session_obj)
                    await db.commit()
                    await db.refresh(session_obj)

                    self.assertTrue(hasattr(visitor_sessions, "save_session_message"))

                    await visitor_sessions.save_session_message(
                        db,
                        session_id=session_obj.id,
                        role="user",
                        content="Tell me about the old street.",
                    )
                    await db.refresh(session_obj)

                    self.assertGreater(session_obj.updated_at, original_updated_at)
                    messages = await load_session_messages(db, session_obj.id)

                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].content, "Tell me about the old street.")
            finally:
                await engine.dispose()

    async def test_update_session_interest_tags_persists_new_tags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'update.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.commit()
                await db.refresh(session_obj)

                updated = await update_session_interest_tags_service(db, session_obj.id, ["family", "relaxed"])

            self.assertEqual(updated.interest_tags, ["family", "relaxed"])
            await engine.dispose()

    async def test_sessions_route_lists_session_summaries(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'route-list.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_response = await create_session(
                    payload=SessionCreateRequest(interest_tags=["history"]),
                    db=db,
                )
                db.add(
                    Message(
                        session_id=session_response.session_id,
                        role="assistant",
                        content="Welcome to the old city night tour.",
                    )
                )
                await db.commit()

                response = await list_sessions(limit=20, db=db)

            self.assertEqual(len(response.items), 1)
            self.assertEqual(response.items[0].last_message_preview, "Welcome to the old city night tour.")
            await engine.dispose()

    async def test_sessions_route_returns_session_messages(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'route-detail.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.flush()
                db.add(Message(session_id=session_obj.id, role="user", content="I want to see the old street."))
                await db.commit()

                response = await get_session_messages(session_id=session_obj.id, db=db)

            self.assertEqual(len(response.items), 1)
            self.assertEqual(response.items[0].content, "I want to see the old street.")
            await engine.dispose()

    async def test_sessions_route_raises_404_when_loading_messages_for_missing_session(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'route-detail-missing.db'}")
            try:
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)

                async with session_factory() as db:
                    with self.assertRaises(HTTPException) as raised:
                        await get_session_messages(session_id="missing-session", db=db)

                self.assertEqual(raised.exception.status_code, 404)
            finally:
                await engine.dispose()

    async def test_sessions_route_updates_interest_tags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'route-patch.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                session_obj = Session(interest_tags=["history"], device_type="mobile")
                db.add(session_obj)
                await db.commit()

                response = await update_session_interest_tags(
                    session_id=session_obj.id,
                    payload=SessionInterestTagsUpdate(interest_tags=["family", "relaxed"]),
                    db=db,
                )

            self.assertEqual(response.interest_tags, ["family", "relaxed"])
            await engine.dispose()

    async def test_sessions_route_raises_404_when_updating_missing_session(self) -> None:
        with TemporaryDirectory() as temp_dir:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(temp_dir) / 'route-missing.db'}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as db:
                with self.assertRaises(HTTPException) as raised:
                    await update_session_interest_tags(
                        session_id="missing-session",
                        payload=SessionInterestTagsUpdate(interest_tags=["family"]),
                        db=db,
                    )

            self.assertEqual(raised.exception.status_code, 404)
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
