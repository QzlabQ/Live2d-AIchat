from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.visitor import create_session_recommendations, router as visitor_router
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Session
from app.db.session import get_db
from app.schemas.visitor import VisitorRecommendationRequest, VisitorRecommendationResponse
from app.services.recommendations import (
    RecommendationRequest,
    RecommendationResult,
    VisitorRecommendationService,
    get_visitor_recommendation_service,
)


class VisitorRecommendationServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_recommendation_request_requires_interest_tags(self) -> None:
        with self.assertRaises(ValidationError):
            VisitorRecommendationRequest.model_validate({})

    async def test_recommend_returns_structured_result_when_llm_succeeds(self) -> None:
        service = VisitorRecommendationService(Settings())
        expected = RecommendationResult(
            route_title="History Walk",
            intro="A compact route for first-time visitors who like stories.",
            highlights=["Old City Gate", "Memorial Hall"],
            suggested_questions=["What should I see first?"],
            applied_interest_tags=["history", "architecture"],
        )
        service._complete_structured = AsyncMock(return_value=expected)

        result = await service.recommend(
            RecommendationRequest(
                session_id="session-1",
                interest_tags=["history", "architecture"],
                device_type="mobile",
            )
        )

        self.assertEqual(result, expected)
        service._complete_structured.assert_awaited_once()

    async def test_recommend_returns_fallback_when_llm_generation_fails(self) -> None:
        class InvalidJsonLLM:
            async def complete(self, messages: list[dict[str, str]]) -> str:
                return "not-json"

        service = VisitorRecommendationService(Settings(), llm=InvalidJsonLLM())

        with self.assertLogs("app.services.recommendations", level="WARNING") as captured:
            result = await service.recommend(
                RecommendationRequest(
                    session_id="session-2",
                    interest_tags=["family"],
                    device_type="mobile",
                )
            )

        self.assertTrue(result.route_title)
        self.assertTrue(result.intro)
        self.assertGreater(len(result.highlights), 0)
        self.assertGreater(len(result.suggested_questions), 0)
        self.assertEqual(result.applied_interest_tags, ["family"])
        self.assertIn("Structured recommendation fallback", captured.output[0])

    async def test_recommend_propagates_unexpected_exceptions(self) -> None:
        service = VisitorRecommendationService(Settings())
        service._complete_structured = AsyncMock(side_effect=RuntimeError("unexpected"))

        with self.assertRaises(RuntimeError):
            await service.recommend(
                RecommendationRequest(
                    session_id="session-3",
                    interest_tags=["history"],
                    device_type="mobile",
                )
            )

    async def test_complete_structured_falls_back_to_request_tags_when_llm_tags_are_invalid(self) -> None:
        class StaticJsonLLM:
            def __init__(self, payload: dict[str, object]) -> None:
                self.payload = payload

            async def complete(self, messages: list[dict[str, str]]) -> str:
                return json.dumps(self.payload)

        service = VisitorRecommendationService(
            Settings(),
            llm=StaticJsonLLM(
                {
                    "route_title": "Culture Route",
                    "intro": "See the highlights first.",
                    "highlights": ["Gate", "Hall"],
                    "suggested_questions": ["Where should I stop first?"],
                    "applied_interest_tags": ["night-tour", "unknown"],
                }
            ),
        )

        result = await service._complete_structured(
            RecommendationRequest(
                session_id="session-4",
                interest_tags=["history", "family"],
                device_type="mobile",
            )
        )

        self.assertEqual(result.applied_interest_tags, ["history", "family"])


class StubRecommendationService:
    def __init__(self, result: RecommendationResult) -> None:
        self.result = result
        self.requests: list[RecommendationRequest] = []

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        self.requests.append(request)
        return self.result


class RecommendationsApiRouteTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'recommendations.db'}"
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        await self._create_schema()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _insert_session(self, *, interest_tags: list[str], device_type: str = "mobile") -> Session:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=interest_tags, device_type=device_type)
            session.add(session_obj)
            await session.commit()
            await session.refresh(session_obj)
            return session_obj

    async def test_recommendations_route_returns_404_for_missing_session(self) -> None:
        stub = StubRecommendationService(
            RecommendationResult(
                route_title="Unused",
                intro="Unused",
                highlights=["Unused"],
                suggested_questions=["Unused"],
                applied_interest_tags=["unused"],
            )
        )
        payload = VisitorRecommendationRequest(
            interest_tags=["history"],
            visitor_profile="first-time visitor",
        )

        async with self.session_factory() as db:
            with self.assertRaises(HTTPException) as raised:
                await create_session_recommendations(
                    session_id="missing-session",
                    payload=payload,
                    db=db,
                    service=stub,
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Session not found.")
        self.assertEqual(stub.requests, [])

    async def test_recommendations_route_returns_structured_response_for_existing_session(self) -> None:
        session_obj = await self._insert_session(
            interest_tags=["existing-session-tag"],
            device_type="kiosk",
        )
        stub = StubRecommendationService(
            RecommendationResult(
                route_title="Family History Route",
                intro="Start with iconic landmarks, then slow down for stories.",
                highlights=["Main Square", "Old Street", "Memorial Hall"],
                suggested_questions=["Which stop is best for kids?"],
                applied_interest_tags=["history", "family"],
            )
        )
        payload = VisitorRecommendationRequest(
            interest_tags=["history", "family"],
            visitor_profile="traveling with children",
        )

        async with self.session_factory() as db:
            response = await create_session_recommendations(
                session_id=session_obj.id,
                payload=payload,
                db=db,
                service=stub,
            )

        structured = VisitorRecommendationResponse.model_validate(response.model_dump())
        self.assertEqual(structured.route_title, "Family History Route")
        self.assertEqual(structured.applied_interest_tags, ["history", "family"])
        self.assertEqual(len(stub.requests), 1)
        self.assertEqual(stub.requests[0].session_id, session_obj.id)
        self.assertEqual(stub.requests[0].interest_tags, ["history", "family"])
        self.assertEqual(stub.requests[0].visitor_profile, "traveling with children")
        self.assertEqual(stub.requests[0].device_type, "kiosk")


class RecommendationsHttpSmokeTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'recommendations-http.db'}"
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        await self._create_schema()

        self.app = FastAPI()
        self.app.include_router(visitor_router, prefix="/api/v1")
        self.app.dependency_overrides[get_db] = self._override_db
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _override_db(self):
        async with self.session_factory() as session:
            yield session

    async def _insert_session(self) -> Session:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["history"], device_type="mobile")
            session.add(session_obj)
            await session.commit()
            await session.refresh(session_obj)
            return session_obj

    async def test_post_recommendations_returns_serialized_body(self) -> None:
        session_obj = await self._insert_session()
        stub = StubRecommendationService(
            RecommendationResult(
                route_title="Classic Route",
                intro="Start with the main landmark.",
                highlights=["Main Landmark", "Old Street"],
                suggested_questions=["What is the best next stop?"],
                applied_interest_tags=["history"],
            )
        )
        self.app.dependency_overrides[get_visitor_recommendation_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/recommendations",
            json={
                "interest_tags": ["history"],
                "visitor_profile": "first visit",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "route_title": "Classic Route",
                "intro": "Start with the main landmark.",
                "highlights": ["Main Landmark", "Old Street"],
                "suggested_questions": ["What is the best next stop?"],
                "applied_interest_tags": ["history"],
            },
        )

    async def test_post_recommendations_requires_interest_tags_in_request_body(self) -> None:
        session_obj = await self._insert_session()
        stub = StubRecommendationService(
            RecommendationResult(
                route_title="Unused",
                intro="Unused",
                highlights=["Unused"],
                suggested_questions=["Unused"],
                applied_interest_tags=["unused"],
            )
        )
        self.app.dependency_overrides[get_visitor_recommendation_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/recommendations",
            json={"visitor_profile": "first visit"},
        )

        self.assertEqual(response.status_code, 422)


class AggregatedApiRouterSmokeTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'recommendations-aggregated.db'}"
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        await self._create_schema()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _override_db(self):
        async with self.session_factory() as session:
            yield session

    async def _insert_session(self) -> Session:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["history"], device_type="mobile")
            session.add(session_obj)
            await session.commit()
            await session.refresh(session_obj)
            return session_obj

    def _stub_route_module(self) -> types.ModuleType:
        module = types.ModuleType("stub_route_module")
        module.router = FastAPI().router
        return module

    async def test_api_router_includes_visitor_recommendations_post_route(self) -> None:
        stubbed_modules = {
            "app.api.routes.health": self._stub_route_module(),
            "app.api.routes.avatar": self._stub_route_module(),
            "app.api.routes.knowledge": self._stub_route_module(),
            "app.api.routes.sessions": self._stub_route_module(),
        }

        with patch.dict(sys.modules, stubbed_modules):
            sys.modules.pop("app.api.router", None)
            api_router_module = importlib.import_module("app.api.router")
            api_router_module = importlib.reload(api_router_module)

            app = FastAPI()
            app.include_router(api_router_module.api_router, prefix="/api/v1")
            app.dependency_overrides[get_db] = self._override_db
            stub = StubRecommendationService(
                RecommendationResult(
                    route_title="Aggregated Route",
                    intro="Served through aggregated api_router.",
                    highlights=["Main Landmark"],
                    suggested_questions=["What comes next?"],
                    applied_interest_tags=["history"],
                )
            )
            app.dependency_overrides[get_visitor_recommendation_service] = lambda: stub

            route_match = [
                route
                for route in api_router_module.api_router.routes
                if getattr(route, "path", None) == "/sessions/{session_id}/recommendations"
            ]
            self.assertEqual(len(route_match), 1)
            self.assertIn("POST", route_match[0].methods)

            session_obj = await self._insert_session()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app if False else app),
                base_url="http://testserver",
            ) as client:
                response = await client.post(
                    f"/api/v1/sessions/{session_obj.id}/recommendations",
                    json={"interest_tags": ["history"]},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["route_title"], "Aggregated Route")


if __name__ == "__main__":
    unittest.main()
