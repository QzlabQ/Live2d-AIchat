import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import Settings
from app.services.tts import TTSService


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
