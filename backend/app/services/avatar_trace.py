from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "avatar_trace.log"


@dataclass(slots=True)
class ReplyTrace:
    reply_id: str
    session_id: str
    streaming: bool
    chat_mode: str
    tts_engine: str
    prompt_cache_hit: bool | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metrics: dict[str, int] = field(default_factory=dict)
    segment_count: int = 0
    audio_chunk_count: int = 0
    max_chunk_gap_ms: int = 0
    _last_audio_chunk_at_ms: int | None = field(default=None, init=False, repr=False)

    def mark(self, name: str, at_ms: int) -> None:
        if name not in self.metrics:
            self.metrics[name] = int(at_ms)

    def observe_audio_chunk(self, at_ms: int) -> None:
        observed_at = int(at_ms)
        self.audio_chunk_count += 1
        if self._last_audio_chunk_at_ms is not None:
            self.max_chunk_gap_ms = max(
                self.max_chunk_gap_ms,
                observed_at - self._last_audio_chunk_at_ms,
            )
        self._last_audio_chunk_at_ms = observed_at

    def to_payload(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "reply_id": self.reply_id,
            "session_id": self.session_id,
            "streaming": self.streaming,
            "chat_mode": self.chat_mode,
            "tts_engine": self.tts_engine,
            "prompt_cache_hit": self.prompt_cache_hit,
            "segment_count": self.segment_count,
            "audio_chunk_count": self.audio_chunk_count,
            "max_chunk_gap_ms": self.max_chunk_gap_ms,
            "metrics": dict(self.metrics),
        }


class TraceLoggerWorker:
    def __init__(self, log_path: Path | str = _DEFAULT_LOG_PATH) -> None:
        self.log_path = Path(log_path)
        self._queue: asyncio.Queue[ReplyTrace | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="avatar-trace-logger")

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None

    def enqueue(self, trace: ReplyTrace) -> None:
        self._queue.put_nowait(trace)

    async def _run(self) -> None:
        while True:
            trace = await self._queue.get()
            try:
                if trace is None:
                    return
                await asyncio.to_thread(self._append_trace, trace)
            except Exception:
                logger.exception("Failed to write avatar trace.")
            finally:
                self._queue.task_done()

    def _append_trace(self, trace: ReplyTrace) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(trace.to_payload(), ensure_ascii=False, sort_keys=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class AvatarTraceService:
    def __init__(self, worker: TraceLoggerWorker | None = None) -> None:
        self.worker = worker or TraceLoggerWorker()

    async def start(self) -> None:
        await self.worker.start()

    async def stop(self) -> None:
        await self.worker.stop()

    def enqueue_trace(self, trace: ReplyTrace) -> None:
        self.worker.enqueue(trace)


_avatar_trace_service: AvatarTraceService | None = None


def get_avatar_trace_service() -> AvatarTraceService:
    global _avatar_trace_service
    if _avatar_trace_service is None:
        _avatar_trace_service = AvatarTraceService()
    return _avatar_trace_service
