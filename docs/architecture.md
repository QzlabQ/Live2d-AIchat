# 系统架构设计

## 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         客户端层                              │
│  ┌──────────────────────────┐  ┌───────────────────────┐   │
│  │    游客交互端 (Vue3)       │  │   管理后台 (Vue3)      │   │
│  │  ┌────────────────────┐  │  │  ┌─────────────────┐  │   │
│  │  │  Live2D 数字人渲染  │  │  │  │  知识库管理      │  │   │
│  │  │  (pixi-live2d)     │  │  │  │  数字人配置      │  │   │
│  │  ├────────────────────┤  │  │  │  数据大屏        │  │   │
│  │  │  语音录制 / 文本输入 │  │  │  │  感受度报告      │  │   │
│  │  └────────────────────┘  │  │  └─────────────────┘  │   │
│  └─────────────┬────────────┘  └──────────┬────────────┘   │
└────────────────┼───────────────────────────┼────────────────┘
                 │ WebSocket                  │ HTTP/REST
┌────────────────▼───────────────────────────▼────────────────┐
│                      FastAPI 后端                             │
│  ┌─────────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │  对话 API   │  │ 知识库API│  │ 管理API │  │ 大屏API  │  │
│  └──────┬──────┘  └────┬─────┘  └────┬────┘  └────┬─────┘  │
│         │              │             │              │        │
│  ┌──────▼──────────────▼─────────────▼──────────────▼─────┐ │
│  │                    服务编排层 (Services)                  │ │
│  │  ASR Service   RAG Service   LLM Service   TTS Service  │ │
│  └──────┬──────────────┬─────────────┬──────────────┬─────┘ │
└─────────┼──────────────┼─────────────┼──────────────┼───────┘
          │              │             │              │
    ┌─────▼─────┐  ┌─────▼──────┐  ┌──▼──────┐  ┌───▼──────┐
    │  Whisper  │  │ ChromaDB   │  │  Qwen   │  │CosyVoice│
    │  (ASR)    │  │ + bge-m3   │  │  API    │  │  (TTS)  │
    └───────────┘  └─────┬──────┘  └─────────┘  └─────────┘
                         │
                   ┌─────▼──────┐
                   │ PostgreSQL  │
                   │   Redis     │
                   └────────────┘
```

---

## 模块职责

### 游客端核心流程

```
用户输入（语音/文本）
       ↓
  [若语音] WebSocket 传送音频块 → ASR → 文本
       ↓
  发送文本到后端 /chat
       ↓
  后端流式返回：{ text_chunk, audio_chunk, phoneme_timestamps, emotion }
       ↓
  前端：
    ├── 播放音频（Web Audio API）
    ├── 根据 phoneme_timestamps 驱动 Live2D 口型参数
    └── 根据 emotion 驱动 Live2D 表情参数
```

### 数据流详解

#### 实时对话（WebSocket）

```json
// 客户端 → 服务端（语音块）
{ "type": "audio_chunk", "data": "<base64 PCM>", "session_id": "xxx" }

// 客户端 → 服务端（文本）
{ "type": "text", "content": "这里有什么历史故事？", "session_id": "xxx" }

// 服务端 → 客户端（流式响应）
{ "type": "text_delta",  "content": "这里相传..." }
{ "type": "audio_chunk", "data": "<base64 MP3>", "seq": 0 }
{ "type": "phonemes",    "data": [{"ph":"a","start":0.1,"end":0.3}, ...] }
{ "type": "emotion",     "value": "happy" }
{ "type": "done" }
```

#### 知识库管理（HTTP）

```
POST /admin/knowledge/upload  → 文档解析 → 切片 → Embedding → ChromaDB
GET  /admin/knowledge/list    → 返回文档列表
DELETE /admin/knowledge/{id}  → 删除文档及其向量
```

---

## 数据库设计

### PostgreSQL 主要表

```sql
-- 对话会话
CREATE TABLE sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMP DEFAULT NOW(),
    interest_tags TEXT[],          -- ['history', 'nature']
    device_type VARCHAR(20)        -- 'mobile' | 'kiosk'
);

-- 对话消息
CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID REFERENCES sessions(id),
    role        VARCHAR(10),       -- 'user' | 'assistant'
    content     TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    emotion     VARCHAR(20),       -- 'happy'|'neutral'|'surprised'
    latency_ms  INTEGER            -- 响应延迟，用于监控
);

-- 知识库文档
CREATE TABLE knowledge_docs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename    VARCHAR(255),
    category    VARCHAR(50),       -- 'history'|'scenery'|'faq'
    chunk_count INTEGER,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    status      VARCHAR(20)        -- 'processing'|'ready'|'error'
);

-- 数字人配置
CREATE TABLE avatar_config (
    id          SERIAL PRIMARY KEY,
    model_path  VARCHAR(255),      -- Live2D 模型路径
    voice_id    VARCHAR(100),      -- CosyVoice 音色ID
    persona     TEXT,              -- 系统Prompt人设
    updated_at  TIMESTAMP DEFAULT NOW()
);
```

---

## 部署架构

### 开发环境（本机）

```
localhost:5173  →  Vue3 dev server (前端)
localhost:8000  →  FastAPI (后端)
localhost:5432  →  PostgreSQL
localhost:6379  →  Redis
localhost:8001  →  ChromaDB HTTP server（可选）
```

### 生产/演示环境（Docker Compose）

```yaml
# docker-compose.yml（简化）
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
    env_file: .env

  frontend:
    build: ./frontend
    ports: ["80:80"]       # nginx 静态托管

  postgres:
    image: postgres:15-alpine
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
```

---

## 性能设计要点

### 延迟分解（目标总延迟 < 5s）

| 阶段 | 目标耗时 | 优化手段 |
|------|---------|---------|
| ASR（语音→文本） | < 0.8s | faster-whisper float16 |
| RAG检索 | < 0.2s | ChromaDB本地，HNSW索引 |
| LLM首token | < 1.5s | 流式输出，不等完整回答 |
| TTS首句合成 | < 1.5s | 分句并行合成（句子≤30字即开始） |
| 网络传输 | < 0.5s | WebSocket，音频分块 |
| **合计** | **< 4.5s** | 留0.5s余量 |

### 并发与稳定性

- FastAPI + uvicorn 异步模型，单实例支持100+并发长连接
- LLM 调用加 `asyncio.timeout(10)` 超时保护
- TTS 失败时降级为文字回复 + 简单口型动画
