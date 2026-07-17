# 景区导览服务 AI 数字人

> 中国软件杯 A5 赛题项目  
> 当前仓库状态更新于 `2026-07-14`

一个面向景区导览场景的多模态 AI 数字人系统，支持文字/语音问答、Live2D 数字人驱动、RAG 知识库问答、游客端个性化推荐、管理后台配置与数据大屏。

项目目标不是只做“会回答问题的聊天框”，而是做一个可演示、可配置、可部署的景区导览数字人产品原型。

## 当前进度

按照 [docs/roadmap.md](docs/roadmap.md) 统计，目前整体进度如下：

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| Phase 1 基础骨架 | 已完成 | 前后端骨架、WebSocket、ASR/TTS 基础链路、知识库导入已打通 |
| Phase 2 核心 AI 能力 | 基本完成 | RAG、CosyVoice2 TTS、流式音频、口型同步、情绪与动作联动已落地 |
| Phase 3 功能完整化 | 基本完成 | 游客端、管理后台、数字人配置、知识库管理、会话记录、语音与多模态体验已完成主链路 |
| Phase 4 数据大屏与体验打磨 | 部分完成 | 数据大屏、感受度报告已完成；TTS 延迟、口型精度、体验收尾仍在优化 |
| Phase 5 测试与交付 | 未开始/进行前准备 | 一键部署、完整验收、最终材料整理仍待收尾 |

如果只看“是否已经可演示”，答案是：**可以**。  
如果看“是否已经达到比赛最终交付质量”，答案是：**还在做性能与部署收尾**。

## 已实现能力

### 游客端

- 文字对话与语音对话
- `faster-whisper` 语音识别链路
- Live2D 数字人展示、情绪切换、思考态/说话态动作协调
- CosyVoice2 本地 TTS 发声
- 流式音频播放与基础口型同步
- 拍照上传后进行景点识别与问答
- 个性化路线/偏好推荐入口
- GPT 风格的历史会话侧边栏与多模态 `+` 入口
- 多数字人切换

### 管理后台

- 数字人配置页
- 知识库管理页
- 会话记录页
- 感受度报告页
- 数据大屏页
- 后台数字人实时预览与情绪预览

### 后端与 AI

- FastAPI + WebSocket 实时对话通道
- PostgreSQL / SQLite 数据持久化
- RAG 检索、重排、生成与口语化改写
- 澄清追问状态管理
- CosyVoice2-0.5B 本地 TTS
- 本地/远程 TTS Provider 抽象
- ASR / RAG / TTS / 前端缓冲 trace 记录

## 核心亮点

1. **不是纯聊天机器人**  
   以景区导览为主场景，强调“可讲解、可推荐、可配置、可管理”。

2. **RAG 回答做人性化改写**  
   不直接把知识库原文拼接给游客，而是先重写成导览式口语回答，并在需要时主动澄清。

3. **数字人链路已完整打通**  
   从游客输入，到 LLM/RAG 回答，到 TTS 发声，再到 Live2D 表情与口型联动，已经形成端到端演示链路。

4. **已经考虑真实部署问题**  
   仓库内已经补齐 Docker 部署资产、原生无 Docker 部署脚本与文档、GPU 环境说明和后续 A100/V100 扩展路线。

## 仓库结构

```text
AI-chat-live2d/
├─ frontend/                  # Vue 3 + Vite 游客端 / 管理后台
│  ├─ src/
│  ├─ public/live2d/          # Live2D 模型与静态资源
│  └─ tests/
├─ backend/                   # FastAPI 后端
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ models/
│  │  └─ services/
│  ├─ storage/                # 模型、知识库、上传文件等运行时资源
│  ├─ scripts/                # 评测与辅助脚本
│  └─ tests/
├─ docs/                      # 架构、路线图、部署、知识库、口型同步等文档
├─ deploy/                    # Docker Compose / 原生部署资产
└─ .github/workflows/         # CI
```

## 技术栈

### 前端

- Vue 3
- TypeScript
- Vite
- PixiJS
- `pixi-live2d-display`

### 后端

- FastAPI
- SQLAlchemy
- WebSocket
- PostgreSQL / SQLite

### AI 能力

- DashScope / Qwen
- `faster-whisper`
- CosyVoice2-0.5B
- ChromaDB
- BGE Embedding / Reranker

## 快速开始

### 1. 本地开发启动

后端推荐直接参考 [backend/README.md](backend/README.md) 中的 conda 方案。当前项目主要在 `ai-chat-gpu` 这套环境中联调。

后端：

```powershell
cd backend
conda activate ai-chat-gpu
python -m uvicorn main:app --reload
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

默认访问地址：

- 游客端：`http://127.0.0.1:5173/`
- 管理后台：`http://127.0.0.1:5173/admin.html`
- 后端健康检查：`http://127.0.0.1:8000/api/v1/health`
- Swagger：`http://127.0.0.1:8000/docs`

### 2. 测试服务器部署

仓库已提供两套测试服务器部署资产：

- [deploy/docker-compose.yml](deploy/docker-compose.yml)
- [deploy/docker/](deploy/docker/)
- [deploy/native/](deploy/native/)
- [docs/deployment/test-server-docker.md](docs/deployment/test-server-docker.md)
- [docs/deployment/test-server-native.md](docs/deployment/test-server-native.md)

适用场景：

- `Ubuntu 22.04 + Docker`：看 Docker 文档
- `Ubuntu 22.04 + 禁用 Docker`：看原生部署文档
- `PostgreSQL`
- `V100 / A100` 测试服务器

### 3. CI

当前仓库已配置基础 CI：

- 前端构建测试
- 后端轻量测试

工作流位置：

- [.github/workflows/ci.yml](.github/workflows/ci.yml)

## 重要文档导航

- [docs/roadmap.md](docs/roadmap.md)：项目阶段计划与完成情况
- [docs/architecture.md](docs/architecture.md)：整体架构
- [docs/api-design.md](docs/api-design.md)：接口设计
- [docs/knowledge-base.md](docs/knowledge-base.md)：知识库方案
- [docs/lipsync.md](docs/lipsync.md)：口型同步方案
- [docs/gpu-upgrade.md](docs/gpu-upgrade.md)：显卡升级与迁移建议
- [docs/deployment/test-server-docker.md](docs/deployment/test-server-docker.md)：测试服务器 Docker 部署手册
- [docs/deployment/test-server-native.md](docs/deployment/test-server-native.md)：测试服务器原生部署手册

## 当前重点问题

目前最需要继续打磨的不是“有没有功能”，而是“体验是否足够稳定”：

- TTS 流式发声速度仍慢于理想状态
- 4060 本机环境下偶发卡顿仍需继续优化
- 口型同步主观体验已可用，但还需要更严格的量化验收
- 最终部署、评测、交付材料还需要补齐

## 说明

- 仓库体积相对偏大，主要原因是 `frontend/public/live2d/` 中直接纳入了 Live2D 模型资源。
- `data/`、本地模型、虚拟环境、日志等运行时目录默认不纳入 Git。
- 如果后续要做正式开源整理，建议把大体积数字人资源与模型下载步骤进一步拆分。

## License

当前仓库主要用于比赛开发与校内测试。  
其中部分模型、数字人资源、第三方依赖存在各自的许可证约束，正式公开发布前需要逐项核对授权范围。
