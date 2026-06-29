# Backend Phase 1

这个目录实现了 `roadmap.md` 中 Phase 1 的后端基础能力：

- FastAPI 工程骨架与健康检查
- `sessions` / `messages` / `avatar_config` / `knowledge_docs` 表
- WebSocket 实时对话通道
- `faster-whisper` ASR 封装
- `edge-tts` TTS 封装
- `.env` 配置管理

## 启动

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload
```

如果你要切到 PostgreSQL：

```bash
pip install -r requirements.postgres.txt
```

然后把 `.env` 里的 `DATABASE_URL` 改成 `postgresql+psycopg://...`

如果你要启用本地 `faster-whisper`：

```bash
pip install -r requirements.asr.txt
```

然后把 `.env` 里的 `ASR_ENGINE=mock` 改成 `ASR_ENGINE=faster-whisper`

## 接口

- `GET /api/v1/health`
- `POST /api/v1/sessions`
- `GET /api/v1/admin/avatar/config`
- `PUT /api/v1/admin/avatar/config`
- `WS /ws/chat/{session_id}`

## 联调建议

- 如果本机暂时没有配置 Whisper，先把 `ASR_ENGINE=mock`
- 如果暂时不走 Edge TTS，先把 `TTS_ENGINE=mock`
- 正式接 PostgreSQL 时，修改 `DATABASE_URL`

## 验收结果 20260629

Phase 1 后端验收结果 ✅
修复的问题
.env 中CORS_ORIGINS 用逗号分隔，但 pydantic-settings 对list[str] 字段先尝试 JSON decode，导致启动崩溃。已修正为 JSON 数组格式：

CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
.env.example 同步更新。

验收对照
Roadmap 任务 结果 说明
FastAPI 项目初始化 + 健康检查 ✅ GET / 和 GET /api/v1/health 正常返回
SQLAlchemy 建表 (sessions / messages / avatar_config / knowledge_docs) ✅ 启动时自动 CREATE_ALL，SQLite 可运行
.env 配置管理 ✅ pydantic-settings 读取正常，含降级默认值
WebSocket 通道（文本消息流） ✅ emotion → text_delta → phonemes → done 顺序正确
ASR 服务封装（mock + faster-whisper 接口） ✅ audio_end 触发 mock → asr_result →正常对话流
Edge-TTS 接入（mock fallback +音素帧） ✅ mock 模式返回 phonemes 数据，TTS 引擎可切换
Avatar 管理后台 GET/PUT ✅ 配置读写正常
下一步切换真实引擎

# 启用 Edge-TTS（真实语音合成）

TTS_ENGINE=edge-tts# 在 .env 中修改

# 启用 Whisper（真实语音识别），需先安装：

pip install -r requirements.asr.txt
ASR_ENGINE=whisper # 在 .env 中修改
Phase 1 全部通过，可以进入 Phase 2：RAG 问答链+ 口型同步。
