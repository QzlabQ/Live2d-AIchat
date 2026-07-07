import unittest

from scripts.evaluate_rag import EvalCase, evaluate_case


class EvaluateCaseTests(unittest.TestCase):
    def test_supports_keyword_groups_and_inline_citation_requirement(self) -> None:
        case = EvalCase(
            question="灵山胜境有哪些核心景点？",
            expected_keywords=["核心景点"],
            expected_keyword_groups=[["灵山大佛", "大佛"], ["灵山梵宫", "梵宫"]],
            requires_citations=True,
        )

        result = evaluate_case(
            case,
            "灵山胜境的核心景点包括灵山大佛、梵宫和九龙灌浴。\n\n参考资料：\n[1] 灵山胜境导览.docx",
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.missing_keywords, [])
        self.assertEqual(result.missing_groups, [])

    def test_accepts_sources_as_citation_evidence(self) -> None:
        case = EvalCase(
            question="九龙灌浴讲的是什么故事？",
            expected_keyword_groups=[["释迦牟尼", "佛陀诞生"], ["九龙吐水", "花开见佛"]],
            requires_citations=True,
        )

        result = evaluate_case(
            case,
            "九龙灌浴主要讲述的是释迦牟尼佛诞生的故事。表演会生动还原典籍中“花开见佛、九龙吐水”的经典场景。",
            sources=[{"title": "九龙灌浴资料", "filename": "guide.docx"}],
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.missing_groups, [])
        self.assertTrue(result.citation_satisfied)

    def test_route_planning_keyword_accepts_natural_route_language(self) -> None:
        case = EvalCase(
            question="亲子家庭来灵山胜境怎么安排路线？",
            expected_keywords=["路线规划"],
            expected_keyword_groups=[["百子戏弥勒"], ["佛手广场", "天下第一掌"], ["五印坛城"]],
            requires_citations=True,
        )

        result = evaluate_case(
            case,
            "推荐您走这条4小时的亲子轻松路线：从南门入园先看九龙灌浴表演，接着去佛手广场摸“天下第一掌”祈福，再到百子戏弥勒感受童趣，最后在五印坛城转转经筒互动。",
            sources=[{"title": "亲子路线资料", "filename": "route.docx"}],
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.missing_keywords, [])

    def test_standard_refusal_phrase_is_accepted(self) -> None:
        case = EvalCase(
            question="现在无锡今天会下雨吗？",
            expected_keywords=[],
            expects_refusal=True,
        )

        result = evaluate_case(case, "这个问题超出了我当前的景区知识范围。你可以继续问我景点、历史、路线或参观建议。")

        self.assertTrue(result.passed)
        self.assertTrue(result.refusal_satisfied)

    def test_refusal_cases_fail_when_answer_goes_out_of_scope(self) -> None:
        case = EvalCase(
            question="你会解微积分吗？",
            expected_keywords=[],
            expects_refusal=True,
            unexpected_keywords=["积分公式"],
        )

        result = evaluate_case(case, "积分公式里最常见的是牛顿-莱布尼茨公式。")

        self.assertFalse(result.passed)
        self.assertTrue(result.unexpected_hits)
        self.assertFalse(result.refusal_satisfied)


if __name__ == "__main__":
    unittest.main()
