# Phase 2 TTS 升级与口型同步重构设计

## 背景

Phase 2 原本采用的是 `CosyVoice-300M-SFT + inference_sft`。现在这条路线不再适合本项目，原因包括：

- 音质还不够好，难以支撑里程碑演示效果
- `inference_sft` 不支持自然语言情感控制
- 当前情感系统无法真正驱动发声音色与语气
- 现有口型同步在部分引擎下仍依赖近似时序

新的目标是：

- 切换到 `CosyVoice2-0.5B + inference_instruct2`
- 将 TTS 参考音频绑定到 `avatar_config`
- 让 `happy / excited / thinking / sad / neutral` 同时影响表情和发声指令
- 在模型可提供结构化时序时优先使用它；不可提供时，使用高质量音频包络兜底提升口型同步

## 已确认的用户决策

- 先使用临时样例参考音频打通链路，后续再替换为正式导览员声音
- TTS 音色配置绑定到 `avatar_config`，而不是全局配置
- 这次就实现完整的“情感 -> TTS 指令”联动
- 口型同步采用双通路设计：
  - 如果当前 CosyVoice2 运行时暴露了结构化时序或 duration 信息，优先使用
  - 如果当前运行时没有稳定暴露这些字段，则退化到基于音频包络的高精度时序

## 目标

- 将当前本地 TTS 后端替换为 `CosyVoice2-0.5B + inference_instruct2`
- 保持当前 WebSocket 对话链路不变，方便前端继续联调
- 为每个 avatar 存储参考音频和相关合成参数
- 让后端情感分类结果真实影响发声风格
- 在不被某个 vendor 特定输出结构卡死的前提下，提升口型同步精度
- 保持与当前前端 `phonemes` 播放协议兼容

## 非目标

- 本阶段不做完整的音色资源库
- 本阶段不做参考音频上传 UI
- 本阶段不做训练、微调或 voice cloning 流程
- 本阶段不做独立的管理端试听页
- 本阶段不迁移到 Alembic

## 当前约束

### CosyVoice2 运行时约束

仓库内当前接入的本地 CosyVoice 代码已经确认 `inference_instruct2` 是 `CosyVoice2-0.5B` 的正确合成入口：

- [backend/storage/vendor/CosyVoice/cosyvoice/cli/cosyvoice.py](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/vendor/CosyVoice/cosyvoice/cli/cosyvoice.py:177>)

但从当前已检查的本地 Python 生成器路径来看，公开暴露的结果中可以明确看到 `tts_speech`，却不能保证 `duration`、`alignment`、`phoneme` 等字段会始终以稳定一致的方式暴露：

- [backend/storage/vendor/CosyVoice/cosyvoice/cli/model.py](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/vendor/CosyVoice/cosyvoice/cli/model.py:361>)
- [backend/storage/models/CosyVoice2-0.5B/README.md](</E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice2-0.5B/README.md:1>)

因此，后续实现不能把“当前本地运行时一定稳定返回 `duration` 字段”当成硬前提。

### 数据库迁移约束

项目当前使用的是 `Base.metadata.create_all()` 初始化表结构，并未接入 Alembic：

- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)

这意味着已存在的 SQLite 数据库不会自动补齐新列。因此，这次重构必须包含一个针对 `avatar_config` 的启动期轻量迁移步骤。

## 总体架构

### 端到端流程

运行时主链路保持为：

`ASR -> chat / RAG -> emotion -> streamed text -> TTS -> audio + phoneme frames -> Live2D`

本次后端变化的核心位于 TTS 合成阶段：

1. 读取 `avatar_config`
2. 从 avatar 配置中解析参考音频路径和参考文本
3. 根据当前情感生成中文 TTS 指令模板
4. 调用 `CosyVoice2.inference_instruct2(...)`
5. 将音频结果转换为 WAV 字节流
6. 从以下两种来源之一生成口型帧：
   - 有结构化时序字段时，直接使用结构化时序
   - 无结构化时序字段时，使用音频包络推导时序
7. 继续通过现有 WebSocket 协议下发 `audio` 和 `phonemes`

### 为什么采用 avatar 绑定配置

把 TTS 配置绑定到 `avatar_config` 是当前最轻、同时又能兼顾后续扩展的方案：

- 后续可以替换正式导览员音色
- 后续可以做按角色维度的音色微调
- 后续可以做前端或管理端的音色切换

这样可以避免以后在“声音切换”阶段再次重构数据模型。

## 数据模型调整

涉及文件：

- [backend/app/db/models.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/models.py:1>)

建议为 `AvatarConfig` 新增以下字段：

- `tts_reference_audio_path: str`
  - `inference_instruct2` 使用的参考音频文件路径
- `tts_reference_text: str`
  - 参考音频对应文本，便于后续扩展零样本或更强控制能力
- `tts_speed: float`
  - 默认值 `1.0`
- `tts_emotion_enabled: bool`
  - 默认值 `true`

保留现有字段：

- `model_path`
- `voice_id`
- `persona`

### `voice_id` 的兼容角色

`voice_id` 暂时不删除，但含义会变化：

- 短期内作为展示名或兼容别名保留
- 不再是 CosyVoice2 的主音色选择参数

这样可以避免现有前端假设和旧数据初始化逻辑立刻失效。

## API 调整

涉及文件：

- [backend/app/api/routes/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/routes/avatar.py:1>)
- [backend/app/schemas/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/schemas/avatar.py:1>)

继续沿用现有接口：

- `GET /api/v1/admin/avatar/config`
- `PUT /api/v1/admin/avatar/config`

并在返回与更新模型中加入新的 TTS 字段：

- `tts_reference_audio_path`
- `tts_reference_text`
- `tts_speed`
- `tts_emotion_enabled`

### 校验规则

- 当 `TTS_ENGINE=cosyvoice` 时，`tts_reference_audio_path` 不能为空
- `tts_speed` 必须为正数，并限制在安全范围内，例如 `0.5 <= speed <= 1.5`
- `tts_reference_audio_path` 必须解析到后端工作区或 storage 目录下
- 如果 `tts_reference_audio_path` 指向的文件不存在，接口应明确拒绝更新

## 配置项调整

涉及文件：

- [backend/app/core/config.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/core/config.py:1>)

环境配置应从原来的 SFT 假设切换为 CosyVoice2 假设：

- `TTS_ENGINE=cosyvoice`
- `TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B`
- `TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice`
- `TTS_COSYVOICE_DEVICE=cuda`
- `TTS_COSYVOICE_SAMPLE_RATE` 应与当前模型实际采样率保持一致

同时增加 avatar 初始化默认值：

- 默认临时参考音频路径
- 默认临时参考文本
- 默认 `tts_speed=1.0`
- 默认 `tts_emotion_enabled=true`

`.env` 继续只负责引擎级默认值，角色级的音色行为由数据库中的 `avatar_config` 控制。

## TTS 服务重构

涉及文件：

- [backend/app/services/tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/services/tts.py:1>)

### 服务职责

TTS 服务需要扩展为：

- 加载 `CosyVoice2`，不再依赖 `inference_sft`
- 使用 `inference_instruct2` 合成
- 根据情感标签生成中文发声指令
- 解析 avatar 级参考音频配置
- 提取或推导口型同步时序
- 在本地 CosyVoice 失败时保留降级能力

### 情感指令映射

建议采用以下映射：

- `happy` -> `用愉快、亲切、自然的语气介绍这段内容。<|endofprompt|>`
- `excited` -> `用热情、兴奋、感染力强的语气介绍这段内容。<|endofprompt|>`
- `thinking` -> `用平静、思考感更强、略带停顿的语气介绍这段内容。<|endofprompt|>`
- `sad` -> `用温和、克制、略低沉的语气介绍这段内容。<|endofprompt|>`
- `neutral` -> `用自然、友好、清晰的语气介绍这段内容。<|endofprompt|>`

当 `tts_emotion_enabled` 为 false 时，统一使用 `neutral` 指令。

### 方法签名变化

`synthesize_chunk(...)` 应接收足够的上下文，以支持按 avatar 动态合成：

- `text`
- `seq`
- `emotion`
- `voice_id`，仅作兼容保留
- `reference_audio_path`
- `reference_text`
- `speed`

WebSocket 层可以传完整 avatar，也可以拆分出显式参数传入。推荐传显式参数，以保持 TTS 服务与 ORM 解耦。

### CosyVoice 运行时加载

模型加载逻辑应继续保持：

- 导入 `cosyvoice.cli.cosyvoice`
- 实例化 `CosyVoice2`
- 从配置中解析运行设备
- 当请求 `cuda` 但环境不支持时，明确报错

这与当前本地加载模式一致，也避免在本阶段额外引入新的运行时包装层。

## 口型同步设计

### 协议兼容性

当前前端消费的是：

- `audio`
- `phonemes`

并且口型播放已经绑定到真实 `audio.currentTime`：

- [frontend/src/App.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/App.vue:1>)
- [frontend/src/components/Live2DStage.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/components/Live2DStage.vue:1>)

这本身就是正确方向。因此，这次重构应保持 `phonemes` 事件结构不变：

- `ph`
- `start`
- `end`
- `openY`
- `form`

### 时序来源优先级

建议优先级如下：

1. 当前 CosyVoice2 运行时返回的结构化时序
2. 从合成音频中推导出的音频包络时序
3. 当前基于文本的 fallback，仅作为最终降级方案

### 结构化时序路径

如果运行结果中存在稳定可用的结构化时序字段，则后端应：

- 将 vendor 差异化字段统一规整为内部 timed-unit 列表
- 把每个时序单元映射为口型形状
- 直接生成带 `start/end` 的 `phonemes`

可以安全探测但不能强依赖的字段包括：

- `duration`
- `alignment`
- `alignments`
- `phonemes`
- `phoneme_alignment`

这些字段必须按“可选、版本相关”来处理。

### 音频包络兜底路径

如果当前运行时没有暴露结构化时序，则改为从合成音频波形生成口型时序：

1. 将音频解码为单声道 PCM
2. 计算短窗 RMS 或能量包络
3. 对曲线做归一化与平滑
4. 将曲线按固定时间步长切片，例如 25 Hz 或 50 Hz
5. 将能量等级映射为嘴巴开合程度
6. 生成短时 `phonemes` 帧，例如：
   - 高能量帧 -> `a`
   - 中能量帧 -> `e`
   - 低能量帧 -> `N`
7. 直接在每帧中写入 `openY/form`

这种方案不是真正的音素级对齐，但它能显著改善“嘴型跟着声音走”的观感，同时对 vendor 输出结构变化更稳健。

### 最终 fallback

仍需保留当前基于文本的口型兜底，以应对：

- 音频合成失败，但文本仍然存在
- 时序提取链路异常

这样可以维持当前系统的韧性。

## WebSocket 调整

涉及文件：

- [backend/app/api/ws_router.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/ws_router.py:1>)

需要的改动包括：

- 将 avatar 的 TTS 配置传入 `synthesize_chunk(...)`
- 将 `generated.emotion` 一并传入 TTS 合成
- 保持现有 `audio` 与 `phonemes` 消息类型不变

本阶段不需要做破坏性协议升级。

## 启动期迁移策略

涉及文件：

- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)
- 如有需要，可新增一个小型 DB 兼容辅助模块

实现一个轻量级 SQLite 启动迁移步骤：

- 检查 `avatar_config` 当前列集合
- 如缺失以下列，则自动补齐：
  - `tts_reference_audio_path`
  - `tts_reference_text`
  - `tts_speed`
  - `tts_emotion_enabled`
- 使用 `ALTER TABLE` 增列
- 为已有行回填默认值

这样可以保证现有 `phase1.db` 继续可用，而无需删库重建。

## 前端范围

后续实现中可能涉及的文件：

- [frontend/src/App.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/App.vue:1>)
- [frontend/src/components/Live2DStage.vue](</E:/2026spring/software contest/AI-chat-live2d/frontend/src/components/Live2DStage.vue:1>)

本阶段前端改动应尽量保持轻量：

- 继续使用现有 `phonemes` 播放逻辑
- 如后端帧更密集，可按需补一点平滑处理
- 可选增加少量调试信息，但不是这次重构的必需项

由于当前前端已经绑定真实音频播放时间，因此只要后端时序更准确，前端就会自然获得更好的同步效果。

## 错误处理

### 参考音频无效

当 avatar 的参考音频路径不存在或无法读取时：

- TTS 应在日志中明确报错
- WebSocket 回复仍应尽量优雅降级
- 如果配置允许，可回退到 edge TTS 或 mock fallback

### CosyVoice 运行时失败

如果本地 CosyVoice2 运行时抛错：

- 保持当前服务的降级策略
- 当音频无法生成时，仍尽可能返回 fallback 口型帧
- 不允许整个 WebSocket 会话直接崩溃

### 无结构化时序输出

如果运行结果中没有结构化时序字段：

- 明确记录日志，说明当前启用了音频包络兜底
- 继续返回 `phonemes`

这应被视为预期运行路径，而不是异常。

## 验收标准

### 功能验收

- 文本对话能够产出本地 CosyVoice2 音频
- 情感变化时，声音风格也会跟着变化
- avatar 的参考音频配置真实来自 `avatar_config`
- 管理接口能够读写新增的 TTS 字段
- 旧数据库在启动时可自动完成兼容升级

### 口型同步验收

- 前端仍然收到 `audio` 和 `phonemes`
- 嘴型与音频播放有明显对齐关系
- 人工验收时，目标同步误差控制在 `80 ms` 以内

### 韧性验收

- 即使没有结构化时序字段，音频包络兜底仍可驱动口型
- 即使本地 TTS 失败，整个会话也不会硬崩溃

## 测试策略

### 后端自动化测试

扩展：

- [backend/tests/test_tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/tests/test_tts.py:1>)

新增覆盖点包括：

- 情感标签到指令文本的映射
- `inference_instruct2` 调用签名与参数顺序
- avatar 参考音频路径解析
- 当存在时序字段时的结构化时序归一化
- 当不存在时序字段时的音频包络 fallback 生成
- 针对旧版 SQLite schema 的迁移补列逻辑

### API 测试

新增覆盖：

- `GET /admin/avatar/config` 返回新增字段
- `PUT /admin/avatar/config` 能正确校验并持久化这些字段

### 人工联调验证

人工验收步骤建议如下：

1. 在 GPU 上启动带 `CosyVoice2-0.5B` 的后端
2. 用临时参考音频初始化 avatar 配置
3. 分别提问容易触发不同情感的内容
4. 核查：
   - 音频成功生成
   - 表情与声音风格同时变化
   - 口型跟着声音走，没有明显漂移
5. 验证在不删除 `phase1.db` 的情况下，旧库可以自动升级

## 后续扩展路径

本设计已经为后续 TTS 工作预留了自然延展方向，但本次不实现：

- 将临时参考音频替换为正式导览员声音
- 增加管理端的音色资源管理
- 增加前端或管理端的音色下拉切换
- 增加更细粒度的 TTS 风格、情感强度、说话模式控制
- 增加参考音频预览和校验工具

## 预计影响范围

后续实现中预计需要重点修改的后端文件：

- [backend/app/core/config.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/core/config.py:1>)
- [backend/app/db/models.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/models.py:1>)
- [backend/app/db/session.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/db/session.py:1>)
- [backend/app/schemas/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/schemas/avatar.py:1>)
- [backend/app/api/routes/avatar.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/routes/avatar.py:1>)
- [backend/app/api/ws_router.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/api/ws_router.py:1>)
- [backend/app/services/tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/app/services/tts.py:1>)
- [backend/tests/test_tts.py](</E:/2026spring/software contest/AI-chat-live2d/backend/tests/test_tts.py:1>)

前端大概率只需少量配合，除非后续联调发现更密集的口型帧流需要额外平滑处理。
