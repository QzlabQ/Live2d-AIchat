import unittest

from scripts.evaluate_rag import EvalCase, evaluate_case


class EvaluateCaseTests(unittest.TestCase):
    def test_supports_keyword_groups_and_citation_requirement(self) -> None:
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
