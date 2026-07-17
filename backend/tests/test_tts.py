import asyncio
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.services.tts import (
    RemoteTTSProvider,
    StreamingTTSChunk,
    TTSService,
    TTSRuntimeValidationError,
    resolve_stream_hop_limit,
    resolve_stream_initial_hop_len,
    resolve_stream_profile,
)


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

    def test_stream_profile_defaults_to_stable_for_4060(self) -> None:
        profile = resolve_stream_profile(Settings(tts_stream_profile="stable"))

        self.assertEqual(profile.name, "stable")
        self.assertEqual(profile.initial_token_hop_len, 25)
        self.assertEqual(profile.growth_factor, 2.0)
        self.assertEqual(profile.max_hop_multiplier, 4)

    def test_stream_profile_low_latency_keeps_fixed_small_chunks(self) -> None:
        profile = resolve_stream_profile(Settings(tts_stream_profile="low_latency"))

        self.assertEqual(profile.name, "low_latency")
        self.assertEqual(profile.growth_factor, 1.0)
        self.assertEqual(profile.max_hop_multiplier, 1)

    def test_stable_stream_profile_expands_hop_when_vendor_max_matches_base(self) -> None:
        profile = resolve_stream_profile(Settings(tts_stream_profile="stable"))

        self.assertEqual(resolve_stream_hop_limit(profile, base_token_hop_len=25, configured_max_hop_len=25), 100)

    def test_stable_stream_profile_warm_starts_followup_segments_one_growth_step_ahead(self) -> None:
        profile = resolve_stream_profile(Settings(tts_stream_profile="stable"))

        self.assertEqual(
            resolve_stream_initial_hop_len(
                profile,
                base_token_hop_len=25,
                configured_max_hop_len=25,
                reply_segment_index=0,
            ),
            25,
        )
        self.assertEqual(
            resolve_stream_initial_hop_len(
                profile,
                base_token_hop_len=25,
                configured_max_hop_len=25,
                reply_segment_index=1,
            ),
            50,
        )

    def test_low_latency_stream_profile_keeps_followup_segments_at_base_hop(self) -> None:
        profile = resolve_stream_profile(Settings(tts_stream_profile="low_latency"))

        self.assertEqual(
            resolve_stream_initial_hop_len(
                profile,
                base_token_hop_len=25,
                configured_max_hop_len=25,
                reply_segment_index=3,
            ),
            25,
        )

    def test_remote_provider_enables_reply_streaming_without_cosyvoice_engine(self) -> None:
        service = TTSService(
            Settings(tts_engine="mock", tts_provider="remote", tts_remote_url="http://tts.example/stream")
        )

        self.assertTrue(service.supports_reply_streaming)

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
            service._inspect_cosyvoice_runtime_environment = lambda provider: "cpu"
            service._configure_cosyvoice_runtime_environment()
            self.assertEqual(os.environ.get('COSYVOICE_ONNX_PROVIDER'), 'cpu')
        finally:
            if original is None:
                os.environ.pop('COSYVOICE_ONNX_PROVIDER', None)
            else:
                os.environ['COSYVOICE_ONNX_PROVIDER'] = original

    def test_cuda_provider_validation_fails_without_cuda_execution_provider(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_onnx_provider='cuda'))
        fake_torch = SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True,
                get_device_name=lambda _index: 'Tesla V100-PCIE-32GB',
            )
        )
        fake_ort = SimpleNamespace(get_available_providers=lambda: ['CPUExecutionProvider'])

        with patch.dict('sys.modules', {'torch': fake_torch, 'onnxruntime': fake_ort}):
            with self.assertRaises(TTSRuntimeValidationError):
                service._inspect_cosyvoice_runtime_environment('cuda')

        snapshot = service.get_runtime_trace_snapshot()
        self.assertEqual(snapshot['requested_onnx_provider'], 'cuda')
        self.assertEqual(snapshot['available_onnx_providers'], ['CPUExecutionProvider'])

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
            service._resolve_cosyvoice_device = lambda: "cpu"
            service._configure_cosyvoice_runtime_environment = lambda: None

            service._load_cosyvoice_model()
        self.assertEqual(calls[0]['model_path'], str(Path(temp_dir)))
        self.assertTrue(calls[0]['fp16'])
        self.assertFalse(calls[0].get('load_trt', False))
        snapshot = service.get_runtime_trace_snapshot()
        self.assertTrue(snapshot['tts_cosyvoice_fp16'])
        self.assertFalse(snapshot['tts_cosyvoice_load_jit'])
        self.assertEqual(snapshot['tts_ar_backend'], 'pytorch')
        self.assertEqual(snapshot['tts_flow_backend'], 'pytorch')

    def test_load_cosyvoice_model_passes_trt_flags_to_factory_when_enabled(self) -> None:
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
                    tts_cosyvoice_load_trt=True,
                    tts_cosyvoice_trt_concurrent=1,
                    tts_segment_soft_min_chars=22,
                    tts_segment_soft_max_chars=40,
                    tts_segment_hard_max_chars=64,
                )
            )
            service._import_cosyvoice_module = lambda: SimpleNamespace(CosyVoice2=fake_factory)
            service._resolve_cosyvoice_device = lambda: "cpu"
            service._configure_cosyvoice_runtime_environment = lambda: None

            service._load_cosyvoice_model()

        self.assertEqual(calls[0]['model_path'], str(Path(temp_dir)))
        self.assertTrue(calls[0]['fp16'])
        self.assertTrue(calls[0]['load_trt'])
        self.assertEqual(calls[0]['trt_concurrent'], 1)
        snapshot = service.get_runtime_trace_snapshot()
        self.assertTrue(snapshot['tts_cosyvoice_load_trt'])
        self.assertEqual(snapshot['tts_cosyvoice_trt_concurrent'], 1)
        self.assertTrue(snapshot['tts_cosyvoice_fp16'])
        self.assertFalse(snapshot['tts_cosyvoice_load_jit'])
        self.assertEqual(snapshot['tts_ar_backend'], 'pytorch')
        self.assertEqual(snapshot['tts_flow_backend'], 'trt')
        self.assertTrue(snapshot['tts_trt_engine_expected'])
        self.assertTrue(snapshot['tts_trt_engine_loaded'])
        self.assertEqual(snapshot['tts_segment_soft_min_chars'], 22)
        self.assertEqual(snapshot['tts_segment_soft_max_chars'], 40)
        self.assertEqual(snapshot['tts_segment_hard_max_chars'], 64)

    def test_load_cosyvoice_model_fails_fast_when_trt_requested_but_runtime_load_fails(self) -> None:
        def fake_factory(model_path: str, **kwargs):
            raise RuntimeError("TensorRT runtime unavailable")

        with TemporaryDirectory() as temp_dir:
            service = TTSService(
                Settings(
                    tts_engine='cosyvoice',
                    tts_cosyvoice_model_path=temp_dir,
                    tts_cosyvoice_device='cpu',
                    tts_cosyvoice_load_trt=True,
                )
            )
            service._import_cosyvoice_module = lambda: SimpleNamespace(CosyVoice2=fake_factory)
            service._resolve_cosyvoice_device = lambda: "cpu"
            service._configure_cosyvoice_runtime_environment = lambda: None

            with self.assertRaises(TTSRuntimeValidationError):
                service._load_cosyvoice_model()

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

            first, first_snapshot = service._get_cached_prompt_features(
                frontend, str(prompt_wav), 'reference text'
            )
            second, second_snapshot = service._get_cached_prompt_features(
                frontend, str(prompt_wav), 'reference text'
            )

        self.assertEqual(first, second)
        self.assertFalse(first_snapshot.hit)
        self.assertTrue(second_snapshot.hit)
        self.assertGreaterEqual(first_snapshot.build_ms, 0.0)
        self.assertEqual(second_snapshot.build_ms, 0.0)
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
            service._resolve_cosyvoice_device = lambda: "cpu"

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

    def test_cosyvoice_synthesis_strips_spoken_guidance_from_tts_text(self) -> None:
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

            service._synthesize_cosyvoice(
                '九龙灌浴：用生动语言讲述释迦牟尼诞生的故事，让孩子理解佛教文化中的慈悲精神。',
                seq=0,
                voice_id=None,
                emotion='neutral',
                reference_audio_path=str(prompt_wav),
                reference_text='prompt text',
                speed=1.0,
                emotion_enabled=True,
            )

        self.assertIn('释迦牟尼诞生的故事', model.calls[0]['tts_text'])
        self.assertNotIn('用生动语言讲述', model.calls[0]['tts_text'])
        self.assertNotIn('让孩子理解', model.calls[0]['tts_text'])

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

    async def test_cosyvoice_reply_streaming_synthesizes_each_segment_independently(self) -> None:
        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def inference_instruct2_reply(self, *args, **kwargs):
                raise AssertionError("reply-scoped vendor session should not be used")

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
                yield {
                    'tts_speech': [0.0] * 2400 + [0.3] * 2400,
                    'sample_rate': 24000,
                    '_ai_chat_trace': {'token_offset': 0},
                }

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

        self.assertEqual(len(model.calls), 2)
        self.assertEqual([call['tts_text'] for call in model.calls], ['welcome to the', 'botanical garden'])
        self.assertTrue(all(call['stream'] for call in model.calls))
        self.assertEqual(len(chunks), 2)
        self.assertEqual([item.chunk_index for item in chunks], [0, 0])
        self.assertEqual([item.seq for item in chunks], [0, 1])
        self.assertEqual([item.token_offset for item in chunks], [0, 0])
        self.assertTrue(chunks[-1].is_final)

    async def test_cosyvoice_reply_streaming_emits_first_chunk_before_reply_completion(self) -> None:
        release_second_segment = asyncio.Event()

        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def inference_instruct2_reply(self, *args, **kwargs):
                raise AssertionError("reply-scoped vendor session should not be used")

            def inference_instruct2(self, tts_text, instruct_text, prompt_wav, stream=False, speed=1.0):
                self.calls.append(tts_text)
                if tts_text == 'welcome to the':
                    yield {'tts_speech': [0.3] * 2400, 'sample_rate': 24000}
                    return
                if tts_text == 'botanical garden':
                    yield {'tts_speech': [0.2] * 2400, 'sample_rate': 24000}
                    return
                raise AssertionError(f'unexpected text: {tts_text}')

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
        self.assertTrue(first.is_final)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].seq, 1)
        self.assertTrue(remaining[0].is_final)

    async def test_cosyvoice_reply_streaming_reuses_prompt_cache_across_segments(self) -> None:
        class FakeFrontend:
            def __init__(self) -> None:
                self.calls = {'feat': 0, 'token': 0, 'embedding': 0}

            def _extract_speech_feat(self, prompt_wav):
                self.calls['feat'] += 1
                return f'feat:{prompt_wav}'

            def _extract_speech_token(self, prompt_wav):
                self.calls['token'] += 1
                return f'token:{prompt_wav}'

            def _extract_spk_embedding(self, prompt_wav):
                self.calls['embedding'] += 1
                return f'embedding:{prompt_wav}'

        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.frontend = FakeFrontend()

            def inference_instruct2_reply(self, *args, **kwargs):
                raise AssertionError("reply-scoped vendor session should not be used")

            def inference_instruct2(self, tts_text, instruct_text, prompt_wav, stream=False, speed=1.0):
                yield {'tts_speech': [0.1] * 2400, 'sample_rate': 24000}

        async def segment_stream():
            yield 0, 'first stop'
            yield 1, 'second stop'

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
                    reference_text='prompt text',
                    speed=1.0,
                )
            ]

        self.assertEqual([item.prompt_cache_hit for item in chunks], [False, True])
        self.assertEqual(model.frontend.calls, {'feat': 1, 'token': 1, 'embedding': 1})

    async def test_local_reply_streaming_warm_starts_followup_segments(self) -> None:
        captured_segment_indexes: list[tuple[int, int]] = []
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))

        class FakeSession:
            def __init__(self, request) -> None:
                self.request = request
                self.has_emitted_audio = False
                self._returned = False

            def add_prefetch_started_count(self, count: int) -> None:
                del count

            def mark_prefetch_hit(self) -> None:
                return None

            async def prime(self) -> None:
                return None

            async def next_event(self):
                if self._returned:
                    return SimpleNamespace(kind='done')
                self._returned = True
                self.has_emitted_audio = True
                return SimpleNamespace(
                    kind='chunk',
                    chunk=StreamingTTSChunk(
                        seq=self.request.seq,
                        chunk_index=0,
                        text='segment',
                        audio_bytes=b'\x01\x02',
                        phonemes=[],
                        offset_ms=0,
                        sample_rate=24000,
                        is_final=True,
                    ),
                )

        def fake_create_session(request, **kwargs):
            del kwargs
            captured_segment_indexes.append((request.seq, request.reply_segment_index))
            return FakeSession(request)

        service._create_local_segment_stream_session = fake_create_session  # type: ignore[attr-defined]

        async def segment_stream():
            yield 0, 'first stop'
            yield 1, 'second stop'
            yield 2, 'third stop'

        chunks = [item async for item in service.stream_synthesize_reply(segment_stream())]

        self.assertEqual(captured_segment_indexes, [(0, 0), (1, 1), (2, 2)])
        self.assertEqual([item.seq for item in chunks], [0, 1, 2])

    async def test_local_reply_streaming_prefetches_only_one_followup_after_llm_done(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
        event_log: list[str] = []

        def make_chunk(seq: int, text: str, *, is_final: bool = True) -> StreamingTTSChunk:
            return StreamingTTSChunk(
                seq=seq,
                chunk_index=0,
                text=text,
                audio_bytes=b'\x01\x02',
                phonemes=[],
                offset_ms=0,
                sample_rate=24000,
                is_final=is_final,
                tts_prefetch_enabled=True,
            )

        class FakeSession:
            def __init__(self, request, events) -> None:
                self.request = request
                self._events = list(events)
                self.has_emitted_audio = False
                self._prefetch_started_count = 0
                self._prefetch_hit = False

            def add_prefetch_started_count(self, count: int) -> None:
                self._prefetch_started_count += count

            def mark_prefetch_hit(self) -> None:
                self._prefetch_hit = True

            async def prime(self) -> None:
                return None

            async def next_event(self):
                if not self._events:
                    return SimpleNamespace(kind='done')
                event = self._events.pop(0)
                event_log.append(f'event:{self.request.text}:{event.kind}')
                if event.kind == 'chunk':
                    self.has_emitted_audio = True
                    event.chunk.tts_prefetch_started_count_delta = self._prefetch_started_count
                    event.chunk.tts_prefetch_hit = self._prefetch_hit
                    event.chunk.tts_prefetch_hit_count_delta = 1 if self._prefetch_hit else 0
                    self._prefetch_started_count = 0
                    self._prefetch_hit = False
                return event

        session_events = {
            'first': [
                SimpleNamespace(kind='chunk', chunk=make_chunk(0, 'first', is_final=False)),
                SimpleNamespace(kind='llm_done'),
                SimpleNamespace(kind='chunk', chunk=make_chunk(0, 'first')),
                SimpleNamespace(kind='done'),
            ],
            'second': [
                SimpleNamespace(kind='chunk', chunk=make_chunk(1, 'second')),
                SimpleNamespace(kind='llm_done'),
                SimpleNamespace(kind='done'),
            ],
            'third': [
                SimpleNamespace(kind='chunk', chunk=make_chunk(2, 'third')),
                SimpleNamespace(kind='done'),
            ],
        }

        def fake_create_session(request, **kwargs):
            del kwargs
            event_log.append(f'start:{request.text}:{request.reply_segment_index}')
            return FakeSession(request, session_events[request.text])

        service._create_local_segment_stream_session = fake_create_session  # type: ignore[attr-defined]

        async def segment_stream():
            yield 0, 'first'
            yield 1, 'second'
            yield 2, 'third'

        chunks = [item async for item in service.stream_synthesize_reply(segment_stream())]

        self.assertEqual([item.seq for item in chunks], [0, 0, 1, 2])
        self.assertEqual([item.tts_prefetch_hit for item in chunks], [False, False, True, True])
        self.assertEqual([item.tts_prefetch_hit_count_delta for item in chunks], [0, 0, 1, 1])
        self.assertEqual(
            event_log,
            [
                'start:first:0',
                'event:first:chunk',
                'start:second:1',
                'event:first:llm_done',
                'event:first:chunk',
                'event:first:done',
                'event:second:chunk',
                'start:third:2',
                'event:second:llm_done',
                'event:second:done',
                'event:third:chunk',
                'event:third:done',
            ],
        )

    async def test_local_reply_streaming_falls_back_to_serial_when_next_segment_is_not_cached(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
        release_second_segment = asyncio.Event()
        event_log: list[str] = []

        def make_chunk(seq: int, text: str) -> StreamingTTSChunk:
            return StreamingTTSChunk(
                seq=seq,
                chunk_index=0,
                text=text,
                audio_bytes=b'\x01\x02',
                phonemes=[],
                offset_ms=0,
                sample_rate=24000,
                is_final=True,
                tts_prefetch_enabled=True,
            )

        class FakeSession:
            def __init__(self, request, events) -> None:
                self.request = request
                self._events = list(events)
                self.has_emitted_audio = False

            def add_prefetch_started_count(self, count: int) -> None:
                del count

            def mark_prefetch_hit(self) -> None:
                raise AssertionError('serial fallback should not mark a prefetch hit')

            async def prime(self) -> None:
                return None

            async def next_event(self):
                if not self._events:
                    return SimpleNamespace(kind='done')
                event = self._events.pop(0)
                event_log.append(f'event:{self.request.text}:{event.kind}')
                if self.request.text == 'first' and event.kind == 'llm_done':
                    asyncio.get_running_loop().call_soon(release_second_segment.set)
                if event.kind == 'chunk':
                    self.has_emitted_audio = True
                return event

        session_events = {
            'first': [
                SimpleNamespace(kind='llm_done'),
                SimpleNamespace(kind='chunk', chunk=make_chunk(0, 'first')),
                SimpleNamespace(kind='done'),
            ],
            'second': [
                SimpleNamespace(kind='chunk', chunk=make_chunk(1, 'second')),
                SimpleNamespace(kind='done'),
            ],
        }

        def fake_create_session(request, **kwargs):
            del kwargs
            event_log.append(f'start:{request.text}:{request.reply_segment_index}')
            return FakeSession(request, session_events[request.text])

        service._create_local_segment_stream_session = fake_create_session  # type: ignore[attr-defined]

        async def segment_stream():
            yield 0, 'first'
            await release_second_segment.wait()
            yield 1, 'second'

        chunks = [item async for item in service.stream_synthesize_reply(segment_stream())]

        self.assertEqual([item.seq for item in chunks], [0, 1])
        self.assertEqual([item.tts_prefetch_hit for item in chunks], [False, False])
        self.assertEqual(
            event_log,
            [
                'start:first:0',
                'event:first:llm_done',
                'event:first:chunk',
                'event:first:done',
                'start:second:1',
                'event:second:chunk',
                'event:second:done',
            ],
        )

    async def test_local_reply_streaming_retries_prefetched_segment_serially_when_prefetch_fails(self) -> None:
        service = TTSService(Settings(tts_engine='cosyvoice', tts_cosyvoice_sample_rate=24000))
        event_log: list[str] = []
        start_attempts: dict[str, int] = {'second': 0}

        def make_chunk(seq: int, text: str) -> StreamingTTSChunk:
            return StreamingTTSChunk(
                seq=seq,
                chunk_index=0,
                text=text,
                audio_bytes=b'\x01\x02',
                phonemes=[],
                offset_ms=0,
                sample_rate=24000,
                is_final=True,
                tts_prefetch_enabled=True,
            )

        class FakeSession:
            def __init__(self, request, events) -> None:
                self.request = request
                self._events = list(events)
                self.has_emitted_audio = False
                self._prefetch_started_count = 0
                self._prefetch_hit = False

            def add_prefetch_started_count(self, count: int) -> None:
                self._prefetch_started_count += count

            def mark_prefetch_hit(self) -> None:
                self._prefetch_hit = True

            async def prime(self) -> None:
                return None

            async def next_event(self):
                if not self._events:
                    return SimpleNamespace(kind='done')
                event = self._events.pop(0)
                if isinstance(event, Exception):
                    event_log.append(f'event:{self.request.text}:error')
                    raise event
                event_log.append(f'event:{self.request.text}:{event.kind}')
                if event.kind == 'chunk':
                    self.has_emitted_audio = True
                    event.chunk.tts_prefetch_started_count_delta = self._prefetch_started_count
                    event.chunk.tts_prefetch_hit = self._prefetch_hit
                    event.chunk.tts_prefetch_hit_count_delta = 1 if self._prefetch_hit else 0
                    self._prefetch_started_count = 0
                    self._prefetch_hit = False
                return event

        def fake_create_session(request, **kwargs):
            del kwargs
            event_log.append(f'start:{request.text}:{request.reply_segment_index}')
            if request.text == 'first':
                return FakeSession(
                    request,
                    [
                        SimpleNamespace(kind='llm_done'),
                        SimpleNamespace(kind='chunk', chunk=make_chunk(0, 'first')),
                        SimpleNamespace(kind='done'),
                    ],
                )
            if request.text == 'second':
                start_attempts['second'] += 1
                if start_attempts['second'] == 1:
                    return FakeSession(request, [RuntimeError('prefetch failed before first chunk')])
                return FakeSession(
                    request,
                    [
                        SimpleNamespace(kind='chunk', chunk=make_chunk(1, 'second')),
                        SimpleNamespace(kind='done'),
                    ],
                )
            raise AssertionError(f'unexpected request: {request.text}')

        service._create_local_segment_stream_session = fake_create_session  # type: ignore[attr-defined]

        async def segment_stream():
            yield 0, 'first'
            yield 1, 'second'

        chunks = [item async for item in service.stream_synthesize_reply(segment_stream())]

        self.assertEqual([item.seq for item in chunks], [0, 1])
        self.assertEqual(chunks[1].tts_prefetch_started_count_delta, 1)
        self.assertFalse(chunks[1].tts_prefetch_hit)
        self.assertEqual(
            event_log,
            [
                'start:first:0',
                'event:first:llm_done',
                'start:second:1',
                'event:first:chunk',
                'event:first:done',
                'event:second:error',
                'start:second:1',
                'event:second:chunk',
                'event:second:done',
            ],
        )

    async def test_remote_tts_provider_streams_common_chunk_shape(self) -> None:
        class FakeRemoteTTSProvider(RemoteTTSProvider):
            async def _iter_remote_events(self, payload):
                yield {
                    "seq": 0,
                    "chunk_index": 0,
                    "text": "hello",
                    "audio_bytes": b"\x01\x02",
                    "phonemes": [{"ph": "a", "start": 0.0, "end": 0.1, "openY": 0.8, "form": 0.0}],
                    "offset_ms": 0,
                    "sample_rate": 24000,
                    "is_final": True,
                }

        provider = FakeRemoteTTSProvider(Settings(tts_remote_url="http://tts.example/stream"))

        async def segment_stream():
            yield 0, "hello"

        chunks = [
            item
            async for item in provider.stream_synthesize_reply(
                segment_stream(),
                voice_id="voice",
                emotion="happy",
                reference_audio_path=None,
                reference_text=None,
                speed=1.0,
                tts_emotion_enabled=True,
            )
        ]

        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0], StreamingTTSChunk)
        self.assertEqual(chunks[0].seq, 0)
        self.assertEqual(chunks[0].encoding, "pcm16le")
        self.assertTrue(chunks[0].is_final)

    async def test_remote_tts_provider_emits_first_chunk_before_all_segments_arrive(self) -> None:
        release_second_segment = asyncio.Event()

        class FakeRemoteTTSProvider(RemoteTTSProvider):
            async def _iter_remote_events(self, payload):
                segment_iter = payload["segments"]
                first_segment = await anext(segment_iter)
                self.first_segment = first_segment
                yield {
                    "seq": first_segment["seq"],
                    "chunk_index": 0,
                    "text": first_segment["text"],
                    "audio_bytes": b"\x01\x02",
                    "sample_rate": 24000,
                    "is_final": False,
                }
                second_segment = await anext(segment_iter)
                yield {
                    "seq": second_segment["seq"],
                    "chunk_index": 1,
                    "text": second_segment["text"],
                    "audio_bytes": b"\x03\x04",
                    "sample_rate": 24000,
                    "is_final": True,
                }

        provider = FakeRemoteTTSProvider(Settings(tts_remote_url="http://tts.example/stream"))

        async def segment_stream():
            yield 0, "first"
            await release_second_segment.wait()
            yield 1, "second"

        stream = provider.stream_synthesize_reply(segment_stream())
        first = await asyncio.wait_for(stream.__anext__(), timeout=0.3)
        release_second_segment.set()
        remaining = [item async for item in stream]

        self.assertEqual(first.seq, 0)
        self.assertEqual(provider.first_segment, {"seq": 0, "text": "first"})
        self.assertFalse(first.is_final)
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
