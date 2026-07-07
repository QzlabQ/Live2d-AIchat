import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.avatar_trace import ReplyTrace, TraceLoggerWorker


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
        from app.main import lifespan

        events: list[str] = []

        class FakeTraceService:
            async def start(self) -> None:
                events.append("trace_start")

            async def stop(self) -> None:
                events.append("trace_stop")

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
            patch("app.main.get_tts_service", return_value=FakeTTSService()),
            patch("app.main.get_asr_service", return_value=FakeASRService()),
            patch("app.main.asyncio.to_thread", side_effect=fake_to_thread),
            patch("app.main.get_avatar_trace_service", return_value=FakeTraceService()),
            patch("app.main.shutdown_db", side_effect=fake_shutdown_db),
        ):
            async with lifespan(SimpleNamespace()):
                events.append("inside")

        self.assertEqual(
            events,
            [
                "init_db",
                "seed",
                "tts_warmup",
                "asr_warmup",
                "trace_start",
                "inside",
                "trace_stop",
                "shutdown_db",
            ],
        )


if __name__ == "__main__":
    unittest.main()
