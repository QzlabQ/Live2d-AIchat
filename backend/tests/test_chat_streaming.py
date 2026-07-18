import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.ws_router import (
    ClientCapabilities,
    process_audio_buffer,
    process_text_message,
    stream_assistant_reply,
)
from app.core.config import Settings
from app.services.asr import ASRTranscriptionResult
from app.services.chat import RAGGuideChatService, ReplyStreamEvent, TTSSegmenter
from app.services.emotion import EmotionAnalysis
from app.services.rag import PreparedRAGAnswer
from app.services.tts import StreamingTTSChunk
from app.services.vision import VisitorVisionResult


class FakeTraceService:
    def __init__(self) -> None:
        self.enqueued_payloads: list[dict[str, object]] = []

    def enqueue_trace(self, trace) -> None:
        self.enqueued_payloads.append(trace.to_payload())


class TTSSegmenterTestCase(unittest.TestCase):
    def test_waits_for_strong_boundary_when_it_is_within_hard_limit(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        text = "先介绍夜游开放时间，再补充灯光路线。最后说明游客拍照注意事项。"

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(segments[0].endswith("。"))
        self.assertIn("灯光路线。", segments[0])

    def test_does_not_hard_split_long_sentence_every_24_chars(self) -> None:
        segmenter = TTSSegmenter()
        text = (
            "来到灵山胜境之后可以先沿着主游览线慢慢参观大佛和梵宫，"
            "再去九龙灌浴和五印坛城，最后根据时间安排自由活动。"
        )

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertGreater(len(segments[0]), 24)
        self.assertTrue(segments[0].endswith("，"))

    def test_prefers_soft_boundary_before_forced_limit(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=16, soft_max_chars=24, hard_max_chars=32)
        text = "这是第一段介绍景区整体风貌，接着说明核心景点分布，最后补充参观建议和注意事项"

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(segments[0].endswith("，"))
        self.assertLessEqual(len(segments[0]), 25)

    def test_hard_limit_still_applies_when_entire_reply_arrives_in_one_piece(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        text = (
            '唐贞观年间，玄奘法师西行取经归来，携大乘佛法东传，途经马山时，见此地"层峦丛翠，'
            '曲水净秀，山形酷似印度灵鹫山"，顿觉此地与佛法渊源深厚，遂将所译《大般若经》中的'
            '"灵鹫胜境"之名赐予此地，命名为"小灵山"，并嘱咐大弟子窥基法师在此住持道场，'
            '兴建小灵山庵，奠定了此地的佛教根基。灵山胜境坐落于江苏省无锡市太湖西北部的马山镇，'
            '地处秦履峰、青龙山、白虎山三山环抱之间，占地面积约30万平方米，是国家5A级旅游景区、'
            '世界佛教论坛永久会址，被誉为"东方佛国"和"太湖佛国"。'
        )

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreater(len(segments), 2)
        self.assertTrue(all(len(segment) <= 28 for segment in segments))

    def test_flush_keeps_hard_splitting_overlong_tail(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        text = "甲" * 65
        segmenter.buffer = text

        segments = segmenter.flush()

        self.assertEqual("".join(segments), text)
        self.assertEqual([len(segment) for segment in segments], [28, 28, 9])

    def test_v100_segmenter_merges_short_sentence_into_later_strong_boundary(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=24, soft_max_chars=56, hard_max_chars=96)
        first = "如果你是第一次来，建议优先走核心景点主线。"
        second = "路线规划：南门入园→佛足坛→九龙灌浴观赏表演→菩提大道欣赏太湖风光→灵山大佛登顶俯瞰全景→曼飞龙塔园林景观→灵山。"

        segments = segmenter.feed(first)
        segments.extend(segmenter.feed(second))
        segments.extend(segmenter.flush())

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0], first + second)

    def test_v100_segment_thresholds_reduce_segment_count_for_long_reply(self) -> None:
        sentence_pieces = [
            "如果你是第一次来，建议优先走核心景点主线。",
            "路线规划：南门入园→佛足坛→九龙灌浴观赏表演→菩提大道欣赏太湖风光→灵山大佛登顶俯瞰全景→曼飞龙塔园林景观→灵山。",
            "精舍禅意园林→梵宫广场→出口。",
            "如果你偏亲子、夜游或半日游，我可以再帮你细化路线。",
        ]

        default_segments = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        v100_segments = TTSSegmenter(soft_min_chars=24, soft_max_chars=56, hard_max_chars=96)

        baseline: list[str] = []
        optimized: list[str] = []
        for piece in sentence_pieces:
            baseline.extend(default_segments.feed(piece))
            optimized.extend(v100_segments.feed(piece))
        baseline.extend(default_segments.flush())
        optimized.extend(v100_segments.flush())

        self.assertEqual(len(baseline), 5)
        self.assertEqual(len(optimized), 2)
        self.assertLess(len(optimized), len(baseline))


class StreamAssistantReplyTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_capability_uses_new_tts_protocol(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            settings = SimpleNamespace(chat_mode="rag")

            async def stream_reply(
                self,
                user_text: str,
                persona: str | None = None,
                response_language: str | None = None,
                *,
                query_text: str | None = None,
                history: list[dict[str, str]] | None = None,
            ):
                yield ReplyStreamEvent(
                    kind="metrics",
                    metrics={
                        "rag_retrieve_ms": 12,
                        "rag_rerank_ms": 7,
                        "rag_decision_llm_ms": 34,
                        "rag_prepare_total_ms": 60,
                    },
                )
                yield ReplyStreamEvent(kind="text_delta", content="Hello there.")
                yield ReplyStreamEvent(kind="tts_segment", content="Hello there.")
                yield ReplyStreamEvent(
                    kind="final",
                    text="Hello there. Ask me anything else.",
                    spoken_text="Hello there. Ask me anything else.",
                    sources=[
                        SimpleNamespace(
                            filename="guide.docx",
                            title="Opening hours",
                            category="schedule",
                            chunk_index=0,
                            retrieval_score=0.88,
                            rerank_score=0.91,
                            text="Open daily from 09:00 to 21:00.",
                        )
                    ],
                    mode="rag",
                    confidence=0.91,
                    reply_kind="answer",
                    needs_followup=True,
                    missing_slots=["target_scope"],
                    confidence_note="partial",
                )

            async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
                return EmotionAnalysis(
                    label="thinking",
                    confidence=0.88,
                    keywords=["history"],
                    reason="final emotion",
                    source="llm",
                )

        class FakeTTSService:
            settings = SimpleNamespace(tts_engine="cosyvoice")

            def get_runtime_trace_snapshot(self) -> dict[str, object]:
                return {"tts_synthesis_strategy": "per_segment"}

            async def stream_synthesize_segment(self, *args, **kwargs):
                yield StreamingTTSChunk(
                    seq=0,
                    chunk_index=0,
                    text="Hello there.",
                    audio_bytes=b"\x01\x02" * 2400,
                    phonemes=[{"ph": "a", "start": 0.0, "end": 0.1, "openY": 0.8, "form": 0.0}],
                    offset_ms=0,
                    sample_rate=24000,
                    channels=1,
                    encoding="pcm16le",
                    is_final=True,
                )

        websocket = FakeWebSocket()
        avatar = SimpleNamespace(
            persona="guide",
            response_language="en",
            voice_id="voice",
            tts_reference_audio_path="prompt.wav",
            tts_reference_text="prompt text",
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )
        trace_service = FakeTraceService()

        with patch("app.api.ws_router.get_avatar_trace_service", return_value=trace_service):
            result = await stream_assistant_reply(
                websocket=websocket,
                session_id="session-1",
                avatar=avatar,
                content="Introduce this place.",
                query_text="Introduce this place.",
                history=[{"role": "user", "content": "Introduce this place."}],
                chat_service=FakeChatService(),
                tts_service=FakeTTSService(),
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                reply_id="reply-1",
                locked_emotion="happy",
                emotion_payload={
                    "type": "emotion",
                    "stage": "preview",
                    "value": "happy",
                    "confidence": 0.7,
                    "keywords": [],
                    "reason": "quick",
                    "source": "heuristic",
                },
                initial_metrics={
                    "asr_model_load_ms": 84,
                    "asr_transcribe_ms": 146,
                    "asr_total_ms": 230,
                },
                started_at=0.0,
            )

        message_types = [item["type"] for item in websocket.messages]
        emotion_messages = [item for item in websocket.messages if item["type"] == "emotion"]
        phase_messages = [item for item in websocket.messages if item["type"] == "avatar_phase"]
        reply_meta = next(item for item in websocket.messages if item["type"] == "reply_meta")
        sources_message = next(item for item in websocket.messages if item["type"] == "sources")
        trace_payload = trace_service.enqueued_payloads[0]

        self.assertIn("tts_audio_chunk", message_types)
        self.assertIn("tts_viseme_chunk", message_types)
        self.assertIn("reply_meta", message_types)
        self.assertIn("text_done", message_types)
        self.assertIn("audio_done", message_types)
        self.assertEqual(
            [item["phase"] for item in phase_messages],
            ["thinking", "speaking", "cooldown", "idle"],
        )
        self.assertEqual(len(emotion_messages), 2)
        self.assertEqual(emotion_messages[0]["stage"], "preview")
        self.assertEqual(emotion_messages[0]["value"], "happy")
        self.assertEqual(emotion_messages[1]["stage"], "final")
        self.assertEqual(emotion_messages[1]["value"], "thinking")
        self.assertEqual(reply_meta["reply_kind"], "answer")
        self.assertTrue(reply_meta["needs_followup"])
        self.assertEqual(reply_meta["missing_slots"], ["target_scope"])
        self.assertEqual(sources_message["reply_id"], "reply-1")
        self.assertEqual(
            sources_message["items"][0]["excerpt"],
            "Open daily from 09:00 to 21:00.",
        )
        self.assertEqual(result.text, "Hello there. Ask me anything else.")
        self.assertEqual(result.mode, "rag")
        self.assertEqual(result.emotion.label, "thinking")
        self.assertEqual(len(trace_service.enqueued_payloads), 1)
        self.assertEqual(trace_payload["reply_id"], "reply-1")
        self.assertEqual(trace_payload["chat_mode"], "rag")
        self.assertEqual(trace_payload["tts_engine"], "cosyvoice")
        self.assertTrue(trace_payload["streaming"])
        self.assertEqual(trace_payload["tts_synthesis_strategy"], "per_segment")
        self.assertEqual(trace_payload["tts_vendor_session_count"], 1)
        self.assertEqual(trace_payload["segment_count"], 1)
        self.assertEqual(trace_payload["audio_chunk_count"], 1)
        self.assertIn("llm_stream_start_ms", trace_payload["metrics"])
        self.assertIn("llm_first_delta_ms", trace_payload["metrics"])
        self.assertEqual(trace_payload["metrics"]["asr_model_load_ms"], 84)
        self.assertEqual(trace_payload["metrics"]["asr_transcribe_ms"], 146)
        self.assertEqual(trace_payload["metrics"]["asr_total_ms"], 230)
        self.assertEqual(trace_payload["metrics"]["rag_retrieve_ms"], 12)
        self.assertEqual(trace_payload["metrics"]["rag_rerank_ms"], 7)
        self.assertEqual(trace_payload["metrics"]["rag_decision_llm_ms"], 34)
        self.assertEqual(trace_payload["metrics"]["rag_prepare_total_ms"], 60)
        self.assertIn("tts_first_segment_ms", trace_payload["metrics"])
        self.assertIn("tts_first_audio_chunk_ms", trace_payload["metrics"])
        self.assertEqual(trace_payload["tts_chunks"][0]["tts_chunk_audio_ms"], 100)
        self.assertIn("tts_ws_send_lag_ms", trace_payload["tts_chunks"][0])
        self.assertIn("text_done_ms", trace_payload["metrics"])
        self.assertIn("audio_done_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_thinking_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_speaking_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_cooldown_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_idle_ms", trace_payload["metrics"])

    async def test_streaming_capability_prefers_reply_streaming_api_with_per_segment_tts(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            settings = SimpleNamespace(chat_mode="rag")

            async def stream_reply(self, *args, **kwargs):
                yield ReplyStreamEvent(kind="text_delta", content="Hello")
                yield ReplyStreamEvent(kind="tts_segment", content="Hello")
                yield ReplyStreamEvent(kind="text_delta", content=" there.")
                yield ReplyStreamEvent(kind="tts_segment", content="there.")
                yield ReplyStreamEvent(
                    kind="final",
                    text="Hello there.",
                    spoken_text="Hello there.",
                    mode="rag",
                    confidence=0.9,
                )

            async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
                return EmotionAnalysis(
                    label="happy",
                    confidence=0.8,
                    keywords=["hello"],
                    reason="final emotion",
                    source="llm",
                )

        class FakeTTSService:
            settings = SimpleNamespace(tts_engine="cosyvoice")
            supports_reply_streaming = True

            def __init__(self) -> None:
                self.segments: list[tuple[int, str]] = []

            def get_runtime_trace_snapshot(self) -> dict[str, object]:
                return {"tts_synthesis_strategy": "per_segment"}

            async def stream_synthesize_reply(self, segments, **kwargs):
                async for seq, text in segments:
                    self.segments.append((seq, text))
                    yield StreamingTTSChunk(
                        seq=seq,
                        chunk_index=0,
                        text=text,
                        audio_bytes=b"\x01\x02",
                        phonemes=[],
                        offset_ms=0,
                        sample_rate=24000,
                        channels=1,
                        encoding="pcm16le",
                        is_final=seq == 1,
                    )

            async def stream_synthesize_segment(self, *args, **kwargs):
                raise AssertionError("reply streaming API should be preferred")

        websocket = FakeWebSocket()
        trace_service = FakeTraceService()
        tts_service = FakeTTSService()

        with patch("app.api.ws_router.get_avatar_trace_service", return_value=trace_service):
            await stream_assistant_reply(
                websocket=websocket,
                session_id="session-reply",
                avatar=SimpleNamespace(
                    persona="guide",
                    response_language="en",
                    voice_id="voice",
                    tts_reference_audio_path="prompt.wav",
                    tts_reference_text="prompt text",
                    tts_speed=1.0,
                    tts_emotion_enabled=True,
                ),
                content="Say hello.",
                query_text="Say hello.",
                history=[],
                chat_service=FakeChatService(),
                tts_service=tts_service,
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                reply_id="reply-reply",
                locked_emotion="happy",
                emotion_payload={
                    "type": "emotion",
                    "stage": "preview",
                    "value": "happy",
                    "confidence": 0.7,
                    "keywords": [],
                    "reason": "quick",
                    "source": "heuristic",
                },
                started_at=0.0,
            )

        audio_chunks = [item for item in websocket.messages if item["type"] == "tts_audio_chunk"]
        self.assertEqual(tts_service.segments, [(0, "Hello"), (1, "there.")])
        self.assertEqual([item["segment_id"] for item in audio_chunks], [0, 1])
        self.assertEqual([item["chunk_index"] for item in audio_chunks], [0, 0])
        self.assertIn("audio_done", [item["type"] for item in websocket.messages])
        self.assertEqual(trace_service.enqueued_payloads[0]["segment_count"], 2)
        self.assertEqual(trace_service.enqueued_payloads[0]["tts_synthesis_strategy"], "per_segment")
        self.assertEqual(trace_service.enqueued_payloads[0]["tts_vendor_session_count"], 2)

    async def test_streaming_without_audio_falls_back_to_cooldown_and_idle(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            settings = SimpleNamespace(chat_mode="template")

            async def stream_reply(
                self,
                user_text: str,
                persona: str | None = None,
                response_language: str | None = None,
                *,
                query_text: str | None = None,
                history: list[dict[str, str]] | None = None,
            ):
                yield ReplyStreamEvent(kind="text_delta", content="No audio.")
                yield ReplyStreamEvent(
                    kind="final",
                    text="No audio available.",
                    spoken_text="No audio available.",
                )

            async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
                return EmotionAnalysis(
                    label="neutral",
                    confidence=0.66,
                    keywords=["audio"],
                    reason="no audio",
                    source="llm",
                )

        class FakeTTSService:
            settings = SimpleNamespace(tts_engine="cosyvoice")

            async def stream_synthesize_segment(self, *args, **kwargs):
                if False:
                    yield None

        websocket = FakeWebSocket()
        trace_service = FakeTraceService()

        with patch("app.api.ws_router.get_avatar_trace_service", return_value=trace_service):
            await stream_assistant_reply(
                websocket=websocket,
                session_id="session-2",
                avatar=SimpleNamespace(
                    persona="guide",
                    response_language="zh",
                    voice_id="voice",
                    tts_reference_audio_path="prompt.wav",
                    tts_reference_text="prompt text",
                    tts_speed=1.0,
                    tts_emotion_enabled=True,
                ),
                content="Finish cleanly without audio.",
                query_text="Finish cleanly without audio.",
                history=[],
                chat_service=FakeChatService(),
                tts_service=FakeTTSService(),
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                reply_id="reply-2",
                locked_emotion="neutral",
                emotion_payload={
                    "type": "emotion",
                    "stage": "preview",
                    "value": "neutral",
                    "confidence": 0.6,
                    "keywords": [],
                    "reason": "quick",
                    "source": "heuristic",
                },
                started_at=0.0,
            )

        phase_messages = [item for item in websocket.messages if item["type"] == "avatar_phase"]
        phase_metric_names = [
            name
            for name in trace_service.enqueued_payloads[0]["metrics"]
            if name.startswith("avatar_phase_")
        ]

        self.assertEqual(
            [item["phase"] for item in phase_messages],
            ["thinking", "cooldown", "idle"],
        )
        self.assertNotIn("speaking", [item["phase"] for item in phase_messages])
        self.assertIn("audio_done", [item["type"] for item in websocket.messages])
        self.assertEqual(
            phase_metric_names,
            ["avatar_phase_thinking_ms", "avatar_phase_cooldown_ms", "avatar_phase_idle_ms"],
        )
        self.assertEqual(trace_service.enqueued_payloads[0]["audio_chunk_count"], 0)
        self.assertIn("llm_first_delta_ms", trace_service.enqueued_payloads[0]["metrics"])
        self.assertIn("text_done_ms", trace_service.enqueued_payloads[0]["metrics"])
        self.assertIn("audio_done_ms", trace_service.enqueued_payloads[0]["metrics"])
        self.assertNotIn("tts_first_audio_chunk_ms", trace_service.enqueued_payloads[0]["metrics"])

    async def test_streaming_audio_metric_ignores_empty_chunks(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            settings = SimpleNamespace(chat_mode="rag")

            async def stream_reply(self, *args, **kwargs):
                yield ReplyStreamEvent(kind="text_delta", content="Chunked audio.")
                yield ReplyStreamEvent(kind="tts_segment", content="Chunked audio.")
                yield ReplyStreamEvent(kind="final", text="Chunked audio.", spoken_text="Chunked audio.")

            async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
                return EmotionAnalysis(
                    label="neutral",
                    confidence=0.5,
                    keywords=[],
                    reason="final emotion",
                    source="llm",
                )

        class FakeTTSService:
            settings = SimpleNamespace(tts_engine="cosyvoice")

            async def stream_synthesize_segment(self, *args, **kwargs):
                yield StreamingTTSChunk(
                    seq=0,
                    chunk_index=0,
                    text="Chunked audio.",
                    audio_bytes=b"",
                    phonemes=[],
                    offset_ms=0,
                    sample_rate=24000,
                    channels=1,
                    encoding="pcm16le",
                    is_final=False,
                )
                await asyncio.sleep(0.01)
                yield StreamingTTSChunk(
                    seq=0,
                    chunk_index=1,
                    text="Chunked audio.",
                    audio_bytes=b"\x01\x02",
                    phonemes=[],
                    offset_ms=20,
                    sample_rate=24000,
                    channels=1,
                    encoding="pcm16le",
                    is_final=True,
                )

        websocket = FakeWebSocket()
        trace_service = FakeTraceService()

        with patch("app.api.ws_router.get_avatar_trace_service", return_value=trace_service):
            await stream_assistant_reply(
                websocket=websocket,
                session_id="session-3",
                avatar=SimpleNamespace(
                    persona="guide",
                    response_language="zh",
                    voice_id="voice",
                    tts_reference_audio_path="prompt.wav",
                    tts_reference_text="prompt text",
                    tts_speed=1.0,
                    tts_emotion_enabled=True,
                ),
                content="Chunked audio.",
                query_text="Chunked audio.",
                history=[],
                chat_service=FakeChatService(),
                tts_service=FakeTTSService(),
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                reply_id="reply-3",
                locked_emotion="neutral",
                emotion_payload={
                    "type": "emotion",
                    "stage": "preview",
                    "value": "neutral",
                    "confidence": 0.5,
                    "keywords": [],
                    "reason": "quick",
                    "source": "heuristic",
                },
                started_at=0.0,
            )

        phase_messages = [item for item in websocket.messages if item["type"] == "avatar_phase"]
        self.assertEqual(
            [item["phase"] for item in phase_messages],
            ["thinking", "speaking", "cooldown", "idle"],
        )
        self.assertEqual(trace_service.enqueued_payloads[0]["audio_chunk_count"], 1)
        self.assertIn("tts_first_audio_chunk_ms", trace_service.enqueued_payloads[0]["metrics"])
        self.assertLessEqual(
            trace_service.enqueued_payloads[0]["metrics"]["tts_first_audio_chunk_ms"],
            trace_service.enqueued_payloads[0]["metrics"]["avatar_phase_speaking_ms"],
        )

    async def test_trace_is_enqueued_even_when_streaming_reply_fails(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            settings = SimpleNamespace(chat_mode="rag")

            async def stream_reply(self, *args, **kwargs):
                yield ReplyStreamEvent(kind="text_delta", content="Before failure.")
                yield ReplyStreamEvent(kind="tts_segment", content="Before failure.")
                yield ReplyStreamEvent(kind="final", text="Before failure.", spoken_text="Before failure.")

            async def analyze_emotion(self, user_text: str, reply_text: str) -> EmotionAnalysis:
                return EmotionAnalysis(
                    label="neutral",
                    confidence=0.5,
                    keywords=[],
                    reason="final emotion",
                    source="llm",
                )

        class FailingTTSService:
            settings = SimpleNamespace(tts_engine="cosyvoice")

            async def stream_synthesize_segment(self, *args, **kwargs):
                raise RuntimeError("tts failed")
                yield  # pragma: no cover

        websocket = FakeWebSocket()
        trace_service = FakeTraceService()

        with (
            patch("app.api.ws_router.get_avatar_trace_service", return_value=trace_service),
            self.assertRaises(RuntimeError),
        ):
            await stream_assistant_reply(
                websocket=websocket,
                session_id="session-4",
                avatar=SimpleNamespace(
                    persona="guide",
                    response_language="zh",
                    voice_id="voice",
                    tts_reference_audio_path="prompt.wav",
                    tts_reference_text="prompt text",
                    tts_speed=1.0,
                    tts_emotion_enabled=True,
                ),
                content="This one fails.",
                query_text="This one fails.",
                history=[],
                chat_service=FakeChatService(),
                tts_service=FailingTTSService(),
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                reply_id="reply-4",
                locked_emotion="neutral",
                emotion_payload={
                    "type": "emotion",
                    "stage": "preview",
                    "value": "neutral",
                    "confidence": 0.5,
                    "keywords": [],
                    "reason": "quick",
                    "source": "heuristic",
                },
                started_at=0.0,
            )

        self.assertEqual(len(trace_service.enqueued_payloads), 1)
        self.assertEqual(trace_service.enqueued_payloads[0]["reply_id"], "reply-4")
        self.assertIn("avatar_phase_thinking_ms", trace_service.enqueued_payloads[0]["metrics"])


class ProcessAudioBufferTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_process_audio_buffer_passes_asr_metrics_into_text_pipeline(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        websocket = FakeWebSocket()
        captured: dict[str, object] = {}
        fake_asr_service = SimpleNamespace(
            transcribe_with_metrics=AsyncMock(
                return_value=ASRTranscriptionResult(
                    text="语音识别结果",
                    model_load_ms=612,
                    asr_transcribe_ms=288,
                    asr_total_ms=900,
                )
            )
        )

        async def fake_process_text_message(
            websocket,
            db_session,
            session_id: str,
            content: str,
            capabilities: ClientCapabilities,
            *,
            started_at: float | None = None,
            initial_metrics: dict[str, int] | None = None,
            send_lock: asyncio.Lock | None = None,
        ) -> None:
            captured["session_id"] = session_id
            captured["content"] = content
            captured["started_at"] = started_at
            captured["initial_metrics"] = initial_metrics

        with (
            patch("app.api.ws_router.get_asr_service", return_value=fake_asr_service),
            patch("app.api.ws_router.process_text_message", side_effect=fake_process_text_message),
        ):
            await process_audio_buffer(
                websocket=websocket,
                db_session=object(),
                session_id="session-audio",
                audio_data=b"\x01\x00\x02\x00",
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
            )

        self.assertEqual(websocket.messages, [{"type": "asr_result", "content": "语音识别结果"}])
        self.assertEqual(captured["session_id"], "session-audio")
        self.assertEqual(captured["content"], "语音识别结果")
        self.assertIsNotNone(captured["started_at"])
        self.assertEqual(
            captured["initial_metrics"],
            {
                "asr_model_load_ms": 612,
                "asr_transcribe_ms": 288,
                "asr_total_ms": 900,
            },
        )


class RAGGuideChatServiceFallbackTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_stream_reply_prefers_llm_stream_deltas_when_llm_messages_exist(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode="rag"))
        prepared = PreparedRAGAnswer(
            answer_text="",
            spoken_text="",
            sources=[],
            confidence=0.74,
            used_llm=True,
            llm_messages=[{"role": "user", "content": "open time?"}],
            fallback_text="fallback answer from retrieval.",
        )
        captured_messages: list[list[dict[str, str]]] = []

        async def fake_stream_complete(messages: list[dict[str, str]]):
            captured_messages.append(messages)
            for chunk in ("streamed answer", " with detail."):
                yield chunk

        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=self._async_return(prepared),
            llm=SimpleNamespace(stream_complete=fake_stream_complete),
        )

        with patch("app.services.chat.get_rag_service", return_value=fake_rag_service):
            events = [event async for event in service.stream_reply("open time?", persona="guide")]

        text_deltas = [event.content for event in events if event.kind == "text_delta"]
        tts_segments = [event.content for event in events if event.kind == "tts_segment"]
        finals = [event for event in events if event.kind == "final"]

        self.assertEqual(len(captured_messages), 1)
        self.assertTrue(text_deltas)
        self.assertTrue(tts_segments)
        self.assertEqual("".join(text_deltas), "streamed answer with detail.")
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, "streamed answer with detail.")

    async def test_stream_reply_falls_back_after_llm_stream_error(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode="rag"))
        prepared = PreparedRAGAnswer(
            answer_text="",
            spoken_text="",
            sources=[],
            confidence=0.62,
            used_llm=True,
            llm_messages=[{"role": "user", "content": "open time?"}],
            fallback_text="fallback answer from retrieval.",
        )
        stream_attempts: list[list[dict[str, str]]] = []

        async def failing_stream_complete(messages: list[dict[str, str]]):
            stream_attempts.append(messages)
            raise RuntimeError("stream failed")
            yield  # pragma: no cover

        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=self._async_return(prepared),
            llm=SimpleNamespace(stream_complete=failing_stream_complete),
        )

        with patch("app.services.chat.get_rag_service", return_value=fake_rag_service):
            events = [event async for event in service.stream_reply("open time?", persona="guide")]

        text_deltas = [event.content for event in events if event.kind == "text_delta"]
        finals = [event for event in events if event.kind == "final"]

        self.assertEqual(len(stream_attempts), 1)
        self.assertTrue(text_deltas)
        self.assertEqual("".join(text_deltas), "fallback answer from retrieval.")
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, "fallback answer from retrieval.")

    async def test_stream_reply_keeps_partial_stream_when_failure_happens_after_visible_output(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode="rag"))
        streamed_prefix = "streamed answer already visible."
        prepared = PreparedRAGAnswer(
            answer_text="",
            spoken_text="",
            sources=[],
            confidence=0.65,
            used_llm=True,
            llm_messages=[{"role": "user", "content": "open time?"}],
            fallback_text="fallback answer from retrieval.",
        )

        async def partially_failing_stream(messages: list[dict[str, str]]):
            del messages
            yield streamed_prefix
            raise RuntimeError("stream failed after visible output")
            yield  # pragma: no cover

        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=self._async_return(prepared),
            llm=SimpleNamespace(stream_complete=partially_failing_stream),
        )

        with patch("app.services.chat.get_rag_service", return_value=fake_rag_service):
            events = [event async for event in service.stream_reply("open time?", persona="guide")]

        event_kinds = [event.kind for event in events]
        text_deltas = [event.content for event in events if event.kind == "text_delta"]
        finals = [event for event in events if event.kind == "final"]

        self.assertIn("text_delta", event_kinds)
        self.assertEqual(event_kinds[-1], "final")
        self.assertTrue(text_deltas)
        self.assertNotIn("fallback answer", "".join(text_deltas))
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, streamed_prefix)
        self.assertNotIn("fallback answer", finals[0].text)

    async def test_stream_reply_uses_fallback_text_when_llm_stream_fails(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode="rag"))
        prepared = PreparedRAGAnswer(
            answer_text="",
            spoken_text="",
            sources=[],
            confidence=0.62,
            used_llm=True,
            fallback_text="fallback answer from retrieval.",
        )
        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=self._async_return(prepared),
        )

        with patch("app.services.chat.get_rag_service", return_value=fake_rag_service):
            events = [event async for event in service.stream_reply("open time?", persona="guide")]

        text_deltas = [event.content for event in events if event.kind == "text_delta"]
        finals = [event for event in events if event.kind == "final"]

        self.assertTrue(text_deltas)
        self.assertEqual("".join(text_deltas), "fallback answer from retrieval.")
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, "fallback answer from retrieval.")

    async def test_stream_reply_passes_photo_context_to_rag_service(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode="rag"))
        prepared = PreparedRAGAnswer(
            answer_text="这是五印坛城。",
            spoken_text="这是五印坛城。",
            sources=[],
            confidence=0.92,
            used_llm=False,
        )
        prepare_stream_answer = AsyncMock(return_value=prepared)
        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=prepare_stream_answer,
        )
        photo_context = {
            "recognized_spot": "五印坛城",
            "recognition_summary": "图片主体是一座白色藏式佛塔。",
            "recognized_spot_canonical": True,
        }

        with patch("app.services.chat.get_rag_service", return_value=fake_rag_service):
            events = [
                event
                async for event in service.stream_reply(
                    "这是哪个景点？",
                    persona="guide",
                    photo_context=photo_context,
                )
            ]

        prepare_stream_answer.assert_awaited_once_with(
            "这是哪个景点？",
            persona="guide",
            history=[],
            response_language=None,
            photo_context=photo_context,
        )
        finals = [event for event in events if event.kind == "final"]
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, "这是五印坛城。")

    @staticmethod
    def _async_return(value):
        async def _inner(*args, **kwargs):
            return value

        return _inner


class ProcessTextMessageTestCase(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _advancing_perf_counter(start: float = 100.0, step: float = 0.01):
        current = start

        def _fake_perf_counter() -> float:
            nonlocal current
            current += step
            return current

        return _fake_perf_counter

    async def test_cancelled_reply_does_not_persist_user_or_assistant_messages(self) -> None:
        avatar = SimpleNamespace(
            persona="guide",
            response_language="zh",
            voice_id="voice",
            tts_reference_audio_path="prompt.wav",
            tts_reference_text="prompt text",
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )
        quick_emotion = EmotionAnalysis(
            label="thinking",
            confidence=0.72,
            keywords=["首次来访"],
            reason="quick emotion",
            source="heuristic",
        )
        save_message_mock = AsyncMock()

        with (
            patch("app.api.ws_router.get_chat_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_tts_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_avatar_config", AsyncMock(return_value=avatar)),
            patch("app.api.ws_router.load_recent_history", AsyncMock(return_value=[])),
            patch("app.api.ws_router.get_active_clarification_state", AsyncMock(return_value=None)),
            patch(
                "app.api.ws_router.get_emotion_analyzer",
                return_value=SimpleNamespace(analyze_quick=lambda user_text: quick_emotion),
            ),
            patch(
                "app.api.ws_router.stream_assistant_reply",
                AsyncMock(side_effect=asyncio.CancelledError()),
            ),
            patch("app.api.ws_router.save_message", save_message_mock),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await process_text_message(
                    websocket=SimpleNamespace(),
                    db_session=SimpleNamespace(),
                    session_id="session-1",
                    content="这轮先取消",
                    capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                    send_lock=asyncio.Lock(),
                )

        save_message_mock.assert_not_awaited()

    async def test_photo_attachment_is_recognized_inside_chat_mainline(self) -> None:
        avatar = SimpleNamespace(
            persona="guide",
            response_language="zh",
            voice_id="voice",
            tts_reference_audio_path="prompt.wav",
            tts_reference_text="prompt text",
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )
        quick_emotion = EmotionAnalysis(
            label="thinking",
            confidence=0.72,
            keywords=["景点照片"],
            reason="quick emotion",
            source="heuristic",
        )
        save_message_mock = AsyncMock(
            side_effect=[
                SimpleNamespace(id=101),
                SimpleNamespace(id=102),
            ]
        )
        stream_result = SimpleNamespace(
            text="这张图片看起来像灵山大佛。",
            sources=[],
            confidence=0.88,
            mode="rag",
            emotion=None,
            metrics={},
            reply_kind="answer",
            needs_followup=False,
            followup_question="",
            missing_slots=[],
            confidence_note="confirmed",
        )
        vision_service = SimpleNamespace(
            recognize_stored_photo=AsyncMock(
                return_value=VisitorVisionResult(
                    recognized_spot="灵山大佛",
                    recognition_summary="画面主体是一尊高大的金色佛像，周围是开阔广场。",
                    resolved_question="这张图里的灵山大佛有什么看点？",
                    stored_image_path="session-1/photo.jpg",
                )
            )
        )

        with (
            patch("app.api.ws_router.get_chat_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_tts_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_avatar_config", AsyncMock(return_value=avatar)),
            patch("app.api.ws_router.load_recent_history", AsyncMock(return_value=[])),
            patch("app.api.ws_router.get_active_clarification_state", AsyncMock(return_value=None)),
            patch(
                "app.api.ws_router.get_emotion_analyzer",
                return_value=SimpleNamespace(analyze_quick=lambda user_text: quick_emotion),
            ),
            patch("app.api.ws_router.get_visitor_vision_service", return_value=vision_service),
            patch("app.api.ws_router.stream_assistant_reply", AsyncMock(return_value=stream_result)) as stream_reply_mock,
            patch("app.api.ws_router.save_message", save_message_mock),
            patch("app.api.ws_router.perf_counter", side_effect=self._advancing_perf_counter()),
        ):
            await process_text_message(
                websocket=SimpleNamespace(),
                db_session=SimpleNamespace(),
                session_id="session-1",
                content="",
                attachments=[
                    {
                        "kind": "photo",
                        "stored_image_path": "session-1/photo.jpg",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                    }
                ],
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                send_lock=asyncio.Lock(),
            )

        stream_kwargs = stream_reply_mock.await_args.kwargs
        self.assertEqual(stream_kwargs["content"], "请帮我看看这张图片。")
        self.assertIn("灵山大佛", stream_kwargs["query_text"])
        self.assertIn("金色佛像", stream_kwargs["query_text"])
        self.assertEqual(stream_kwargs["photo_context"]["recognized_spot"], "灵山大佛")
        self.assertIn("reply_context_prepare_ms", stream_kwargs["initial_metrics"])
        self.assertEqual(stream_kwargs["initial_metrics"]["clarification_resolve_ms"], 0)
        self.assertGreater(stream_kwargs["initial_metrics"]["photo_recognition_ms"], 0)
        self.assertEqual(save_message_mock.await_args_list[0].kwargs["content"], "请帮我看看这张图片。")
        self.assertEqual(
            save_message_mock.await_args_list[0].kwargs["attachments"][0]["stored_image_path"],
            "session-1/photo.jpg",
        )
        self.assertEqual(
            save_message_mock.await_args_list[0].kwargs["attachments"][0]["recognized_spot"],
            "灵山大佛",
        )

    async def test_photo_attachment_uses_canonical_spot_name_in_query_text(self) -> None:
        avatar = SimpleNamespace(
            persona="guide",
            response_language="zh",
            voice_id="voice",
            tts_reference_audio_path="prompt.wav",
            tts_reference_text="prompt text",
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )
        quick_emotion = EmotionAnalysis(
            label="thinking",
            confidence=0.72,
            keywords=["景点照片"],
            reason="quick emotion",
            source="heuristic",
        )
        save_message_mock = AsyncMock(
            side_effect=[
                SimpleNamespace(id=201),
                SimpleNamespace(id=202),
            ]
        )
        stream_result = SimpleNamespace(
            text="这是五印坛城。",
            sources=[],
            confidence=0.92,
            mode="rag",
            emotion=None,
            metrics={},
            reply_kind="answer",
            needs_followup=False,
            followup_question="",
            missing_slots=[],
            confidence_note="confirmed",
        )
        vision_service = SimpleNamespace(
            recognize_stored_photo=AsyncMock(
                return_value=VisitorVisionResult(
                    recognized_spot="五印坛城",
                    recognition_summary="图片主体是一座藏式白塔建筑。",
                    resolved_question="请介绍一下这个景点。",
                    stored_image_path="session-2/photo.jpg",
                    is_canonical_spot=True,
                )
            )
        )

        with (
            patch("app.api.ws_router.get_chat_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_tts_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_avatar_config", AsyncMock(return_value=avatar)),
            patch("app.api.ws_router.load_recent_history", AsyncMock(return_value=[])),
            patch("app.api.ws_router.get_active_clarification_state", AsyncMock(return_value=None)),
            patch(
                "app.api.ws_router.get_emotion_analyzer",
                return_value=SimpleNamespace(analyze_quick=lambda user_text: quick_emotion),
            ),
            patch("app.api.ws_router.get_visitor_vision_service", return_value=vision_service),
            patch("app.api.ws_router.stream_assistant_reply", AsyncMock(return_value=stream_result)) as stream_reply_mock,
            patch("app.api.ws_router.save_message", save_message_mock),
            patch("app.api.ws_router.perf_counter", side_effect=self._advancing_perf_counter()),
        ):
            await process_text_message(
                websocket=SimpleNamespace(),
                db_session=SimpleNamespace(),
                session_id="session-2",
                content="这是哪个景点？",
                attachments=[
                    {
                        "kind": "photo",
                        "stored_image_path": "session-2/photo.jpg",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                    }
                ],
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                send_lock=asyncio.Lock(),
            )

        stream_kwargs = stream_reply_mock.await_args.kwargs
        self.assertIn("图片标准景点名：五印坛城", stream_kwargs["query_text"])
        self.assertNotIn("图片识别名称：五印坛城", stream_kwargs["query_text"])
        self.assertTrue(stream_kwargs["photo_context"]["recognized_spot_canonical"])
        self.assertEqual(
            save_message_mock.await_args_list[0].kwargs["attachments"][0]["recognized_spot"],
            "五印坛城",
        )

    async def test_process_text_message_records_clarification_prepare_metrics(self) -> None:
        avatar = SimpleNamespace(
            persona="guide",
            response_language="zh",
            voice_id="voice",
            tts_reference_audio_path="prompt.wav",
            tts_reference_text="prompt text",
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )
        quick_emotion = EmotionAnalysis(
            label="thinking",
            confidence=0.72,
            keywords=["开放时间"],
            reason="quick emotion",
            source="heuristic",
        )
        active_state = SimpleNamespace(
            original_question="开放时间是什么时候？",
            assistant_followup_question="你想问的是景区整体开放时间，还是商铺/夜游时间？",
        )
        stream_result = SimpleNamespace(
            text="景区整体开放一般是9:00-21:30。",
            sources=[],
            confidence=0.9,
            mode="rag",
            emotion=None,
            metrics={},
            reply_kind="answer",
            needs_followup=False,
            followup_question="",
            missing_slots=[],
            confidence_note="confirmed",
        )
        resolver = SimpleNamespace(
            resolve=AsyncMock(
                return_value=SimpleNamespace(
                    continues_clarification=True,
                    resolved_question="景区整体开放时间是什么时候？",
                )
            )
        )
        rag_service = SimpleNamespace(clarification_resolver=resolver)

        with (
            patch("app.api.ws_router.get_chat_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_tts_service", return_value=SimpleNamespace()),
            patch("app.api.ws_router.get_avatar_config", AsyncMock(return_value=avatar)),
            patch("app.api.ws_router.load_recent_history", AsyncMock(return_value=[])),
            patch("app.api.ws_router.get_active_clarification_state", AsyncMock(return_value=active_state)),
            patch("app.api.ws_router.get_rag_service", return_value=rag_service),
            patch(
                "app.api.ws_router.get_emotion_analyzer",
                return_value=SimpleNamespace(analyze_quick=lambda user_text: quick_emotion),
            ),
            patch("app.api.ws_router.stream_assistant_reply", AsyncMock(return_value=stream_result)) as stream_reply_mock,
            patch(
                "app.api.ws_router.save_message",
                AsyncMock(side_effect=[SimpleNamespace(id=301), SimpleNamespace(id=302)]),
            ),
            patch("app.api.ws_router.resolve_pending_clarification_state", AsyncMock()),
            patch("app.api.ws_router.perf_counter", side_effect=self._advancing_perf_counter()),
        ):
            await process_text_message(
                websocket=SimpleNamespace(),
                db_session=SimpleNamespace(),
                session_id="session-3",
                content="我想问景区整体开放时间。",
                capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
                send_lock=asyncio.Lock(),
            )

        stream_kwargs = stream_reply_mock.await_args.kwargs
        self.assertEqual(stream_kwargs["query_text"], "景区整体开放时间是什么时候？")
        self.assertGreater(stream_kwargs["initial_metrics"]["reply_context_prepare_ms"], 0)
        self.assertGreater(stream_kwargs["initial_metrics"]["clarification_resolve_ms"], 0)
        self.assertEqual(stream_kwargs["initial_metrics"]["photo_recognition_ms"], 0)


if __name__ == "__main__":
    unittest.main()
