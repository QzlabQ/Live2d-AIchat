from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.services.chat import get_chat_service

REFUSAL_HINTS = ("暂时无法确认", "景区知识库")
REFUSAL_COMPOUND_HINTS = (
    ("超出", "景区知识范围"),
    ("超出了", "景区知识范围"),
    ("不在", "景区知识范围"),
)
INLINE_CITATION_MARKERS = ("参考资料：", "[1]")
ROUTE_PLANNING_KEYWORD = "路线规划"
ROUTE_DIRECT_HINTS = ("路线", "行程", "游览顺序", "参观顺序", "路线推荐", "路线安排", "逛法")
ROUTE_SEQUENCE_HINTS = ("先", "再", "接着", "然后", "最后", "依次")
ROUTE_START_HINTS = ("从", "先从")


@dataclass(slots=True)
class EvalCase:
    question: str
    expected_keywords: list[str] = field(default_factory=list)
    expected_keyword_groups: list[list[str]] = field(default_factory=list)
    unexpected_keywords: list[str] = field(default_factory=list)
    expects_refusal: bool = False
    requires_citations: bool = False
    persona: str | None = None


@dataclass(slots=True)
class EvalResult:
    passed: bool
    matched_keywords: list[str]
    missing_keywords: list[str]
    matched_groups: list[list[str]]
    missing_groups: list[list[str]]
    unexpected_hits: list[str]
    refusal_satisfied: bool
    citation_satisfied: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the Phase 2 RAG answer quality on a JSONL dataset.")
    parser.add_argument("--dataset", required=True, help="Path to a JSONL file that contains evaluation cases.")
    parser.add_argument(
        "--target",
        type=float,
        default=1.0,
        help="Minimum accuracy target. Defaults to 1.0 to preserve the original strict behavior.",
    )
    return parser


def load_cases(path: Path) -> list[EvalCase]:
    rows: list[EvalCase] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        payload = json.loads(line)
        question = str(payload["question"]).strip()
        expected_keywords = [str(item).strip() for item in payload.get("expected_keywords", []) if str(item).strip()]
        expected_keyword_groups = [
            [str(item).strip() for item in group if str(item).strip()]
            for group in payload.get("expected_keyword_groups", [])
            if isinstance(group, list)
        ]
        expected_keyword_groups = [group for group in expected_keyword_groups if group]
        unexpected_keywords = [
            str(item).strip() for item in payload.get("unexpected_keywords", []) if str(item).strip()
        ]
        expects_refusal = bool(payload.get("expects_refusal", False))
        requires_citations = bool(payload.get("requires_citations", False))
        persona = payload.get("persona")
        if not question:
            raise ValueError(f"Dataset line {line_number} is missing a question.")
        rows.append(
            EvalCase(
                question=question,
                expected_keywords=expected_keywords,
                expected_keyword_groups=expected_keyword_groups,
                unexpected_keywords=unexpected_keywords,
                expects_refusal=expects_refusal,
                requires_citations=requires_citations,
                persona=persona,
            )
        )
    return rows


def keyword_matches(keyword: str, answer_text: str) -> bool:
    if keyword in answer_text:
        return True

    if keyword == ROUTE_PLANNING_KEYWORD:
        if any(token in answer_text for token in ROUTE_DIRECT_HINTS):
            return True
        return any(token in answer_text for token in ROUTE_START_HINTS) and any(
            token in answer_text for token in ROUTE_SEQUENCE_HINTS
        )

    return False


def refusal_matches(answer_text: str) -> bool:
    if any(token in answer_text for token in REFUSAL_HINTS):
        return True

    return any(all(token in answer_text for token in group) for group in REFUSAL_COMPOUND_HINTS)


def evaluate_case(case: EvalCase, answer_text: str, *, sources: list[object] | None = None) -> EvalResult:
    matched_keywords = [keyword for keyword in case.expected_keywords if keyword_matches(keyword, answer_text)]
    missing_keywords = [keyword for keyword in case.expected_keywords if not keyword_matches(keyword, answer_text)]

    matched_groups: list[list[str]] = []
    missing_groups: list[list[str]] = []
    for group in case.expected_keyword_groups:
        matched = [keyword for keyword in group if keyword in answer_text]
        if matched:
            matched_groups.append(matched)
        else:
            missing_groups.append(group)

    unexpected_hits = [keyword for keyword in case.unexpected_keywords if keyword in answer_text]
    refusal_satisfied = (not case.expects_refusal) or refusal_matches(answer_text)
    citation_satisfied = (not case.requires_citations) or (
        all(token in answer_text for token in INLINE_CITATION_MARKERS) or bool(sources)
    )
    passed = (
        not missing_keywords
        and not missing_groups
        and not unexpected_hits
        and refusal_satisfied
        and citation_satisfied
    )
    return EvalResult(
        passed=passed,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        matched_groups=matched_groups,
        missing_groups=missing_groups,
        unexpected_hits=unexpected_hits,
        refusal_satisfied=refusal_satisfied,
        citation_satisfied=citation_satisfied,
    )


async def run(dataset: Path, target: float) -> int:
    service = get_chat_service()
    cases = load_cases(dataset)
    if not cases:
        print("No evaluation cases were found.")
        return 1

    passed = 0
    for index, case in enumerate(cases, start=1):
        reply = await service.generate_reply(case.question, persona=case.persona)
        answer_text = reply.text
        result = evaluate_case(case, answer_text, sources=reply.sources)
        if result.passed:
            passed += 1

        print(f"[{index}] Q: {case.question}")
        print(f"    A: {answer_text}")
        print(f"    matched keywords: {result.matched_keywords or '[]'}")
        if result.matched_groups:
            print(f"    matched groups: {result.matched_groups}")
        if result.missing_keywords:
            print(f"    missing keywords: {result.missing_keywords}")
        if result.missing_groups:
            print(f"    missing groups: {result.missing_groups}")
        if result.unexpected_hits:
            print(f"    unexpected hits: {result.unexpected_hits}")
        if case.expects_refusal:
            print(f"    refusal: {'OK' if result.refusal_satisfied else 'MISSING'}")
        if case.requires_citations:
            print(f"    citations: {'OK' if result.citation_satisfied else 'MISSING'}")
        print(f"    result: {'PASS' if result.passed else 'FAIL'}")

    accuracy = passed / len(cases)
    print("")
    print(f"Total cases: {len(cases)}")
    print(f"Passed: {passed}")
    print(f"Accuracy: {accuracy:.2%}")
    print(f"Target: {target:.2%}")
    return 0 if accuracy >= target else 1


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run(Path(args.dataset), target=args.target)))


if __name__ == "__main__":
    main()
