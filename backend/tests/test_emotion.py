import asyncio
import unittest

from app.core.config import Settings
from app.services.emotion import EmotionAnalysis, EmotionAnalyzer


class EmotionAnalyzerTestCase(unittest.TestCase):
    def test_detects_happy_guidance_tone(self) -> None:
        analyzer = EmotionAnalyzer(Settings())

        result = asyncio.run(
            analyzer.analyze(
                user_text="你好，第一次来这里有什么推荐？",
                reply_text="欢迎来到景区，推荐你先去灵山大佛和梵宫，整体会比较轻松。",
            )
        )

        self.assertEqual(result.label, "happy")
        self.assertEqual(result.source, "heuristic")
        self.assertGreater(result.confidence, 0.5)
        self.assertIn("欢迎", result.keywords)

    def test_detects_thinking_for_history_answers(self) -> None:
        analyzer = EmotionAnalyzer(Settings())

        result = asyncio.run(
            analyzer.analyze(
                user_text="这里有什么历史故事？",
                reply_text="这段历史和玄奘文化有关，背后还有景区的建设由来与典故。",
            )
        )

        self.assertEqual(result.label, "thinking")
        self.assertIn("历史", result.keywords)

    def test_detects_excited_for_route_recommendation(self) -> None:
        analyzer = EmotionAnalyzer(Settings())

        result = asyncio.run(
            analyzer.analyze(
                user_text="第一次来应该怎么游览？",
                reply_text="建议你先走核心景点主线，接着去九龙灌浴，再去梵宫，路线会很顺。",
            )
        )

        self.assertEqual(result.label, "excited")
        self.assertIn("路线", result.keywords)

    def test_defaults_to_neutral_when_signal_is_weak(self) -> None:
        analyzer = EmotionAnalyzer(Settings())

        result = asyncio.run(
            analyzer.analyze(
                user_text="开放时间是什么时候？",
                reply_text="开放时间请以景区当天公告为准。",
            )
        )

        self.assertEqual(
            result,
            EmotionAnalysis(
                label="neutral",
                confidence=0.45,
                keywords=[],
                reason="未命中特别明显的情绪关键词，保持中性导览语气。",
                source="heuristic",
            ),
        )


if __name__ == "__main__":
    unittest.main()
