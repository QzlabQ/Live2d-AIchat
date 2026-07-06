# Avatar Action Tracing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Live2D 数字人增加明确的 `thinking / speaking / cooldown / idle` 阶段动作协调，并补齐后端非阻塞耗时 trace 日志，在不破坏现有流式文本、音频和口型协议的前提下提升自然度与可排障性。

**Architecture:** 后端在 `ws_router.py` 中新增 `avatar_phase` 事件发送和 `ReplyTrace` 采集，trace 通过后台 `asyncio.Queue` worker 异步写入独立日志文件；前端把新的阶段事件与现有 `emotion`、`tts_viseme_chunk` 合成统一的 avatar presentation，由 `App.vue` 管理状态、`Live2DStage.vue` 执行轻动作和 idle gating。

**Tech Stack:** FastAPI, asyncio, Python unittest/pytest, Vue 3, TypeScript, node:test, Pixi Live2D, WebSocket

---

## File Structure

- Create: `backend/app/services/avatar_trace.py`
  - 负责 `ReplyTrace`、`TraceLoggerWorker`、全局 trace service 生命周期和结构化日志落盘。
- Create: `backend/tests/test_avatar_trace.py`
  - 覆盖 trace 关键字段、chunk gap 统计、worker 异步写日志。
- Modify: `backend/app/api/ws_router.py:30-417`
  - 在回复主链路中插入 `avatar_phase` 事件、trace 打点、队列入栈和兜底阶段切换。
- Modify: `backend/app/main.py:21-31`
  - 在应用生命周期里启动 / 停止 trace worker。
- Modify: `backend/tests/test_chat_streaming.py:1-188`
  - 覆盖 `avatar_phase` 发送顺序、无音频兜底和 trace 指标写入。
- Create: `frontend/src/lib/avatarPresentation.ts`
  - 纯函数层，负责阶段状态、表现合成和前端降级策略。
- Create: `frontend/tests/avatarPresentation.test.ts`
  - 覆盖 `thinking` 优先级、`speaking` 轻动作、`cooldown` 回落和 stale 事件忽略。
- Modify: `frontend/src/types/chat.ts:30-191`
  - 新增 `ConversationPhase`、`AvatarPhaseEvent`、`AvatarPresentation` 类型。
- Modify: `frontend/src/App.vue:84-812`
  - 消费 `avatar_phase`、维护阶段状态、驱动调试面板和向 `Live2DStage` 下发 presentation。
- Modify: `frontend/src/components/Live2DStage.vue:75-346`
  - 增加阶段感知、idle motion gating、speaking/cooldown 轻动作控制。
- Modify: `docs/roadmap.md:58-78, 87-92`
  - 同步 Phase 2 里“动作协调”和“trace 调试”完成状态。

---

### Task 1: 搭好后端 Trace 基础设施

**Files:**
- Create: `backend/app/services/avatar_trace.py`
- Test: `backend/tests/test_avatar_trace.py`

- [ ] **Step 1: 先写后端 trace 的失败测试**

```python
import json
import tempfile
import unittest
from pathlib import Path

from app.services.avatar_trace import ReplyTrace, TraceLoggerWorker


class ReplyTraceTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_worker_writes_structured_summary_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "avatar_trace.log"
            worker = TraceLoggerWorker(log_path)
            await worker.start()

            trace = ReplyTrace(
                reply_id="reply-1",
                session_id="session-1",
                streaming=True,
                chat_mode="rag",
                tts_engine="cosyvoice",
            )
            trace.mark("avatar_phase_thinking_ms", 12)
            trace.mark("tts_first_audio_chunk_ms", 480)

            await worker.enqueue(trace)
            await worker.stop()

            payload = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["reply_id"], "reply-1")
            self.assertEqual(payload["avatar_phase_thinking_ms"], 12)
            self.assertEqual(payload["tts_first_audio_chunk_ms"], 480)

    def test_mark_keeps_first_timestamp_and_tracks_max_gap(self) -> None:
        trace = ReplyTrace(
            reply_id="reply-2",
            session_id="session-2",
            streaming=True,
            chat_mode="rag",
            tts_engine="cosyvoice",
        )

        trace.mark("llm_first_delta_ms", 90)
        trace.mark("llm_first_delta_ms", 180)
        trace.observe_audio_chunk(320)
        trace.observe_audio_chunk(470)

        self.assertEqual(trace.metrics["llm_first_delta_ms"], 90)
        self.assertEqual(trace.audio_chunk_count, 2)
        self.assertEqual(trace.max_chunk_gap_ms, 150)
```

- [ ] **Step 2: 运行测试并确认它先失败**

Run: `python -m pytest backend/tests/test_avatar_trace.py -q`

Expected: `FAIL`，提示 `ModuleNotFoundError: No module named 'app.services.avatar_trace'` 或 `ImportError: cannot import name 'ReplyTrace'`

- [ ] **Step 3: 写最小实现让测试通过**

```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReplyTrace:
    reply_id: str
    session_id: str
    streaming: bool
    chat_mode: str
    tts_engine: str
    metrics: dict[str, int] = field(default_factory=dict)
    prompt_cache_hit: bool | None = None
    segment_count: int = 0
    audio_chunk_count: int = 0
    max_chunk_gap_ms: int = 0
    _last_audio_chunk_ms: int | None = None

    def mark(self, name: str, value_ms: int) -> None:
        if name not in self.metrics:
            self.metrics[name] = value_ms

    def observe_audio_chunk(self, ready_ms: int) -> None:
        self.audio_chunk_count += 1
        if self._last_audio_chunk_ms is not None:
            self.max_chunk_gap_ms = max(self.max_chunk_gap_ms, ready_ms - self._last_audio_chunk_ms)
        self._last_audio_chunk_ms = ready_ms

    def to_payload(self) -> dict[str, Any]:
        return {
            "reply_id": self.reply_id,
            "session_id": self.session_id,
            "streaming": self.streaming,
            "chat_mode": self.chat_mode,
            "tts_engine": self.tts_engine,
            "prompt_cache_hit": self.prompt_cache_hit,
            "segment_count": self.segment_count,
            "audio_chunk_count": self.audio_chunk_count,
            "max_chunk_gap_ms": self.max_chunk_gap_ms,
            **self.metrics,
        }


class TraceLoggerWorker:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._queue: asyncio.Queue[ReplyTrace | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._task = asyncio.create_task(self._run())

    async def enqueue(self, trace: ReplyTrace) -> None:
        await self._queue.put(trace)

    async def stop(self) -> None:
        if self._task is None:
            return
        await self._queue.put(None)
        await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item.to_payload(), ensure_ascii=False) + "\n")
```

- [ ] **Step 4: 重新运行测试确认通过**

Run: `python -m pytest backend/tests/test_avatar_trace.py -q`

Expected: `2 passed`

- [ ] **Step 5: 提交这一小步**

```bash
git add backend/app/services/avatar_trace.py backend/tests/test_avatar_trace.py
git commit -m "test: add avatar trace scaffolding"
```

---

### Task 2: 接入后端 `avatar_phase` 与异步 trace

**Files:**
- Modify: `backend/app/services/avatar_trace.py`
- Modify: `backend/app/api/ws_router.py:30-417`
- Modify: `backend/app/main.py:21-31`
- Modify: `backend/tests/test_chat_streaming.py:1-188`

- [ ] **Step 1: 先补 WebSocket 行为测试**

```python
class FakeTraceService:
    def __init__(self) -> None:
        self.items = []

    def enqueue_nowait(self, trace) -> None:
        self.items.append(trace)


async def test_streaming_capability_emits_avatar_phase_events(self) -> None:
    fake_trace = FakeTraceService()

    with patch("app.api.ws_router.get_avatar_trace_service", return_value=fake_trace):
        result = await stream_assistant_reply(
            websocket=websocket,
            session_id="session-1",
            avatar=avatar,
            content="介绍一下这里",
            query_text="介绍一下这里",
            history=[{"role": "user", "content": "介绍一下这里"}],
            chat_service=FakeChatService(),
            tts_service=FakeTTSService(),
            capabilities=ClientCapabilities(tts_streaming=True, audio_format="pcm16le"),
            reply_id="reply-1",
            locked_emotion="happy",
            emotion_payload=emotion_payload,
            started_at=0.0,
        )

    phase_messages = [item for item in websocket.messages if item["type"] == "avatar_phase"]
    self.assertEqual(
        [item["phase"] for item in phase_messages],
        ["thinking", "speaking", "cooldown", "idle"],
    )
    self.assertIn("avatar_phase_speaking_ms", result.metrics)
    self.assertEqual(len(fake_trace.items), 1)
```

- [ ] **Step 2: 运行测试确认先失败**

Run: `python -m pytest backend/tests/test_chat_streaming.py::StreamAssistantReplyTestCase::test_streaming_capability_emits_avatar_phase_events -q`

Expected: `FAIL`，提示消息里缺少 `avatar_phase`，或 `get_avatar_trace_service` 尚不存在

- [ ] **Step 3: 修改 trace service，补全全局入口**

```python
class AvatarTraceService:
    def __init__(self, log_path: Path) -> None:
        self.worker = TraceLoggerWorker(log_path)

    async def start(self) -> None:
        await self.worker.start()

    async def stop(self) -> None:
        await self.worker.stop()

    def enqueue_nowait(self, trace: ReplyTrace) -> None:
        self.worker._queue.put_nowait(trace)


BACKEND_ROOT = Path(__file__).resolve().parents[2]
_trace_service: AvatarTraceService | None = None


def get_avatar_trace_service() -> AvatarTraceService:
    global _trace_service
    if _trace_service is None:
        _trace_service = AvatarTraceService(BACKEND_ROOT / "logs" / "avatar_trace.log")
    return _trace_service
```

- [ ] **Step 4: 修改后端主链，增加阶段事件和 trace 生命周期**

```python
def build_avatar_phase_payload(reply_id: str, phase: str, at_ms: int, reason: str) -> dict[str, object]:
    return {
        "type": "avatar_phase",
        "reply_id": reply_id,
        "phase": phase,
        "at_ms": at_ms,
        "reason": reason,
    }


async def emit_avatar_phase(send_json, trace, reply_id: str, phase: str, reason: str, started_at: float) -> None:
    at_ms = int((perf_counter() - started_at) * 1000)
    trace.mark(f"avatar_phase_{phase}_ms", at_ms)
    await send_json(build_avatar_phase_payload(reply_id, phase, at_ms, reason))


trace = ReplyTrace(
    reply_id=reply_id,
    session_id=session_id,
    streaming=capabilities.tts_streaming,
    chat_mode=chat_service.settings.chat_mode,
    tts_engine=tts_service.settings.tts_engine,
)
trace.mark("user_received_ms", 0)
await emit_avatar_phase(send_json, trace, reply_id, "thinking", "user_input_received", started_at)
```

```python
if tts_chunk.audio_bytes:
    if not speaking_sent:
        speaking_sent = True
        await emit_avatar_phase(send_json, trace, reply_id, "speaking", "first_audio_chunk", started_at)
    trace.observe_audio_chunk(int((perf_counter() - started_at) * 1000))
```

```python
if not cooldown_sent:
    await emit_avatar_phase(send_json, trace, reply_id, "cooldown", "audio_done", started_at)
await emit_avatar_phase(send_json, trace, reply_id, "idle", "reply_done", started_at)
get_avatar_trace_service().enqueue_nowait(trace)
```

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await init_db()
        await ensure_default_avatar_config()
        await get_avatar_trace_service().start()
        await asyncio.to_thread(get_tts_service().warmup)
        logger.info("Database initialization finished.")
    except Exception:
        logger.exception("Backend startup finished with degraded database state.")
    yield
    await get_avatar_trace_service().stop()
    await shutdown_db()
```

- [ ] **Step 5: 跑后端测试确认通过并提交**

Run: `python -m pytest backend/tests/test_avatar_trace.py backend/tests/test_chat_streaming.py -q`

Expected: `passed`，并且 `StreamAssistantReplyTestCase` 能看到 `avatar_phase` 顺序为 `thinking -> speaking -> cooldown -> idle`

```bash
git add backend/app/services/avatar_trace.py backend/app/api/ws_router.py backend/app/main.py backend/tests/test_chat_streaming.py
git commit -m "feat: add avatar phase and reply tracing"
```

---

### Task 3: 建立前端阶段状态与表现合成纯函数

**Files:**
- Create: `frontend/src/lib/avatarPresentation.ts`
- Create: `frontend/tests/avatarPresentation.test.ts`
- Modify: `frontend/src/types/chat.ts:30-191`

- [ ] **Step 1: 先写前端纯函数测试**

```ts
import assert from 'node:assert/strict'
import test from 'node:test'

import {
  computeAvatarPresentation,
  createDefaultConversationPhaseState,
  reduceAvatarPhaseEvent,
} from '../src/lib/avatarPresentation.ts'

test('thinking phase suppresses idle motion and forces thinking baseline', () => {
  const state = reduceAvatarPhaseEvent(
    createDefaultConversationPhaseState(),
    { type: 'avatar_phase', reply_id: 'reply-1', phase: 'thinking', at_ms: 12, reason: 'user_input_received' },
  )

  const presentation = computeAvatarPresentation({
    phaseState: state,
    emotion: {
      value: 'happy',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'heuristic',
    },
    hasLipSync: false,
  })

  assert.equal(presentation.phase, 'thinking')
  assert.equal(presentation.emotion.value, 'thinking')
  assert.equal(presentation.allowIdleMotion, false)
})

test('speaking phase keeps final emotion but only allows light motion', () => {
  const state = reduceAvatarPhaseEvent(
    createDefaultConversationPhaseState(),
    { type: 'avatar_phase', reply_id: 'reply-1', phase: 'speaking', at_ms: 400, reason: 'first_audio_chunk' },
  )

  const presentation = computeAvatarPresentation({
    phaseState: state,
    emotion: {
      value: 'happy',
      stage: 'final',
      confidence: 0.9,
      keywords: [],
      reason: '',
      source: 'llm',
    },
    hasLipSync: true,
  })

  assert.equal(presentation.phase, 'speaking')
  assert.equal(presentation.emotion.value, 'happy')
  assert.equal(presentation.allowIdleMotion, false)
  assert.equal(presentation.motionPreset, 'light-speaking')
})
```

- [ ] **Step 2: 运行测试并确认它先失败**

Run: `node --experimental-strip-types --test frontend/tests/avatarPresentation.test.ts`

Expected: `FAIL`，提示 `Cannot find module '../src/lib/avatarPresentation.ts'`

- [ ] **Step 3: 补类型和纯函数实现**

```ts
export type ConversationPhase = 'idle' | 'thinking' | 'speaking' | 'cooldown'

export interface AvatarPhaseEvent {
  type: 'avatar_phase'
  reply_id: string
  phase: ConversationPhase
  at_ms: number
  reason: string
}

export interface ConversationPhaseState {
  replyId: string | null
  phase: ConversationPhase
  atMs: number
  reason: string
}

export interface AvatarPresentation {
  phase: ConversationPhase
  emotion: EmotionTelemetry
  allowIdleMotion: boolean
  motionPreset: 'idle' | 'thinking' | 'light-speaking' | 'cooldown'
  cooldownMs: number
}

export function createDefaultConversationPhaseState(): ConversationPhaseState {
  return { replyId: null, phase: 'idle', atMs: 0, reason: 'initial' }
}

export function reduceAvatarPhaseEvent(
  state: ConversationPhaseState,
  event: AvatarPhaseEvent,
): ConversationPhaseState {
  return {
    replyId: event.reply_id,
    phase: event.phase,
    atMs: event.at_ms,
    reason: event.reason,
  }
}

export function computeAvatarPresentation(args: {
  phaseState: ConversationPhaseState
  emotion: EmotionTelemetry
  hasLipSync: boolean
}): AvatarPresentation {
  if (args.phaseState.phase === 'thinking') {
    return {
      phase: 'thinking',
      emotion: { ...args.emotion, value: 'thinking' },
      allowIdleMotion: false,
      motionPreset: 'thinking',
      cooldownMs: 0,
    }
  }
  if (args.phaseState.phase === 'speaking') {
    return {
      phase: 'speaking',
      emotion: args.emotion,
      allowIdleMotion: false,
      motionPreset: 'light-speaking',
      cooldownMs: 0,
    }
  }
  if (args.phaseState.phase === 'cooldown') {
    return {
      phase: 'cooldown',
      emotion: args.emotion,
      allowIdleMotion: false,
      motionPreset: 'cooldown',
      cooldownMs: 420,
    }
  }
  return {
    phase: 'idle',
    emotion: args.emotion,
    allowIdleMotion: true,
    motionPreset: 'idle',
    cooldownMs: 0,
  }
}
```

- [ ] **Step 4: 重新运行前端纯函数测试**

Run: `node --experimental-strip-types --test frontend/tests/avatarPresentation.test.ts`

Expected: `ok`，显示新增的 2 个测试通过

- [ ] **Step 5: 提交这一小步**

```bash
git add frontend/src/lib/avatarPresentation.ts frontend/src/types/chat.ts frontend/tests/avatarPresentation.test.ts
git commit -m "test: add avatar presentation state helpers"
```

---

### Task 4: 把阶段状态接入 App 和 Live2DStage

**Files:**
- Modify: `frontend/src/lib/avatarPresentation.ts`
- Modify: `frontend/src/App.vue:84-812`
- Modify: `frontend/src/components/Live2DStage.vue:75-346`

- [ ] **Step 1: 先扩展纯函数测试，锁定 stale reply 不能覆盖新回复**

```ts
test('phase reducer ignores stale events from an older reply', () => {
  const active = reduceAvatarPhaseEvent(
    createDefaultConversationPhaseState(),
    { type: 'avatar_phase', reply_id: 'reply-2', phase: 'thinking', at_ms: 20, reason: 'user_input_received' },
  )

  const stale = reduceAvatarPhaseEvent(
    active,
    { type: 'avatar_phase', reply_id: 'reply-1', phase: 'idle', at_ms: 999, reason: 'reply_done' },
  )

  assert.equal(stale.replyId, 'reply-2')
  assert.equal(stale.phase, 'thinking')
})
```

- [ ] **Step 2: 运行前端测试确认新增断言先红**

Run: `node --experimental-strip-types --test frontend/tests/avatarPresentation.test.ts`

Expected: `FAIL`，因为当前的 `reduceAvatarPhaseEvent()` 还会直接接受旧 reply 的阶段事件

- [ ] **Step 3: 在 `avatarPresentation.ts`、`App.vue` 和 `Live2DStage.vue` 完成接线**

```ts
export function reduceAvatarPhaseEvent(
  state: ConversationPhaseState,
  event: AvatarPhaseEvent,
): ConversationPhaseState {
  if (state.replyId && state.replyId !== event.reply_id && event.phase === 'idle') {
    return state
  }
  return {
    replyId: event.reply_id,
    phase: event.phase,
    atMs: event.at_ms,
    reason: event.reason,
  }
}
```

```ts
const conversationPhase = ref<ConversationPhaseState>(createDefaultConversationPhaseState())

const avatarPresentation = computed(() =>
  computeAvatarPresentation({
    phaseState: conversationPhase.value,
    emotion: emotionTelemetry.value,
    hasLipSync: activeStreamReplyId !== null || currentAudio !== null,
  }),
)

function handleAvatarPhase(payload: AvatarPhaseEvent) {
  conversationPhase.value = reduceAvatarPhaseEvent(conversationPhase.value, payload)
}

if (payload.type === 'avatar_phase') {
  handleAvatarPhase(payload)
  return
}

watch([avatarPresentation, live2dRef], ([presentation, live2d]) => {
  live2d?.setAvatarPresentation?.(presentation)
}, { immediate: true })
```

```ts
let currentPhase: ConversationPhase = 'idle'
let allowIdleMotion = true

function playIdleMotion() {
  if (!model) {
    return
  }
  window.clearInterval(idleTimer)
  idleTimer = window.setInterval(() => {
    if (!model || !allowIdleMotion || currentPhase !== 'idle') {
      return
    }
    try {
      model.motion('Idle')
    } catch {
      return
    }
  }, 16000)
}

function setAvatarPresentation(presentation: AvatarPresentation) {
  currentPhase = presentation.phase
  allowIdleMotion = presentation.allowIdleMotion
  setEmotion(presentation.emotion.value, presentation.emotion.stage)
}

defineExpose({
  setEmotion,
  playPhonemes,
  queueScheduledPhonemes,
  setAvatarPresentation,
})
```

- [ ] **Step 4: 跑前端测试和构建验证**

Run: `node --experimental-strip-types --test frontend/tests/avatarPresentation.test.ts frontend/tests/chatMessageMeta.test.ts frontend/tests/emotionLamp.test.ts frontend/tests/streamAudioBuffer.test.ts`

Expected: `ok`

Run: `cd frontend; npm run build`

Expected: `vue-tsc` 和 `vite build` 都成功，没有新的 TypeScript 类型错误

- [ ] **Step 5: 提交这一小步**

```bash
git add frontend/src/lib/avatarPresentation.ts frontend/src/App.vue frontend/src/components/Live2DStage.vue
git commit -m "feat: orchestrate avatar phase driven motion"
```

---

### Task 5: 同步 roadmap 并做整体验证

**Files:**
- Modify: `docs/roadmap.md:58-78, 87-92`

- [ ] **Step 1: 先写文档变更目标，确保 roadmap 有明确落点**

```md
- [x] 动作协调：新增 `avatar_phase(thinking/speaking/cooldown/idle)`，等待阶段明确进入思考态，说话阶段只保留轻动作
- [x] 非阻塞耗时追踪：按 `reply_id` 记录一轮回复关键阶段 trace，异步写入 `backend/logs/avatar_trace.log`
```

- [ ] **Step 2: 修改 roadmap，把本轮完成项同步进去**

```md
**表情系统**

- [x] 情感关键词提取（LLM分析回答情感）
- [x] 情感 → Live2D 表情参数映射表
- [x] 动作协调：游客发问后进入 `thinking`，TTS 发声时进入 `speaking`，结束后 `cooldown -> idle`
- [x] 后端 reply trace：记录 `llm_first_delta_ms / tts_first_audio_chunk_ms / audio_done_ms / avatar_phase_*`
```

- [ ] **Step 3: 跑最终自动验证**

Run: `python -m pytest backend/tests/test_avatar_trace.py backend/tests/test_chat_streaming.py -q`

Expected: `passed`

Run: `node --experimental-strip-types --test frontend/tests/avatarPresentation.test.ts frontend/tests/chatMessageMeta.test.ts frontend/tests/emotionLamp.test.ts frontend/tests/streamAudioBuffer.test.ts`

Expected: `ok`

Run: `cd frontend; npm run build`

Expected: `built in ...`

- [ ] **Step 4: 做一次手工联调**

Run:

```powershell
cd backend
conda activate ai-chat-gpu
python -m uvicorn main:app --reload
```

Run:

```powershell
cd frontend
npm run dev
```

Manual expected:
- 提问后 150ms 内明显进入思考态
- 首个 TTS chunk 到来后切到 `speaking`，不再随机 `idle`
- 音频结束后 1 秒内回到 `idle`
- `backend/logs/avatar_trace.log` 中可按 `reply_id` 找到完整记录

- [ ] **Step 5: 提交收尾**

```bash
git add docs/roadmap.md
git commit -m "docs: sync roadmap for avatar action tracing"
```
