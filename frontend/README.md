# Frontend Phase 1

这个前端已经完成 `docs/roadmap.md` 中 Phase 1 的游客端能力：

- `Vue 3 + Vite + TypeScript` 基础工程
- `pixi-live2d-display` 集成和本地示例 Live2D 模型加载
- WebSocket 连接管理，包含心跳和断线重连
- 麦克风录音、100ms PCM 分片推流、文本输入与发送

## 启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 构建验证

```bash
cd frontend
npm run build
```

## 环境变量

复制 `.env.example` 为 `.env` 后可按需修改：

- `VITE_API_BASE_URL`
- `VITE_WS_BASE_URL`
- `VITE_LIVE2D_MODEL_PATH`
- `VITE_HEARTBEAT_MS`
- `VITE_RECONNECT_BASE_MS`

## 联调说明

- 页面加载时会先调用 `POST /api/v1/sessions` 创建会话
- 创建成功后会自动连接 `WS /ws/chat/{session_id}`
- 文本输入走 `text`
- 语音输入走 `audio_chunk` / `audio_end`
- 服务端返回的 `audio`、`phonemes`、`emotion` 会分别驱动音频播放、口型和表情
- `emotion` 事件现在除情绪值外，还会携带 `confidence / keywords / reason / source`
- 页面左侧已加入“情绪熔岩灯”调试面板，方便观察当前表情判断

## 验收结果 20260629

vue-tsc -b && vite build 零 TypeScript 错误，444 模块在 2.61s 内构建完成。

验收对照
Roadmap 任务 结果 实现位置
Vue3 + Vite + TypeScript 项目初始化 ✅ package.json，tsconfig.\*
pixi-live2d-display 集成，载入 Live2D 模型 ✅ Live2DStage.vue，haru 模型已在 public/live2d/
WebSocket 连接管理（心跳 + 断线重连） ✅ useChatSocket.ts：ping/pong 心跳 + 指数退避重连（最大 8s）
麦克风录音（边录边传） ✅ useAudioRecorder.ts：ScriptProcessorNode → PCM 下采样到 16kHz →100ms 分块 base64 发送
文本输入框 + 发送逻辑 ✅ App.vue：Enter 发送，流式气泡实时更新
额外完成（Phase 2 已接入）
- 音素/口型帧驱动的口型同步（rAF 时间轴调度 + lerp 平滑，`lipsync.ts`）
- 按真实音频 `currentTime` 对齐嘴型，而不是只靠本地计时器估算
- 兼容后端返回的 `audio/mpeg`（Edge-TTS）和 `audio/wav`（CosyVoice）两类音频
- Live2D 表情改为平滑过渡，不再瞬间切换

5 种情绪预设驱动 Live2D 参数
音频队列顺序播放 + Blob URL 自动回收
ASR 识别文字回显
快捷提问chip
一个需注意的问题
index.html 从官方 CDN 加载 Cubism Core：

<script src="https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js" ...>
演示或比赛环境如果无外网，模型会加载失败。 建议把 live2dcubismcore.min.js 下载后放到 public/ 并改为本地路径。

Phase 1 前后端全部通过，可以进入Phase 2：RAG 问答链+ LLM 接入。
