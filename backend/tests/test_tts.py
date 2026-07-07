import asyncio
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.core.config import Settings
from app.services.tts import StreamingTTSChunk, TTSService


HAPPY_INSTRUCT = '\u7528\u6109\u5feb\u3001\u4eb2\u5207\u3001\u81ea\u7136\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>'
NEUTRAL_INSTRUCT = '\u7528\u81ea\u7136\u3001\u53cb\u597d\u3001\u6e05\u6670\u7684\u8bed\u6c14\u4ecb\u7ecd\u8fd9\u6bb5\u5185\u5bb9\u3002<|endofprompt|>'


class TTSServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_mock_synthesis_uses_text_driven_visemes_for_chinese(self) -> None:
        service = TTSService(Settings(tts_engine='mock'))

        chunk = await service.synthesize_chunk('\u82f1\u8bed', seq=0)

        self.assertEqual([frame['ph'] for frame in chunk.phonemes], ['i', 'u', 'N'])
        self.assertEqual(chunk.phonemes[0]['openY'], 0.42)
        self.assertEqual(chunk.phonemes[1]['form'], -0.72)

    def test_boundaries_are_split_with_token_specific_mouth_shapes(self) -> None:
        service = TTSService(Settings(tts_engine='mock'))

        frames = service._phonemes_from_boundaries(
            '\u4e4c\u9e26',
            [{'text': '\u4e4c\u9e26', 'offset': 0, 'duration': 2_000_000}],
        )

        self.assertEqual([frame['ph'] for frame in frames], ['u', 'a', 'N'])
        self.assertEqual(frames[0]['start'], 0.0)
        self.assertEqual(frames[0]['end'], 0.1)
        self.assertEqual(frames[1]['start'], 0.1)
        self.assertEqual(frames[1]['end'], 0.2)

    def test_builds_emotion_instruct_prompt(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice'))

        self.assertEqual(service._build_cosyvoice_instruction('happy', emotion_enabled=True), HAPPY_INSTRUCT)
        self.assertEqual(service._build_cosyvoice_instruction('unknown', emotion_enabled=True), NEUTRAL_INSTRUCT)
        self.assertEqual(service._build_cosyvoice_instruction('excited', emotion_enabled=False), NEUTRAL_INSTRUCT)

    def test_reference_audio_path_resolves_relative_to_backend_root(self) -> None:
        backend_root = Path(__file__).resolve().parents[1]

        with TemporaryDirectory(dir=backend_root) as backend_temp, TemporaryDirectory() as other_cwd:
            prompt_wav = Path(backend_temp) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')
            relative_prompt = './' + prompt_wav.relative_to(backend_root).as_posix()
            service = TTSService(Settings(default_tts_reference_audio_path=relative_prompt))

            original_cwd = Path.cwd()
            os.chdir(other_cwd)
            try:
                resolved = service._resolve_reference_audio_path(None)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(resolved, str(prompt_wav.resolve()))

    def test_configures_cosyvoice_frontend_onnx_provider_environment(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_onnx_provider='cpu'))

        original = os.environ.get('COSYVOICE_ONNX_PROVIDER')
        try:
            service._configure_cosyvoice_runtime_environment()
            self.assertEqual(os.environ.get('COSYVOICE_ONNX_PROVIDER'), 'cpu')
        finally:
            if original is None:
                os.environ.pop('COSYVOICE_ONNX_PROVIDER', None)
            else:
                os.environ['COSYVOICE_ONNX_PROVIDER'] = original

    def test_load_cosyvoice_model_passes_runtime_flags_to_factory(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_factory(model_path: str, **kwargs):
            calls.append({'model_path': model_path, **kwargs})
            return object()

        with TemporaryDirectory() as temp_dir:
            service = TTSService(
                Settings(
                    tts_engine='cosyvoice',
                    tts_cosyvoice_model_path=temp_dir,
                    tts_cosyvoice_device='cpu',
                    tts_cosyvoice_fp16=True,
                    tts_cosyvoice_load_jit=False,
                )
            )
            service._import_cosyvoice_module = lambda: SimpleNamespace(CosyVoice2=fake_factory)

            service._load_cosyvoice_model()

        self.assertEqual(calls[0]['model_path'], str(Path(temp_dir)))
        self.assertTrue(calls[0]['fp16'])

    def test_prompt_feature_cache_reuses_reference_audio_features(self) -> None:
        calls = {'feat': 0, 'token': 0, 'embedding': 0}

        class FakeFrontend:
            def _extract_speech_feat(self, prompt_wav):
                calls['feat'] += 1
                return 'feat'

            def _extract_speech_token(self, prompt_wav):
                calls['token'] += 1
                return 'token'

            def _extract_spk_embedding(self, prompt_wav):
                calls['embedding'] += 1
                return 'embedding'

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')
            service = TTSService(Settings(tts_engine='cosyvoice'))
            frontend = FakeFrontend()

            first = service._get_cached_prompt_features(frontend, str(prompt_wav), 'reference text')
            second = service._get_cached_prompt_features(frontend, str(prompt_wav), 'reference text')

        self.assertEqual(first, second)
        self.assertEqual(calls, {'feat': 1, 'token': 1, 'embedding': 1})

    def test_cosyvoice2_synthesis_uses_instruct2_signature(self) -> None:
        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def inference_instruct2(self, tts_text, instruct_text, prompt_wav, stream=False, speed=1.0):
                self.calls.append(
                    {
                        'tts_text': tts_text,
                        'instruct_text': instruct_text,
                        'prompt_wav': prompt_wav,
                        'stream': stream,
                        'speed': speed,
                    }
                )
                return {'tts_speech': [0.0, 0.2, -0.2, 0.0], 'sample_rate': 24000}

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
            model = FakeCosyVoiceModel()
            service._load_cosyvoice_model = lambda: model

            chunk = service._synthesize_cosyvoice(
                'welcome',
                seq=0,
                voice_id=None,
                emotion='happy',
                reference_audio_path=str(prompt_wav),
                reference_text='\u5e0c\u671b\u4f60\u4ee5\u540e\u80fd\u591f\u505a\u5f97\u6bd4\u6211\u8fd8\u597d\u3002',
                speed=1.2,
                emotion_enabled=True,
            )

            self.assertEqual(model.calls[0]['tts_text'], 'welcome')
            self.assertEqual(model.calls[0]['instruct_text'], HAPPY_INSTRUCT)
            self.assertEqual(model.calls[0]['prompt_wav'], str(prompt_wav))
            self.assertEqual(model.calls[0]['stream'], False)
            self.assertEqual(model.calls[0]['speed'], 1.2)
            self.assertEqual(chunk.mime_type, 'audio/wav')
            self.assertGreater(len(chunk.audio_bytes), 0)

    async def test_cosyvoice2_streaming_yields_multiple_audio_chunks(self) -> None:
        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def inference_instruct2(self, tts_text, instruct_text, prompt_wav, stream=False, speed=1.0):
                self.calls.append(
                    {
                        'tts_text': tts_text,
                        'instruct_text': instruct_text,
                        'prompt_wav': prompt_wav,
                        'stream': stream,
                        'speed': speed,
                    }
                )
                yield {'tts_speech': [0.0] * 2400 + [0.3] * 2400, 'sample_rate': 24000}
                yield {'tts_speech': [0.0] * 800 + [0.2] * 2400 + [0.0] * 800, 'sample_rate': 24000}

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
            model = FakeCosyVoiceModel()
            service._load_cosyvoice_model = lambda: model

            chunks = [
                item
                async for item in service.stream_synthesize_segment(
                    'welcome to the park',
                    seq=0,
                    emotion='happy',
                    reference_audio_path=str(prompt_wav),
                    speed=1.0,
                )
            ]

        self.assertEqual(model.calls[0]['stream'], True)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(isinstance(item, StreamingTTSChunk) for item in chunks))
        self.assertEqual([item.chunk_index for item in chunks], [0, 1])
        self.assertTrue(chunks[-1].is_final)
        self.assertTrue(all(item.audio_bytes for item in chunks))
        self.assertTrue(all(item.sample_rate == 24000 for item in chunks))

    async def test_cosyvoice2_streaming_emits_first_chunk_without_waiting_for_second(self) -> None:
        release_second_chunk = threading.Event()

        class FakeCosyVoiceModel:
            def inference_instruct2(self, tts_text, instruct_text, prompt_wav, stream=False, speed=1.0):
                yield {'tts_speech': [0.3] * 2400, 'sample_rate': 24000}
                release_second_chunk.wait(timeout=2)
                yield {'tts_speech': [0.2] * 2400, 'sample_rate': 24000}

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
            service._load_cosyvoice_model = lambda: FakeCosyVoiceModel()

            stream = service.stream_synthesize_segment(
                'welcome to the park',
                seq=0,
                emotion='happy',
                reference_audio_path=str(prompt_wav),
                speed=1.0,
            )

            first = await asyncio.wait_for(stream.__anext__(), timeout=0.3)
            release_second_chunk.set()
            remaining = [item async for item in stream]

        self.assertEqual(first.chunk_index, 0)
        self.assertFalse(first.is_final)
        self.assertEqual(len(remaining), 1)
        self.assertTrue(remaining[0].is_final)

    async def test_cosyvoice_reply_streaming_reuses_single_vendor_session(self) -> None:
        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def inference_instruct2_reply(self, text_iterator, instruct_text, prompt_wav, stream=False, speed=1.0):
                received = list(text_iterator)
                self.calls.append(
                    {
                        'texts': received,
                        'instruct_text': instruct_text,
                        'prompt_wav': prompt_wav,
                        'stream': stream,
                        'speed': speed,
                    }
                )
                yield {'tts_speech': [0.0] * 2400 + [0.3] * 2400, 'sample_rate': 24000}
                yield {'tts_speech': [0.0] * 800 + [0.2] * 2400 + [0.0] * 800, 'sample_rate': 24000}

        async def segment_stream():
            yield 0, 'welcome to the'
            yield 1, ' botanical garden'

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
            model = FakeCosyVoiceModel()
            service._load_cosyvoice_model = lambda: model

            chunks = [
                item
                async for item in service.stream_synthesize_reply(
                    segment_stream(),
                    emotion='happy',
                    reference_audio_path=str(prompt_wav),
                    speed=1.0,
                )
            ]

        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0]['texts'], ['welcome to the', 'botanical garden'])
        self.assertTrue(model.calls[0]['stream'])
        self.assertEqual(len(chunks), 2)
        self.assertEqual([item.chunk_index for item in chunks], [0, 1])
        self.assertEqual([item.seq for item in chunks], [0, 1])
        self.assertTrue(chunks[-1].is_final)

    async def test_cosyvoice_reply_streaming_emits_first_chunk_before_reply_completion(self) -> None:
        release_second_segment = asyncio.Event()

        class FakeCosyVoiceModel:
            def inference_instruct2_reply(self, text_iterator, instruct_text, prompt_wav, stream=False, speed=1.0):
                first = next(text_iterator)
                yield {'tts_speech': [0.3] * 2400, 'sample_rate': 24000}
                assert first == 'welcome to the'
                second = next(text_iterator)
                assert second == 'botanical garden'
                yield {'tts_speech': [0.2] * 2400, 'sample_rate': 24000}

        async def segment_stream():
            yield 0, 'welcome to the'
            await release_second_segment.wait()
            yield 1, 'botanical garden'

        with TemporaryDirectory() as temp_dir:
            prompt_wav = Path(temp_dir) / 'prompt.wav'
            prompt_wav.write_bytes(b'fake wav')

            service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
            service._load_cosyvoice_model = lambda: FakeCosyVoiceModel()

            stream = service.stream_synthesize_reply(
                segment_stream(),
                emotion='happy',
                reference_audio_path=str(prompt_wav),
                speed=1.0,
            )

            first = await asyncio.wait_for(stream.__anext__(), timeout=0.3)
            release_second_segment.set()
            remaining = [item async for item in stream]

        self.assertEqual(first.seq, 0)
        self.assertEqual(first.chunk_index, 0)
        self.assertFalse(first.is_final)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].seq, 1)
        self.assertTrue(remaining[0].is_final)

    def test_trim_pcm_silence_preserves_core_audio(self) -> None:
        service = TTSService(Settings(tts_engine='mock', tts_cosyvoice_sample_rate=1000))

        trimmed, info = service._trim_pcm_silence(
            [0] * 120 + [8000] * 240 + [0] * 160,
            sample_rate=1000,
            leading_ms=20,
            trailing_ms=20,
        )

        self.assertLess(len(trimmed), 520)
        self.assertGreater(len(trimmed), 200)
        self.assertGreater(info['trimmed_leading_ms'], 0)
        self.assertGreater(info['trimmed_trailing_ms'], 0)

    def test_structured_duration_frames_are_normalized(self) -> None:
        service = TTSService(Settings(tts_engine='mock'))

        frames = service._phonemes_from_duration_units(
            [
                {'ph': 'a', 'duration': 0.1},
                {'ph': 'u', 'duration': 0.2},
            ]
        )

        self.assertEqual([frame['ph'] for frame in frames], ['a', 'u', 'N'])
        self.assertEqual(frames[0]['start'], 0.0)
        self.assertEqual(frames[0]['end'], 0.1)
        self.assertEqual(frames[1]['start'], 0.1)
        self.assertEqual(frames[1]['end'], 0.3)

    def test_waveform_fallback_generates_dense_mouth_frames(self) -> None:
        service = TTSService(Settings(tts_engine='mock', tts_cosyvoice_sample_rate=1000))

        frames = service._phonemes_from_waveform([0.0] * 20 + [0.8] * 20 + [0.1] * 20, sample_rate=1000)

        self.assertGreaterEqual(len(frames), 3)
        self.assertEqual(frames[0]['start'], 0.0)
        self.assertTrue(any(frame['openY'] > 0.5 for frame in frames))
        self.assertEqual(frames[-1]['ph'], 'N')

    async def test_cosyvoice_failure_returns_text_fallback_frames(self) -> None:
        async def fail_edge(*args, **kwargs):
            raise RuntimeError('edge failed')

        service = TTSService(Settings(tts_engine='cosyvoice'))
        service._synthesize_cosyvoice = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('cosy failed'))
        service._synthesize_edge = fail_edge

        chunk = await service.synthesize_chunk('\u4f60\u597d', seq=1, emotion='happy')

        self.assertEqual(chunk.seq, 1)
        self.assertEqual(chunk.audio_bytes, b'')
        self.assertGreater(len(chunk.phonemes), 0)


if __name__ == '__main__':
    unittest.main()
