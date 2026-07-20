# Scenic Area Guide AI Digital Human

[![README 中文](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87-0F766E?style=for-the-badge)](./README.md)
[![README English](https://img.shields.io/badge/README-English-1D4ED8?style=for-the-badge)](./README.en.md)

The Chinese README is the primary submission and maintenance version; this English README is provided as an external overview and quick-start entry.

> China Software Cup A5 Track Project  
> A multimodal AI digital human system for scenic-area guidance

AI Chat Live2D is a multimodal scenic-area guide system that combines RAG, ASR, TTS, image understanding, Live2D digital human presentation, an admin console, and analytics. It is built to answer, explain, recommend, and clarify more like a real guide than a generic chatbot.

Repository: https://github.com/QzlabQ/Live2d-AI-Guide

Further reading: [Overall Design](docs/overall-design.md)

> Most detailed technical documents under `docs/` are currently maintained in Chinese.

## Demo Preview

- Visitor-side digital human demo GIF: `.github/assets/readme/visitor-demo.gif`
- Admin dashboard screenshot: `.github/assets/readme/admin-dashboard.png`

## Key Highlights

### 1. End-to-end multimodal closed loop

Text questions, voice input, and image uploads are all routed into the same digital-human interaction pipeline. User input goes through ASR or vision understanding, then into RAG / LLM, and finally drives TTS, Live2D expressions, motion, and lip sync for a complete immersive guide experience.

See: [Architecture](docs/architecture.md)

### 2. Humanized RAG rewriting with clarification follow-up

The system does not simply paste raw knowledge-base content into replies. Instead, it rewrites retrieved evidence into spoken guide-style answers and decides whether a clarification question is needed, reducing the "reading documents aloud" feeling.

See: [Knowledge Base Design](docs/knowledge-base.md)

### 3. Layered deployment for RTX 4060 / V100 / A100

The project already supports a layered deployment path including local development, Docker-based test-server deployment, native GPU deployment, and future remote TTS extension. This makes it suitable both for low-VRAM edge devices and for higher-end servers with stronger performance requirements.

See: [GPU Upgrade Guide](docs/gpu-upgrade.md) | [Docker Deployment Guide](docs/deployment/test-server-docker.md)

### 4. High answer accuracy with fine-grained tracing

On the local 50-question document evaluation set, the average answer accuracy reached 98%, while still producing more natural, guide-like responses. The system also includes structured tracing across ASR, RAG, LLM, TTS, and frontend buffering, making it easier to locate latency bottlenecks by `reply_id`.

See: [Knowledge Base Design](docs/knowledge-base.md) | [Roadmap](docs/roadmap.md) | [Backend README](backend/README.md)

## System Capabilities

### Visitor Experience

- Supports text, voice, and image input
- Supports Live2D digital human rendering, thinking state, speaking state, emotion lamp, and basic motion coordination
- Supports streaming replies, speech playback, and lip sync
- Supports a GPT-style session sidebar, multimodal `+` entry, and route recommendation entry

See: [Overall Design](docs/overall-design.md) | [Lip Sync Design](docs/lipsync.md)

### Admin Closed Loop

- Supports avatar configuration, voice-profile management, knowledge-base management, and session inspection
- Supports knowledge-gap collection, manual answer supplementation, and knowledge-base feedback
- Supports dashboard analytics and sentiment reports for continuous service optimization

See: [Overall Design](docs/overall-design.md) | [Roadmap](docs/roadmap.md)

### AI and System Foundation

- `FastAPI + WebSocket` real-time interaction channel
- `faster-whisper` local ASR
- `Qwen / DashScope` chat and visual understanding
- `CosyVoice2-0.5B` local TTS with emotion instruction control
- `bge-m3 + bge-reranker-v2-m3 + ChromaDB` retrieval pipeline
- Trace instrumentation for RAG / ASR / TTS / frontend buffering, with room for multi-GPU migration

See: [Architecture](docs/architecture.md) | [Knowledge Base Design](docs/knowledge-base.md)

## Demo Scenarios / Functional Overview

### Visitor-side guide Q&A

Visitors can type questions, start voice queries, or upload scenic-spot images. The system recognizes intent, retrieves scenic knowledge, generates natural spoken explanations, and presents them through the digital human with speech, expressions, and lip sync.

### Personalized route recommendation

The system supports interest tags and route recommendation for preferences such as history and culture, family travel, night tours, relaxed sightseeing, low-effort routes, and photo spots.

### Admin-side operations

Administrators can switch avatar models, configure reference audio, update the knowledge base, inspect historical sessions, analyze knowledge gaps, and monitor service quality through dashboards and reports.

## Quick Start

### Option 1: Recommended test-server deployment with Docker

This option is intended for a test server with `Ubuntu 22.04 + Docker + NVIDIA GPU`, and is the recommended deployment path for demos and judging. The current Compose setup and helper scripts are organized around the project’s test-server directory conventions, so it should not be interpreted as a universal one-click local installer.

1. Prepare the server directories, model weights, and runtime assets.
2. Run the Docker bootstrap script.
3. Start the full frontend, backend, and database stack.

```bash
./deploy/docker/bootstrap.sh
./deploy/docker/up.sh
```

Detailed steps, directory conventions, environment variables, and access instructions are available in: [Test Server Docker Compose Deployment Guide](docs/deployment/test-server-docker.md)

If Docker is not allowed in the target environment, see: [Test Server Native Deployment Guide](docs/deployment/test-server-native.md)

### Option 2: Local development fallback

Backend:

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

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Default local URLs:

- Visitor UI: `http://127.0.0.1:5173/`
- Admin UI: `http://127.0.0.1:5173/admin.html`
- Backend health check: `http://127.0.0.1:8000/api/v1/health`
- Backend API docs: `http://127.0.0.1:8000/docs`

For Conda notes, Windows dependency fixes, GPU environment details, or a fuller backend setup guide, see: [backend/README.md](backend/README.md)

## Models and Assets

For a full local run or competition deployment, prepare the following assets:

| Resource | Suggested Directory |
| --- | --- |
| `FunAudioLLM/CosyVoice2-0.5B` | `backend/storage/models/CosyVoice2-0.5B` |
| `Systran/faster-whisper-small` | `backend/storage/models/faster-whisper-small` |
| `BAAI/bge-m3` | `backend/storage/models/bge-m3` |
| `BAAI/bge-reranker-v2-m3` | `backend/storage/models/bge-reranker-v2-m3` |
| `FunAudioLLM/CosyVoice` vendor code | `backend/storage/vendor/CosyVoice` |

For model download details, server-side asset mapping, and environment setup, see: [backend/README.md](backend/README.md) | [Test Server Docker Compose Deployment Guide](docs/deployment/test-server-docker.md)

## Repository Structure

```text
AI-chat-live2d/
├─ frontend/                  # Vue 3 + Vite visitor UI / admin console
├─ backend/                   # FastAPI backend and AI service orchestration
├─ docs/                      # Architecture, knowledge base, deployment, lip sync, etc.
├─ deploy/                    # Docker / native deployment assets
└─ .github/workflows/         # CI
```

## Stage Progress

As of `2026-07-18`, the project has completed the following major milestones:

- Established the frontend-backend base architecture, WebSocket pipeline, ASR/TTS chain, knowledge import, and dialogue main loop
- Completed RAG retrieval, humanized answer rewriting, clarification follow-up, CosyVoice2 speech generation, and lip-sync integration
- Completed multimodal visitor interaction, session sidebar, admin console, voice-profile management, knowledge-gap management, dashboard analytics, and sentiment reports
- Added Docker and native test-server deployment documents, along with an upgrade path for stronger GPU environments

The current follow-up work is mainly focused on streaming audio performance evolution on low-VRAM edge devices, quantitative lip-sync validation, and final stress testing and submission polishing.

See: [Roadmap](docs/roadmap.md)

## Important Documentation

- [Overall Design](docs/overall-design.md)
- [Architecture](docs/architecture.md)
- [Knowledge Base Design](docs/knowledge-base.md)
- [Lip Sync Design](docs/lipsync.md)
- [Test Server Docker Compose Deployment Guide](docs/deployment/test-server-docker.md)
- [Test Server Native Deployment Guide](docs/deployment/test-server-native.md)
- [GPU Upgrade Guide](docs/gpu-upgrade.md)
- [Roadmap](docs/roadmap.md)

## License

This repository is currently used mainly for competition development and internal testing.  
Some models, digital-human assets, and third-party dependencies are subject to their own licenses, so authorization scope should be checked carefully before any public release.
