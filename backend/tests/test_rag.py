import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import Settings
from app.services.rag import (
    ClarificationResolver,
    RetrievedChunk,
    ScenicRAGService,
    build_structured_answer,
    detect_query_intent,
    is_out_of_domain_question,
)


def make_chunk(
    *,
    text: str,
    category: str = "scenery",
    title: str = "灵山胜境：历史、文化、景点特色与个性化游览指南",
    filename: str = "灵山胜境：历史、文化、景点特色与个性化游览指南.docx",
    chunk_index: int = 0,
    retrieval_score: float = 0.8,
    rerank_score: float = 0.9,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"chunk-{chunk_index}",
        doc_id="doc-1",
        filename=filename,
        title=title,
        category=category,
        text=text,
        chunk_index=chunk_index,
        retrieval_score=retrieval_score,
        rerank_score=rerank_score,
    )


class DetectQueryIntentTests(unittest.TestCase):
    def test_detects_route_queries(self) -> None:
        self.assertEqual(detect_query_intent("第一次来灵山胜境应该怎么逛？"), "route")

    def test_detects_overview_queries(self) -> None:
        self.assertEqual(detect_query_intent("灵山胜境有哪些核心景点？"), "overview")

    def test_detects_timeline_queries(self) -> None:
        self.assertEqual(detect_query_intent("九龙灌浴属于灵山胜境哪一期工程？"), "timeline")

    def test_detects_out_of_domain_weather_queries(self) -> None:
        self.assertTrue(is_out_of_domain_question("现在无锡今天会下雨吗？"))


class BuildStructuredAnswerTests(unittest.TestCase):
    def test_route_query_prefers_route_plan_over_unrelated_spot_copy(self) -> None:
        sources = [
            make_chunk(
                category="route",
                text=(
                    "历史文化爱好者路线（6小时深度游）\n"
                    "路线规划：南门入园→灵山大照壁→祥符禅寺→灵山大佛→灵山梵宫→五印坛城→出口\n"
                    "特色体验：在梵宫欣赏《吉祥颂》演出。"
                ),
            ),
            make_chunk(
                category="scenery",
                chunk_index=1,
                text="灵山精舍：景区内禅意酒店，含素斋与早课体验，适合深度感受佛教文化。",
            ),
        ]

        answer = build_structured_answer("第一次来灵山胜境应该怎么逛？", sources)

        self.assertIn("南门入园", answer)
        self.assertIn("灵山大佛", answer)
        self.assertNotIn("灵山精舍", answer)

    def test_overview_query_summarizes_core_spots(self) -> None:
        sources = [
            make_chunk(
                category="route",
                text=(
                    "核心景点特色详解：佛教艺术的殿堂\n"
                    "灵山大佛：世界最高露天青铜释迦牟尼立像\n"
                    "灵山梵宫：佛教艺术的瑰宝\n"
                    "九龙灌浴：佛陀诞生的神圣再现\n"
                    "五印坛城：藏传佛教文化的珍宝\n"
                    "祥符禅寺：千年古刹的历史遗存"
                ),
            )
        ]

        answer = build_structured_answer("灵山胜境有哪些核心景点？", sources)

        self.assertIn("灵山大佛", answer)
        self.assertIn("灵山梵宫", answer)
        self.assertIn("九龙灌浴", answer)

    def test_timeline_query_extracts_year_and_phase(self) -> None:
        sources = [
            make_chunk(
                category="history",
                text=(
                    "2003年：二期工程建成开放，以九龙灌浴为主体，完成了佛诞园四相成道的轴线布局。\n"
                    "1997年11月15日：灵山大佛落成开光。"
                ),
            )
        ]

        answer = build_structured_answer("九龙灌浴属于灵山胜境哪一期工程？", sources)

        self.assertIn("2003", answer)
        self.assertIn("二期工程", answer)


class ClarificationResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_marks_user_reply_as_followup_when_it_answers_previous_clarification(self) -> None:
        resolver = ClarificationResolver(Settings(chat_mode="rag"))

        result = await resolver.resolve(
            original_question="开放时间是什么时候？",
            assistant_followup_question="你想问的是景区整体开放时间，还是商铺/夜游时间？",
            user_reply="我想问景区整体开放时间。",
        )

        self.assertTrue(result.continues_clarification)
        self.assertIn("景区整体", result.resolved_question)

    async def test_marks_unrelated_user_reply_as_new_question(self) -> None:
        resolver = ClarificationResolver(Settings(chat_mode="rag"))

        result = await resolver.resolve(
            original_question="开放时间是什么时候？",
            assistant_followup_question="你想问的是景区整体开放时间，还是商铺/夜游时间？",
            user_reply="这里有什么历史故事？",
        )

        self.assertFalse(result.continues_clarification)
        self.assertEqual(result.resolved_question, "这里有什么历史故事？")


class RAGReplyDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ambiguous_schedule_question_returns_answer_with_followup(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag"))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="schedule",
                    text=(
                        "拈花湾小镇开放时间为9:00-21:30，冬季闭园时间会提前。\n"
                        "商铺营业时间一般为9:30-21:00，部分餐饮会延长到21:30。\n"
                        "夜间18:00点亮灯笼，21:30关闭。"
                    ),
                    title="拈花湾小镇开放与夜游时间说明",
                )
            ]
        )
        service.llm = SimpleNamespace(
            complete=self._async_return(
                json.dumps(
                    {
                        "reply_kind": "answer",
                        "needs_followup": True,
                        "spoken_answer": "景区整体开放一般是 9:00 到 21:30，冬季闭园会稍早一些。",
                        "followup_question": "如果你问的是商铺或夜游时间，我也可以继续帮你细看。",
                        "missing_slots": ["target_scope"],
                        "used_source_indexes": [1],
                        "confidence_note": "partial",
                    },
                    ensure_ascii=False,
                )
            )
        )

        answer = await service.answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertIn("9:00", answer.answer_text)
        self.assertIn("如果你问的是商铺或夜游时间", answer.answer_text)
        self.assertNotIn("参考资料", answer.answer_text)
        self.assertTrue(answer.needs_followup)
        self.assertEqual(answer.reply_kind, "answer")
        self.assertEqual(answer.missing_slots, ["target_scope"])
        self.assertEqual(len(answer.sources), 1)

    async def test_invalid_decision_json_falls_back_to_humanized_answer(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag"))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="schedule",
                    text="景区开放时间为9:00-21:30，冬季闭园会提前。",
                    title="景区开放时间",
                )
            ]
        )
        service.llm = SimpleNamespace(complete=self._async_return("not-json"))

        answer = await service.answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertTrue(answer.answer_text)
        self.assertNotIn("参考资料", answer.answer_text)
        self.assertIn("9:00", answer.answer_text)

    @staticmethod
    def _async_return(value):
        async def _inner(*args, **kwargs):
            return value

        return _inner


if __name__ == "__main__":
    unittest.main()
