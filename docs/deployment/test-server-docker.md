# 测试服务器 Docker Compose 部署手册

如果你的服务器 **禁止使用 Docker**，请直接看 [test-server-native.md](./test-server-native.md)。  
当前测试服务器已经补充了对应的原生部署链路与脚本，不需要再硬套本文的容器方案。

本文对应当前项目的测试服务器部署方案，目标环境为 `Ubuntu 22.04 + Docker + NVIDIA GPU`，并默认学校集群只能通过 `SSH` 访问。

## 1. 适用环境

- 操作系统：`Ubuntu 22.04`
- 容器环境：`Docker`、`docker compose`
- GPU：`V100`、`A100`，或其他已正确配置 Docker GPU runtime 的 NVIDIA 显卡
- 访问方式：仅 `SSH`
- 网络前提：
  - 代码仓库最好能 `git clone / git pull`
  - 模型、知识库、CosyVoice 代码不要依赖服务器在线下载
  - 如果服务器无法访问 Docker Hub / apt / PyPI，请看文末“离线兜底”

## 2. 服务器目录结构

统一约定部署根目录为：

```text
/opt/ai-chat-live2d/
├── app/                         # 项目仓库根目录
├── deploy/                      # docker-compose.yml / *.env / nginx 配置
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

先在服务器创建目录：

```bash
sudo mkdir -p /opt/ai-chat-live2d/{app,deploy,models,vendor,data}
sudo mkdir -p /opt/ai-chat-live2d/data/{postgres,knowledge,uploads,logs}
sudo chown -R "$USER":"$USER" /opt/ai-chat-live2d
```

## 3. 代码同步

### 3.1 首选：`git clone / git pull`

首次部署：

```bash
cd /opt/ai-chat-live2d/app
git clone https://github.com/QzlabQ/Live2d-AIchat .
```

后续更新：

```bash
cd /opt/ai-chat-live2d/app
git pull
```

### 3.2 兜底：`rsync` 同步当前工作树

当服务器拉仓库不稳定，或者你需要同步本地尚未 push 的代码时，用本机执行：

```bash
rsync -avz --delete \
  --exclude ".git" \
  --exclude "backend/.venv" \
  --exclude "frontend/node_modules" \
  ./ user@server:/opt/ai-chat-live2d/app/
```

说明：

- `rsync` 在这里是“同步代码”的兜底方案，不是“版本回滚”
- 真正回滚请在服务器代码目录里执行 `git checkout <commit-or-tag>`

## 4. 上传模型与大资源

服务器不依赖在线拉模型，统一从本机传。

### 4.1 需要上传的目录

本机路径与服务器目标路径建议如下：

```text
backend/storage/models/CosyVoice2-0.5B        -> /opt/ai-chat-live2d/models/CosyVoice2-0.5B
backend/storage/models/faster-whisper-small   -> /opt/ai-chat-live2d/models/faster-whisper-small
backend/storage/models/bge-m3                 -> /opt/ai-chat-live2d/models/bge-m3
backend/storage/models/bge-reranker-v2-m3     -> /opt/ai-chat-live2d/models/bge-reranker-v2-m3
backend/storage/vendor/CosyVoice              -> /opt/ai-chat-live2d/vendor/CosyVoice
backend/storage/knowledge                     -> /opt/ai-chat-live2d/data/knowledge
```

### 4.2 `scp` 示例

在本机项目根目录执行：

```bash
scp -r ./backend/storage/models/CosyVoice2-0.5B user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/faster-whisper-small user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-reranker-v2-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/vendor/CosyVoice user@server:/opt/ai-chat-live2d/vendor/
scp -r ./backend/storage/knowledge user@server:/opt/ai-chat-live2d/data/
```

如果传输容易中断，更推荐 `rsync -avz --progress`。

## 5. 准备部署文件

项目仓库里已经提供模板文件：

- `deploy/docker-compose.yml`
- `deploy/backend.env.example`
- `deploy/backend.env.v100.example`
- `deploy/postgres.env.example`
- `deploy/nginx/default.conf`
- `deploy/docker/bootstrap.sh`
- `deploy/docker/up.sh`
- `deploy/docker/down.sh`
- `deploy/docker/logs.sh`

现在推荐直接使用 Docker helper 脚本，而不是手工一条条 `cp`。

首次部署时：

```bash
/opt/ai-chat-live2d/app/deploy/docker/bootstrap.sh
```

如果是 `V100` 服务器，首次可直接：

```bash
/opt/ai-chat-live2d/app/deploy/docker/bootstrap.sh --v100
```

它会：

- 同步仓库里的 `docker-compose.yml` 和 `nginx/default.conf` 到 `/opt/ai-chat-live2d/deploy/`
- 如果 `deploy/backend.env` 不存在，则按普通模板或 `--v100` 模板创建
- 如果 `deploy/postgres.env` 不存在，则创建默认模板
- 自动创建 `deploy/nginx/`、`data/logs/` 等目录

这份 V100 示例会额外打开：

- `TTS_COSYVOICE_ONNX_PROVIDER=cuda`
- `TTS_COSYVOICE_LOAD_TRT=true`
- `TTS_COSYVOICE_TRT_CONCURRENT=1`
- `TTS_STREAM_PROFILE=stable`
- `TTS_SEGMENT_SOFT_MIN_CHARS=12`
- `TTS_SEGMENT_SOFT_MAX_CHARS=20`
- `TTS_SEGMENT_HARD_MAX_CHARS=28`

这里要特别注意：旧版 V100 调参文档里曾经用过 `22 / 40 / 64` 这组更长的 TTS 分段阈值，它会减少分段数量，但也会显著放大长句在单个 segment 内的 `token_wait_ms` 与 `token2wav_ms` 退化。当前测试服务器如果要优先避免长句断流，建议继续使用 `12 / 20 / 28`，不要因为沿用了老的 `backend.env` 而误以为那是稳定默认值。

还要区分清楚 TRT 覆盖范围：`TTS_COSYVOICE_LOAD_TRT=true` 目前只代表 flow 侧 TensorRT 路径开启，不代表 AR speech-token LLM 已被 TRT 或 vLLM 加速。后台 trace 里的 `tts_ar_backend` 与 `tts_flow_backend` 会直接反映真实运行态。

对 `V100` 来说，当前不建议把 vLLM 当成默认提速选项。由于这类卡在缺少 `flash attention` 时容易走到更慢路径，实际效果可能比现有 PyTorch AR 还差；第一轮排障应优先确认短分段是否真正生效，再看 AR 侧是否需要更换方案。

然后至少修改这几个值：

```env
# /opt/ai-chat-live2d/deploy/backend.env
DASHSCOPE_API_KEY=你的真实 Key
ADMIN_PASSWORD=请改成自己的后台密码
ADMIN_JWT_SECRET=请改成随机长字符串
DATABASE_URL=postgresql+psycopg://ai_chat:你的数据库密码@postgres:5432/ai_chat_live2d
CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080","http://localhost:18080","http://127.0.0.1:18080"]
```

```env
# /opt/ai-chat-live2d/deploy/postgres.env
POSTGRES_PASSWORD=请改成自己的数据库密码
```

### 5.1 受限网络下的代理写法

如果服务器本身不能直接访问 Docker Hub / PyPI / npm，但你已经通过 SSH 反向隧道给它开了代理，可以把下面这些值填到 `/opt/ai-chat-live2d/deploy/backend.env`：

```env
HTTP_PROXY=http://127.0.0.1:17897
HTTPS_PROXY=http://127.0.0.1:17897
ALL_PROXY=socks5://127.0.0.1:17897
http_proxy=http://127.0.0.1:17897
https_proxy=http://127.0.0.1:17897
all_proxy=socks5://127.0.0.1:17897
NO_PROXY=127.0.0.1,localhost
no_proxy=127.0.0.1,localhost
```

`deploy/docker/up.sh` 会先加载 `backend.env`，再执行 `docker compose up -d --build`。因此这里的代理变量会同时作用于：

- `backend` 镜像构建阶段的 `apt / curl / pip`
- `frontend` 镜像构建阶段的 `npm / pnpm`
- 后端容器运行阶段对 DashScope 等外部服务的访问

如果你不用代理，这一段保持注释即可。

## 6. 启动服务

先确认服务器 GPU 可见：

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 nvidia-smi
```

然后启动：

```bash
/opt/ai-chat-live2d/app/deploy/docker/up.sh
```

查看状态：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose ps
/opt/ai-chat-live2d/app/deploy/docker/logs.sh backend
/opt/ai-chat-live2d/app/deploy/docker/logs.sh frontend
/opt/ai-chat-live2d/app/deploy/docker/logs.sh postgres
```

如果要停止：

```bash
/opt/ai-chat-live2d/app/deploy/docker/down.sh
```

### 6.1 V100 上的 TRT / provider 验收

如果你使用的是 `backend.env.v100.example`，建议在容器启动后再做一轮运行态确认：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose exec backend python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
docker compose exec backend python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

输出里至少应看到：

- `True`
- `CUDAExecutionProvider`

如果没有，请先修 Docker GPU runtime，不要继续排查 TTS 断流。

## 7. 从本机访问网页

因为服务器只开放 SSH，不直接开放 `8080`，所以在本机执行：

```bash
ssh -L 18080:127.0.0.1:8080 user@server
```

隧道建立后，在本机浏览器访问：

```text
http://127.0.0.1:18080
```

常用入口：

- 游客端：`http://127.0.0.1:18080/`
- 管理后台：`http://127.0.0.1:18080/admin.html`
- 后端健康检查：`http://127.0.0.1:18080/api/v1/health`

## 8. 每日更新流程

### 8.1 常规更新

```bash
cd /opt/ai-chat-live2d/app
git pull

/opt/ai-chat-live2d/app/deploy/docker/bootstrap.sh
/opt/ai-chat-live2d/app/deploy/docker/up.sh
```

如果 `backend.env` / `postgres.env` 已经按你的服务器修改过，不要再用 `.example` 覆盖它们。

### 8.2 仓库访问不稳时

在本机执行 `rsync` 同步代码后，再在服务器执行：

```bash
/opt/ai-chat-live2d/app/deploy/docker/bootstrap.sh
/opt/ai-chat-live2d/app/deploy/docker/up.sh
```

### 8.3 版本回滚

```bash
cd /opt/ai-chat-live2d/app
git checkout <commit-or-tag>
/opt/ai-chat-live2d/app/deploy/docker/bootstrap.sh
/opt/ai-chat-live2d/app/deploy/docker/up.sh
```

## 9. 常见排查

### 9.1 后端起不来

先看日志：

```bash
/opt/ai-chat-live2d/app/deploy/docker/logs.sh backend
```

常见原因：

- `DASHSCOPE_API_KEY` 未配置或无效
- `CosyVoice2-0.5B`、`faster-whisper-small`、`bge-m3`、`bge-reranker-v2-m3` 未上传完整
- `/opt/ai-chat-live2d/vendor/CosyVoice` 缺少完整代码
- Docker GPU runtime 未配置好，导致 `torch.cuda.is_available()` 为 `False`

### 9.2 前端能开但接口不通

检查：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose ps
curl http://127.0.0.1:8080/api/v1/health
```

如果 `frontend` 正常但 `/api/v1/health` 不通，重点看：

- `backend` 是否 healthy
- `deploy/nginx/default.conf` 是否和仓库版本一致
- `docker-compose.yml` 里的 `../app/backend`、`../app/frontend` 路径是否和服务器目录结构一致

### 9.3 上传知识库/音色时报 `413`

默认已经在 Nginx 里设置了：

```nginx
client_max_body_size 64m;
```

如果后续上传文件更大，可以继续调高它，并重启前端容器：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build frontend
```

### 9.4 服务器无法联网构建镜像

如果服务器连 Docker Hub、apt、PyPI 都不稳定，推荐离线兜底：

1. 在一台可联网、系统尽量接近的 Linux 机器上完成镜像构建
2. 导出镜像：

```bash
docker save ai-chat-backend:latest | gzip > ai-chat-backend.tar.gz
docker save ai-chat-frontend:latest | gzip > ai-chat-frontend.tar.gz
docker pull postgres:16
docker save postgres:16 | gzip > postgres-16.tar.gz
```

3. 用 `scp` 传到服务器
4. 在服务器导入：

```bash
gunzip -c ai-chat-backend.tar.gz | docker load
gunzip -c ai-chat-frontend.tar.gz | docker load
gunzip -c postgres-16.tar.gz | docker load
```

这种方式更适合后续学校集群彻底断外网时再启用。

### 9.5 本机 Docker 继承了错误代理

如果你在自己的电脑上验证镜像构建，且 Docker 内部继承到了像 `127.0.0.1:7890` 这样的本机代理，常见现象是：

- `npm install` / `npm ci` 报 `ECONNREFUSED 127.0.0.1:7890`
- `corepack` / `pnpm` / `pip` 看起来能联网但实际构建异常卡住

本机验证时可以显式清空 build-arg：

```bash
docker build \
  --build-arg HTTP_PROXY= \
  --build-arg HTTPS_PROXY= \
  --build-arg ALL_PROXY= \
  --build-arg http_proxy= \
  --build-arg https_proxy= \
  --build-arg all_proxy= \
  -t ai-chat-frontend:test \
  -f frontend/Dockerfile frontend
```

后端镜像同理。

### 9.6 后端首轮镜像构建很慢

后端镜像首轮构建会经历：

1. `apt` 安装系统依赖
2. Miniconda 安装
3. `conda` 安装 `Python + CUDA + PyTorch`
4. `pip` 安装 `ASR / RAG / TTS` 相关依赖

第一次构建时间明显长于前端是正常现象，尤其在网络一般时更明显。建议：

- 首轮构建尽量在网络更稳定的时段执行
- 如学校集群外网不稳，优先使用上面的“离线兜底”
- 不要在第一次构建时频繁 `Ctrl+C`，否则前面的层缓存价值会变低
