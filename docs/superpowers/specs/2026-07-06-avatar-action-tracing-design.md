# Phase 2 动作协调与耗时追踪设计

## 概述

本设计用于完善当前数字人对话体验中的两个问题：

1. 动作协调不足。当前前端主要依赖 `emotion` 参数切换表情，Live2D 的实际 motion 仍以 `Idle` 为主，因此在游客提问后的等待阶段，数字人看起来像在随机切换动态，而不是明确进入“思考中”状态。
2. 卡顿排查证据不足。当前后端已经有 `reply_metrics` 和 `tts_ws_chunk` 日志，但更偏结果汇总，缺少一轮回复内各阶段的完整轨迹，后续定位停顿来源时效率不高。

本轮目标不是重写现有聊天、TTS 或口型协议，而是在现有 Phase 2 链路上增加一层轻量但可扩展的动作编排与时序追踪能力，使数字人“先会等、再会说、最后能查”。

## 设计目标

- 游客发出问题后，前端应在极短时间内进入明确的 `thinking` 等待态，让用户愿意等待。
- TTS 开始稳定输出后，数字人进入 `speaking` 态，说话时以轻动作和口型驱动为主，避免夸张 motion 抢戏。
- 回复结束后，数字人自然回落到 `idle`，不出现“刚说完就随机乱动”的观感。
- 后端记录一轮回复的关键阶段耗时，但日志采集不得阻塞 WebSocket 主链，不得显著影响前端响应。
- 方案应能兼容现有 `emotion`、`audio`、`tts_audio_chunk`、`tts_viseme_chunk`、`done` 协议，避免大规模重构。

## 非目标

- 本轮不新增外部动作服务，不引入独立调度进程。
- 本轮不重写现有 TTS 流式协议，也不替换 CosyVoice 主链。
- 本轮不做复杂的多情绪大动作表演系统，不追求夸张的舞台化演出。
- 本轮不在浏览器端写入额外日志文件，只保留调试面板级别的数据展示。

## 当前实现现状

### 前端现状

- `frontend/src/App.vue` 已消费 `emotion`、`tts_audio_chunk`、`tts_viseme_chunk`、`audio_done`、`done` 等消息。
- `emotion` 事件已区分 `preview` 和 `final`，但它表达的是“情绪判断”，不是“动作阶段”。
- `frontend/src/components/Live2DStage.vue` 当前只暴露 `setEmotion()`、`playPhonemes()`、`queueScheduledPhonemes()`。
- Live2D motion 目前主要使用 `Idle` 和 `Tap`，没有明确的“等待中 / 说话中 / 回落中”动作状态机。

### 后端现状

- `backend/app/api/ws_router.py` 负责串联文本流、TTS 流和 WebSocket 下发。
- 当前已经有：
  - `reply_metrics`：一轮回复结束时输出阶段摘要
  - `tts_ws_chunk`：每个流式音频 chunk 发送时输出单条日志
- 但没有一类专门面向“数字人表现层”的阶段信号，也没有按 `reply_id` 聚合的一轮完整 trace。

## 方案选择

本设计采用“完整动作编排器 + 结构化异步 trace”的方案。

原因如下：

- 仅在前端推断等待/发声阶段，容易和后端真实 TTS 时序脱节。
- 仅做轻量日志补点，能查性能，但无法解决“等待时表演不明确”的体验问题。
- 将“情绪”和“动作阶段”拆开后，后续可以继续扩展更复杂的 motion，而不需要重写聊天页或 WebSocket 主协议。

## 总体架构

新增一个逻辑概念：`AvatarActionDirector`。它不是独立服务，而是由前后端协同完成。

### 后端职责

后端负责产出“数字人语义阶段”，并维护一轮回复的时序 trace：

- `thinking`：用户发问后，系统正在生成文字或等待 TTS 首包
- `speaking`：系统已经开始稳定发送首个可播放 TTS 音频
- `cooldown`：音频刚结束、准备回落到待机
- `idle`：整轮回复完全结束后的待机状态

### 前端职责

前端负责把阶段翻译成 Live2D 的最终表现：

- 阶段决定“当前该处于等待、说话还是待机”
- 情绪决定“眉眼、头部、视线、轻微姿态参数”
- 口型继续由现有 `phonemes` / `tts_viseme_chunk` 驱动

最终规则为：

- 阶段优先
- 情绪叠加
- 口型优先级最高

这意味着：

- 等待时即便最终情绪是 `happy`，前端也先进入 `thinking` 阶段表现
- 一旦真正开始播音，再把最终情绪轻量叠加到说话态上
- 嘴型驱动始终覆盖说话时的口部参数，避免动作把口型吃掉

## 阶段模型

### 阶段定义

#### `idle`

- 无活跃回复时的默认状态
- 允许低频、低扰动的待机 motion
- 保持自然呼吸和极轻微头部变化

#### `thinking`

- 在用户发问后尽快进入
- 以思考中的静态等待感为主
- 禁止高扰动 idle motion
- 保留轻呼吸和轻微视线偏移

#### `speaking`

- 在首个可播放音频开始后进入
- 口型由音频/viseme 主导
- 允许非常轻的说话姿态变化，但不允许夸张动作

#### `cooldown`

- 在音频结束后短时间保留
- 用于把 speaking 态自然收回 idle
- 持续时间固定在 300ms 到 600ms 的平滑过渡区间

### 状态迁移

- `idle -> thinking`：收到用户输入并开始处理回复
- `thinking -> speaking`：首个可播放 TTS 音频块发送完成
- `speaking -> cooldown`：收到 `audio_done`
- `cooldown -> idle`：回落计时完成，或收到整轮 `done` 后进入最终待机

### 超时与兜底

- 如果某轮没有产生 TTS 音频，后端仍需在本轮结束时补发 `cooldown -> idle`
- 如果前端未收到阶段事件，应自动降级为当前 `emotion-only` 行为，不阻塞消息展示

## WebSocket 协议扩展

在保留现有消息类型的前提下，新增 `avatar_phase` 事件。

### 新增事件

```json
{
  "type": "avatar_phase",
  "reply_id": "session-123-456",
  "phase": "thinking",
  "at_ms": 12,
  "reason": "user_input_received"
}
```

### 字段说明

- `type`：固定为 `avatar_phase`
- `reply_id`：当前轮回复唯一标识
- `phase`：`thinking | speaking | cooldown | idle`
- `at_ms`：相对本轮开始时间的毫秒值
- `reason`：阶段切换原因，便于调试

### 发送时机

- 收到 `text` 或 `audio_end`，并开始进入回复链路时：`thinking`
- 首个可播放 TTS 音频 chunk 真正发出时：`speaking`
- 发出 `audio_done` 时：`cooldown`
- 发出整轮 `done` 后，或 cooldown 计时结束后：`idle`

## 前端动作编排设计

### 新的前端状态

在 `frontend/src/App.vue` 中新增并维护：

- `conversationPhase`：仅反映后端下发的阶段
- `phaseStartedAt`：当前阶段进入时间
- `avatarPresentation`：由阶段 + 情绪合成后的最终表现

### 表现合成规则

前端新增一个纯函数，例如 `computeAvatarPresentation()`，输入：

- `conversationPhase`
- `emotionTelemetry`
- 当前是否存在口型播放

输出：

- Live2D 参数目标
- 是否允许 idle motion
- 是否允许 speaking motion
- cooldown 平滑系数

### 阶段对应表现

#### `thinking`

- 强制采用 `thinking` 情绪参数基线
- 如果存在 `preview/final emotion`，只允许做极小幅度叠加
- 停止高扰动 idle motion
- 保持轻呼吸和轻微眼球偏移

#### `speaking`

- 启用口型与 viseme 调度
- 允许轻动作集合，例如轻微头部和身体偏移
- 禁止跳跃式 motion 切换

#### `cooldown`

- 让 mouth open / emotion overlay 平滑回落
- 让 speaking 的轻动作在短时间内衰减

#### `idle`

- 恢复待机逻辑
- 降低现有随机 idle 动作触发频率
- 避免刚说完立即切回明显 motion

### Live2DStage 扩展方向

`frontend/src/components/Live2DStage.vue` 需要扩展为不仅接受情绪，还能接受阶段。

建议新增暴露方法：

- `setConversationPhase(phase)`
- `setAvatarPresentation(presentation)`

或保留现有 `setEmotion()`，再增加：

- `setPhase(phase)`

这样 App 层负责状态组合，Stage 层只负责执行。

## 后端时序追踪设计

### ReplyTrace

后端为每轮回复维护一个轻量 `ReplyTrace`，仅在内存中积累，不在主链路同步写磁盘。

建议字段：

- `reply_id`
- `session_id`
- `streaming`
- `chat_mode`
- `tts_engine`
- `user_received_ms`
- `avatar_phase_thinking_ms`
- `llm_first_delta_ms`
- `tts_first_segment_ms`
- `text_done_ms`
- `tts_first_audio_chunk_ms`
- `avatar_phase_speaking_ms`
- `audio_done_ms`
- `avatar_phase_cooldown_ms`
- `reply_done_ms`
- `prompt_cache_hit`
- `segment_count`
- `audio_chunk_count`
- `max_chunk_gap_ms`
- `trace_version`

### TraceLoggerWorker

新增一个后台异步 trace worker：

- WebSocket 主链只负责收集事件并把完整 trace 放入 `asyncio.Queue`
- worker 后台消费队列并写入独立日志文件
- 目标日志文件示例：`backend/logs/avatar_trace.log`

这样可以保证：

- WebSocket 优先把文字、音频、口型和阶段消息发给前端
- 磁盘写入慢时，不反向阻塞用户可感知路径

### 记录粒度

本轮不记录每个音频样本级别的明细。

保留的信息以“足够定位问题”为准：

- 每轮阶段耗时
- 每段 TTS 的首包延迟
- 每轮 chunk 数量
- 最大 chunk gap
- prompt cache 命中情况

这能支持后续判断：

- 是 LLM 首字慢
- 是 TTS 首包慢
- 还是 chunk 间隙太大导致播放端断流

## 日志策略

### 原有日志保留

保留现有：

- `reply_metrics`
- `tts_ws_chunk`
- `tts_prompt_cache`

### 新增日志

新增两类：

1. `avatar_phase_transition`
   - 用于记录阶段切换
   - 便于快速查看阶段是否异常卡住
2. `avatar_trace_summary`
   - 一轮完成后输出聚合摘要
   - 写入专用 trace 文件，便于按 `reply_id` 回放

### 性能约束

- 新增日志默认只写结构化短行
- 不在主链路拼接大段文本正文
- 不同步写入大量 chunk 细节
- trace worker 写日志失败仅警告，不影响主流程

## 错误处理与降级

### 阶段事件缺失

- 前端自动退回当前的 emotion-only 行为
- 不阻断文字、音频或口型显示

### TTS 无输出

- 后端必须补发 `cooldown -> idle`
- 避免数字人无限停留在 `thinking`

### Trace 写入失败

- 捕获异常并记录 `warning`
- 丢弃本轮 trace，不重试阻塞主链路

### 前端调试区异常

- 调试面板数据只作为展示用途
- 计算失败时不影响聊天、发声和 Live2D 本体

## 测试策略

### 后端测试

- `avatar_phase` 发送顺序正确：
  - `thinking`
  - `speaking`
  - `cooldown`
  - `idle`
- 无 TTS 输出时仍会补齐 `cooldown -> idle`
- `ReplyTrace` 能正确记录关键阶段毫秒值
- trace queue / worker 写失败不会中断 WebSocket 主流程

### 前端测试

- 收到 `avatar_phase(thinking)` 后立即进入思考态
- 收到 `avatar_phase(speaking)` 后不再继续明显 idle 动作
- `cooldown` 会平滑回落，不出现瞬间表情跳变
- 阶段事件缺失时，页面仍能回退到当前情绪驱动方案

### 集成验收

- 游客发问后 150ms 内，数字人主观上进入“思考中”
- TTS 首包到达后，数字人切入说话态，嘴型与轻动作协调
- 音频结束后 1 秒内自然回到待机
- `backend/logs/avatar_trace.log` 中能按 `reply_id` 找到一轮完整轨迹
- 即使 trace 日志关闭或写失败，前端响应不受显著影响

## 与 roadmap 的关系

本设计属于 Phase 2 的体验收尾与稳定性增强，主要补足：

- 情绪系统从“只有表情判断”升级到“表情 + 阶段动作协调”
- TTS/口型链路从“只能听和看”升级到“能查卡顿发生在哪里”

它不改变 Phase 2 既有目标，但会提升人工验收中的自然度和可调试性，为后续更强显卡或更复杂动作系统打基础。

## 实施边界

本轮只做：

- 新增 `avatar_phase` 事件
- 新增前端阶段状态机
- 新增后端轻量 trace 与异步日志
- 微调 Live2D 待机与说话表现

本轮不做：

- 外部动作编排服务
- WebRTC 或新的音频协议
- 多角色动作模板系统
- 大规模前端 UI 改版
