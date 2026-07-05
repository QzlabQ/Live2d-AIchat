import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.services.chat import DisplayChunker, RAGGuideChatService, ReplyStreamEvent, TTSSegmenter
from app.services.rag import PreparedRAGAnswer
from app.services.tts import StreamingTTSChunk
from app.api.ws_router import ClientCapabilities, stream_assistant_reply


class TTSSegmenterTestCase(unittest.TestCase):
    def test_prefers_soft_boundary_even_when_strong_boundary_exists_later(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=12, soft_max_chars=20, hard_max_chars=28)
        text = (
            '第一段先介绍夜游开放时间，接着补充灯光亮起后的路线建议，'
            '最后再说明游客拍照和排队的注意事项。'
        )

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(segments[0].endswith('，'))
        self.assertLessEqual(len(segments[0]), 20)

    def test_does_not_hard_split_long_sentence_every_24_chars(self) -> None:
        segmenter = TTSSegmenter()
        text = (
            '来到灵山胜境之后可以先沿着主游览线慢慢参观大佛和梵宫，'
            '再去九龙灌浴和五印坛城，最后根据时间安排自由活动'
        )

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertGreater(len(segments[0]), 24)
        self.assertTrue(segments[0].endswith('，'))

    def test_prefers_soft_boundary_before_forced_limit(self) -> None:
        segmenter = TTSSegmenter(soft_min_chars=16, soft_max_chars=24, hard_max_chars=32)
        text = '这是第一段介绍景区整体风貌，接着说明核心景点分布，最后补充参观建议和注意事项'

        segments = segmenter.feed(text) + segmenter.flush()

        self.assertGreaterEqual(len(segments), 2)
        self.assertTrue(segments[0].endswith('，'))
        self.assertLessEqual(len(segments[0]), 25)


class StreamAssistantReplyTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_capability_uses_new_tts_protocol(self) -> None:
        class FakeWebSocket:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.messages.append(payload)

        class FakeChatService:
            async def stream_reply(self, user_text: str, persona: str | None = None):
                yield ReplyStreamEvent(kind='text_delta', content='第一句。')
                yield ReplyStreamEvent(kind='tts_segment', content='第一句。')
                yield ReplyStreamEvent(kind='final', text='第一句。', spoken_text='第一句。', sources=[], mode='rag', confidence=0.91)

        class FakeTTSService:
            async def stream_synthesize_segment(self, *args, **kwargs):
                yield StreamingTTSChunk(
                    seq=0,
                    chunk_index=0,
                    text='第一句。',
                    audio_bytes=b'\x01\x02\x03\x04',
                    phonemes=[{'ph': 'a', 'start': 0.0, 'end': 0.1, 'openY': 0.8, 'form': 0.0}],
                    offset_ms=0,
                    sample_rate=24000,
                    channels=1,
                    encoding='pcm16le',
                    is_final=True,
                )

        websocket = FakeWebSocket()
        avatar = SimpleNamespace(
            persona='guide',
            voice_id='voice',
            tts_reference_audio_path='prompt.wav',
            tts_reference_text='prompt text',
            tts_speed=1.0,
            tts_emotion_enabled=True,
        )

        result = await stream_assistant_reply(
            websocket=websocket,
            session_id='session-1',
            avatar=avatar,
            content='介绍一下这里',
            chat_service=FakeChatService(),
            tts_service=FakeTTSService(),
            capabilities=ClientCapabilities(tts_streaming=True, audio_format='pcm16le'),
            reply_id='reply-1',
            locked_emotion='happy',
            emotion_payload={'type': 'emotion', 'value': 'happy', 'confidence': 0.7, 'keywords': [], 'reason': 'quick', 'source': 'heuristic'},
            started_at=0.0,
        )

        message_types = [item['type'] for item in websocket.messages]

        self.assertIn('tts_audio_chunk', message_types)
        self.assertIn('tts_viseme_chunk', message_types)
        self.assertIn('text_done', message_types)
        self.assertIn('audio_done', message_types)
        self.assertEqual(result.text, '第一句。')
        self.assertEqual(result.mode, 'rag')


class RAGGuideChatServiceFallbackTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_stream_reply_uses_fallback_text_when_llm_stream_fails(self) -> None:
        service = RAGGuideChatService(Settings(chat_mode='rag'))
        prepared = PreparedRAGAnswer(
            answer_text='',
            spoken_text='',
            sources=[],
            confidence=0.62,
            used_llm=True,
            llm_messages=[{'role': 'user', 'content': 'open time?'}],
            fallback_text='fallback answer from retrieval.',
        )
        fake_rag_service = SimpleNamespace(
            prepare_stream_answer=self._async_return(prepared),
            llm=SimpleNamespace(stream_complete=self._async_raise(RuntimeError('401 Unauthorized'))),
        )

        with patch('app.services.chat.get_rag_service', return_value=fake_rag_service):
            events = [event async for event in service.stream_reply('open time?', persona='guide')]

        text_deltas = [event.content for event in events if event.kind == 'text_delta']
        finals = [event for event in events if event.kind == 'final']

        self.assertTrue(text_deltas)
        self.assertEqual(''.join(text_deltas), 'fallback answer from retrieval.')
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, 'fallback answer from retrieval.')

    @staticmethod
    def _async_return(value):
        async def _inner(*args, **kwargs):
            return value

        return _inner

    @staticmethod
    def _async_raise(exc: Exception):
        async def _inner(*args, **kwargs):
            raise exc
            yield  # pragma: no cover

        return _inner
