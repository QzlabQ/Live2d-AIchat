from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import admin_auth, reports
from app.db.base import Base
from app.db.models import Message, Session
from app.db.session import get_db
from app.services.admin_auth import get_admin_auth_service
from app.services.reports import DailyEmotionReportService
from app.core.config import get_settings


class ReportsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'reports.db'}")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.app = FastAPI()
        self.app.include_router(admin_auth.router, prefix="/api/v1")
        self.app.include_router(reports.router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = self._override_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )
        self.headers = {
            "Authorization": f"Bearer {get_admin_auth_service().create_access_token('admin', ttl_seconds=3600)}"
        }
        self.report_service = DailyEmotionReportService(self.session_factory, get_settings())

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _override_db(self):
        async with self.session_factory() as session:
            yield session

    async def _seed_messages(self) -> None:
        target_day = datetime(2026, 7, 12, 10, 0, 0)
        async with self.session_factory() as db:
            session_obj = Session(
                interest_tags=["亲子", "文化"],
                device_type="mobile",
                created_at=target_day,
                updated_at=target_day,
            )
            db.add(session_obj)
            await db.flush()
            db.add_all(
                [
                    Message(
                        session_id=session_obj.id,
                        role="user",
                        content="开放时间是什么时候？",
                        created_at=target_day,
                    ),
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="景区整体通常 9:00 到 21:30 开放。",
                        created_at=target_day,
                        emotion="happy",
                        latency_ms=1320,
                    ),
                    Message(
                        session_id=session_obj.id,
                        role="user",
                        content="亲子路线怎么安排？",
                        created_at=datetime(2026, 7, 12, 10, 5, 0),
                    ),
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="建议先看九龙灌浴，再走轻松亲子路线。",
                        created_at=datetime(2026, 7, 12, 10, 5, 8),
                        emotion="excited",
                        latency_ms=1680,
                    ),
                ]
            )
            await db.commit()

    async def test_generate_daily_report_aggregates_messages(self) -> None:
        await self._seed_messages()

        async with self.session_factory() as db:
            report = await self.report_service.generate_for_date_in_session(db, date(2026, 7, 12), force=True)

        self.assertEqual(report.session_count, 1)
        self.assertEqual(report.message_count, 4)
        self.assertEqual(report.user_message_count, 2)
        self.assertEqual(report.assistant_message_count, 2)
        self.assertEqual(report.emotion_counts["happy"], 1)
        self.assertEqual(report.emotion_counts["excited"], 1)
        self.assertIn("亲子", report.top_interest_tags)
        self.assertTrue(report.summary_text)

    async def test_reports_routes_return_daily_and_summary_payloads(self) -> None:
        await self._seed_messages()

        generate_response = await self.client.post(
            "/api/v1/admin/reports/daily/generate",
            headers=self.headers,
            params={"report_date": "2026-07-12", "force": "true"},
        )
        self.assertEqual(generate_response.status_code, 200)
        self.assertEqual(generate_response.json()["report_date"], "2026-07-12")

        list_response = await self.client.get(
            "/api/v1/admin/reports/daily",
            headers=self.headers,
            params={"date_from": "2026-07-12", "date_to": "2026-07-12"},
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        summary_response = await self.client.get(
            "/api/v1/admin/reports/summary",
            headers=self.headers,
            params={"date_from": "2026-07-12", "date_to": "2026-07-12"},
        )
        self.assertEqual(summary_response.status_code, 200)
        payload = summary_response.json()
        self.assertEqual(payload["report_count"], 1)
        self.assertEqual(payload["message_count"], 4)
        self.assertIn("亲子", payload["top_interest_tags"])
        self.assertTrue(payload["summary_text"])


if __name__ == "__main__":
    unittest.main()
