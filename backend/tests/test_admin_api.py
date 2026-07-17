from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import struct
import unittest
import wave
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import admin_auth, admin_sessions, avatar, knowledge, voice_profiles
from app.db.base import Base
from app.db.models import Message, Session
from app.db.session import get_db
from app.services.admin_auth import get_admin_auth_service


def build_wav_bytes(duration_ms: int = 200) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        frame_count = int(16_000 * (duration_ms / 1000))
        wav_file.writeframes(b"\x00\x00" * frame_count)
    return buffer.getvalue()


def build_wav_bytes_min_size(min_bytes: int) -> bytes:
    bytes_per_second = 16_000 * 2
    payload_bytes = max(0, min_bytes - 44)
    duration_ms = int((payload_bytes / bytes_per_second) * 1000) + 1000
    wav_bytes = build_wav_bytes(duration_ms)
    if len(wav_bytes) < min_bytes:
        extra_ms = int(((min_bytes - len(wav_bytes)) / bytes_per_second) * 1000) + 1000
        wav_bytes = build_wav_bytes(duration_ms + extra_ms)
    return wav_bytes


def build_float_wav_bytes(duration_ms: int = 500, sample_rate: int = 48_000) -> bytes:
    frame_count = int(sample_rate * (duration_ms / 1000))
    channels = 1
    bits_per_sample = 32
    block_align = channels * (bits_per_sample // 8)
    byte_rate = sample_rate * block_align
    audio_data = b"".join(struct.pack("<f", 0.0) for _ in range(frame_count))
    fmt_chunk = struct.pack(
        "<HHIIHH",
        3,  # WAVE_FORMAT_IEEE_FLOAT
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    riff_size = 4 + (8 + len(fmt_chunk)) + (8 + len(audio_data))
    return (
        b"RIFF"
        + struct.pack("<I", riff_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt_chunk))
        + fmt_chunk
        + b"data"
        + struct.pack("<I", len(audio_data))
        + audio_data
    )


class AdminApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{Path(self.temp_dir.name) / 'admin.db'}")
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        self.app = FastAPI()
        self.app.include_router(admin_auth.router, prefix="/api/v1")
        self.app.include_router(admin_sessions.router, prefix="/api/v1")
        self.app.include_router(avatar.router, prefix="/api/v1")
        self.app.include_router(knowledge.router, prefix="/api/v1")
        self.app.include_router(voice_profiles.router, prefix="/api/v1")
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

    async def test_admin_login_returns_bearer_token(self) -> None:
        response = await self.client.post(
            "/api/v1/admin/auth/login",
            json={"username": "admin", "password": "admin123"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "bearer")
        self.assertTrue(payload["access_token"])

    async def test_upload_and_list_voice_profiles(self) -> None:
        response = await self.client.post(
            "/api/v1/admin/voice-profiles",
            headers=self.headers,
            data={
                "name": "Warm Guide",
                "reference_text": "欢迎来到景区。",
                "description": "用于后台测试",
            },
            files={"file": ("guide.wav", build_wav_bytes(), "audio/wav")},
        )

        self.assertEqual(response.status_code, 201)
        profile_id = response.json()["item"]["id"]

        list_response = await self.client.get("/api/v1/admin/voice-profiles", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        audio_response = await self.client.get(
            f"/api/v1/admin/voice-profiles/{profile_id}/audio",
            headers=self.headers,
        )
        self.assertEqual(audio_response.status_code, 200)
        self.assertGreater(len(audio_response.content), 0)

        delete_response = await self.client.delete(
            f"/api/v1/admin/voice-profiles/{profile_id}",
            headers=self.headers,
        )
        self.assertEqual(delete_response.status_code, 200)

    async def test_upload_large_voice_profile_under_new_default_limit(self) -> None:
        oversized_for_old_limit = build_wav_bytes_min_size((8 * 1024 * 1024) + 1024)

        response = await self.client.post(
            "/api/v1/admin/voice-profiles",
            headers=self.headers,
            data={
                "name": "Large Guide",
                "reference_text": "Hello and welcome to the scenic area.",
                "description": "Used to verify larger wav uploads.",
            },
            files={"file": ("large-guide.wav", oversized_for_old_limit, "audio/wav")},
        )

        self.assertEqual(response.status_code, 201)
        self.assertGreater(len(oversized_for_old_limit), 8 * 1024 * 1024)

    async def test_upload_float_wav_voice_profile(self) -> None:
        response = await self.client.post(
            "/api/v1/admin/voice-profiles",
            headers=self.headers,
            data={
                "name": "Float Guide",
                "reference_text": "Hello and welcome.",
                "description": "Used to verify float wav uploads.",
            },
            files={"file": ("float-guide.wav", build_float_wav_bytes(), "audio/wav")},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["item"]["mime_type"], "audio/wav")

    async def test_upload_knowledge_doc_returns_processing_row(self) -> None:
        with patch("app.api.routes.knowledge._schedule_knowledge_import", return_value=None):
            response = await self.client.post(
                "/api/v1/admin/knowledge/upload",
                headers=self.headers,
                data={"category": "history"},
                files={"file": ("history.txt", "灵山胜境历史介绍".encode("utf-8"), "text/plain")},
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["status"], "processing")

        list_response = await self.client.get("/api/v1/admin/knowledge", headers=self.headers)
        self.assertEqual(list_response.status_code, 200)
        items = list_response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "history.txt")
        self.assertEqual(items[0]["category"], "history")
        self.assertEqual(items[0]["status"], "processing")

    async def test_admin_can_list_sessions(self) -> None:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["family", "night"], device_type="kiosk")
            session.add(session_obj)
            await session.flush()
            session.add_all(
                [
                    Message(session_id=session_obj.id, role="user", content="开放时间是什么时候？"),
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="景区通常 9:00 开放，夜间运营到 21:30 左右。",
                        emotion="neutral",
                        latency_ms=1320,
                    ),
                ]
            )
            await session.commit()

        response = await self.client.get("/api/v1/admin/sessions", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["device_type"], "kiosk")
        self.assertEqual(payload["items"][0]["interest_tags"], ["family", "night"])
        self.assertEqual(payload["items"][0]["message_count"], 2)
        self.assertIn("21:30", payload["items"][0]["last_message_preview"])

    async def test_admin_can_load_session_detail_with_message_meta(self) -> None:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["history"], device_type="mobile")
            session.add(session_obj)
            await session.flush()
            session.add_all(
                [
                    Message(session_id=session_obj.id, role="user", content="这里有什么历史故事？"),
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="可以先从九龙灌浴看起，它讲的是释迦牟尼诞生的典故。",
                        emotion="thinking",
                        latency_ms=2480,
                    ),
                ]
            )
            await session.commit()
            session_id = session_obj.id

        response = await self.client.get(f"/api/v1/admin/sessions/{session_id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["session_id"], session_id)
        self.assertEqual(payload["message_count"], 2)
        self.assertEqual(payload["items"][1]["emotion"], "thinking")
        self.assertEqual(payload["items"][1]["latency_ms"], 2480)
        self.assertIn("九龙灌浴", payload["items"][1]["content"])

    async def test_admin_session_detail_includes_reply_trace_diagnostics(self) -> None:
        async with self.session_factory() as session:
            session_obj = Session(interest_tags=["history"], device_type="mobile")
            session.add(session_obj)
            await session.flush()
            session.add_all(
                [
                    Message(session_id=session_obj.id, role="user", content="开放时间是什么时候？"),
                    Message(
                        session_id=session_obj.id,
                        role="assistant",
                        content="景区整体开放一般是 9:00-21:30。",
                        emotion="neutral",
                        latency_ms=1240,
                    ),
                ]
            )
            await session.commit()
            session_id = session_obj.id

        trace_log_path = Path(self.temp_dir.name) / "avatar_trace.log"
        trace_log_path.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "created_at": "2026-07-16T16:10:49+00:00",
                            "reply_id": f"{session_id}-new",
                            "session_id": session_id,
                            "streaming": True,
                            "chat_mode": "rag",
                            "tts_engine": "cosyvoice",
                            "tts_stream_profile": "stable",
                            "prompt_cache_hit": True,
                            "prompt_cache_build_ms": 0.0,
                            "torch_cuda_available": True,
                            "torch_device_name": "Tesla V100-PCIE-32GB",
                            "requested_onnx_provider": "cuda",
                            "tts_cosyvoice_fp16": True,
                            "tts_cosyvoice_load_jit": False,
                            "tts_ar_backend": "pytorch",
                            "tts_flow_backend": "trt",
                            "audio_chunk_count": 4,
                            "segment_count": 1,
                            "max_chunk_gap_ms": 3200,
                            "tts_chunks": [
                                {
                                    "seq": 0,
                                    "chunk_index": 0,
                                    "token_offset": 0,
                                    "token_wait_ms": 1800,
                                    "token2wav_ms": 600,
                                    "tts_chunk_audio_ms": 1000,
                                    "chunk_supply_lag_ms": 0,
                                    "tts_chunk_rtf": 2.4,
                                    "tts_chunk_ready_ratio": 2.4,
                                    "tts_chunk_real_rtf": 0.417,
                                    "is_final": False,
                                }
                            ],
                            "metrics": {
                                "rag_embed_ms": 30,
                                "rag_vector_search_ms": 10,
                                "rag_retrieve_ms": 40,
                                "rag_rerank_ms": 100,
                                "rag_retrieve_total_ms": 140,
                                "tts_first_audio_chunk_ms": 3400,
                            },
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "created_at": "2026-07-16T16:05:49+00:00",
                            "reply_id": f"{session_id}-old",
                            "session_id": session_id,
                            "streaming": True,
                            "chat_mode": "rag",
                            "tts_engine": "cosyvoice",
                            "tts_stream_profile": "stable",
                            "prompt_cache_hit": False,
                            "prompt_cache_build_ms": 108.3,
                            "torch_cuda_available": True,
                            "torch_device_name": "Tesla V100-PCIE-32GB",
                            "requested_onnx_provider": "cuda",
                            "tts_cosyvoice_fp16": True,
                            "tts_cosyvoice_load_jit": False,
                            "tts_ar_backend": "pytorch",
                            "tts_flow_backend": "trt",
                            "audio_chunk_count": 5,
                            "segment_count": 2,
                            "max_chunk_gap_ms": 4100,
                            "tts_chunks": [],
                            "metrics": {
                                "rag_embed_ms": 50,
                                "rag_vector_search_ms": 20,
                                "rag_retrieve_ms": 70,
                                "rag_rerank_ms": 2100,
                                "rag_retrieve_total_ms": 2170,
                                "tts_first_audio_chunk_ms": 9100,
                            },
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "created_at": "2026-07-16T16:11:49+00:00",
                            "reply_id": "other-session",
                            "session_id": "other-session-id",
                            "streaming": True,
                            "chat_mode": "rag",
                            "tts_engine": "cosyvoice",
                            "audio_chunk_count": 1,
                            "segment_count": 1,
                            "max_chunk_gap_ms": 100,
                            "tts_chunks": [],
                            "metrics": {"rag_rerank_ms": 9999},
                        },
                        ensure_ascii=False,
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch("app.services.admin_sessions._DEFAULT_LOG_PATH", trace_log_path):
            response = await self.client.get(f"/api/v1/admin/sessions/{session_id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["reply_traces"]), 2)
        self.assertEqual(payload["reply_traces"][0]["reply_id"], f"{session_id}-new")
        self.assertEqual(payload["reply_traces"][0]["metrics"]["rag_rerank_ms"], 100)
        self.assertEqual(payload["reply_traces"][0]["tts_chunks"][0]["tts_chunk_real_rtf"], 0.417)
        self.assertTrue(payload["reply_traces"][0]["tts_cosyvoice_fp16"])
        self.assertEqual(payload["reply_traces"][0]["tts_ar_backend"], "pytorch")
        self.assertEqual(payload["reply_traces"][0]["tts_flow_backend"], "trt")
        self.assertEqual(payload["reply_trace_summary"]["trace_count"], 2)
        self.assertEqual(payload["reply_trace_summary"]["avg_metrics"]["rag_rerank_ms"], 1100.0)
        self.assertEqual(payload["reply_trace_summary"]["max_metrics"]["tts_first_audio_chunk_ms"], 9100)


if __name__ == "__main__":
    unittest.main()
