import unittest
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.services.asr import ASRService, ASRTranscriptionResult


class ASRServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_mock_transcript_is_normalized_to_simplified_chinese(self) -> None:
        service = ASRService(Settings(asr_engine="mock", asr_mock_transcript="開放時間是什麼時候"))

        result = await service.transcribe_with_metrics(b"\x00\x00\x01\x00")

        self.assertEqual(result.text, "开放时间是什么时候")

    async def test_warmup_preloads_faster_whisper_model(self) -> None:
        service = ASRService(Settings(asr_engine="faster-whisper"))
        service._model = object()

        with patch.object(service, "ensure_model_loaded", AsyncMock(return_value=37)) as ensure_loaded:
            warmup_ms = await service.warmup()

        ensure_loaded.assert_awaited_once()
        self.assertEqual(warmup_ms, 37)

    async def test_transcribe_with_metrics_reports_load_and_transcribe_timings(self) -> None:
        service = ASRService(Settings(asr_engine="faster-whisper", asr_mock_transcript="mock fallback"))
        service._model = object()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(service, "ensure_model_loaded", AsyncMock(return_value=18)),
            patch("app.services.asr.asyncio.to_thread", side_effect=fake_to_thread),
            patch.object(service, "_transcribe_sync", return_value="识别完成") as transcribe_sync,
        ):
            result = await service.transcribe_with_metrics(b"\x00\x00\x01\x00")

        transcribe_sync.assert_called_once()
        self.assertIsInstance(result, ASRTranscriptionResult)
        self.assertEqual(result.text, "识别完成")
        self.assertEqual(result.model_load_ms, 18)
        self.assertGreaterEqual(result.asr_transcribe_ms, 0)
        self.assertGreaterEqual(result.asr_total_ms, result.asr_transcribe_ms)

    async def test_transcribe_with_metrics_normalizes_traditional_chinese(self) -> None:
        service = ASRService(Settings(asr_engine="faster-whisper", asr_mock_transcript="mock fallback"))
        service._model = object()

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(service, "ensure_model_loaded", AsyncMock(return_value=18)),
            patch("app.services.asr.asyncio.to_thread", side_effect=fake_to_thread),
            patch.object(service, "_transcribe_sync", return_value="開放時間是什麼時候") as transcribe_sync,
        ):
            result = await service.transcribe_with_metrics(b"\x00\x00\x01\x00")

        transcribe_sync.assert_called_once()
        self.assertEqual(result.text, "开放时间是什么时候")


if __name__ == "__main__":
    unittest.main()
