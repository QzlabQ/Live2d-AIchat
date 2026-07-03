from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from app.services.chat import get_chat_service


@dataclass(slots=True)
class EvalCase:
    question: str
    expected_keywords: list[str]
    persona: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the Phase 2 RAG answer quality on a JSONL dataset.")
    parser.add_argument("--dataset", required=True, help="Path to a JSONL file that contains evaluation cases.")
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
        persona = payload.get("persona")
        if not question:
            raise ValueError(f"Dataset line {line_number} is missing a question.")
        rows.append(EvalCase(question=question, expected_keywords=expected_keywords, persona=persona))
    return rows


async def run(dataset: Path) -> int:
    service = get_chat_service()
    cases = load_cases(dataset)
    if not cases:
        print("No evaluation cases were found.")
        return 1

    passed = 0
    for index, case in enumerate(cases, start=1):
        reply = await service.generate_reply(case.question, persona=case.persona)
        answer_text = reply.text
        matched = [keyword for keyword in case.expected_keywords if keyword in answer_text]
        success = len(matched) == len(case.expected_keywords)
        if success:
            passed += 1

        print(f"[{index}] Q: {case.question}")
        print(f"    A: {answer_text}")
        print(f"    matched: {matched or '[]'}")
        print(f"    result: {'PASS' if success else 'FAIL'}")

    accuracy = passed / len(cases)
    print("")
    print(f"Total cases: {len(cases)}")
    print(f"Passed: {passed}")
    print(f"Accuracy: {accuracy:.2%}")
    return 0 if passed == len(cases) else 1


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run(Path(args.dataset))))


if __name__ == "__main__":
    main()
