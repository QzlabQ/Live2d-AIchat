#!/usr/bin/env python3
# Usage: python deploy/native/benchmark_avatar_trace.py --limit 20 [--only-vllm]
# Purpose: summarize recent backend/logs/avatar_trace.log replies using supply_ratio, token_wait, and token2wav style metrics.

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
import statistics
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_PATH = REPO_ROOT / "backend" / "logs" / "avatar_trace.log"


@dataclass(frozen=True)
class ReplyBenchmark:
    created_at: str
    reply_id: str
    streaming: bool
    load_trt: bool | None
    load_vllm: bool | None
    chunk_count: int
    audio_ms: int
    first_chunk_sent_at_ms: int | None
    first_audio_ms: int | None
    audio_done_ms: int | None
    supply_ratio: float | None
    steady_supply_ratio: float | None
    positive_supply_lag_ms: int
    max_supply_lag_ms: int
    token_wait_ms: int
    token2wav_ms: int
    avg_token_wait_ms: float
    avg_token2wav_ms: float
    avg_chunk_rtf: float
    max_chunk_rtf: float
    max_chunk_gap_ms: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize recent avatar_trace replies for backend-side trace benchmarking."
    )
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_PATH),
        help="Path to backend/logs/avatar_trace.log.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent replies to report.",
    )
    parser.add_argument(
        "--only-vllm",
        action="store_true",
        help="Only include replies where tts_cosyvoice_load_vllm=true.",
    )
    parser.add_argument(
        "--streaming-only",
        action="store_true",
        help="Only include replies where streaming=true.",
    )
    return parser.parse_args()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    lower_value = values[lower_index]
    upper_value = values[upper_index]
    return lower_value + (upper_value - lower_value) * (position - lower_index)


def format_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def coerce_chunks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = payload.get("tts_chunks")
    if not isinstance(chunks, list):
        return []
    return [chunk for chunk in chunks if isinstance(chunk, dict)]


def benchmark_reply(payload: dict[str, Any]) -> ReplyBenchmark | None:
    chunks = coerce_chunks(payload)
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}

    if not chunks:
        return None

    audio_ms = sum(max(int(chunk.get("tts_chunk_audio_ms", 0)), 0) for chunk in chunks)
    token_wait_ms = int(metrics.get("tts_total_token_wait_ms", 0))
    if token_wait_ms <= 0:
        token_wait_ms = sum(max(int(chunk.get("token_wait_ms", 0)), 0) for chunk in chunks)
    token2wav_ms = int(metrics.get("tts_total_token2wav_ms", 0))
    if token2wav_ms <= 0:
        token2wav_ms = sum(max(int(chunk.get("token2wav_ms", 0)), 0) for chunk in chunks)

    chunk_gaps = [max(int(chunk.get("tts_chunk_gap_ms", 0)), 0) for chunk in chunks[1:]]
    prior_audio = [max(int(chunk.get("tts_chunk_audio_ms", 0)), 0) for chunk in chunks[:-1]]
    gap_budget_ms = sum(chunk_gaps)
    cover_audio_ms = sum(prior_audio)
    steady_supply_ratio = None if gap_budget_ms <= 0 else cover_audio_ms / gap_budget_ms

    first_chunk_sent_at_ms = int(chunks[0].get("sent_at_ms", 0)) if chunks else None
    audio_done_ms = int(metrics["audio_done_ms"]) if "audio_done_ms" in metrics else None
    supply_ratio = None
    if (
        first_chunk_sent_at_ms is not None
        and audio_done_ms is not None
        and audio_done_ms > first_chunk_sent_at_ms
    ):
        supply_ratio = audio_ms / (audio_done_ms - first_chunk_sent_at_ms)

    supply_lags = [max(int(chunk.get("chunk_supply_lag_ms", 0)), 0) for chunk in chunks[1:]]
    positive_supply_lag_ms = sum(supply_lags)
    max_supply_lag_ms = max(supply_lags, default=0)
    chunk_rtfs = [float(chunk.get("tts_chunk_rtf", 0.0)) for chunk in chunks]

    chunk_count = len(chunks)
    return ReplyBenchmark(
        created_at=str(payload.get("created_at", "")),
        reply_id=str(payload.get("reply_id", "")),
        streaming=bool(payload.get("streaming", False)),
        load_trt=payload.get("tts_cosyvoice_load_trt"),
        load_vllm=payload.get("tts_cosyvoice_load_vllm"),
        chunk_count=chunk_count,
        audio_ms=audio_ms,
        first_chunk_sent_at_ms=first_chunk_sent_at_ms,
        first_audio_ms=int(metrics["tts_first_audio_chunk_ms"]) if "tts_first_audio_chunk_ms" in metrics else None,
        audio_done_ms=audio_done_ms,
        supply_ratio=supply_ratio,
        steady_supply_ratio=steady_supply_ratio,
        positive_supply_lag_ms=positive_supply_lag_ms,
        max_supply_lag_ms=max_supply_lag_ms,
        token_wait_ms=token_wait_ms,
        token2wav_ms=token2wav_ms,
        avg_token_wait_ms=(token_wait_ms / chunk_count) if chunk_count else 0.0,
        avg_token2wav_ms=(token2wav_ms / chunk_count) if chunk_count else 0.0,
        avg_chunk_rtf=statistics.mean(chunk_rtfs) if chunk_rtfs else 0.0,
        max_chunk_rtf=max(chunk_rtfs, default=0.0),
        max_chunk_gap_ms=max(int(payload.get("max_chunk_gap_ms", 0)), 0),
    )


def load_recent_benchmarks(
    log_path: Path,
    *,
    limit: int,
    only_vllm: bool,
    streaming_only: bool,
) -> tuple[list[ReplyBenchmark], int]:
    rows: deque[ReplyBenchmark] = deque(maxlen=max(limit, 1))
    skipped_invalid = 0

    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                skipped_invalid += 1
                continue
            if not isinstance(payload, dict):
                skipped_invalid += 1
                continue
            if only_vllm and payload.get("tts_cosyvoice_load_vllm") is not True:
                continue
            if streaming_only and payload.get("streaming") is not True:
                continue
            benchmark = benchmark_reply(payload)
            if benchmark is None:
                skipped_invalid += 1
                continue
            rows.append(benchmark)
    return list(rows), skipped_invalid


def print_summary(rows: list[ReplyBenchmark], *, log_path: Path, skipped_invalid: int) -> None:
    supply_values = [row.supply_ratio for row in rows if row.supply_ratio is not None]
    steady_supply_values = [row.steady_supply_ratio for row in rows if row.steady_supply_ratio is not None]
    token_wait_values = [float(row.token_wait_ms) for row in rows]
    token2wav_values = [float(row.token2wav_ms) for row in rows]
    first_audio_values = [float(row.first_audio_ms) for row in rows if row.first_audio_ms is not None]
    avg_rtf_values = [row.avg_chunk_rtf for row in rows]

    print("Trace summary")
    print(f"log_file={log_path}")
    print(f"replies={len(rows)} skipped_invalid_rows={skipped_invalid}")
    print(
        "supply_ratio avg=%s p50=%s p10=%s min=%s"
        % (
            format_float(statistics.mean(supply_values) if supply_values else None),
            format_float(percentile(supply_values, 0.50)),
            format_float(percentile(supply_values, 0.10)),
            format_float(min(supply_values) if supply_values else None),
        )
    )
    print(
        "steady_supply_ratio avg=%s p50=%s p10=%s min=%s"
        % (
            format_float(statistics.mean(steady_supply_values) if steady_supply_values else None),
            format_float(percentile(steady_supply_values, 0.50)),
            format_float(percentile(steady_supply_values, 0.10)),
            format_float(min(steady_supply_values) if steady_supply_values else None),
        )
    )
    print(
        "token_wait_ms avg=%s p50=%s p95=%s"
        % (
            format_float(statistics.mean(token_wait_values) if token_wait_values else None),
            format_float(percentile(token_wait_values, 0.50)),
            format_float(percentile(token_wait_values, 0.95)),
        )
    )
    print(
        "token2wav_ms avg=%s p50=%s p95=%s"
        % (
            format_float(statistics.mean(token2wav_values) if token2wav_values else None),
            format_float(percentile(token2wav_values, 0.50)),
            format_float(percentile(token2wav_values, 0.95)),
        )
    )
    print(
        "tts_first_audio_chunk_ms avg=%s p50=%s p95=%s"
        % (
            format_float(statistics.mean(first_audio_values) if first_audio_values else None),
            format_float(percentile(first_audio_values, 0.50)),
            format_float(percentile(first_audio_values, 0.95)),
        )
    )
    print(
        "avg_chunk_rtf avg=%s p95=%s"
        % (
            format_float(statistics.mean(avg_rtf_values) if avg_rtf_values else None, digits=3),
            format_float(percentile(avg_rtf_values, 0.95), digits=3),
        )
    )
    print("")
    print("Recent replies")
    for row in rows:
        print(
            "%s reply=%s chunks=%s audio_ms=%s first_chunk_sent_at_ms=%s first_audio_ms=%s audio_done_ms=%s "
            "supply_ratio=%s steady_supply_ratio=%s supply_lag_ms=%s max_supply_lag_ms=%s token_wait_ms=%s avg_token_wait_ms=%s "
            "token2wav_ms=%s avg_token2wav_ms=%s avg_chunk_rtf=%s max_chunk_gap_ms=%s trt=%s vllm=%s"
            % (
                row.created_at or "unknown_time",
                row.reply_id or "unknown_reply",
                row.chunk_count,
                row.audio_ms,
                row.first_chunk_sent_at_ms if row.first_chunk_sent_at_ms is not None else "n/a",
                row.first_audio_ms if row.first_audio_ms is not None else "n/a",
                row.audio_done_ms if row.audio_done_ms is not None else "n/a",
                format_float(row.supply_ratio),
                format_float(row.steady_supply_ratio),
                row.positive_supply_lag_ms,
                row.max_supply_lag_ms,
                row.token_wait_ms,
                format_float(row.avg_token_wait_ms),
                row.token2wav_ms,
                format_float(row.avg_token2wav_ms),
                format_float(row.avg_chunk_rtf, digits=3),
                row.max_chunk_gap_ms,
                row.load_trt,
                row.load_vllm,
            )
        )
    print("")
    print(
        "Formula: supply_ratio = sum(tts_chunk_audio_ms) / (audio_done_ms - first_chunk_sent_at_ms). "
        "steady_supply_ratio = sum(previous chunk audio_ms) / sum(next chunk gap_ms)."
    )


def main() -> int:
    args = parse_args()
    log_path = Path(args.log_file).expanduser()
    if not log_path.is_file():
        raise SystemExit(f"avatar trace log not found: {log_path}")
    if args.limit <= 0:
        raise SystemExit("--limit must be a positive integer.")

    rows, skipped_invalid = load_recent_benchmarks(
        log_path,
        limit=args.limit,
        only_vllm=args.only_vllm,
        streaming_only=args.streaming_only,
    )
    if not rows:
        raise SystemExit("no matching replies found in avatar trace log.")

    print_summary(rows, log_path=log_path, skipped_invalid=skipped_invalid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
