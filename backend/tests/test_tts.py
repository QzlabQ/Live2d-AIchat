import unittest

from app.core.config import Settings
from app.services.tts import TTSService


class TTSServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_mock_synthesis_uses_text_driven_visemes_for_chinese(self) -> None:
        service = TTSService(Settings(tts_engine="mock"))

        chunk = await service.synthesize_chunk("英语", seq=0)

        self.assertEqual([frame["ph"] for frame in chunk.phonemes], ["i", "u", "N"])
        self.assertEqual(chunk.phonemes[0]["openY"], 0.42)
        self.assertEqual(chunk.phonemes[1]["form"], -0.72)

    def test_boundaries_are_split_with_token_specific_mouth_shapes(self) -> None:
        service = TTSService(Settings(tts_engine="mock"))

        frames = service._phonemes_from_boundaries(
            "乌鸦",
            [{"text": "乌鸦", "offset": 0, "duration": 2_000_000}],
        )

        self.assertEqual([frame["ph"] for frame in frames], ["u", "a", "N"])
        self.assertEqual(frames[0]["start"], 0.0)
        self.assertEqual(frames[0]["end"], 0.1)
        self.assertEqual(frames[1]["start"], 0.1)
        self.assertEqual(frames[1]["end"], 0.2)

    def test_cosyvoice_synthesis_matches_current_vendor_signature(self) -> None:
        class FakeCosyVoiceModel:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, bool]] = []

            def inference_sft(self, tts_text: str, spk_id: str, stream: bool = False):
                self.calls.append((tts_text, spk_id, stream))
                return {
                    "audio": [0.0, 0.2, -0.2, 0.0],
                    "sample_rate": 22050,
                }

        service = TTSService(Settings(tts_engine="cosyvoice"))
        model = FakeCosyVoiceModel()
        service._load_cosyvoice_model = lambda: model
        service._resolve_cosyvoice_speaker = lambda voice_id: "speaker-a"

        chunk = service._synthesize_cosyvoice("welcome", seq=0, voice_id=None)

        self.assertEqual(model.calls, [("welcome", "speaker-a", False)])
        self.assertEqual(chunk.mime_type, "audio/wav")
        self.assertGreater(len(chunk.audio_bytes), 0)


if __name__ == "__main__":
    unittest.main()
