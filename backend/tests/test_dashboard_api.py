from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import admin_auth, dashboard
from app.db.base import Base
from app.db.models import Message, Session
from app.db.session import get_db
from app.services.admin_auth import get_admin_auth_service


class DashboardApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'dashboard.db'}")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.app = FastAPI()
        self.app.include_router(admin_auth.router, prefix="/api/v1")
        self.app.include_router(dashboard.router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = self._override_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        self.headers = {
            "Authorization": f"Bearer {get_admin_auth_service().create_access_token('admin', ttl_seconds=3600)}"
        }

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _override_db(self):
        async with self.session_factory() as session:
            yield session

    async def _seed_dashboard_data(self) -> None:
        now = datetime.now()
        base_day = now.replace(hour=10, minute=0, second=0, microsecond=0)
        async with self.session_factory() as db:
            session_a = Session(
                interest_tags=["路线", "亲子"],
                device_type="mobile",
                created_at=base_day,
                updated_at=now - timedelta(minutes=2),
            )
            session_b = Session(
                interest_tags=["开放时间"],
                device_type="desktop",
                created_at=base_day - timedelta(days=1),
                updated_at=now - timedelta(minutes=4),
            )
            db.add_all([session_a, session_b])
            await db.flush()
            db.add_all(
                [
                    Message(
                        session_id=session_a.id,
                        role="user",
                        content="开放时间是什么时候？",
                        created_at=base_day,
                    ),
                    Message(
                        session_id=session_a.id,
                        role="assistant",
                        content="景区通常 9:00 到 21:30 开放。",
                        created_at=base_day + timedelta(seconds=6),
                        emotion="happy",
                        latency_ms=1200,
                    ),
                    Message(
                        session_id=session_b.id,
                        role="user",
                        content="亲子家庭来灵山胜境怎么安排路线？",
                        created_at=base_day - timedelta(days=1),
                    ),
                    Message(
                        session_id=session_b.id,
                        role="assistant",
                        content="推荐走轻松路线。",
                        created_at=base_day - timedelta(days=1, seconds=-7),
                        emotion="thinking",
                        latency_ms=900,
                    ),
                ]
            )
            await db.commit()

    async def test_dashboard_endpoints_return_aggregates(self) -> None:
        await self._seed_dashboard_data()

        overview_response = await self.client.get(
            "/api/v1/admin/dashboard/overview",
            headers=self.headers,
            params={"period": "week"},
        )
        self.assertEqual(overview_response.status_code, 200)
        overview = overview_response.json()
        self.assertEqual(overview["session_count"], 2)
        self.assertEqual(overview["message_count"], 4)
        self.assertGreaterEqual(overview["realtime_online_count"], 1)
        self.assertTrue(overview["top_questions"])
        self.assertTrue(
            any("开放时间" in item["question"] for item in overview["top_questions"]),
        )
        self.assertTrue(overview["service_trend"])
        self.assertTrue(overview["satisfaction_trend"])
        self.assertTrue(overview["keyword_cloud"])
        self.assertTrue(any(item["word"] == "开放时间" for item in overview["keyword_cloud"]))

        emotion_response = await self.client.get(
            "/api/v1/admin/dashboard/emotion",
            headers=self.headers,
            params={
                "start": (datetime.now().date() - timedelta(days=2)).isoformat(),
                "end": datetime.now().date().isoformat(),
            },
        )
        self.assertEqual(emotion_response.status_code, 200)
        emotion = emotion_response.json()
        self.assertTrue(emotion["trend"])
        self.assertIn("happy", emotion["emotion_counts"])
        self.assertIn("summary_text", emotion)


if __name__ == "__main__":
    unittest.main()
