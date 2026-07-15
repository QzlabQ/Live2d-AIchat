# 测试服务器 Docker Compose 部署手册

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

首次部署时，在服务器执行：

```bash
cp /opt/ai-chat-live2d/app/deploy/docker-compose.yml /opt/ai-chat-live2d/deploy/docker-compose.yml
cp /opt/ai-chat-live2d/app/deploy/backend.env.example /opt/ai-chat-live2d/deploy/backend.env
cp /opt/ai-chat-live2d/app/deploy/postgres.env.example /opt/ai-chat-live2d/deploy/postgres.env
mkdir -p /opt/ai-chat-live2d/deploy/nginx
cp /opt/ai-chat-live2d/app/deploy/nginx/default.conf /opt/ai-chat-live2d/deploy/nginx/default.conf
```

如果你这台服务器是 V100，并且你更在意流式 TTS 连续播放稳定性，可以把第二行替换成：

```bash
cp /opt/ai-chat-live2d/app/deploy/backend.env.v100.example /opt/ai-chat-live2d/deploy/backend.env
```

这份 V100 示例会额外打开：

- `TTS_COSYVOICE_ONNX_PROVIDER=cuda`
- `TTS_COSYVOICE_LOAD_TRT=true`
- `TTS_COSYVOICE_TRT_CONCURRENT=1`
- `TTS_STREAM_PROFILE=stable`
- `TTS_SEGMENT_SOFT_MIN_CHARS=22`
- `TTS_SEGMENT_SOFT_MAX_CHARS=40`
- `TTS_SEGMENT_HARD_MAX_CHARS=64`

然后至少修改这几个值：

```env
# /opt/ai-chat-live2d/deploy/backend.env
DASHSCOPE_API_KEY=你的真实 Key
ADMIN_PASSWORD=请改成自己的后台密码
ADMIN_JWT_SECRET=请改成随机长字符串
CORS_ORIGINS=http://127.0.0.1:18080,http://localhost:18080
```

```env
# /opt/ai-chat-live2d/deploy/postgres.env
POSTGRES_PASSWORD=请改成自己的数据库密码
```

## 5.1 V100 原生 venv 安装顺序与 TRT 校验

如果这台 V100 服务器不是常驻跑 Docker，而是原生 `venv/conda` 部署，建议把运行时修复顺序固定成下面这样：

```bash
cd /opt/ai-chat-live2d/app/backend
python -m pip install -r requirements.runtime.txt --no-build-isolation
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install onnxruntime-gpu==1.18.0 --no-build-isolation
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
```

输出里必须包含 `CUDAExecutionProvider`。如果没有，不要继续启动后端。

注意：`chromadb` 和 `faster-whisper` 的依赖链可能会重新拉回 CPU 版 `onnxruntime`，所以只要后面改过依赖，就要再次执行一次 provider 校验。

如果你准备启用 `TTS_COSYVOICE_LOAD_TRT=true`，再补一轮 TensorRT 自检和 engine 预热：

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
python -c "import tensorrt as trt; print(trt.__version__)"
python -c "from cosyvoice.cli.cosyvoice import CosyVoice2; CosyVoice2('/opt/ai-chat-live2d/app/backend/storage/models/CosyVoice2-0.5B', load_trt=True, fp16=True)"
```

预期会生成或加载类似下面的 plan 文件：

```text
flow.decoder.estimator.fp16.mygpu.plan
```

## 6. 启动服务

先确认服务器 GPU 可见：

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04 nvidia-smi
```

然后启动：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

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

cp /opt/ai-chat-live2d/app/deploy/docker-compose.yml /opt/ai-chat-live2d/deploy/docker-compose.yml
cp /opt/ai-chat-live2d/app/deploy/nginx/default.conf /opt/ai-chat-live2d/deploy/nginx/default.conf

cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

如果 `backend.env` / `postgres.env` 已经按你的服务器修改过，不要再用 `.example` 覆盖它们。

### 8.2 仓库访问不稳时

在本机执行 `rsync` 同步代码后，再在服务器执行：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

### 8.3 版本回滚

```bash
cd /opt/ai-chat-live2d/app
git checkout <commit-or-tag>
cd /opt/ai-chat-live2d/deploy
docker compose up -d --build
```

## 9. 常见排查

### 9.1 后端起不来

先看日志：

```bash
cd /opt/ai-chat-live2d/deploy
docker compose logs -f backend
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
