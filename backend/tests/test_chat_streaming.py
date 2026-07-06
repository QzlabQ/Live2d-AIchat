import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.ws_router import ClientCapabilities, stream_assistant_reply
from app.core.config import Settings
from app.services.chat import RAGGuideChatService, ReplyStreamEvent, TTSSegmenter
from app.services.emotion import EmotionAnalysis
from app.services.rag import PreparedRAGAnswer
from app.services.tts import StreamingTTSChunk


class FakeTraceService:
    def __init__(self) -> None:
        self.enqueued_payloads: list[dict[str, object]] = []

    def enqueue_trace(self, trace) -> None:
        self.enqueued_payloads.append(trace.to_payload())


class TTSSegmenterTestCase(unittest.TestCase):
    def test_prefers_soft_boundary_even_when_strong_boundary_exists_later(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        text = (
            "第一段先介绍夜游开放时间，接着补充灯光亮起后的路线建议，"
            "最后再说明游客拍照和排队的注意事项。"
        )

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(segments[0].endswith("，"))
        self.assertLessEqual(len(segments[0]), 20)

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
                *,
                query_text: str | None = None,
                history: list[dict[str, str]] | None = None,
            ):
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

            async def stream_synthesize_segment(self, *args, **kwargs):
                yield StreamingTTSChunk(
                    seq=0,
                    chunk_index=0,
                    text="Hello there.",
                    audio_bytes=b"\x01\x02\x03\x04",
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
        self.assertEqual(trace_payload["segment_count"], 1)
        self.assertEqual(trace_payload["audio_chunk_count"], 1)
        self.assertIn("llm_first_delta_ms", trace_payload["metrics"])
        self.assertIn("tts_first_segment_ms", trace_payload["metrics"])
        self.assertIn("tts_first_audio_chunk_ms", trace_payload["metrics"])
        self.assertIn("text_done_ms", trace_payload["metrics"])
        self.assertIn("audio_done_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_thinking_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_speaking_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_cooldown_ms", trace_payload["metrics"])
        self.assertIn("avatar_phase_idle_ms", trace_payload["metrics"])

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


class RAGGuideChatServiceFallbackTestCase(unittest.IsolatedAsyncioTestCase):
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

    @staticmethod
    def _async_return(value):
        async def _inner(*args, **kwargs):
            return value

        return _inner


if __name__ == "__main__":
    unittest.main()
