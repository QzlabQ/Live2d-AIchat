# 景区导览服务 AI 数字人

> 中国软件杯 A5 赛题项目  
> 面向景区导览场景的多模态 AI 数字人系统

本项目聚焦“景区导览”这一真实服务场景，构建了一套集文字问答、语音交互、图片识图、Live2D 数字人展示、知识库问答、管理后台与数据分析于一体的完整系统。它不仅能“回答问题”，还强调“像导游一样讲解、推荐、追问与持续运营”。

仓库连接：https://github.com/QzlabQ/Live2d-AI-Guide

延伸阅读：[总体设计说明](docs/overall-design.md)

## 演示预览

https://github.com/user-attachments/assets/721c7be0-dc56-4576-bde2-b6f160619382

## 核心亮点

### 1. 端到端多模态闭环

系统将文本提问、语音输入、拍照识图统一纳入同一条数字人问答主链：用户输入经过 ASR 或视觉识别后进入 RAG / LLM，再联动 TTS、Live2D 表情、动作和口型同步，形成完整的沉浸式导览体验。

详见：[系统架构设计](docs/architecture.md)

### 2. 口语化 RAG 改写与澄清追问

系统并不直接把知识库原文拼接给游客，而是先对检索结果做导览式口语重写，再根据问题是否模糊决定是否继续澄清追问，从而显著降低“念资料”的机器感。

详见：[知识库建设方案](docs/knowledge-base.md)

### 3. 面向 4060 / V100 / A100 的多层部署方案

项目已形成“本机开发联调 + 测试服务器 Docker 部署 + 原生 GPU 部署 + 后续远程 TTS 扩展”的多层方案，既能适配低显存边缘端环境，也为更高算力服务器上的性能演进留出了清晰路径。

详见：[显卡升级与迁移建议](docs/gpu-upgrade.md)｜[Docker 部署手册](docs/deployment/test-server-docker.md)

### 4. 高准确率回答与高细度的 tracing

本地 50 道文档准确率均值达到 98%，能够在保证事实准确性的同时，生成更自然、更像导览员的口语化回答。
系统同时对 ASR、RAG、LLM、TTS 以及前端缓冲做了结构化 tracing，支持按 `reply_id` 回放关键耗时链路，便于快速定位瓶颈与卡顿来源。

详见：[知识库建设方案](docs/knowledge-base.md)｜[研发路线与阶段记录](docs/roadmap.md)｜[后端 Trace 与日志](backend/README.md#trace-与日志)

## 系统能力总览

### 游客体验

- 支持文本、语音、图片三类输入方式
- 支持 Live2D 数字人展示、思考态、说话态、情绪灯与基础动作协调
- 支持流式回复、语音播报与口型同步
- 支持 GPT 风格历史会话侧边栏、多模态 `+` 入口与路线推荐入口

详见：[总体设计说明](docs/overall-design.md)｜[口型同步方案](docs/lipsync.md)

### 管理闭环

- 支持数字人配置、音色管理、知识库管理、会话记录查看
- 支持知识缺口统计、人工补答并回流知识库
- 支持数据大屏与感受度报告，便于从“服务记录”走向“运营分析”

详见：[总体设计说明](docs/overall-design.md)｜[研发路线与阶段记录](docs/roadmap.md)

### AI 与系统底座

- `FastAPI + WebSocket` 实时对话通道
- `faster-whisper` 本地 ASR
- `Qwen / DashScope` 问答与视觉识别
- `CosyVoice2-0.5B` 本地 TTS 与情绪指令发声
- `bge-m3 + bge-reranker-v2-m3 + ChromaDB` 知识库检索链路
- RAG / ASR / TTS / 前端缓冲 trace 与多显卡迁移预留

详见：[系统架构设计](docs/architecture.md)｜[知识库建设方案](docs/knowledge-base.md)

## 演示场景 / 功能概览

### 游客端导览问答

游客可以直接输入文字、发起语音提问，或上传景点图片。系统会识别问题意图、检索景区资料、生成自然讲解，并通过数字人进行语音播报与表情口型联动。

### 个性化游览推荐

系统支持兴趣标签与路线推荐能力，能够围绕“历史文化、亲子、夜游、轻松、省力、拍照打卡”等偏好生成更贴近游客需求的游览建议。

### 管理后台运营

管理员可以切换数字人形象、配置参考音频、更新知识库、查看历史会话、分析知识缺口，并通过数据大屏与日报总结持续优化服务质量。

## 快速开始

### 方式一：测试服务器推荐部署（Docker 优先）

该方式适用于 `Ubuntu 22.04 + Docker + NVIDIA GPU` 的测试服务器环境，适合作为评审演示部署方案。当前 Compose 与辅助脚本围绕测试服务器目录约定组织，不等价于“任意本地机器直接一键启动”。

1. 准备服务器目录、模型权重与运行资源
2. 执行 Docker 部署自举脚本
3. 启动完整前后端与数据库栈

```bash
./deploy/docker/bootstrap.sh
./deploy/docker/up.sh
```

详细步骤、目录约定、环境变量与访问方式详见：[测试服务器 Docker Compose 部署手册](docs/deployment/test-server-docker.md)

如果目标环境禁用 Docker，请改看：[测试服务器原生部署手册](docs/deployment/test-server-native.md)

### 方式二：本地开发兜底

后端：

```bash
cd backend
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements.asr.txt
python -m pip install -r requirements.knowledge.txt
python -m pip install -r requirements.tts.txt --no-build-isolation
cp .env.example .env
python -m uvicorn main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：

- 游客端：`http://127.0.0.1:5173/`
- 管理后台：`http://127.0.0.1:5173/admin.html`
- 后端健康检查：`http://127.0.0.1:8000/api/v1/health`
- 后端接口文档：`http://127.0.0.1:8000/docs`

如果需要 Conda、Windows 二进制依赖修复、GPU 环境说明或更完整的后端启动说明，请看：[backend/README.md](backend/README.md)

## 模型与资源准备

比赛部署或本地完整联调时，建议准备以下资源：

| 资源                                | 建议目录                                      |
| ----------------------------------- | --------------------------------------------- |
| `FunAudioLLM/CosyVoice2-0.5B`       | `backend/storage/models/CosyVoice2-0.5B`      |
| `Systran/faster-whisper-small`      | `backend/storage/models/faster-whisper-small` |
| `BAAI/bge-m3`                       | `backend/storage/models/bge-m3`               |
| `BAAI/bge-reranker-v2-m3`           | `backend/storage/models/bge-reranker-v2-m3`   |
| `FunAudioLLM/CosyVoice` vendor 代码 | `backend/storage/vendor/CosyVoice`            |

模型下载细节、服务器资源映射和环境配置详见：[backend/README.md](backend/README.md)｜[测试服务器 Docker Compose 部署手册](docs/deployment/test-server-docker.md)

## 仓库结构

```text
AI-chat-live2d/
├─ frontend/                  # Vue 3 + Vite 游客端 / 管理后台
├─ backend/                   # FastAPI 后端与 AI 服务编排
├─ docs/                      # 架构、知识库、部署、口型同步等文档
├─ deploy/                    # Docker / 原生部署资产
└─ .github/workflows/         # CI
```

## 阶段成果

截至 `2026-07-18`，项目已经完成以下阶段性成果：

- 已打通前后端基础骨架、WebSocket、ASR/TTS、知识库导入与对话主链
- 已完成 RAG 检索、口语化回答改写、澄清追问、CosyVoice2 发声与数字人口型同步主链
- 已完成游客端多模态体验、会话侧边栏、管理后台、音色管理、知识缺口、数据大屏与感受度报告
- 已补齐测试服务器 Docker / 原生部署文档，以及面向更高算力 GPU 的扩展思路

当前的后续工作重点主要集中在低显存边缘端设备的流式音频链路性能演进、口型同步量化验收以及最终压测与交付材料收尾。

详见：[研发路线与阶段记录](docs/roadmap.md)

## 重要文档导航

- [总体设计说明](docs/overall-design.md)
- [系统架构设计](docs/architecture.md)
- [知识库建设方案](docs/knowledge-base.md)
- [口型同步方案](docs/lipsync.md)
- [测试服务器 Docker Compose 部署手册](docs/deployment/test-server-docker.md)
- [测试服务器原生部署手册](docs/deployment/test-server-native.md)
- [显卡升级与迁移建议](docs/gpu-upgrade.md)
- [研发路线与阶段记录](docs/roadmap.md)

## License

当前仓库主要用于比赛开发与校内测试。  
其中部分模型、数字人资源、第三方依赖存在各自的许可证约束，正式公开发布前需要逐项核对授权范围。
