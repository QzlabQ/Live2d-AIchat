# Backend Phase 1

这个目录已经覆盖 `docs/roadmap.md` 中 Phase 1 的后端与知识库基础能力：

- FastAPI 项目骨架与健康检查
- `sessions` / `messages` / `avatar_config` / `knowledge_docs` 表
- WebSocket 实时对话通道
- `faster-whisper` ASR 封装
- `edge-tts` TTS 封装
- `.env` 配置管理
- Phase 1 知识库导入链路：
  - 文档解析：`docx` / `txt` / `md` / `pdf` / `xlsx`
  - 文本切片：`chunk_size=512`，`chunk_overlap=64`
  - `bge-m3` 向量化并写入本地 `ChromaDB`

## 推荐环境

建议使用 conda，并优先选择 Python `3.11`。

```powershell
cd backend
conda create -n ai-chat python=3.11 -y
conda activate ai-chat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

如果你已经在 `ai-chat` 环境里，只需要执行：

```powershell
cd backend
conda activate ai-chat
python -m pip install -r requirements.txt
```

## 启动后端

```powershell
cd backend
conda activate ai-chat
python -m uvicorn main:app --reload
```

启动后默认地址：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 可选依赖

如果你要切到 PostgreSQL：

```powershell
conda activate ai-chat
python -m pip install -r requirements.postgres.txt
```

然后把 `.env` 里的 `DATABASE_URL` 改成 `postgresql+psycopg://...`

如果你要启用本地 `faster-whisper`：

```powershell
conda activate ai-chat
python -m pip install -r requirements.asr.txt
```

然后把 `.env` 里的 `ASR_ENGINE=mock` 改成 `ASR_ENGINE=faster-whisper`

## Phase 1 知识库依赖

```powershell
cd backend
conda activate ai-chat
python -m pip install -r requirements.knowledge.txt
```

说明：

- `KNOWLEDGE_EMBEDDING_ENGINE=bge-m3` 会使用 `bge-m3`
- 如果在线下载不稳定，可以先手动下载完整 `BAAI/bge-m3` 模型快照到本地目录，例如 `backend/storage/models/bge-m3`
- 然后把 `.env` 中的 `KNOWLEDGE_EMBEDDING_MODEL` 改成这个本地路径，例如 `./storage/models/bge-m3`
- 默认向量库存放在 `backend/storage/knowledge`
- `xlsx` 如果识别为游客行为分析数据，会默认跳过，不混入景区问答知识

## 导入知识库

```powershell
cd backend
conda activate ai-chat
python -m scripts.import_knowledge --source "..\data\20260323113204906 (1)\示范景区公开资料包" --reset
```

导入完成后会：

- 写入 `knowledge_docs` 表
- 按文档切片并生成 embedding
- 写入本地 `ChromaDB`

## 接口

- `GET /api/v1/health`
- `POST /api/v1/sessions`
- `GET /api/v1/admin/avatar/config`
- `PUT /api/v1/admin/avatar/config`
- `GET /api/v1/admin/knowledge`
- `DELETE /api/v1/admin/knowledge/{doc_id}`
- `WS /ws/chat/{session_id}`

## 联调建议

- 如果本机暂时没有配置 Whisper，先保留 `ASR_ENGINE=mock`
- 如果暂时不走 Edge TTS，先保留 `TTS_ENGINE=mock`
- 如果知识库导入要使用 `bge-m3`，优先保证本地模型目录已下载完成
