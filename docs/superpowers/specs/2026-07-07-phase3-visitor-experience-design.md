# Phase 3 游客端功能设计

## 背景

当前项目已经完成了 Phase 1 和 Phase 2 的基础能力：

- 前端已有单页游客端原型，包含 Live2D、文本输入、语音输入、WebSocket 对话、流式 TTS、口型同步和情绪驱动。
- 后端已有 `sessions`、`messages`、RAG、ASR、TTS、澄清追问、多轮对话状态和知识库能力。

`docs/roadmap.md` 中 Phase 3 的游客端目标是补齐以下 4 项能力：

1. 个性化推荐：兴趣标签选择 UI + 路线推荐 Prompt
2. 多模态：拍照上传 -> Qwen-VL-Max 识别景点 -> 回答
3. 对话历史展示：侧边栏
4. 数字人“思考中”动画：LLM 响应期间给游客明确反馈

本设计的目标是在不重写现有聊天主链的前提下，把游客端升级为可完整演示的单页导览台。

## 目标

- 保持单页游客端形态，不拆成新的游客路由页面。
- 在现有聊天主链上增加会话历史、兴趣偏好、多模态识图和更明确的思考态。
- 让图片识别结果直接进入当前会话，而不是成为独立工具页。
- 优先复用现有 `sessions + messages + ws_router + RAG/TTS` 架构，避免额外引入新的复杂子系统。

## 非目标

- 本轮不开发游客端完整图片相册、缩略图历史回放或图片资源库。
- 本轮不开发游客登录、收藏、分享等账号体系。
- 本轮不开发管理后台中的图片审核、视觉素材管理等后台能力。
- 本轮不重写现有 WebSocket 文本/TTS 协议。
- 本轮不为了游客端新增新的消息总线、Redis 或对象存储服务。

## 方案决策

### 采用方案

采用“轻后端扩展 + 单页增强”方案：

- 前端保持单页导览台结构，在当前页面上增加历史会话栏、兴趣标签面板和拍照入口。
- 后端新增轻量游客端接口，分别覆盖会话历史、兴趣标签更新、路线推荐和图片识别。
- 图片识别结果先转换为当前会话中的一条文本化提问，再复用现有 WebSocket 聊天、RAG、TTS 和 Live2D 主链。

### 不采用的方案

- 不采用“前端强编排、后端尽量不改”的方案，因为历史切换、图片识别和推荐结果最终都需要可靠持久化，全部堆到前端会导致状态过重。
- 不采用“游客端全面模块化重构、多路由拆页”的方案，因为本轮验收目标是补齐功能，不是做一次产品级路由重构。

## 总体架构

### 页面结构

游客端保持单页，但在布局上拆分为 4 个协作区域：

1. 左侧 `历史会话栏`
   - 展示最近会话列表
   - 显示会话摘要、最后更新时间、兴趣标签和消息数
   - 支持切换并回看旧会话

2. 中间上方 `数字人主舞台`
   - 继续承载 Live2D、情绪灯、录音电平、流式缓冲状态和数字人动作表现
   - 强化 `thinking -> speaking -> cooldown -> idle` 的可视反馈

3. 中间下方 `对话区`
   - 展示当前会话消息、来源卡片、追问提示
   - 支持历史会话切换后的消息回显

4. 右上或聊天区顶部 `兴趣标签 / 推荐入口`
   - 游客选择“历史文化、亲子、夜游、轻松、省力、拍照打卡”等偏好
   - 展示推荐路线卡片与推荐问题按钮

5. 对话底部 `多模态输入区`
   - 保留文本输入与录音
   - 新增“拍照 / 上传图片”入口
   - 图片识别完成后自动进入当前对话流

### 前端模块边界

当前 [frontend/src/App.vue](/abs/E:/2026spring/software%20contest/AI-chat-live2d/frontend/src/App.vue) 已经承担了过多状态。Phase 3 需要把游客端拆成以下模块：

- `SessionHistoryRail`
  - 显示历史会话列表
  - 触发切换会话

- `InterestTagPanel`
  - 管理兴趣标签选择
  - 展示推荐路线卡片和推荐问题

- `ChatTranscript`
  - 负责消息列表、来源卡片、追问提示

- `PhotoAskPanel`
  - 管理拍照/上传状态
  - 展示图片识别过程和失败提示

- `ChatComposer`
  - 聚合文本输入、录音按钮、图片入口和发送逻辑

- `Live2DStage`
  - 保持现有口型与动作播放职责，不并入游客端业务逻辑

状态层建议优先使用“组合式 composable + 局部组件拆分”，不在本轮额外引入新的状态库。核心状态包括：

- `sessionList`
- `activeSessionId`
- `activeMessages`
- `selectedInterestTags`
- `recommendationState`
- `photoUploadState`
- `thinkingState`

## 后端接口设计

### 1. 会话历史接口

在现有 `sessions` 体系上补充游客端读取能力：

- `GET /api/v1/sessions`
  - 返回最近会话列表
  - 字段包含：
    - `session_id`
    - `created_at`
    - `updated_at`
    - `interest_tags`
    - `message_count`
    - `last_message_preview`

- `GET /api/v1/sessions/{session_id}/messages`
  - 返回目标会话下的消息列表
  - 供前端点击左侧历史会话后直接回填聊天区

- `PATCH /api/v1/sessions/{session_id}`
  - 支持更新 `interest_tags`
  - 游客调整兴趣偏好后立即生效

### 2. 个性化推荐接口

新增游客端推荐接口：

- `POST /api/v1/sessions/{session_id}/recommendations`

输入：

- `interest_tags`
- 可选 `visitor_profile`
  - 如 `family`, `night-tour`, `history-first`, `photo-first`

输出：

- `route_title`
- `intro`
- `highlights`
- `suggested_questions`
- `applied_interest_tags`

设计原则：

- 推荐不是独立算法系统，而是现有 RAG/LLM 的结构化包装。
- 推荐输出必须适合前端卡片展示，不能直接返回大段自由文本。
- 推荐结果同时影响后续聊天 Prompt，让“路线推荐入口”和“正常提问”使用同一套游客偏好。

### 3. 图片识别接口

新增游客端图片识别接口：

- `POST /api/v1/sessions/{session_id}/vision/recognize`

输入：

- `multipart/form-data`
  - `file`
  - 可选 `user_prompt`
  - 可选 `interest_tags`

输出：

- `recognized_spot`
- `recognition_summary`
- `resolved_question`
- `stored_image_path`

处理链路固定为：

1. 前端上传图片到识别接口
2. 后端将文件落盘到 `backend/storage/uploads/visitor/`
3. 后端调用真实视觉模型 `Qwen-VL-Max`
4. 将视觉结果整理为游客口吻下可继续追问的 `resolved_question`
5. 前端自动把 `resolved_question` 作为当前会话中的一次用户提问送入现有 WebSocket 聊天链路

这样可以保证：

- 图片能力直接并入当前会话
- RAG、TTS、Live2D、消息持久化都继续复用现有主链
- 视觉模型只负责“看图 + 帮忙改写提问”，而不是独立承担整条讲解链路

## 数据模型与持久化策略

### 会话与历史

继续复用现有表：

- `sessions`
- `messages`

不新增会话摘要表。会话摘要由查询聚合得到：

- 最后消息时间
- 消息数
- 最后一条消息预览
- 兴趣标签

### 兴趣标签

继续使用 `sessions.interest_tags` 保存游客偏好。

这是本轮的默认偏好来源：

- 路线推荐接口读取它
- 图片识别后的问题改写可参考它
- 正常文字/语音提问在进入 RAG/LLM 时也可参考它

### 图片识别持久化

本轮不新增图片资源表。

采用“文件落盘 + 消息语义持久化”的轻量策略：

- 图片文件落盘到 `backend/storage/uploads/visitor/`
- 会话中至少保存一条文本化用户消息，内容表达“我上传了一张图，这可能是某某景点，我想了解它”

这样历史回看时，即使不显示原图缩略图，仍保留了完整语义上下文。

### 是否需要新增表

本轮不强制新增新的游客端表，除非实现中发现“会话更新时间”无法可靠获取。

如果必须补充字段，优先考虑在 `sessions` 上增加：

- `updated_at`

用于更准确地按最近活跃时间排序历史会话列表。

## 现有聊天主链的复用方式

### 文本与语音

现有链路保持不变：

- 文本输入 -> WebSocket `text`
- 录音 -> ASR -> WebSocket `text`
- 回复 -> RAG/LLM -> TTS -> Live2D/口型/情绪

### 图片

图片不直接走 WebSocket 二进制聊天协议。

采用“两段式”接入：

1. HTTP 图片识别接口先把图像理解转成文字化问题
2. 前端再自动通过现有 WebSocket `text` 把该问题送入主聊天链路

这样实现最稳，理由是：

- 避免当前聊天协议被一次性扩成多模态协议
- 图片上传重试、文件大小校验、错误反馈更适合用 HTTP
- 后端聊天主链可以把图片识别后的问题当作普通用户提问处理

## 数字人“思考中”表现设计

当前系统已经有 `avatar_phase` 与 `thinking/speaking/cooldown/idle` 状态机。Phase 3 游客端只增强呈现，不重做协议。

思考中状态的表现要求：

- 游客发出文字、语音或图片提问后，数字人立即进入 `thinking`
- `thinking` 阶段的 UI 要有明确提示，避免游客误以为系统卡住
- 首个文本增量或首个音频 chunk 到达后，切到 `speaking`
- 回答结束后进入 `cooldown`，再回到 `idle`

前端表现建议：

- 舞台区域增加更明显的“思考中”文案或小徽标
- 情绪灯与动作表现保持一致，不再只显示随机待机变化
- 当图片识别或推荐请求尚未返回时，同样进入思考态

## 错误处理与降级规则

### 图片识别失败

- 不让整轮会话中断
- 在当前聊天区给出明确提示：
  - “这张图我暂时没看清，你可以换个角度再拍一次”
- 保持当前会话和输入内容不丢失

### 视觉模型未配置

- 图片入口仍可见，但点击后返回清晰提示
- 不允许静默失败
- 错误提示需要告诉开发者缺的是模型配置还是 API Key

### 推荐接口失败

- 不阻塞主聊天
- 前端降级显示本地预设推荐问题

### 历史会话切换时存在流式回复

- 前端切换会话前先停止当前播放、清空未完成草稿和流式缓冲
- 避免旧会话文本、语音、口型继续串到新会话界面

### 历史会话内容异常

- 如果旧会话缺少结构化来源信息，只保证文本可回看
- 不要求历史会话恢复当时的音频播放进度或表情状态

## 实现建议

### 前端建议修改范围

- 重构 [frontend/src/App.vue](/abs/E:/2026spring/software%20contest/AI-chat-live2d/frontend/src/App.vue)
  - 从“大而全页面组件”收束为页面装配层
- 新增游客端组件
  - `frontend/src/components/SessionHistoryRail.vue`
  - `frontend/src/components/InterestTagPanel.vue`
  - `frontend/src/components/PhotoAskPanel.vue`
  - `frontend/src/components/ChatTranscript.vue`
  - `frontend/src/components/ChatComposer.vue`
- 新增游客端 composable / service
  - `useVisitorSessions`
  - `useVisitorRecommendations`
  - `usePhotoRecognition`

### 后端建议修改范围

- 扩展 `backend/app/api/routes/sessions.py`
- 新增游客端视觉路由与 schema
- 新增游客端推荐 service
- 新增视觉识别 service
- 在现有消息持久化和会话读取逻辑上补齐历史查询能力

## 测试与验收口径

### 后端测试

- 会话列表接口能按最近活跃时间返回摘要
- 会话详情接口能返回消息列表
- 更新兴趣标签接口能正确保存
- 图片识别接口在真实配置存在时可返回 `resolved_question`
- 视觉配置缺失时返回明确错误而不是 500 静默失败

### 前端测试

- 单页聊天台可显示历史会话栏
- 切换会话后消息区正确回填
- 选择兴趣标签后推荐卡片刷新
- 上传图片后能看到识别中的加载态
- 图片识别完成后自动进入当前聊天流
- 切换历史会话时，当前流式音频和草稿能被清理

### 人工验收场景

1. 打开游客端，选择“亲子 + 轻松”
   - 页面展示推荐路线卡片和推荐问题

2. 询问“第一次来怎么逛”
   - 回答应体现已选兴趣标签

3. 上传一张景点图片
   - 系统能识别景点并直接在当前会话里继续讲解

4. 再新建一个会话提问
   - 左侧可看到多个历史会话
   - 点击旧会话可回看内容

5. 发问后等待回复
   - 数字人在等待阶段明确进入 `thinking`

## 风险与约束

- 如果视觉模型接口延迟较大，图片问答的首字时间会慢于纯文本问答，需要单独展示加载反馈。
- 如果不补 `sessions.updated_at`，会话列表只能基于 `created_at` 或最后消息查询排序，实现会更绕。
- 当前游客端页面已有较多状态，若不在本轮先拆组件，后续实现和维护风险会快速升高。
- 图片资产本轮只做落盘，不做完整媒体管理，因此历史会话默认不保证回显原图。

## 结论

Phase 3 游客端采用“单页增强 + 轻量后端扩展”的方式推进：

- 单页内补齐历史会话、兴趣标签、推荐入口和拍照识别
- 图片识别先走 HTTP，再自动进入现有 WebSocket 聊天主链
- 会话和消息继续复用当前数据库结构
- 数字人思考态只增强表现，不重做协议

该方案能够以最小的系统扰动完成 `roadmap` 中游客端 4 个目标，并为下一步的 implementation plan 提供明确边界。
