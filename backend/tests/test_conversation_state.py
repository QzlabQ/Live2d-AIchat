import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Session
from app.services.conversation_state import (
    cancel_pending_clarification_state,
    get_active_clarification_state,
    upsert_clarification_state,
)


class ConversationStateStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_and_replace_pending_clarification_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as session:
                session.add(Session(id="session-1", interest_tags=[], device_type="mobile"))
                await session.commit()

                first = await upsert_clarification_state(
                    session,
                    session_id="session-1",
                    original_question="开放时间是什么时候？",
                    assistant_followup_question="你想问景区整体还是商铺？",
                    missing_slots=["target_scope"],
                    provisional_answer="景区整体一般 9:00-21:30。",
                    used_source_indexes=[1],
                )
                second = await upsert_clarification_state(
                    session,
                    session_id="session-1",
                    original_question="第一次来怎么逛？",
                    assistant_followup_question="你更偏亲子、夜游还是半日游？",
                    missing_slots=["visitor_profile"],
                    provisional_answer="第一次来可以先走核心主线。",
                    used_source_indexes=[1, 2],
                )

                active = await get_active_clarification_state(session, session_id="session-1")

            self.assertNotEqual(first.id, second.id)
            self.assertEqual(active.original_question, "第一次来怎么逛？")
            self.assertEqual(active.status, "pending")
            self.assertEqual(active.missing_slots, ["visitor_profile"])
            await engine.dispose()

    async def test_expired_pending_state_is_not_returned(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as session:
                session.add(Session(id="session-1", interest_tags=[], device_type="mobile"))
                await session.commit()

                await upsert_clarification_state(
                    session,
                    session_id="session-1",
                    original_question="开放时间是什么时候？",
                    assistant_followup_question="你想问景区整体还是商铺？",
                    missing_slots=["target_scope"],
                    provisional_answer="景区整体一般 9:00-21:30。",
                    used_source_indexes=[1],
                    expires_in_minutes=-1,
                )

                active = await get_active_clarification_state(session, session_id="session-1")

            self.assertIsNone(active)
            await engine.dispose()

    async def test_cancel_pending_state_marks_it_cancelled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.db"
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            session_factory = async_sessionmaker(engine, expire_on_commit=False)

            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

            async with session_factory() as session:
                session.add(Session(id="session-1", interest_tags=[], device_type="mobile"))
                await session.commit()

                await upsert_clarification_state(
                    session,
                    session_id="session-1",
                    original_question="开放时间是什么时候？",
                    assistant_followup_question="你想问景区整体还是商铺？",
                    missing_slots=["target_scope"],
                    provisional_answer="景区整体一般 9:00-21:30。",
                    used_source_indexes=[1],
                )
                await cancel_pending_clarification_state(session, session_id="session-1")
                active = await get_active_clarification_state(session, session_id="session-1")

            self.assertIsNone(active)
            await engine.dispose()


if __name__ == "__main__":
    unittest.main()
