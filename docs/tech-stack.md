# 技术选型

## 总览

```
游客端 (Vue3 + Live2D)
        │  WebSocket / HTTP
管理后台 (Vue3 + Ant Design Vue)
        │  HTTP
    FastAPI 后端
    ├── RAG (LangChain + ChromaDB + bge-m3)
    ├── LLM (Qwen-Max / Qwen-VL-Max)
    ├── ASR (Whisper)
    ├── TTS (CosyVoice 2)
    └── 情感分析 (LLM prompt-based)
```

---

## 前端

### 游客交互端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.4 | UI框架 |
| TypeScript | ^5.x | 类型安全 |
| Vite | ^5.x | 构建工具 |
| pixi-live2d-display | ^0.4 | Live2D渲染（基于PixiJS） |
| PixiJS | ^7.x | WebGL渲染引擎 |
| Pinia | ^2.x | 状态管理 |

> **为何选 pixi-live2d-display**：开源免费，支持 Cubism 2/3/4 模型，纯浏览器运行，无需客户端安装，API简洁易于口型参数驱动。

### 管理后台

| 技术 | 用途 |
|------|------|
| Vue 3 + Ant Design Vue | 后台UI组件 |
| ECharts 5 | 数据大屏图表（折线/柱状/词云） |
| vue-echarts | ECharts的Vue封装 |

---

## 后端

### 框架与服务

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 主语言 |
| FastAPI | ^0.110 | Web框架，原生异步+WebSocket |
| SQLAlchemy 2 | ^2.0 | ORM |
| PostgreSQL | 15+ | 主数据库（对话记录/配置） |
| Redis | 7+ | 会话缓存、任务队列 |
| ChromaDB | ^0.4 | 向量数据库（本地部署）|
| LangChain | ^0.2 | RAG编排框架 |

### AI 模型层

#### 大语言模型（LLM）

**主选：通义千问 API（阿里云 DashScope）**

| 模型 | 用途 | 理由 |
|------|------|------|
| qwen-max | 核心问答、推荐生成 | 效果最强，中文优秀 |
| qwen-vl-max | 多模态（图片识别景点） | **满足赛题"多模态大模型"要求** |
| qwen-plus | 情感分析批处理（低成本） | 速度快、成本低 |

> 备选：若API额度不足，本地部署 `Qwen2.5-7B-Instruct`（需8GB VRAM）。

#### 语音识别（ASR）

**选型：OpenAI Whisper（`large-v3`）**

```
优点：开源免费，中文准确率业界顶级，支持本地部署
缺点：large-v3 首次加载约3s，可用 faster-whisper 加速
```

**加速方案：`faster-whisper`（CTranslate2后端）**

```python
# 相比原版快3-5倍，显存占用降低约50%
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", compute_type="float16")
```

#### 语音合成（TTS）

**主选：CosyVoice 2（阿里开源）**

- 支持情感风格控制（温柔/活泼/庄重）
- 可返回**音素级时间戳**，用于口型同步 ← 关键特性
- 支持声音克隆（可定制景区专属声音）

**备选：Edge-TTS（微软免费API）**

- 无需GPU，网络可用即可，延迟约0.5s
- 无音素时间戳，口型同步需用音量包络近似

#### Embedding 模型

**选型：BAAI/bge-m3**

- 国产开源，中英双语，768维
- 支持稀疏+稠密混合检索（hybrid search），召回率更高
- 本地部署，无API成本

---

## 关键技术方案

### RAG 检索流程

```
用户问题
  → bge-m3 Embedding
  → ChromaDB 向量检索（top-k=5）
  → bge-reranker-v2-m3 重排序（top-3）  ← 提升准确率关键
  → 组装Prompt（系统人设 + 检索片段 + 对话历史）
  → Qwen-Max 生成回答
```

### 延迟控制策略（目标 < 5s）

```
总延迟 = ASR识别 + LLM生成首token + TTS合成首句 + 网络传输

优化手段：
1. LLM 流式输出（SSE），边生成边发送
2. TTS 分句合成：收到第一句（约20字）立即合成播放，不等完整回答
3. Whisper 用 faster-whisper，识别延迟 < 0.8s
4. ChromaDB 本地部署，检索 < 0.1s
```

---

## 版本依赖汇总

### backend/requirements.txt（核心）

```
fastapi==0.110.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
asyncpg==0.29.0
chromadb==0.4.24
langchain==0.2.0
langchain-community==0.2.0
openai==1.30.0          # 兼容DashScope OpenAI格式
faster-whisper==1.0.0
torch==2.3.0            # CosyVoice依赖
redis==5.0.4
python-multipart==0.0.9
```

### frontend/package.json（核心）

```json
{
  "dependencies": {
    "vue": "^3.4.0",
    "pinia": "^2.1.0",
    "pixi.js": "^7.4.0",
    "pixi-live2d-display": "^0.4.0",
    "ant-design-vue": "^4.2.0",
    "echarts": "^5.5.0",
    "vue-echarts": "^6.7.0",
    "axios": "^1.6.0"
  }
}
```
