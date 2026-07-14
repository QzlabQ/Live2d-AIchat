# 测试服务器 Docker Compose 部署设计

## 背景

当前项目已经在本地开发环境中跑通了游客端、管理后台、RAG、ASR、TTS、Live2D 和 PostgreSQL 相关能力，但测试服务器存在几个明确约束：

- 服务器假定为 `Ubuntu 22.04`
- 可使用 `V100` 或 `A100`，当前按 `V100` 作为验收基线
- 服务器具备 `Docker`
- 学校集群通常只能通过 `SSH` 访问，不能直接对浏览器开放端口
- 服务器可能无法稳定访问 Git 仓库，也无法依赖 VPN 从 Hugging Face / ModelScope 在线拉模型

这意味着部署方案必须同时解决 4 个问题：

1. 服务形态要尽量接近最终正式落地
2. 模型与大资源必须支持离线传输
3. 浏览器访问必须通过 `SSH` 端口转发闭环
4. 代码更新和版本回退需要有可操作的流程，而不是一次性手工堆命令

## 目标

采用“`frontend + backend + postgres` 三服务 Docker Compose + 宿主机离线资源挂载 + 本地 SSH 端口转发访问”的方案。

- 使用 `docker compose` 一键拉起前端、后端和 PostgreSQL
- 前端通过 `Nginx` 静态托管并反向代理 `/api` 和 `/ws`
- 后端使用 GPU 运行时容器，挂载宿主机模型目录、CosyVoice 代码目录、知识库目录、上传目录和日志目录
- 模型、知识库和 `CosyVoice` vendor 目录不打进镜像，而是先通过 `scp/rsync` 上传到服务器，再以 bind mount 方式注入容器
- 浏览器统一通过 `ssh -L 本地端口:127.0.0.1:服务器前端端口 user@server` 访问，不要求学校网络开放额外端口
- 部署和更新流程既支持 `git clone/git pull` 主路径，也支持网络不稳定时用 `rsync` 同步代码作为兜底

## 非目标

- 本轮不设计 Kubernetes / Slurm / Ingress 版本的部署方案
- 本轮不做对象存储、模型仓库或私有镜像仓库集成
- 本轮不把模型和知识库文件直接打入镜像
- 本轮不优化正式公网域名、HTTPS 证书和外部反向代理
- 本轮不默认把 RAG reranker / embedding 切到 GPU；先以服务稳定拉起为验收基线

## 方案选择

### 方案 A：代码和模型都在线拉取

最省本地操作，但与当前约束冲突最大。服务器缺 VPN 且外网访问不稳定，模型下载失败概率高，不适合作为测试环境标准方案。

### 方案 B：前端本地跑，服务器只部署后端和数据库

适合后端单独排障，但不符合“测试环境尽量贴近最终落地”的目标。前端构建、Nginx 代理、WebSocket 统一入口都无法在服务器上得到验证。

### 方案 C：三服务容器化 + 离线资源上传 + SSH 端口转发

推荐采用。它同时满足“架构接近正式环境”和“学校集群只能 SSH”的两类约束。模型和大资源不依赖服务器出网，浏览器访问通过 SSH 转发解决，更新流程也能兼容 `git pull` 与本地代码直传两种路径。

## 总体架构

服务器目录统一固定为：

```text
/opt/ai-chat-live2d/
├── app/                     # 项目代码
├── deploy/                  # docker-compose.yml / env / nginx.conf
├── models/
│   ├── CosyVoice2-0.5B/
│   ├── faster-whisper-small/
│   ├── bge-m3/
│   └── bge-reranker-v2-m3/
├── vendor/
│   └── CosyVoice/
└── data/
    ├── postgres/
    ├── knowledge/
    ├── uploads/
    └── logs/
```

容器关系如下：

- `frontend`
  - Nginx 托管前端静态文件
  - 反向代理 `/api` 到 `backend:8000`
  - 反向代理 `/ws` 到 `backend:8000`
  - 仅在服务器本机监听 `127.0.0.1:8080`
- `backend`
  - FastAPI + Uvicorn
  - 通过 Docker GPU runtime 访问 `V100`
  - 通过 Docker 内部网络连接 `postgres`
- `postgres`
  - 官方 PostgreSQL 镜像
  - 数据持久化到宿主机 `data/postgres`

浏览器只接触一个入口：服务器本机的 `8080`。  
用户本地通过 SSH 转发把该端口映射出来，例如：

```bash
ssh -L 18080:127.0.0.1:8080 user@server
```

然后在本地访问：

```text
http://127.0.0.1:18080
```

## 服务设计

### frontend

- 使用多阶段 Dockerfile
  - `node` 阶段执行 `npm ci && npm run build`
  - `nginx` 阶段托管构建产物
- Nginx 负责：
  - `/`：静态前端资源
  - `/api/`：代理到 `http://backend:8000/api/`
  - `/ws/`：代理到 `http://backend:8000/ws/`
- compose 中将容器 `8080` 绑定到宿主机 `127.0.0.1:8080`
- 这样既避免公网暴露，也避免本地分别转发前后端多个端口

### backend

- 使用 GPU 运行时镜像，基线为 `Ubuntu 22.04 + CUDA 12.1 runtime + Python 3.11`
- 启动命令固定为：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 容器内代码目录为 `/app`
- 资源挂载：
  - `/opt/ai-chat-live2d/app/backend -> /app`
  - `/opt/ai-chat-live2d/models -> /models`
  - `/opt/ai-chat-live2d/vendor/CosyVoice -> /vendor/CosyVoice`
  - `/opt/ai-chat-live2d/data/knowledge -> /data/knowledge`
  - `/opt/ai-chat-live2d/data/uploads -> /data/uploads`
  - `/opt/ai-chat-live2d/data/logs -> /data/logs`
- 数据库只通过容器内 DNS `postgres` 访问，不向宿主机暴露 `8000`

### postgres

- 使用官方 `postgres:16`
- 容器内数据目录 `/var/lib/postgresql/data`
- 绑定到宿主机 `data/postgres`
- 不向宿主机暴露端口，只对 `backend` 开放

## 代码同步与资源同步策略

### 代码主路径

代码同步主路径采用 `git clone / git pull`。

- 首次部署：
  - 在服务器 `app/` 下执行 `git clone`
- 日常更新：
  - 在服务器代码目录执行 `git pull`

这是常规部署路径，也最符合后续版本演进。

### 代码兜底路径

如果服务器访问代码仓库不稳定，或者需要同步本地尚未推送的版本，则使用 `rsync` 作为兜底同步代码目录。

`rsync` 在这里的用途是“同步当前工作树”，不是“版本回滚”。

### 模型与大资源同步

模型、`CosyVoice` vendor 目录、知识库和大文件资源统一采用 `scp/rsync` 上传，不通过服务器在线拉取。

需要离线同步的核心目录：

- `backend/storage/models/CosyVoice2-0.5B`
- `backend/storage/models/faster-whisper-small`
- `backend/storage/models/bge-m3`
- `backend/storage/models/bge-reranker-v2-m3`
- `backend/storage/vendor/CosyVoice`
- `backend/storage/knowledge`

这些资源不进入 Git，也不进入 Docker 镜像。

## 环境变量策略

部署目录固定为：

```text
/opt/ai-chat-live2d/deploy
```

部署目录至少包含：

- `docker-compose.yml`
- `backend.env`
- `postgres.env`
- `nginx.conf`

### backend.env

从 `backend/.env.example` 派生，但容器部署时需要改成容器内路径与生产模式：

- `APP_ENV=production`
- `DEBUG=false`
- `DATABASE_URL=postgresql+psycopg://...@postgres:5432/...`
- `CORS_ORIGINS=["http://127.0.0.1:18080","http://localhost:18080"]`
- `ASR_MODEL_NAME=/models/faster-whisper-small`
- `TTS_COSYVOICE_MODEL_PATH=/models/CosyVoice2-0.5B`
- `TTS_COSYVOICE_CODE_PATH=/vendor/CosyVoice`
- `KNOWLEDGE_EMBEDDING_MODEL=/models/bge-m3`
- `RAG_RERANKER_MODEL=/models/bge-reranker-v2-m3`
- `KNOWLEDGE_BASE_DIR=/data/knowledge`
- `ADMIN_KNOWLEDGE_UPLOAD_DIR=/data/uploads/admin/knowledge`
- `ADMIN_VOICE_UPLOAD_DIR=/data/uploads/admin/voice_profiles`

日志、trace、上传与知识库目录都指向容器内挂载路径。

### postgres.env

单独存储：

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

## 启动、访问与更新流程

### 首次部署

1. 在服务器创建目录结构
2. 在 `app/` 下执行 `git clone`
3. 用 `scp/rsync` 上传模型、CosyVoice vendor 和知识库目录
4. 在 `deploy/` 下准备 `docker-compose.yml`、`backend.env`、`postgres.env`、`nginx.conf`
5. 执行：

```bash
docker compose up -d --build
```

### 本地访问

固定通过 SSH 转发访问：

```bash
ssh -L 18080:127.0.0.1:8080 user@server
```

本地浏览器访问：

```text
http://127.0.0.1:18080
```

### 日常更新

优先路径：

1. 服务器代码目录 `git pull`
2. 服务器部署目录执行：

```bash
docker compose up -d --build
```

兜底路径：

1. 本地 `rsync` 同步代码到服务器
2. 服务器重新 `docker compose up -d --build`

### 回滚

版本回滚采用 Git：

- `git checkout <tag|commit>`
- 或切回指定稳定分支

不把 `rsync` 视为回滚机制。

## GPU 与模型运行策略

### GPU 前提

服务器必须已经具备：

- 宿主机可见 GPU（`nvidia-smi` 正常）
- Docker GPU runtime 可用

否则 `backend` 容器中的 `CosyVoice` 无法按当前配置启动。

### 默认设备策略

首轮测试部署优先保证稳定拉起：

- `TTS_COSYVOICE_DEVICE=cuda`
- `TTS_COSYVOICE_ONNX_PROVIDER=cpu`
- `ASR_DEVICE=cpu` 或按服务器情况调整
- `RAG_RERANKER_DEVICE=cpu`
- `KNOWLEDGE_EMBEDDING_DEVICE=cpu`

即使服务器有 `V100`，也不把所有模型默认切到 GPU。  
第一优先级是保证 TTS 主链路稳定，RAG 相关 GPU 调优放在部署成功之后。

## 风险与故障边界

### 风险 1：GPU runtime 未配置完成

症状：

- backend 容器启动失败
- `torch.cuda.is_available()` 为 `False`
- CosyVoice 降级或直接报错

处理方式：先修复宿主机 Docker GPU 环境，再继续部署。

### 风险 2：模型目录不完整

症状：

- backend 启动时报找不到模型
- ASR / TTS / RAG 初始化失败

处理方式：按部署手册重新校验宿主机模型目录和挂载路径。

### 风险 3：代码仓库拉取不稳定

症状：

- `git clone` 或 `git pull` 超时 / 中断

处理方式：切换为 `rsync` 同步代码目录。

### 风险 4：学校集群不开放端口

这是已知约束，不作为异常处理。  
标准访问方式就是 SSH 端口转发，不依赖外部端口开放。

## 验收标准

最小部署验收标准如下：

- `docker compose ps` 中 `frontend`、`backend`、`postgres` 均为运行状态
- 建立 SSH 转发后，本地能打开 `http://127.0.0.1:18080`
- `http://127.0.0.1:18080/api/v1/health` 返回正常
- WebSocket `/ws/chat/{session_id}` 可建立连接
- 管理后台可登录
- backend 启动日志中没有 ASR / TTS / PostgreSQL / RAG 的致命初始化报错
- PostgreSQL 数据目录在宿主机有持久化数据

## 交付物范围

本次实现阶段应交付：

- `docker-compose.yml`
- backend Dockerfile
- frontend Dockerfile
- Nginx 配置
- 面向测试服务器的部署与使用手册

部署手册必须覆盖：

- 环境要求
- 服务器目录结构
- 代码同步方式
- 模型同步方式
- `.env` 与部署配置说明
- 首次启动步骤
- 日常更新步骤
- SSH 转发访问步骤
- 常见问题排查
