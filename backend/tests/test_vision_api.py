from __future__ import annotations

import io
import mimetypes
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.visitor import recognize_session_vision, router as visitor_router
from app.core.config import Settings
from app.db.base import Base
from app.db.models import Session
from app.db.session import get_db
from app.services.vision import (
    VisitorVisionError,
    VisitorVisionPayloadTooLargeError,
    VisitorVisionResponseFormatError,
    VisitorVisionResult,
    VisitorVisionService,
    VisitorVisionServiceNotConfiguredError,
    VisitorVisionUnsupportedMediaTypeError,
    VisitorVisionUpstreamError,
    VisitorVisionValidationError,
    get_visitor_vision_service,
)


class VisitorVisionServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_recognize_stores_image_and_returns_relative_storage_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)
            model_payload = {
                "recognized_spot": "Main Gate",
                "recognition_summary": "A stone gate at the scenic area entrance.",
                "resolved_question": "Can you introduce the Main Gate first?",
            }
            request_mock = AsyncMock(return_value=model_payload)

            with patch.object(service, "_request_recognition_payload", request_mock):
                result = await service.recognize(
                    session_id="session-vision-1",
                    filename="gate.jpg",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xff\xe0mock-jpeg",
                    interest_tags=["history", "architecture"],
                    user_prompt="What is this spot?",
                )

            stored_path = Path(settings.visitor_upload_dir) / result.stored_image_path
            self.assertEqual(result.recognized_spot, "Main Gate")
            self.assertEqual(
                result.resolved_question,
                "Can you introduce the Main Gate first?",
            )
            self.assertFalse(Path(result.stored_image_path).is_absolute())
            self.assertEqual(Path(result.stored_image_path).parts[0], "session-vision-1")
            self.assertTrue(stored_path.exists())
            self.assertTrue(
                request_mock.await_args.kwargs["data_url"].startswith("data:image/jpeg;base64,")
            )

    async def test_recognize_raises_when_dashscope_key_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key=None,
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)

            with self.assertRaises(VisitorVisionServiceNotConfiguredError) as raised:
                await service.recognize(
                    session_id="session-vision-2",
                    filename="gate.jpg",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xff\xe0mock-jpeg",
                    interest_tags=["history"],
                )

            self.assertEqual(str(raised.exception), "DASHSCOPE_API_KEY is not configured.")

    async def test_recognize_rejects_unsupported_content_type(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)

            with self.assertRaises(VisitorVisionUnsupportedMediaTypeError):
                await service.recognize(
                    session_id="session-vision-3",
                    filename="gate.gif",
                    content_type="image/gif",
                    data=b"GIF89a",
                    interest_tags=["history"],
                )

    async def test_recognize_rejects_empty_image_data(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)

            with self.assertRaises(VisitorVisionValidationError) as raised:
                await service.recognize(
                    session_id="session-vision-empty",
                    filename="empty.jpg",
                    content_type="image/jpeg",
                    data=b"",
                    interest_tags=["history"],
                )

            self.assertEqual(str(raised.exception), "Image file is empty.")

    async def test_recognize_rejects_invalid_image_bytes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)

            with self.assertRaises(VisitorVisionValidationError) as raised:
                await service.recognize(
                    session_id="session-vision-invalid",
                    filename="invalid.jpg",
                    content_type="image/jpeg",
                    data=b"not-a-real-image",
                    interest_tags=["history"],
                )

            self.assertEqual(
                str(raised.exception),
                "Image file content does not match the declared image type.",
            )

    async def test_recognize_raises_response_error_when_required_field_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)
            request_mock = AsyncMock(
                return_value={
                    "recognized_spot": "Main Gate",
                    "recognition_summary": "A stone gate at the scenic area entrance.",
                }
            )

            with patch.object(service, "_request_recognition_payload", request_mock):
                with self.assertRaises(VisitorVisionResponseFormatError):
                    await service.recognize(
                        session_id="session-vision-4",
                        filename="gate.jpg",
                        content_type="image/jpeg",
                    data=b"\xff\xd8\xff\xe0mock-jpeg",
                    interest_tags=["history"],
                )

    async def test_recognize_uses_validated_content_type_for_stored_extension(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)
            request_mock = AsyncMock(
                return_value={
                    "recognized_spot": "Main Gate",
                    "recognition_summary": "A stone gate at the scenic area entrance.",
                    "resolved_question": "Can you introduce the Main Gate first?",
                }
            )

            with patch.object(service, "_request_recognition_payload", request_mock):
                result = await service.recognize(
                    session_id="session-vision-extension",
                    filename="photo.exe",
                    content_type="image/jpeg",
                    data=b"\xff\xd8\xff\xe0mock-jpeg",
                    interest_tags=["history"],
                )

            expected_extension = mimetypes.guess_extension("image/jpeg") or ".bin"
            self.assertTrue(result.stored_image_path.endswith(expected_extension))
            self.assertFalse(result.stored_image_path.endswith(".exe"))

    async def test_request_recognition_payload_raises_upstream_error_on_http_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            settings = Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(temp_dir) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
            service = VisitorVisionService(settings)

            class FailingAsyncClient:
                def __init__(self, *args, **kwargs) -> None:
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb) -> None:
                    return None

                async def post(self, *args, **kwargs):
                    raise httpx.ConnectError("boom")

            with patch("app.services.vision.httpx.AsyncClient", FailingAsyncClient):
                with self.assertRaises(VisitorVisionUpstreamError) as raised:
                    await service._request_recognition_payload(
                        data_url="data:image/jpeg;base64,/9j/",
                        interest_tags=["history"],
                        user_prompt="What is this spot?",
                    )

            self.assertEqual(str(raised.exception), "Vision model request failed.")


class StubVisionService:
    def __init__(
        self,
        result: VisitorVisionResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[dict[str, object]] = []

    async def recognize(
        self,
        session_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        interest_tags: list[str],
        user_prompt: str | None = None,
    ) -> VisitorVisionResult:
        self.requests.append(
            {
                "session_id": session_id,
                "filename": filename,
                "content_type": content_type,
                "data": data,
                "interest_tags": interest_tags,
                "user_prompt": user_prompt,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class VisitorVisionRouteTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'vision.db'}"
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        await self._create_schema()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        self.temp_dir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _insert_session(self) -> Session:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["history"], device_type="mobile")
            session.add(session_obj)
            await session.commit()
            await session.refresh(session_obj)
            return session_obj

    async def test_recognize_route_returns_404_for_missing_session(self) -> None:
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Unused",
                recognition_summary="Unused",
                resolved_question="Unused",
                stored_image_path="missing/unused.jpg",
            )
        )
        upload = UploadFile(
            file=io.BytesIO(b"\xff\xd8\xff\xe0mock-jpeg"),
            filename="missing.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        async with self.session_factory() as db:
            with self.assertRaises(HTTPException) as raised:
                await recognize_session_vision(
                    session_id="missing-session",
                    file=upload,
                    interest_tags='["history"]',
                    user_prompt="What is this?",
                    db=db,
                    service=stub,
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Session not found.")
        self.assertEqual(stub.requests, [])

    async def test_recognize_route_rejects_invalid_interest_tags_json(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Unused",
                recognition_summary="Unused",
                resolved_question="Unused",
                stored_image_path="unused/unused.jpg",
            )
        )
        upload = UploadFile(
            file=io.BytesIO(b"\xff\xd8\xff\xe0mock-jpeg"),
            filename="invalid-tags.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        async with self.session_factory() as db:
            with self.assertRaises(HTTPException) as raised:
                await recognize_session_vision(
                    session_id=session_obj.id,
                    file=upload,
                    interest_tags='{"history": true}',
                    user_prompt=None,
                    db=db,
                    service=stub,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(
            raised.exception.detail,
            "interest_tags must be a JSON array string.",
        )
        self.assertEqual(stub.requests, [])

    async def test_recognize_route_rejects_invalid_interest_tag_items(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Unused",
                recognition_summary="Unused",
                resolved_question="Unused",
                stored_image_path="unused/unused.jpg",
            )
        )
        upload = UploadFile(
            file=io.BytesIO(b"\xff\xd8\xff\xe0mock-jpeg"),
            filename="invalid-tag-items.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        async with self.session_factory() as db:
            with self.assertRaises(HTTPException) as raised:
                await recognize_session_vision(
                    session_id=session_obj.id,
                    file=upload,
                    interest_tags='[1, {"nested": true}, null]',
                    user_prompt=None,
                    db=db,
                    service=stub,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(
            raised.exception.detail,
            "interest_tags must be a JSON array of non-empty strings.",
        )
        self.assertEqual(stub.requests, [])

    async def test_recognize_route_rejects_blank_interest_tag_items(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Unused",
                recognition_summary="Unused",
                resolved_question="Unused",
                stored_image_path="unused/unused.jpg",
            )
        )
        upload = UploadFile(
            file=io.BytesIO(b"\xff\xd8\xff\xe0mock-jpeg"),
            filename="blank-tag-items.jpg",
            headers=Headers({"content-type": "image/jpeg"}),
        )

        async with self.session_factory() as db:
            with self.assertRaises(HTTPException) as raised:
                await recognize_session_vision(
                    session_id=session_obj.id,
                    file=upload,
                    interest_tags='["   "]',
                    user_prompt=None,
                    db=db,
                    service=stub,
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(
            raised.exception.detail,
            "interest_tags must be a JSON array of non-empty strings.",
        )
        self.assertEqual(stub.requests, [])


class VisitorVisionHttpSmokeTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'vision-http.db'}"
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
        self.app.dependency_overrides.clear()
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

    async def test_post_vision_recognize_returns_structured_payload(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Main Gate",
                recognition_summary="A stone gate at the scenic area entrance.",
                resolved_question="Can you introduce the Main Gate first?",
                stored_image_path=f"{session_obj.id}/main-gate.jpg",
            )
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/vision/recognize",
            data={
                "interest_tags": '["history","architecture"]',
                "user_prompt": "What is this spot?",
            },
            files={"file": ("gate.jpg", b"\xff\xd8\xff\xe0mock-jpeg", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "recognized_spot": "Main Gate",
                "recognition_summary": "A stone gate at the scenic area entrance.",
                "resolved_question": "Can you introduce the Main Gate first?",
                "stored_image_path": f"{session_obj.id}/main-gate.jpg",
            },
        )
        self.assertEqual(len(stub.requests), 1)
        self.assertEqual(stub.requests[0]["session_id"], session_obj.id)
        self.assertEqual(stub.requests[0]["filename"], "gate.jpg")
        self.assertEqual(stub.requests[0]["content_type"], "image/jpeg")
        self.assertEqual(stub.requests[0]["interest_tags"], ["history", "architecture"])
        self.assertEqual(stub.requests[0]["user_prompt"], "What is this spot?")

    async def test_post_vision_recognize_accepts_empty_interest_tags_array(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Main Gate",
                recognition_summary="A stone gate at the scenic area entrance.",
                resolved_question="Can you introduce the Main Gate first?",
                stored_image_path=f"{session_obj.id}/main-gate.jpg",
            )
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/vision/recognize",
            data={"interest_tags": "[]"},
            files={"file": ("gate.jpg", b"\xff\xd8\xff\xe0mock-jpeg", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(stub.requests[0]["interest_tags"], ["history"])

    async def test_post_vision_recognize_returns_415_for_unsupported_media_type(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(error=VisitorVisionUnsupportedMediaTypeError("Unsupported image content type."))
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/vision/recognize",
            data={"interest_tags": '["history"]'},
            files={"file": ("gate.gif", b"GIF89a", "image/gif")},
        )

        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["detail"], "Unsupported image content type.")

    async def test_post_vision_recognize_returns_400_for_empty_upload(self) -> None:
        session_obj = await self._insert_session()
        service = VisitorVisionService(
            Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(self.temp_dir.name) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
        )
        request_mock = AsyncMock(
            return_value={
                "recognized_spot": "Unused",
                "recognition_summary": "Unused",
                "resolved_question": "Unused",
            }
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: service

        with patch.object(service, "_request_recognition_payload", request_mock):
            response = await self.client.post(
                f"/api/v1/sessions/{session_obj.id}/vision/recognize",
                data={"interest_tags": '["history"]'},
                files={"file": ("empty.jpg", b"", "image/jpeg")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Image file is empty.")
        request_mock.assert_not_awaited()

    async def test_post_vision_recognize_returns_400_for_invalid_image_bytes(self) -> None:
        session_obj = await self._insert_session()
        service = VisitorVisionService(
            Settings(
                dashscope_api_key="test-key",
                visitor_upload_dir=str(Path(self.temp_dir.name) / "uploads"),
                visitor_image_max_bytes=1024 * 1024,
            )
        )
        request_mock = AsyncMock(
            return_value={
                "recognized_spot": "Unused",
                "recognition_summary": "Unused",
                "resolved_question": "Unused",
            }
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: service

        with patch.object(service, "_request_recognition_payload", request_mock):
            response = await self.client.post(
                f"/api/v1/sessions/{session_obj.id}/vision/recognize",
                data={"interest_tags": '["history"]'},
                files={"file": ("broken.jpg", b"not-a-real-image", "image/jpeg")},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Image file content does not match the declared image type.",
        )
        request_mock.assert_not_awaited()

    async def test_post_vision_recognize_returns_413_before_calling_service(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            result=VisitorVisionResult(
                recognized_spot="Unused",
                recognition_summary="Unused",
                resolved_question="Unused",
                stored_image_path="unused/unused.jpg",
            )
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        oversized_settings = Settings(visitor_image_max_bytes=4)
        with patch("app.api.routes.visitor.get_settings", return_value=oversized_settings):
            response = await self.client.post(
                f"/api/v1/sessions/{session_obj.id}/vision/recognize",
                data={"interest_tags": '["history"]'},
                files={"file": ("large.jpg", b"\xff\xd8\xff\xe0toolarge", "image/jpeg")},
            )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], "Image file exceeds the configured size limit.")
        self.assertEqual(stub.requests, [])

    async def test_post_vision_recognize_returns_502_for_response_parse_failures(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            error=VisitorVisionResponseFormatError("Vision recognition payload is not valid JSON.")
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/vision/recognize",
            data={"interest_tags": '["history"]'},
            files={"file": ("gate.jpg", b"\xff\xd8\xff\xe0mock-jpeg", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "Vision recognition payload is not valid JSON.",
        )

    async def test_post_vision_recognize_returns_503_for_missing_service_config(self) -> None:
        session_obj = await self._insert_session()
        stub = StubVisionService(
            error=VisitorVisionServiceNotConfiguredError("DASHSCOPE_API_KEY is not configured.")
        )
        self.app.dependency_overrides[get_visitor_vision_service] = lambda: stub

        response = await self.client.post(
            f"/api/v1/sessions/{session_obj.id}/vision/recognize",
            data={"interest_tags": '["history"]'},
            files={"file": ("gate.jpg", b"\xff\xd8\xff\xe0mock-jpeg", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "DASHSCOPE_API_KEY is not configured.",
        )


if __name__ == "__main__":
    unittest.main()
