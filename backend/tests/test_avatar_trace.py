import json
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import APIRouter

from app.services.avatar_trace import ReplyTrace, TraceLoggerWorker
from app.services.tts import TTSRuntimeValidationError


def import_main_for_lifespan_tests():
    with patch.dict(
        sys.modules,
        {
            "app.api.router": SimpleNamespace(api_router=APIRouter()),
            "app.api.ws_router": SimpleNamespace(websocket_router=APIRouter()),
        },
    ):
        import app.main as main_module

        return importlib.reload(main_module)


class ReplyTraceTestCase(unittest.TestCase):
    def test_mark_keeps_first_timestamp(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-1",
            session_id="session-1",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.mark("avatar_phase_thinking_ms", 12)
        trace.mark("avatar_phase_thinking_ms", 48)

        self.assertEqual(trace.metrics["avatar_phase_thinking_ms"], 12)

    def test_observe_audio_chunk_tracks_max_gap(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-2",
            session_id="session-2",
            streaming=True,
            chat_mode="template",
            tts_engine="mock",
        )

        trace.observe_audio_chunk(120)
        trace.observe_audio_chunk(250)
        trace.observe_audio_chunk(300)

        payload = trace.to_payload()

        self.assertEqual(payload["audio_chunk_count"], 3)
        self.assertEqual(payload["max_chunk_gap_ms"], 130)

    def test_observe_tts_chunk_records_detailed_metrics(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-2",
            session_id="session-2",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.observe_tts_chunk(
            seq=1,
            chunk_index=2,
            sent_at_ms=500,
            audio_duration_ms=1200,
            model_ready_ms=430,
            send_lag_ms=7,
        )

        payload = trace.to_payload()

        self.assertEqual(payload["audio_chunk_count"], 1)
        self.assertEqual(payload["max_chunk_gap_ms"], 0)
        self.assertEqual(payload["tts_vendor_session_count"], 1)
        self.assertEqual(payload["metrics"]["tts_total_token_wait_ms"], 0)
        self.assertEqual(payload["metrics"]["tts_total_token2wav_ms"], 0)
        self.assertEqual(
            payload["tts_chunks"],
            [
                {
                    "seq": 1,
                    "chunk_index": 2,
                    "sent_at_ms": 500,
                    "tts_chunk_audio_ms": 1200,
                    "tts_model_ready_ms": 430,
                    "tts_ws_send_lag_ms": 7,
                    "tts_chunk_gap_ms": 0,
                    "tts_chunk_rtf": 0.358,
                    "tts_chunk_ready_ratio": 0.358,
                    "tts_chunk_real_rtf": 0.0,
                    "token_wait_ms": 0,
                    "token2wav_ms": 0,
                    "hop_len": 0,
                    "token_offset": 0,
                    "chunk_supply_lag_ms": 0,
                    "is_final": False,
                }
            ],
        )

    def test_observe_tts_chunk_records_real_rtf_from_wait_and_token2wav(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-2b",
            session_id="session-2b",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.observe_tts_chunk(
            seq=0,
            chunk_index=1,
            sent_at_ms=600,
            audio_duration_ms=4000,
            model_ready_ms=6200,
            send_lag_ms=11,
            token_wait_ms=5200,
            token2wav_ms=1000,
        )

        payload = trace.to_payload()

        self.assertEqual(payload["metrics"]["tts_total_token_wait_ms"], 5200)
        self.assertEqual(payload["metrics"]["tts_total_token2wav_ms"], 1000)
        self.assertEqual(payload["tts_chunks"][0]["tts_chunk_rtf"], 1.55)
        self.assertEqual(payload["tts_chunks"][0]["tts_chunk_ready_ratio"], 1.55)
        self.assertEqual(payload["tts_chunks"][0]["tts_chunk_real_rtf"], 0.645)

    def test_runtime_and_prompt_cache_snapshots_are_serialized(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-4",
            session_id="session-4",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.set_runtime_snapshot(
            {
                "torch_cuda_available": True,
                "torch_device_name": "Tesla V100-PCIE-32GB",
                "requested_onnx_provider": "cuda",
                "available_onnx_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "tts_stream_profile": "balanced",
                "tts_cosyvoice_load_trt": True,
                "tts_cosyvoice_trt_concurrent": 1,
                "tts_trt_engine_expected": True,
                "tts_trt_engine_loaded": True,
                "tts_segment_soft_min_chars": 22,
                "tts_segment_soft_max_chars": 40,
                "tts_segment_hard_max_chars": 64,
                "tts_synthesis_strategy": "per_segment",
                "tts_prefetch_enabled": True,
            }
        )
        trace.set_prompt_cache_snapshot(hit=True, build_ms=18.5)

        payload = trace.to_payload()

        self.assertTrue(payload["torch_cuda_available"])
        self.assertEqual(payload["torch_device_name"], "Tesla V100-PCIE-32GB")
        self.assertEqual(payload["requested_onnx_provider"], "cuda")
        self.assertEqual(
            payload["available_onnx_providers"], ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        self.assertEqual(payload["tts_stream_profile"], "balanced")
        self.assertTrue(payload["tts_cosyvoice_load_trt"])
        self.assertEqual(payload["tts_cosyvoice_trt_concurrent"], 1)
        self.assertTrue(payload["tts_trt_engine_expected"])
        self.assertTrue(payload["tts_trt_engine_loaded"])
        self.assertEqual(payload["tts_segment_soft_min_chars"], 22)
        self.assertEqual(payload["tts_segment_soft_max_chars"], 40)
        self.assertEqual(payload["tts_segment_hard_max_chars"], 64)
        self.assertEqual(payload["tts_synthesis_strategy"], "per_segment")
        self.assertTrue(payload["tts_prefetch_enabled"])
        self.assertEqual(payload["tts_prefetch_started_count"], 0)
        self.assertEqual(payload["tts_prefetch_hit_count"], 0)
        self.assertEqual(payload["tts_vendor_session_count"], 0)
        self.assertTrue(payload["prompt_cache_hit"])
        self.assertEqual(payload["prompt_cache_build_ms"], 18.5)

    def test_observe_tts_chunk_accumulates_prefetch_counts(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-5",
            session_id="session-5",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.observe_tts_chunk(
            seq=1,
            chunk_index=0,
            sent_at_ms=100,
            audio_duration_ms=800,
            model_ready_ms=320,
            send_lag_ms=6,
            prefetch_enabled=True,
            prefetch_started_count_delta=1,
            prefetch_hit_count_delta=1,
        )

        payload = trace.to_payload()

        self.assertTrue(payload["tts_prefetch_enabled"])
        self.assertEqual(payload["tts_prefetch_started_count"], 1)
        self.assertEqual(payload["tts_prefetch_hit_count"], 1)


class TraceLoggerWorkerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_worker_writes_structured_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "avatar_trace.log"
            worker = TraceLoggerWorker(log_path=log_path)
            trace = ReplyTrace(
                reply_id="reply-3",
                session_id="session-3",
                streaming=False,
                chat_mode="rag",
                tts_engine="edge-tts",
                prompt_cache_hit=False,
            )
            trace.mark("avatar_phase_thinking_ms", 15)
            trace.segment_count = 2

            await worker.start()
            worker.enqueue(trace)
            await worker.stop()

            rows = log_path.read_text(encoding="utf-8").strip().splitlines()

            self.assertEqual(len(rows), 1)
            payload = json.loads(rows[0])
            self.assertEqual(payload["reply_id"], "reply-3")
            self.assertEqual(payload["session_id"], "session-3")
            self.assertFalse(payload["streaming"])
            self.assertEqual(payload["segment_count"], 2)
            self.assertEqual(payload["metrics"]["avatar_phase_thinking_ms"], 15)


class LifespanTraceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_starts_and_stops_trace_worker_without_skipping_existing_startup(self) -> None:
        main_module = import_main_for_lifespan_tests()
        lifespan = main_module.lifespan

        events: list[str] = []

        class FakeTraceService:
            async def start(self) -> None:
                events.append("trace_start")

            async def stop(self) -> None:
                events.append("trace_stop")

        class FakeReportService:
            async def start(self) -> None:
                events.append("report_start")

            async def stop(self) -> None:
                events.append("report_stop")

        class FakeTTSService:
            def warmup(self) -> None:
                events.append("tts_warmup")

        class FakeASRService:
            async def warmup(self) -> None:
                events.append("asr_warmup")

        async def fake_init_db() -> None:
            events.append("init_db")

        async def fake_seed() -> None:
            events.append("seed")

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        async def fake_shutdown_db() -> None:
            events.append("shutdown_db")

        with (
            patch("app.main.init_db", side_effect=fake_init_db),
            patch("app.main.ensure_default_avatar_config", side_effect=fake_seed),
            patch("app.main.ensure_default_voice_profile", side_effect=fake_seed),
            patch("app.main.get_tts_service", return_value=FakeTTSService()),
            patch("app.main.get_asr_service", return_value=FakeASRService()),
            patch("app.main.asyncio.to_thread", side_effect=fake_to_thread),
            patch("app.main.get_avatar_trace_service", return_value=FakeTraceService()),
            patch("app.main.get_report_service", return_value=FakeReportService()),
            patch("app.main.shutdown_db", side_effect=fake_shutdown_db),
        ):
            async with lifespan(SimpleNamespace()):
                events.append("inside")

        self.assertEqual(
            events,
            [
                "init_db",
                "seed",
                "seed",
                "tts_warmup",
                "asr_warmup",
                "trace_start",
                "report_start",
                "inside",
                "report_stop",
                "trace_stop",
                "shutdown_db",
            ],
        )

    async def test_lifespan_re_raises_fatal_tts_runtime_errors(self) -> None:
        main_module = import_main_for_lifespan_tests()
        lifespan = main_module.lifespan

        events: list[str] = []

        class FakeTraceService:
            async def start(self) -> None:
                events.append("trace_start")

            async def stop(self) -> None:
                events.append("trace_stop")

        class FakeReportService:
            async def start(self) -> None:
                events.append("report_start")

            async def stop(self) -> None:
                events.append("report_stop")

        class FatalTTSService:
            def warmup(self) -> None:
                raise TTSRuntimeValidationError("missing CUDAExecutionProvider")

        class FakeASRService:
            async def warmup(self) -> None:
                events.append("asr_warmup")

        async def fake_init_db() -> None:
            events.append("init_db")

        async def fake_seed() -> None:
            events.append("seed")

        async def fake_shutdown_db() -> None:
            events.append("shutdown_db")

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("app.main.init_db", side_effect=fake_init_db),
            patch("app.main.ensure_default_avatar_config", side_effect=fake_seed),
            patch("app.main.ensure_default_voice_profile", side_effect=fake_seed),
            patch("app.main.get_tts_service", return_value=FatalTTSService()),
            patch("app.main.get_asr_service", return_value=FakeASRService()),
            patch("app.main.asyncio.to_thread", side_effect=fake_to_thread),
            patch("app.main.get_avatar_trace_service", return_value=FakeTraceService()),
            patch("app.main.get_report_service", return_value=FakeReportService()),
            patch("app.main.shutdown_db", side_effect=fake_shutdown_db),
        ):
            with self.assertRaises(TTSRuntimeValidationError):
                async with lifespan(SimpleNamespace()):
                    pass

        self.assertEqual(events, ["init_db", "seed", "seed", "report_stop", "trace_stop", "shutdown_db"])


if __name__ == "__main__":
    unittest.main()
