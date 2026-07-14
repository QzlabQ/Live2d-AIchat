# 测试服务器 Docker Compose 部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `Ubuntu 22.04 + Docker + V100 + 仅 SSH 访问` 的测试服务器补齐 `frontend + backend + postgres` 三服务 Compose 部署，并交付可执行的中文部署与使用手册。

**Architecture:** 前端使用 Nginx 静态托管并反向代理 `/api` 与 `/ws`；后端使用 GPU 运行时镜像并挂载宿主机模型、CosyVoice vendor、知识库、上传和日志目录；PostgreSQL 独立持久化。浏览器统一通过 `ssh -L 18080:127.0.0.1:8080 user@server` 访问，不要求服务器直接对外开放端口。

**Tech Stack:** Docker Compose、Nginx、FastAPI、PostgreSQL 16、CUDA 12.1 runtime、Conda/Micromamba 等价容器环境、Vue 3 + Vite。

---

## File Structure

### New Files

- `deploy/docker-compose.yml`
  - 三服务编排文件，供服务器 `/opt/ai-chat-live2d/deploy/` 直接使用
- `deploy/backend.env.example`
  - 容器版后端环境变量模板
- `deploy/postgres.env.example`
  - PostgreSQL 环境变量模板
- `deploy/nginx/default.conf`
  - 前端 Nginx 配置，代理 `/api` 和 `/ws`
- `backend/Dockerfile`
  - GPU 运行时后端镜像
- `backend/.dockerignore`
  - 排除 `.env`、`storage`、缓存等构建噪音
- `backend/requirements.container.txt`
  - 聚合容器运行依赖，统一安装 `runtime + postgres + asr + knowledge + tts`
- `frontend/Dockerfile`
  - 多阶段前端镜像
- `frontend/.dockerignore`
  - 排除 `.env`、`node_modules`、`dist`
- `frontend/src/lib/runtimeBaseUrl.ts`
  - 统一处理生产环境相对 API/WS 基地址
- `frontend/src/lib/runtimeBaseUrl.test.ts`
  - 覆盖相对路径、显式 URL、默认回退逻辑
- `docs/deployment/test-server-docker.md`
  - 中文部署与使用手册

### Modified Files

- `frontend/src/App.vue`
  - 改为使用运行时基地址 helper，而不是默认写死 `127.0.0.1:8000`
- `frontend/src/services/adminApi.ts`
  - 管理后台 API 默认值改为生产可用的相对路径
- `frontend/.env.example`
  - 保留本地开发变量，同时说明生产容器构建不应依赖该文件
- `README.md`
  - 新增测试服务器部署入口链接
- `backend/README.md`
  - 增加 Docker Compose 部署说明与链接

### Validation Targets

- `frontend/src/lib/runtimeBaseUrl.test.ts`
- `frontend` `npm test -- --run`
- `frontend` `npm run build`
- `backend` `python -m unittest discover -s tests`
- `docker compose -f deploy/docker-compose.yml --env-file deploy/backend.env.example config`
- `docker build -f backend/Dockerfile backend`
- `docker build -f frontend/Dockerfile frontend`

---

### Task 1: 前端生产基地址改造

**Files:**
- Create: `frontend/src/lib/runtimeBaseUrl.ts`
- Create: `frontend/src/lib/runtimeBaseUrl.test.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/services/adminApi.ts`
- Modify: `frontend/.env.example`
- Test: `frontend/src/lib/runtimeBaseUrl.test.ts`

- [ ] **Step 1: 写前端运行时基地址测试**

```ts
import { describe, expect, it } from 'vitest'

import {
  resolveApiBaseUrl,
  resolveWsBaseUrl,
} from './runtimeBaseUrl'

describe('resolveApiBaseUrl', () => {
  it('uses relative production default when env is empty', () => {
    expect(resolveApiBaseUrl('', 'http://127.0.0.1:18080')).toBe('/api/v1')
  })

  it('preserves explicit absolute API base URL', () => {
    expect(resolveApiBaseUrl('http://127.0.0.1:8000/api/v1', 'http://127.0.0.1:18080')).toBe(
      'http://127.0.0.1:8000/api/v1',
    )
  })
})

describe('resolveWsBaseUrl', () => {
  it('uses page origin for websocket when env is empty', () => {
    expect(resolveWsBaseUrl('', 'http://127.0.0.1:18080')).toBe('ws://127.0.0.1:18080')
  })

  it('converts https origin into wss base URL', () => {
    expect(resolveWsBaseUrl('', 'https://demo.example.com')).toBe('wss://demo.example.com')
  })

  it('preserves explicit websocket base URL', () => {
    expect(resolveWsBaseUrl('ws://127.0.0.1:8000', 'http://127.0.0.1:18080')).toBe(
      'ws://127.0.0.1:8000',
    )
  })
})
```

- [ ] **Step 2: 运行测试并确认先失败**

Run:

```bash
cd frontend
npm test -- --run src/lib/runtimeBaseUrl.test.ts
```

Expected: FAIL，报 `Cannot find module './runtimeBaseUrl'` 或找不到导出函数。

- [ ] **Step 3: 实现运行时基地址 helper**

```ts
function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '')
}

function toWsOrigin(origin: string) {
  if (origin.startsWith('https://')) {
    return `wss://${origin.slice('https://'.length)}`
  }
  if (origin.startsWith('http://')) {
    return `ws://${origin.slice('http://'.length)}`
  }
  return origin.startsWith('ws://') || origin.startsWith('wss://') ? origin : `ws://${origin}`
}

export function resolveApiBaseUrl(envValue: string | undefined, pageOrigin?: string) {
  const normalized = (envValue || '').trim()
  if (normalized) {
    return trimTrailingSlash(normalized)
  }
  void pageOrigin
  return '/api/v1'
}

export function resolveWsBaseUrl(envValue: string | undefined, pageOrigin: string) {
  const normalized = (envValue || '').trim()
  if (normalized) {
    return trimTrailingSlash(normalized)
  }
  return trimTrailingSlash(toWsOrigin(pageOrigin))
}
```

- [ ] **Step 4: 将游客端与管理端切换到 helper**

```ts
// frontend/src/App.vue
import { resolveApiBaseUrl, resolveWsBaseUrl } from './lib/runtimeBaseUrl'

const pageOrigin = window.location.origin
const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, pageOrigin)
const WS_BASE_URL = resolveWsBaseUrl(import.meta.env.VITE_WS_BASE_URL, pageOrigin)
```

```ts
// frontend/src/services/adminApi.ts
import { resolveApiBaseUrl } from '../lib/runtimeBaseUrl'

const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, window.location.origin)
```

```env
# frontend/.env.example
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_WS_BASE_URL=ws://127.0.0.1:8000
VITE_LIVE2D_MODEL_PATH=/live2d/haru/haru_greeter_t03.model3.json
VITE_HEARTBEAT_MS=15000
VITE_RECONNECT_BASE_MS=1200

# 生产容器构建时不依赖这个文件，默认使用 Nginx 同源代理：
# API -> /api/v1
# WS  -> 当前页面 origin 对应的 ws/wss
```

- [ ] **Step 5: 运行测试并确认通过**

Run:

```bash
cd frontend
npm test -- --run src/lib/runtimeBaseUrl.test.ts
```

Expected: PASS

- [ ] **Step 6: 运行前端全量测试与构建**

Run:

```bash
cd frontend
npm test -- --run
npm run build
```

Expected:

- `43 passed` 或当前全量测试数全部通过
- `vite build` 成功

- [ ] **Step 7: Commit**

```bash
git add \
  frontend/src/lib/runtimeBaseUrl.ts \
  frontend/src/lib/runtimeBaseUrl.test.ts \
  frontend/src/App.vue \
  frontend/src/services/adminApi.ts \
  frontend/.env.example
git commit -m "feat: support relative api and ws base urls for docker deploy"
```

---

### Task 2: 后端容器运行时与依赖聚合

**Files:**
- Create: `backend/requirements.container.txt`
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `deploy/backend.env.example`
- Create: `deploy/postgres.env.example`

- [ ] **Step 1: 写容器依赖聚合文件**

```txt
-r requirements.runtime.txt
-r requirements.postgres.txt
-r requirements.asr.txt
-r requirements.knowledge.txt
-r requirements.tts.txt
```

- [ ] **Step 2: 写后端 Docker 构建配置**

```dockerfile
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV CONDA_DIR=/opt/conda
ENV PATH=/opt/conda/bin:/opt/conda/envs/ai-chat-gpu/bin:${PATH}
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    curl \
    ffmpeg \
    git \
    libglib2.0-0 \
    libgomp1 \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-py311_24.5.0-0-Linux-x86_64.sh -o /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p "${CONDA_DIR}" \
    && rm -f /tmp/miniconda.sh

WORKDIR /app

COPY environment.ai-chat-gpu.yml /tmp/environment.ai-chat-gpu.yml
COPY requirements.runtime.txt requirements.postgres.txt requirements.asr.txt requirements.knowledge.txt requirements.tts.txt requirements.container.txt /tmp/

RUN conda env create -f /tmp/environment.ai-chat-gpu.yml \
    && /opt/conda/envs/ai-chat-gpu/bin/python -m pip install --upgrade pip \
    && /opt/conda/envs/ai-chat-gpu/bin/python -m pip install --no-build-isolation -r /tmp/requirements.container.txt \
    && conda clean -afy

COPY main.py /app/main.py
COPY app /app/app

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: 写后端 `.dockerignore`**

```dockerignore
.env
.venv
.pytest_cache
__pycache__
logs
storage
tests
evals
phase1.db
```

- [ ] **Step 4: 写部署用环境变量模板**

```env
# deploy/backend.env.example
APP_NAME=AI Chat Live2D Backend
APP_ENV=production
DEBUG=false
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://ai_chat:ai_chat_pg_2026@postgres:5432/ai_chat_live2d
CORS_ORIGINS=["http://127.0.0.1:18080","http://localhost:18080"]

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_JWT_SECRET=ai-chat-admin-secret-2026
ADMIN_TOKEN_TTL_SECONDS=86400
ADMIN_KNOWLEDGE_UPLOAD_DIR=/data/uploads/admin/knowledge
ADMIN_VOICE_UPLOAD_DIR=/data/uploads/admin/voice_profiles

DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen3.7-plus
DASHSCOPE_VL_MODEL=qwen-vl-max

ASR_ENGINE=faster-whisper
ASR_MODEL_NAME=/models/faster-whisper-small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
ASR_LANGUAGE=zh

TTS_ENGINE=cosyvoice
TTS_COSYVOICE_MODEL_PATH=/models/CosyVoice2-0.5B
TTS_COSYVOICE_CODE_PATH=/vendor/CosyVoice
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_ONNX_PROVIDER=cpu
TTS_COSYVOICE_SAMPLE_RATE=24000
TTS_COSYVOICE_FP16=true
TTS_COSYVOICE_LOAD_JIT=false
TTS_PROVIDER=local
TTS_STREAM_PROFILE=stable

CHAT_MODE=rag
RAG_RESPONSE_MODE=fast_humanized
RAG_RERANKER_ENGINE=lexical
RAG_RERANKER_MODEL=/models/bge-reranker-v2-m3
RAG_RERANKER_DEVICE=cpu

KNOWLEDGE_BASE_DIR=/data/knowledge
KNOWLEDGE_EMBEDDING_ENGINE=bge-m3
KNOWLEDGE_EMBEDDING_MODEL=/models/bge-m3
KNOWLEDGE_EMBEDDING_DEVICE=cpu
```

```env
# deploy/postgres.env.example
POSTGRES_DB=ai_chat_live2d
POSTGRES_USER=ai_chat
POSTGRES_PASSWORD=ai_chat_pg_2026
```

- [ ] **Step 5: 验证后端镜像可以构建**

Run:

```bash
docker build -f backend/Dockerfile backend
```

Expected: build 成功，最终阶段包含 `python` 与 `uvicorn`

- [ ] **Step 6: Commit**

```bash
git add \
  backend/requirements.container.txt \
  backend/Dockerfile \
  backend/.dockerignore \
  deploy/backend.env.example \
  deploy/postgres.env.example
git commit -m "feat: add backend gpu docker runtime and deploy env templates"
```

---

### Task 3: Compose、Nginx 与前端镜像

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `deploy/nginx/default.conf`
- Create: `deploy/docker-compose.yml`

- [ ] **Step 1: 写前端 Dockerfile**

```dockerfile
FROM node:20-bookworm-slim AS build

WORKDIR /frontend

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /frontend/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 2: 写前端 `.dockerignore`**

```dockerignore
.env
node_modules
dist
coverage
```

- [ ] **Step 3: 写 Nginx 代理配置**

```nginx
server {
  listen 8080;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://backend:8000/api/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /ws/ {
    proxy_pass http://backend:8000/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

- [ ] **Step 4: 写 Compose 编排文件**

```yaml
services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    env_file:
      - ./postgres.env
    volumes:
      - /opt/ai-chat-live2d/data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 10

  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - ./backend.env
    depends_on:
      postgres:
        condition: service_healthy
    gpus: all
    expose:
      - "8000"
    volumes:
      - /opt/ai-chat-live2d/app/backend:/app
      - /opt/ai-chat-live2d/models:/models
      - /opt/ai-chat-live2d/vendor/CosyVoice:/vendor/CosyVoice
      - /opt/ai-chat-live2d/data/knowledge:/data/knowledge
      - /opt/ai-chat-live2d/data/uploads:/data/uploads
      - /opt/ai-chat-live2d/data/logs:/data/logs
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')\""]
      interval: 20s
      timeout: 10s
      retries: 10

  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
    restart: unless-stopped
    depends_on:
      backend:
        condition: service_healthy
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
```

- [ ] **Step 5: 验证 Compose 配置与前端镜像**

Run:

```bash
docker build -f frontend/Dockerfile frontend
docker compose -f deploy/docker-compose.yml --env-file deploy/backend.env.example config
```

Expected:

- frontend 镜像 build 成功
- `docker compose config` 输出规范化 YAML，无字段错误

- [ ] **Step 6: Commit**

```bash
git add \
  frontend/Dockerfile \
  frontend/.dockerignore \
  deploy/nginx/default.conf \
  deploy/docker-compose.yml
git commit -m "feat: add compose orchestration and nginx frontend proxy"
```

---

### Task 4: 部署与使用手册

**Files:**
- Create: `docs/deployment/test-server-docker.md`
- Modify: `README.md`
- Modify: `backend/README.md`

- [ ] **Step 1: 写部署手册正文**

```md
# 测试服务器 Docker Compose 部署手册

## 适用环境

- Ubuntu 22.04
- Docker / docker compose
- NVIDIA GPU（V100 / A100）
- 仅可通过 SSH 访问

## 服务器目录结构

```text
/opt/ai-chat-live2d/
├── app/
├── deploy/
├── models/
├── vendor/
└── data/
```

## 首次部署

### 1. 创建目录

```bash
sudo mkdir -p /opt/ai-chat-live2d/{app,deploy,models,vendor,data}
sudo mkdir -p /opt/ai-chat-live2d/data/{postgres,knowledge,uploads,logs}
sudo chown -R "$USER":"$USER" /opt/ai-chat-live2d
```

### 2. 拉代码

```bash
cd /opt/ai-chat-live2d/app
git clone https://github.com/QzlabQ/Live2d-AIchat .
```

### 3. 上传模型与大资源

```bash
scp -r ./backend/storage/models/CosyVoice2-0.5B user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/faster-whisper-small user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-reranker-v2-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/vendor/CosyVoice user@server:/opt/ai-chat-live2d/vendor/
scp -r ./backend/storage/knowledge user@server:/opt/ai-chat-live2d/data/
```

### 4. 准备部署配置

```bash
cp /opt/ai-chat-live2d/app/deploy/docker-compose.yml /opt/ai-chat-live2d/deploy/
cp /opt/ai-chat-live2d/app/deploy/backend.env.example /opt/ai-chat-live2d/deploy/backend.env
cp /opt/ai-chat-live2d/app/deploy/postgres.env.example /opt/ai-chat-live2d/deploy/postgres.env
cp -r /opt/ai-chat-live2d/app/deploy/nginx /opt/ai-chat-live2d/deploy/
```

### 5. 启动服务

```bash
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

## 本地访问

```bash
ssh -L 18080:127.0.0.1:8080 user@server
```

打开：

```text
http://127.0.0.1:18080
```

## 日常更新

### 正常更新

```bash
cd /opt/ai-chat-live2d/app
git pull
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

### 仓库拉取不稳时

```bash
rsync -avz --delete ./ user@server:/opt/ai-chat-live2d/app/
ssh user@server "cd /opt/ai-chat-live2d/deploy && docker compose up -d --build"
```

## 故障排查

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```
```

- [ ] **Step 2: 在 README 中补入口链接**

```md
## 部署

- 测试服务器 Docker Compose 部署：`docs/deployment/test-server-docker.md`
```

```md
## Docker 测试部署

完整步骤见 `../docs/deployment/test-server-docker.md`
```

- [ ] **Step 3: 验证文档中的命令和路径**

Run:

```bash
rg -n "/opt/ai-chat-live2d|docker compose up -d --build|ssh -L 18080:127.0.0.1:8080" docs/deployment/test-server-docker.md README.md backend/README.md
```

Expected: 三份文档都能检出一致的部署路径与访问命令

- [ ] **Step 4: Commit**

```bash
git add \
  docs/deployment/test-server-docker.md \
  README.md \
  backend/README.md
git commit -m "docs: add docker compose deployment manual for test server"
```

---

### Task 5: 最终验证

**Files:**
- Verify only

- [ ] **Step 1: 跑前端测试与构建**

Run:

```bash
cd frontend
npm test -- --run
npm run build
```

Expected: 全部通过

- [ ] **Step 2: 跑后端测试**

Run:

```bash
cd backend
python -m unittest discover -s tests
```

Expected: 全部通过

- [ ] **Step 3: 校验 Compose 配置**

Run:

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/backend.env.example config
```

Expected: 输出规范化 compose 配置，无语法错误

- [ ] **Step 4: 本地构建容器镜像**

Run:

```bash
docker build -f backend/Dockerfile backend
docker build -f frontend/Dockerfile frontend
```

Expected: 两个镜像都可构建成功

- [ ] **Step 5: 汇总已知风险**

Document in final report:

- 服务器若无法访问 Docker Hub / apt / PyPI，则需要补一条“本地预构建镜像后 `docker save` + `scp` + `docker load`”的离线兜底流程
- 当前计划默认服务器 Docker GPU runtime 已可用
- 模型目录不完整会导致 backend 启动失败

- [ ] **Step 6: Commit any remaining validation-related edits**

```bash
git status --short
```

Expected: 只剩下有意保留的工作区变更；若为干净状态则无需额外提交

---

## Self-Review

- Spec coverage:
  - 三服务 Compose：Task 2 + Task 3
  - 宿主机挂载模型与知识库：Task 2 + Task 4
  - SSH 转发访问：Task 4
  - `git clone/git pull` 主路径与 `rsync` 兜底：Task 4
  - Docker 部署文档：Task 4
  - 一键部署验证：Task 3 + Task 5
- Placeholder scan:
  - 无 `TODO/TBD`
  - 所有文件路径、命令、环境变量名都已具体化
- Type consistency:
  - 前端 API/WS helper 命名统一为 `resolveApiBaseUrl` / `resolveWsBaseUrl`
  - Compose 目录统一以 `deploy/` 为仓库内配置源，服务器目标目录统一为 `/opt/ai-chat-live2d/deploy`
