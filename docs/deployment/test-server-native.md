# 测试服务器原生部署手册（禁用 Docker）

如果你的服务器允许 `Docker Compose + NVIDIA Container Runtime`，优先看 [test-server-docker.md](./test-server-docker.md)。  
本文对应的是 **不能使用 Docker**、只能走 **原生系统服务 + `python -m uvicorn` + 本机 `nginx`** 的部署方式。

本文内容基于当前测试服务器在 **2026 年 7 月 17 日** 的真实运行链路整理，目标是让其他同学拿到仓库后，按同一套目录和脚本完成原生部署，而不是再手抄线上机器里的临时命令。

## 1. 当前原生部署架构

当前测试服务器的正式链路是：

- `PostgreSQL 14/main`：系统集群，监听本机 `127.0.0.1:5432`
- `uvicorn`：通过 `/opt/ai-chat-live2d/deploy/native/start-backend.sh` 启动后端
- `nginx`：本机反代 `http://127.0.0.1:8000`，同时提供前端静态文件
- 前端构建产物：`/opt/ai-chat-live2d/app/frontend/dist`
- 后端配置：`/opt/ai-chat-live2d/deploy/backend.env`
- 日志目录：`/opt/ai-chat-live2d/data/logs`

要特别区分这两种启动方式：

- 用 `deploy/native/start-backend.sh` 启动时，实际生效的是 `/opt/ai-chat-live2d/deploy/backend.env`
- 只有你直接 `cd /opt/ai-chat-live2d/app/backend && python -m uvicorn app.main:app ...`，且没有提前导入别的环境变量时，`backend/.env` 才会作为默认配置来源

## 2. 一键流程总览

首次部署推荐直接按下面顺序执行：

```bash
mkdir -p /opt/ai-chat-live2d/deploy

cp /opt/ai-chat-live2d/app/deploy/native/backend.env.v100.example /opt/ai-chat-live2d/deploy/backend.env
cp /opt/ai-chat-live2d/app/deploy/native/postgres.env.example /opt/ai-chat-live2d/deploy/postgres.env

/opt/ai-chat-live2d/app/deploy/native/bootstrap.sh
/opt/ai-chat-live2d/deploy/native/start-stack.sh
```

说明：

- `bootstrap.sh` 是这次补进仓库的“原生部署自举脚本”
- 它会把仓库里的 `deploy/native` 同步到 `/opt/ai-chat-live2d/deploy/native`
- 同时创建后端 `storage` 软链接、准备 `venv`、安装后端依赖、构建前端
- 启动时实际用的是 `/opt/ai-chat-live2d/deploy/native/start-stack.sh`

如果你不是 `V100`，可以把第一行 `backend.env.v100.example` 换成 `backend.env.example`。

## 3. 适用环境

- 操作系统：`Ubuntu 22.04`
- Python：`3.10+`
- PostgreSQL：`14`
- 前端运行时：`Node.js 20`
- 反向代理：`nginx`
- GPU：`V100 / A100 / 4060` 或其他可见的 NVIDIA 显卡
- Docker：**不需要，也不允许**

推荐系统依赖至少具备：

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  postgresql postgresql-client \
  nginx ffmpeg git rsync
```

如果机器不能直连公网，仍然可以部署，但需要提前准备好：

- 项目仓库代码
- 本地模型目录
- `CosyVoice` vendor 代码
- 可用的 `Node.js 20` 二进制或系统包
- `pip / npm` 所需代理或离线镜像

## 4. 目录约定

统一使用下面这套目录：

```text
/opt/ai-chat-live2d/
├── app/                         # Git 仓库根目录
├── deploy/
│   ├── backend.env
│   ├── postgres.env
│   ├── native/                  # 原生部署脚本（由 bootstrap.sh 同步）
│   └── nginx/
│       └── native-nginx.conf
├── models/                      # 大模型目录
├── vendor/
│   └── CosyVoice/
├── data/
│   ├── knowledge/
│   ├── uploads/
│   ├── postgres/
│   └── logs/
└── .venvs/
    └── backend/
```

首次可以直接创建：

```bash
sudo mkdir -p /opt/ai-chat-live2d/{app,deploy,models,vendor,data,.venvs}
sudo mkdir -p /opt/ai-chat-live2d/data/{knowledge,uploads,postgres,logs}
sudo chown -R "$USER":"$USER" /opt/ai-chat-live2d
```

## 5. 同步代码

### 5.1 首选：直接拉仓库

```bash
cd /opt/ai-chat-live2d/app
git clone https://github.com/QzlabQ/Live2d-AIchat .
```

后续更新：

```bash
cd /opt/ai-chat-live2d/app
git pull
```

### 5.2 兜底：`rsync` 本地工作树

如果服务器不能稳定 `git pull`，可以从本机推送：

```bash
rsync -avz --delete \
  --exclude ".git" \
  --exclude "backend/.venv" \
  --exclude "frontend/node_modules" \
  ./ user@server:/opt/ai-chat-live2d/app/
```

## 6. 上传模型、知识库与 CosyVoice 代码

这套原生部署默认 **不在线下载模型**，统一从本机传。

建议的映射关系：

```text
backend/storage/models/CosyVoice2-0.5B        -> /opt/ai-chat-live2d/models/CosyVoice2-0.5B
backend/storage/models/faster-whisper-small   -> /opt/ai-chat-live2d/models/faster-whisper-small
backend/storage/models/bge-m3                 -> /opt/ai-chat-live2d/models/bge-m3
backend/storage/models/bge-reranker-v2-m3     -> /opt/ai-chat-live2d/models/bge-reranker-v2-m3
backend/storage/vendor/CosyVoice              -> /opt/ai-chat-live2d/vendor/CosyVoice
backend/storage/knowledge                     -> /opt/ai-chat-live2d/data/knowledge
```

`scp` 示例：

```bash
scp -r ./backend/storage/models/CosyVoice2-0.5B user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/faster-whisper-small user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/models/bge-reranker-v2-m3 user@server:/opt/ai-chat-live2d/models/
scp -r ./backend/storage/vendor/CosyVoice user@server:/opt/ai-chat-live2d/vendor/
scp -r ./backend/storage/knowledge user@server:/opt/ai-chat-live2d/data/
```

如果网络容易断，更推荐 `rsync -avz --progress`。

## 7. 准备原生部署配置

仓库里现在已经补齐了原生部署模板：

- `deploy/native/backend.env.example`
- `deploy/native/backend.env.v100.example`
- `deploy/native/postgres.env.example`
- `deploy/native/native-nginx.conf`
- `deploy/native/*.sh`

首次部署：

```bash
mkdir -p /opt/ai-chat-live2d/deploy

cp /opt/ai-chat-live2d/app/deploy/native/backend.env.example /opt/ai-chat-live2d/deploy/backend.env
cp /opt/ai-chat-live2d/app/deploy/native/postgres.env.example /opt/ai-chat-live2d/deploy/postgres.env
```

如果是当前这种单卡 `V100` 服务器，推荐改成：

```bash
cp /opt/ai-chat-live2d/app/deploy/native/backend.env.v100.example /opt/ai-chat-live2d/deploy/backend.env
```

### 7.1 当前 V100 基线

`backend.env.v100.example` 对应当前线上原生部署的 V100 思路：

- `TTS_COSYVOICE_DEVICE=cuda`
- `TTS_COSYVOICE_ONNX_PROVIDER=cuda`
- `TTS_COSYVOICE_LOAD_TRT=true`
- `TTS_COSYVOICE_TRT_CONCURRENT=1`
- `TTS_STREAM_PROFILE=stable`
- `TTS_SEGMENT_SOFT_MIN_CHARS=12`
- `TTS_SEGMENT_SOFT_MAX_CHARS=20`
- `TTS_SEGMENT_HARD_MAX_CHARS=28`

这里特别保留了 `12 / 20 / 28` 这组更短分段，而不是旧文档里曾经出现过的 `22 / 40 / 64`。  
后者虽然能减少 segment 数量，但会显著拉长单段语音，导致长句更容易在后半段退化。

### 7.2 必改项

至少把下面这些值改成你自己的：

```env
# /opt/ai-chat-live2d/deploy/backend.env
DATABASE_URL=postgresql+psycopg://ai_chat:你的密码@127.0.0.1:5432/ai_chat_live2d
ADMIN_PASSWORD=请改成自己的后台密码
ADMIN_JWT_SECRET=请改成随机长字符串
DASHSCOPE_API_KEY=你的真实 Key
```

```env
# /opt/ai-chat-live2d/deploy/postgres.env
POSTGRES_PASSWORD=请改成自己的数据库密码
```

### 7.3 受限网络下的代理写法

如果服务器不能直接访问 PyPI / npm / DashScope，可以在 `backend.env` 里按需打开：

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

这对应的是“本地机开代理，再通过 `ssh -R` 暴露给服务器”的场景。

## 8. 初始化 PostgreSQL

当前原生脚本默认使用系统集群 `14/main`。先启动：

```bash
sudo pg_ctlcluster 14 main start
pg_lsclusters
```

然后按 `deploy/postgres.env` 里的库名/用户名，创建一次数据库和角色。示例：

```bash
sudo -u postgres psql
CREATE USER ai_chat WITH PASSWORD 'change-me';
CREATE DATABASE ai_chat_live2d OWNER ai_chat;
\q
```

如果角色或数据库已经存在，这一步只需要确认密码与 `DATABASE_URL` 一致。

## 9. 运行原生自举脚本

仓库里的 `bootstrap.sh` 会做这些事：

- 同步 `app/deploy/native/*` 到 `/opt/ai-chat-live2d/deploy/native/`
- 如果 `deploy/backend.env` / `deploy/postgres.env` / `deploy/nginx/native-nginx.conf` 不存在，则复制默认模板
- 创建 `backend/storage -> /opt/ai-chat-live2d/{models,vendor,data/...}` 软链接
- 创建 `/opt/ai-chat-live2d/.venvs/backend`
- 安装 `backend/requirements.runtime.txt`
- 如果配置要求 `cuda` / TRT，则重新 pin `onnxruntime-gpu==1.18.0`
- 构建前端 `dist`

执行：

```bash
/opt/ai-chat-live2d/app/deploy/native/bootstrap.sh
```

### 9.1 V100 上的 ONNX / TRT 校验

如果你启用了：

- `TTS_COSYVOICE_ONNX_PROVIDER=cuda`
- 或 `TTS_COSYVOICE_LOAD_TRT=true`

那么 `bootstrap.sh` 会自动重装 `onnxruntime-gpu==1.18.0` 并做 provider 校验。

你也可以手工再次确认：

```bash
/opt/ai-chat-live2d/.venvs/backend/bin/python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
```

输出里必须包含：

```text
CUDAExecutionProvider
```

否则不要继续启动后端。

注意：`chromadb` 或 `faster-whisper` 的依赖变更，可能把 CPU 版 `onnxruntime` 再次带回来。只要改过 Python 依赖，就建议重跑一次 `bootstrap.sh` 或重新做 provider 校验。

## 10. 可选：预热 TRT engine

首次启用：

- `TTS_COSYVOICE_LOAD_TRT=true`

时，建议先预热一次：

```bash
/opt/ai-chat-live2d/deploy/native/prewarm-trt.sh
tail -f /opt/ai-chat-live2d/data/logs/trt_prewarm.log
```

预期会生成或加载类似：

```text
flow.decoder.estimator.fp16.mygpu.plan
```

## 11. 启动与停止

启动整套原生服务：

```bash
/opt/ai-chat-live2d/deploy/native/start-stack.sh
```

它会依次启动：

1. `PostgreSQL 14/main`
2. `uvicorn app.main:app`
3. `nginx`

停止整套服务：

```bash
/opt/ai-chat-live2d/deploy/native/stop-stack.sh
```

如果只需要单独处理某一层，也可以直接用：

- `start-backend.sh` / `stop-backend.sh`
- `start-frontend-nginx.sh` / `stop-frontend-nginx.sh`
- `start-postgres.sh` / `stop-postgres.sh`

## 12. 访问方式

如果服务器只能 SSH 访问，不对外暴露 `8080`，在本机建立隧道：

```bash
ssh -L 18080:127.0.0.1:8080 user@server
```

然后本机浏览器访问：

- 游客端：`http://127.0.0.1:18080/`
- 管理后台：`http://127.0.0.1:18080/admin.html`
- 健康检查：`http://127.0.0.1:18080/api/v1/health`

## 13. 每日更新流程

```bash
cd /opt/ai-chat-live2d/app
git pull

/opt/ai-chat-live2d/app/deploy/native/bootstrap.sh
/opt/ai-chat-live2d/deploy/native/stop-stack.sh
/opt/ai-chat-live2d/deploy/native/start-stack.sh
```

说明：

- `bootstrap.sh` 设计成可重复执行
- 它会重新同步原生脚本，并在需要时重装依赖或重新构建前端
- 如果你只改了前端，也可以只跑 `build-frontend.sh`

## 14. 常用排查命令

查看进程：

```bash
pgrep -af "uvicorn app.main:app|python -m uvicorn"
pg_lsclusters
ps -ef | grep nginx
```

查看日志：

```bash
tail -f /opt/ai-chat-live2d/data/logs/backend.log
tail -f /opt/ai-chat-live2d/data/logs/nginx-error.log
tail -f /opt/ai-chat-live2d/data/logs/nginx-access.log
```

检查当前生效的后端配置：

```bash
tr '\0' '\n' < /proc/$(pgrep -f "uvicorn app.main:app" | head -n1)/environ | rg '^(APP_ENV|DEBUG|DATABASE_URL|TTS_PROVIDER|TTS_STREAM_PROFILE)='
```

## 15. 这份文档和 Docker 文档的关系

- 能用 Docker：优先看 [test-server-docker.md](./test-server-docker.md)
- 不能用 Docker：看本文
- 当前测试服务器线上运行的，正是本文这套原生链路

这样做的目的，是把“线上真实可用方案”正式收进仓库，而不是继续依赖某台机器上的临时脚本。
