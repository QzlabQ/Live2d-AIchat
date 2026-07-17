import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.services.rag import (
    ClarificationResolver,
    DashScopeChatCompletionsClient,
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
    def test_default_persona_mentions_lingshan(self) -> None:
        self.assertIn("灵山胜境", Settings().default_avatar_persona)

    def test_default_persona_mentions_on_site_guidance_and_cultural_explanations(self) -> None:
        persona = Settings().default_avatar_persona
        self.assertIn("现场问路", persona)
        self.assertIn("历史文化", persona)

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
        resolver = ClarificationResolver(Settings(chat_mode="rag", dashscope_api_key=None))

        result = await resolver.resolve(
            original_question="开放时间是什么时候？",
            assistant_followup_question="你想问的是景区整体开放时间，还是商铺/夜游时间？",
            user_reply="我想问景区整体开放时间。",
        )

        self.assertTrue(result.continues_clarification)
        self.assertIn("景区整体", result.resolved_question)

    async def test_marks_unrelated_user_reply_as_new_question(self) -> None:
        resolver = ClarificationResolver(Settings(chat_mode="rag", dashscope_api_key=None))

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
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))
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
        answer = await service.answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertIn("9:00", answer.answer_text)
        self.assertIn("商铺", answer.answer_text)
        self.assertIn("夜游", answer.answer_text)
        self.assertNotIn("参考资料", answer.answer_text)
        self.assertTrue(answer.needs_followup)
        self.assertEqual(answer.reply_kind, "answer")
        self.assertTrue(answer.followup_question)
        self.assertIn("商铺", answer.followup_question)
        self.assertIn("夜游", answer.followup_question)
        self.assertEqual(answer.missing_slots, ["target_scope"])
        self.assertEqual(len(answer.sources), 1)

    async def test_answer_falls_back_to_local_humanized_answer_without_llm(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))
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

    def test_builds_answer_only_prompt_when_avatar_language_is_en(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))

        messages = service._build_answer_messages(
            question="开放时间是什么时候？",
            persona="You are a witty guide.",
            context="[1] 景区开放时间 9:00-21:30",
            history=[],
            fallback_text="The scenic area generally opens at 9:00.",
            needs_followup=False,
            followup_question="",
            response_language="en",
        )

        self.assertIn("natural, concise spoken English", messages[0]["content"])
        self.assertIn("Do not output JSON", messages[0]["content"])
        self.assertIn("The scenic area generally opens at 9:00.", messages[1]["content"])

    def test_answer_prompt_reuses_followup_question_verbatim(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))

        followup_question = "如果你问的是商铺、夜游或演出时间，我也可以继续帮你细看。"
        messages = service._build_answer_messages(
            question="开放时间是什么时候？",
            persona="guide",
            context="[1] 景区开放时间 9:00-21:30",
            history=[],
            fallback_text="景区整体开放一般是 9:00-21:30。",
            needs_followup=True,
            followup_question=followup_question,
            response_language="zh",
        )

        self.assertIn("最后一句必须原样输出这句追问", messages[0]["content"])
        self.assertIn(followup_question, messages[1]["content"])

    def test_answer_prompt_prioritizes_canonical_spot_name_for_photo_identification(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))

        messages = service._build_answer_messages(
            question="这是哪个景点？",
            persona="guide",
            context="[1] 五印坛城：采用藏式建筑风格。",
            history=[],
            fallback_text="这是五印坛城。它采用藏式建筑风格。",
            needs_followup=False,
            followup_question="",
            response_language="zh",
            photo_context={
                "recognized_spot": "五印坛城",
                "recognized_spot_canonical": True,
                "recognition_summary": "图片主体是一座藏式白塔建筑。",
            },
        )

        self.assertIn("第一句必须直接回答“这是五印坛城。”", messages[0]["content"])

    async def test_prepare_stream_answer_records_rag_stage_metrics(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key="key"))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="schedule",
                    text="景区开放时间为9:00-21:30，冬季闭园会提前。",
                    title="景区开放时间",
                )
            ]
        )
        service.llm = SimpleNamespace(complete=AsyncMock(side_effect=AssertionError("should not run decision LLM")))

        prepared = await service.prepare_stream_answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertIn("rag_prepare_total_ms", prepared.metrics)
        self.assertIn("rag_retrieve_ms", prepared.metrics)
        self.assertIn("rag_rerank_ms", prepared.metrics)
        self.assertEqual(prepared.metrics["rag_decision_llm_ms"], 0)
        self.assertTrue(prepared.llm_messages)
        self.assertIn("9:00", prepared.fallback_text)

    async def test_prepare_stream_answer_uses_local_followup_meta_when_streaming_llm_answer(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key="key"))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="schedule",
                    text=(
                        "景区开放时间为9:00-21:30，冬季闭园会提前。\n"
                        "商铺营业时间一般为9:30-21:00。\n"
                        "夜游灯光开放时间一般持续到21:30。"
                    ),
                    title="景区开放与夜游时间",
                    rerank_score=0.6,
                )
            ]
        )
        service.llm = SimpleNamespace(complete=AsyncMock(side_effect=AssertionError("should not run decision LLM")))

        prepared = await service.prepare_stream_answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertTrue(prepared.llm_messages)
        self.assertEqual(prepared.reply_kind, "answer")
        self.assertTrue(prepared.needs_followup)
        self.assertEqual(prepared.missing_slots, ["target_scope"])
        self.assertIn("商铺", prepared.followup_question)
        self.assertEqual(prepared.confidence_note, "partial")
        self.assertEqual(prepared.metrics["rag_decision_llm_ms"], 0)

    async def test_prepare_stream_answer_uses_split_retrieve_metrics_when_available(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))

        async def fake_retrieve(*args, **kwargs):
            service._retrieve_metrics.set(
                {
                    "rag_embed_ms": 11,
                    "rag_vector_search_ms": 22,
                    "rag_retrieve_ms": 33,
                    "rag_rerank_ms": 44,
                    "rag_retrieve_total_ms": 77,
                }
            )
            return [
                make_chunk(
                    category="schedule",
                    text="景区开放时间为9:00-21:30，冬季闭园会提前。",
                    title="景区开放时间",
                )
            ]

        service.retrieve = fake_retrieve

        prepared = await service.prepare_stream_answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertEqual(prepared.metrics["rag_embed_ms"], 11)
        self.assertEqual(prepared.metrics["rag_vector_search_ms"], 22)
        self.assertEqual(prepared.metrics["rag_retrieve_ms"], 33)
        self.assertEqual(prepared.metrics["rag_rerank_ms"], 44)
        self.assertEqual(prepared.metrics["rag_retrieve_total_ms"], 77)

    async def test_prepare_stream_answer_records_metrics_for_empty_question(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))

        prepared = await service.prepare_stream_answer("   ", persona="guide", history=[])

        self.assertEqual(prepared.reply_kind, "refuse")
        self.assertIn("rag_prepare_total_ms", prepared.metrics)
        self.assertEqual(prepared.metrics["rag_retrieve_ms"], 0)
        self.assertEqual(prepared.metrics["rag_decision_llm_ms"], 0)

    async def test_fast_humanized_schedule_skips_decision_llm_for_high_confidence_fallback(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(
                Settings(chat_mode="rag", dashscope_api_key="key", rag_response_mode="fast_humanized")
            )
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="schedule",
                    text="景区开放时间为9:00-21:30，冬季闭园会提前。",
                    title="景区开放时间",
                    rerank_score=1.2,
                )
            ]
        )

        async def fail_if_called(*args, **kwargs):
            raise AssertionError("decision LLM should be skipped for fast high-confidence schedule answers")

        service.llm = SimpleNamespace(complete=fail_if_called)

        prepared = await service.prepare_stream_answer("开放时间是什么时候？", persona="guide", history=[])

        self.assertFalse(prepared.used_llm)
        self.assertIn("9:00", prepared.answer_text)
        self.assertEqual(prepared.metrics["rag_decision_llm_ms"], 0)

    async def test_instructional_guide_wording_is_removed_from_fallback_answer(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="route",
                    text=(
                        "九龙灌浴：用生动语言讲述释迦牟尼诞生的故事，让孩子理解佛教文化中的慈悲精神。"
                        "表演会还原“花开见佛、九龙吐水”的经典场景。"
                    ),
                    title="亲子导览讲解建议",
                    rerank_score=0.92,
                )
            ]
        )

        answer = await service.answer("九龙灌浴讲的是什么故事？", persona="guide", history=[])

        self.assertIn("释迦牟尼", answer.answer_text)
        self.assertIn("花开见佛", answer.answer_text)
        self.assertNotIn("用生动语言讲述", answer.answer_text)
        self.assertNotIn("让孩子理解", answer.answer_text)

    async def test_photo_identification_answer_starts_with_canonical_spot_name(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))
        service.retrieve = self._async_return(
            [
                make_chunk(
                    category="scenery",
                    text=(
                        "五印坛城：灵山胜境的重要景点之一，采用藏式建筑风格，"
                        "白墙红边金顶，常用于游客参观与宗教文化展示。"
                    ),
                    title="灵山胜境景点结构化数据集",
                    rerank_score=0.96,
                )
            ]
        )

        answer = await service.answer(
            "这是哪个景点？",
            persona="guide",
            history=[],
            photo_context={
                "recognized_spot": "五印坛城",
                "recognized_spot_canonical": True,
                "recognition_summary": "图片主体是一座藏式白塔建筑。",
            },
        )

        self.assertTrue(answer.answer_text.startswith("这是五印坛城。"))
        self.assertIn("藏式建筑", answer.answer_text)

    async def test_noncanonical_photo_identification_uses_conservative_hint(self) -> None:
        with (
            patch("app.services.rag.KnowledgeVectorStore", return_value=SimpleNamespace()),
            patch("app.services.rag.build_embedding_service", return_value=SimpleNamespace()),
        ):
            service = ScenicRAGService(Settings(chat_mode="rag", dashscope_api_key=None))
        service.retrieve = self._async_return([])

        answer = await service.answer(
            "这是哪个景点？",
            persona="guide",
            history=[],
            photo_context={
                "recognized_spot": "灵山胜境",
                "recognized_spot_canonical": False,
                "recognition_summary": "画面展示景区建筑，但没有足够线索确认具体景点。",
            },
        )

        self.assertIn("从图片看起来像是灵山胜境", answer.answer_text)
        self.assertFalse(answer.answer_text.startswith("这是灵山胜境。"))

    @staticmethod
    def _async_return(value):
        async def _inner(*args, **kwargs):
            return value

        return _inner


class DashScopeChatCompletionsClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_disables_thinking_in_payload(self) -> None:
        captured: dict[str, object] = {}

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"choices": [{"message": {"content": "ok"}}]}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb

            async def post(self, url: str, json: dict[str, object], headers: dict[str, str]):
                del url, headers
                captured.update(json)
                return FakeResponse()

        client = DashScopeChatCompletionsClient(Settings(dashscope_api_key="key"))

        with patch("app.services.rag.httpx.AsyncClient", FakeAsyncClient):
            result = await client.complete([{"role": "user", "content": "hello"}])

        self.assertEqual(result, "ok")
        self.assertIs(captured["enable_thinking"], False)

    async def test_stream_complete_disables_thinking_in_payload(self) -> None:
        captured: dict[str, object] = {}

        class FakeStreamResponse:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb

            def raise_for_status(self) -> None:
                return None

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
                yield "data: [DONE]"

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb

            def stream(self, method: str, url: str, json: dict[str, object], headers: dict[str, str]):
                del method, url, headers
                captured.update(json)
                return FakeStreamResponse()

        client = DashScopeChatCompletionsClient(Settings(dashscope_api_key="key"))

        with patch("app.services.rag.httpx.AsyncClient", FakeAsyncClient):
            chunks = [chunk async for chunk in client.stream_complete([{"role": "user", "content": "hello"}])]

        self.assertEqual(chunks, ["hello"])
        self.assertIs(captured["enable_thinking"], False)


if __name__ == "__main__":
    unittest.main()
