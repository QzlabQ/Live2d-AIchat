# Backend Phase 1-2

这个目录已经覆盖 `docs/roadmap.md` 中 Phase 1-2 的后端、知识库和 RAG 基础能力：

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
- Phase 2 RAG 问答链：
  - 向量检索
  - 重排序
  - 引用资料回答
  - 越界拒答
  - DashScope / Qwen 生成式回答（无 Key 时降级为抽取式回答）

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

## Phase 1-2 知识库 / RAG 依赖

```powershell
cd backend
conda activate ai-chat
python -m pip install -r requirements.knowledge.txt
```

说明：

- `KNOWLEDGE_EMBEDDING_ENGINE=bge-m3` 会使用 `bge-m3`
- 如果在线下载不稳定，可以先手动下载完整 `BAAI/bge-m3` 模型快照到本地目录，例如 `backend/storage/models/bge-m3`
- 然后把 `.env` 中的 `KNOWLEDGE_EMBEDDING_MODEL` 改成这个本地路径，例如 `./storage/models/bge-m3`
- 如果要启用真正的 `bge-reranker-v2-m3`，也可以把模型快照放到本地，例如 `backend/storage/models/bge-reranker-v2-m3`，再把 `.env` 中的 `RAG_RERANKER_ENGINE` 改成 `bge-reranker-v2-m3`，并把 `RAG_RERANKER_MODEL` 指向该目录
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

## Phase 2 RAG 配置

当前 `.env` 默认已经切到：

- `CHAT_MODE=rag`
- `RAG_RERANKER_ENGINE=lexical`
- `TTS_ENGINE=edge-tts`

说明：

- `RAG_RERANKER_ENGINE=lexical` 适合先本地快速联调
- 如果你已经下载 `bge-reranker-v2-m3`，可以改成：

```env
RAG_RERANKER_ENGINE=bge-reranker-v2-m3
RAG_RERANKER_MODEL=./storage/models/bge-reranker-v2-m3
```

- 如果你已经配置 `DASHSCOPE_API_KEY`，RAG 会走“检索 → 重排 → Qwen 生成”
- 如果没有配置 `DASHSCOPE_API_KEY`，RAG 会走“检索 → 重排 → 抽取式回答”，仍可本地验证知识库问答链
- 默认模型已经切到 `qwen3.7-plus`
- `DASHSCOPE_BASE_URL` 当前默认使用共享域名，便于快速联调；如果你已经有 Workspace 专属域名，建议替换成：

```env
DASHSCOPE_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

## Phase 2 RAG 验证

启动后端后，可以直接在前端提问，也可以先在命令行验证：

```powershell
cd backend
conda activate ai-chat
python -m scripts.evaluate_rag --dataset .\evals\phase2_rag_eval.sample.jsonl
```

如果你要跑 roadmap 里的 50 题准确率测试，可以直接使用仓库内置题集：

```powershell
cd backend
conda activate ai-chat
python -m scripts.evaluate_rag --dataset .\evals\phase2_rag_eval.50.jsonl --target 0.9
```

评测脚本现在支持：

- `expected_keywords`: 必须全部命中
- `expected_keyword_groups`: 每组至少命中一个关键词
- `requires_citations`: 检查回答里是否带 `参考资料`
- `expects_refusal`: 检查越界问题是否被拒答

如果你还要继续扩展题库，可以按下面的 JSONL 结构追加：

```json
{"question":"灵山胜境有什么历史故事？","expected_keyword_groups":[["小灵山"],["玄奘"]],"requires_citations":true}
```

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
- 如果暂时不走 Edge TTS，先把 `TTS_ENGINE=edge-tts` 改回 `TTS_ENGINE=mock`
- 如果知识库导入要使用 `bge-m3`，优先保证本地模型目录已下载完成
- 如果要验证 Phase 2 的生成式 RAG，记得配置 `DASHSCOPE_API_KEY`
