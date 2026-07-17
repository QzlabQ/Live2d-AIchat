# Backend Phase 1-2

显卡升级与后续迁移说明见 [docs/gpu-upgrade.md](../docs/gpu-upgrade.md)。

这个目录已经覆盖 `docs/roadmap.md` 中 Phase 1-2 的后端、知识库和 RAG 基础能力：

- FastAPI 项目骨架与健康检查
- `sessions` / `messages` / `avatar_config` / `knowledge_docs` 表
- WebSocket 实时对话通道
- `faster-whisper` ASR 封装
- `edge-tts` / 本地 `CosyVoice` TTS 封装
- Phase 2 表情分析：
  - `DashScope / Qwen` 可选情绪判断
  - 关键词规则兜底
  - WebSocket 下发 `emotion` 元信息（情绪、置信度、关键词、原因、来源）
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

建议使用 conda，并优先选择单独的 GPU 环境 `ai-chat-gpu`。

```powershell
cd backend
conda create -n ai-chat-gpu python=3.11 numpy=1.24.3 -c defaults -y
conda activate ai-chat-gpu
conda install pytorch::pytorch=2.3.1=py3.11_cuda12.1_cudnn8_0 pytorch::torchvision=0.18.1=py311_cu121 pytorch::torchaudio=2.3.1=py311_cu121 pytorch-cuda=12.1 -c pytorch -c nvidia -c defaults -y
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements.asr.txt
python -m pip install -r requirements.knowledge.txt
python -m pip install -r requirements.tts.txt --no-build-isolation
Copy-Item .env.example .env
```

如果你已经建好了 `ai-chat-gpu`，只需要执行：

```powershell
cd backend
conda activate ai-chat-gpu
python -m pip install -r requirements.txt
python -m pip install -r requirements.asr.txt
python -m pip install -r requirements.knowledge.txt
python -m pip install -r requirements.tts.txt --no-build-isolation
```

如果旧环境里已经装过 CPU 版 ONNX Runtime，建议切换 TTS 依赖前先清理一次：

```powershell
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install -r requirements.tts.txt --no-build-isolation
```

如果你是在 Linux 原生服务器上用 `requirements.runtime.txt` 做整套安装，并且希望 CosyVoice 前端 ONNX 也走 GPU，推荐把修复顺序固定成：

```bash
python -m pip install -r requirements.runtime.txt --no-build-isolation
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install onnxruntime-gpu==1.18.0 --no-build-isolation
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
```

如果输出里没有 `CUDAExecutionProvider`，不要继续启动后端。先修环境，再启动。

如果你要在本项目里启用“本地 CosyVoice + 情感指令发声”模式，推荐下载 `CosyVoice2-0.5B`。
- 后端当前使用 `inference_instruct2`，由自然语言情感指令控制语气
- `voice_id` 只作为兼容展示字段保留，真实音色来自 avatar 配置里的参考音频和参考文本

推荐下载命令：

```powershell
conda activate ai-chat-gpu
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice2-0.5B', local_dir='E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice2-0.5B')"
```

如果你用 Hugging Face：

```powershell
conda activate ai-chat-gpu
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='FunAudioLLM/CosyVoice2-0.5B', local_dir='E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice2-0.5B')"
```

说明：

- `requirements.txt` 里故意不再包含 `numpy`
- `requirements.tts.txt` 是本项目为 CosyVoice 推理整理的最小运行时依赖集合
- `requirements.tts.txt` 当前仍保留 `onnxruntime-gpu` 依赖，但本项目默认把 `TTS_COSYVOICE_ONNX_PROVIDER` 固定为 `cpu`，优先把 4060 显存留给 CosyVoice2 主模型
- `chromadb` 和 `faster-whisper` 的依赖链会重新拉入 CPU 版 `onnxruntime`
- 只要你重新安装过知识库 / ASR 相关依赖，就要再次执行一次 provider 校验，确认 `CUDAExecutionProvider` 还在
- `openai-whisper` 在 Windows 下需要 `--no-build-isolation` 才能稳定构建
- 在 `conda` 环境里，`numpy` 和 `torch` 这类二进制包优先用 `conda install`，不要再单独 `pip install numpy` / `pip install torch`
- 否则很容易出现 Windows 下的 `DLL load failed`、`numpy C-extensions failed` 这类混装问题

## 启动后端

```powershell
cd backend
conda activate ai-chat-gpu
python -m uvicorn main:app --reload
```

启动后默认地址：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

如果同时联调前端游客端和管理后台：

```powershell
cd ..\frontend
npm install
npm run dev
```

默认访问地址：

- 游客端：`http://127.0.0.1:5173/`
- 管理后台：`http://127.0.0.1:5173/admin.html`

## 可选依赖

如果你要切到 PostgreSQL：

```powershell
conda activate ai-chat-gpu
python -m pip install -r requirements.postgres.txt
```

然后把 `.env` 里的 `DATABASE_URL` 改成 `postgresql+psycopg://...`

如果你要启用本地 `faster-whisper`：

```powershell
conda activate ai-chat-gpu
python -m pip install -r requirements.asr.txt
```

然后把 `.env` 里的 `ASR_ENGINE=mock` 改成 `ASR_ENGINE=faster-whisper`

推荐把模型先下载到本地目录，避免第一次语音输入时才开始联网下载：

```text
backend/storage/models/faster-whisper-small
```

推荐下载命令：

```powershell
cd backend
conda activate ai-chat-gpu
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Systran/faster-whisper-small', local_dir='./storage/models/faster-whisper-small')"
```

对应 `.env` 建议改成：

```env
ASR_ENGINE=faster-whisper
ASR_MODEL_NAME=./storage/models/faster-whisper-small
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
```

当前后端启动时会主动预加载 ASR 模型，所以只要本地目录和 `.env` 配好，语音首轮不会再等到第一次录音结束后才触发模型下载/加载。

## Phase 2 口型同步 / CosyVoice

当前 TTS 主线已经切换到 `CosyVoice2-0.5B + inference_instruct2`。推荐 `.env` 使用下面这组最终配置：

```env
TTS_ENGINE=cosyvoice
TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B
TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_ONNX_PROVIDER=cpu
TTS_COSYVOICE_SAMPLE_RATE=24000
TTS_COSYVOICE_FP16=true
TTS_COSYVOICE_LOAD_JIT=false
TTS_COSYVOICE_LOAD_TRT=false
TTS_COSYVOICE_TRT_CONCURRENT=1
TTS_PROVIDER=local
TTS_REMOTE_URL=
TTS_REMOTE_PROTOCOL=http_stream
TTS_STREAM_PROFILE=stable
TTS_SEGMENT_SOFT_MIN_CHARS=12
TTS_SEGMENT_SOFT_MAX_CHARS=20
TTS_SEGMENT_HARD_MAX_CHARS=28
DEFAULT_TTS_REFERENCE_AUDIO_PATH=./storage/vendor/CosyVoice/asset/zero_shot_prompt.wav
DEFAULT_TTS_REFERENCE_TEXT=希望你以后能够做得比我还好。
DEFAULT_TTS_SPEED=1.0
DEFAULT_TTS_EMOTION_ENABLED=true

CHAT_MODE=rag
RAG_RESPONSE_MODE=fast_humanized
```

如果你是在 V100 这类显存更宽裕、并且更重视 TensorRT / ONNX GPU 路径的服务器上部署，建议直接参考 `../deploy/backend.env.v100.example`：

- `TTS_COSYVOICE_ONNX_PROVIDER=cuda`
- `TTS_COSYVOICE_LOAD_TRT=true`
- `TTS_COSYVOICE_TRT_CONCURRENT=1`
- `TTS_STREAM_PROFILE=stable`
- `TTS_SEGMENT_SOFT_MIN_CHARS=12`
- `TTS_SEGMENT_SOFT_MAX_CHARS=20`
- `TTS_SEGMENT_HARD_MAX_CHARS=28`
- 首次部署前先预构建或加载 `flow.decoder.estimator.fp16.mygpu.plan`

说明：服务器示例里 `TTS_COSYVOICE_ONNX_PROVIDER=cuda` 与 `TTS_COSYVOICE_LOAD_TRT=true` 适合继续保留，但分段阈值不建议再沿用旧的 `22 / 40 / 64`。那组值会减少 segment 数量，却会把单个 segment 拉得过长，容易在 CosyVoice 单段流式生成后半段触发明显退化。当前稳定推荐仍是 `12 / 20 / 28`，优先保证长句连续播放。

说明：`voice_id` 现在只作为兼容展示字段保留，真实发声由 `avatar_config` 中的参考音频、参考文本、语速和情感开关决定。

### 4060 本机策略

- 当前推荐把 `CosyVoice2` 主模型放在 `cuda`，但把 `TTS_COSYVOICE_ONNX_PROVIDER` 固定为 `cpu`，避免 ONNX 前端额外吃显存。
- `RAG_RERANKER_DEVICE` 和 `KNOWLEDGE_EMBEDDING_DEVICE` 继续保持 `cpu` 即可，不需要为了“统一环境”把知识库和 reranker 一起切到 GPU。
- 这轮优先优化的是现有本机链路：更短的 TTS 分段、稳定档前端 jitter buffer、参考音频前处理缓存、TTS chunk 级 trace。
- `TTS_STREAM_PROFILE=stable` 是 4060 默认推荐：首音频可以略晚一点，但会尽量攒够缓冲，降低播放中断流。
- `RAG_RESPONSE_MODE=fast_humanized` 会让高置信常见问题跳过一次非流式 RAG 决策 LLM，低置信问题仍回退到完整人性化决策。
- `TTS_PROVIDER=local` 表示继续使用本机 CosyVoice；后续接 A100/V100 独立服务时改成 `remote`，前端 WebSocket 协议不需要改。
- `async_cosyvoice` / 官方 gRPC / Triton 暂时不接入。本轮先把本机 4060 方案跑顺，后续再做外部化。

这一轮已经补上：

- 后端返回更真实的口型帧：`ph / start / end / openY / form`
- `edge-tts` 下用 `WordBoundary + 拼音嘴型估计` 生成口型时间轴
- 前端按真实音频 `currentTime` 驱动 Live2D 嘴型，而不是只靠本地计时器估算
- `cosyvoice` 模式下优先使用结构化时序；没有时序字段时用音频波形能量包络生成 50Hz 口型帧

如果你要启用本地 CosyVoice，并让 4060 走 GPU，建议按下面配置：

1. 在 `ai-chat-gpu` conda 环境里安装 **GPU 版** PyTorch，并确认：

```powershell
conda activate ai-chat-gpu
conda install pytorch::pytorch=2.3.1=py3.11_cuda12.1_cudnn8_0 pytorch::torchvision=0.18.1=py311_cu121 pytorch::torchaudio=2.3.1=py311_cu121 pytorch-cuda=12.1 -c pytorch -c nvidia -c defaults -y
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO_GPU')"
```

输出里 `torch.cuda.is_available()` 应为 `True`。

2. 把 CosyVoice 官方仓库完整放到项目内，并安装推理依赖。

建议目录：

```text
backend/storage/vendor/CosyVoice
```

仓库需要带 `third_party/Matcha-TTS` 子模块，示例：

```powershell
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git .\storage\vendor\CosyVoice
python -m pip install -r requirements.tts.txt --no-build-isolation
```

3. 把模型目录放到：

```text
backend/storage/models/CosyVoice2-0.5B
```

4. 把 `.env` 里的 TTS 配置改成：

```env
TTS_ENGINE=cosyvoice
TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B
TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_ONNX_PROVIDER=cpu
TTS_COSYVOICE_SAMPLE_RATE=24000
TTS_COSYVOICE_FP16=true
TTS_COSYVOICE_LOAD_JIT=false
TTS_PROVIDER=local
TTS_REMOTE_URL=
TTS_REMOTE_PROTOCOL=http_stream
TTS_STREAM_PROFILE=stable
TTS_SEGMENT_SOFT_MIN_CHARS=12
TTS_SEGMENT_SOFT_MAX_CHARS=20
TTS_SEGMENT_HARD_MAX_CHARS=28
DEFAULT_TTS_REFERENCE_AUDIO_PATH=./storage/vendor/CosyVoice/asset/zero_shot_prompt.wav
DEFAULT_TTS_REFERENCE_TEXT=希望你以后能够做得比我还好。
DEFAULT_TTS_SPEED=1.0
DEFAULT_TTS_EMOTION_ENABLED=true

CHAT_MODE=rag
RAG_RESPONSE_MODE=fast_humanized
```

- `DEFAULT_TTS_REFERENCE_AUDIO_PATH` 是默认参考音频，新建数据库或迁移旧库时会写入 `avatar_config.tts_reference_audio_path`
- `DEFAULT_TTS_REFERENCE_TEXT` 必须和参考音频内容匹配，默认参考音频对应文本是“希望你以后能够做得比我还好。”

说明：

- 如果 `avatar_config.voice_id` 里还是 `zh-CN-XiaoxiaoNeural` 这类 Edge 音色，CosyVoice2 模式会忽略它；真实音色由参考音频决定
- 如果 `TTS_COSYVOICE_DEVICE=auto`，会优先尝试 `cuda`，不可用时降到 `cpu`
- 如果 `cosyvoice` 不是通过 site-packages 安装，后端会自动尝试从 `TTS_COSYVOICE_CODE_PATH` 导入
- 如果本地 CosyVoice 尚未装好，服务会自动降级回 `edge-tts`，保证联调不断

推荐设备策略：

- `TTS_COSYVOICE_DEVICE=cuda`
- `ASR_DEVICE=cpu` 或 `cuda`
- `RAG_RERANKER_DEVICE=cpu`
- `KNOWLEDGE_EMBEDDING_DEVICE=cpu`

这里不需要“为了避免冲突，把所有东西都切到 GPU”。

- `CPU/GPU` 是各模块自己的运行设备，不会因为同在一个 conda 环境里就产生冲突
- 真正容易冲突的是 `pip` 和 `conda` 混装 `numpy/torch` 这类二进制包
- 对当前项目，最值得优先上 GPU 的是 `CosyVoice`
- `knowledge_base` 的向量化和 `RAG reranker` 完全可以继续走 CPU，这样更稳，也能减少 4060 的显存占用
- 如果后面你觉得 `Whisper` 识别速度不够，再把 `ASR_DEVICE` 切到 `cuda`

## Windows 常见环境问题

如果你看到类似下面的报错：

- `Importing the numpy C-extensions failed`
- `DLL load failed while importing _multiarray_umath`

通常不是代码问题，而是 `conda` 和 `pip` 混装了二进制包。最常见的坏状态是：

- `numpy` 来自 `pip`
- `numpy-base` 来自 `conda`
- `torch` 来自 `pip`
- `pytorch` 又来自 `conda`

修复方式：

```powershell
conda activate ai-chat-gpu
python -m pip uninstall -y numpy torch torchaudio torchvision
conda install numpy=1.24.3 -c defaults -y
conda install pytorch::pytorch=2.3.1=py3.11_cuda12.1_cudnn8_0 pytorch::torchvision=0.18.1=py311_cu121 pytorch::torchaudio=2.3.1=py311_cu121 pytorch-cuda=12.1 -c pytorch -c nvidia -c defaults -y
python -c "import numpy, torch; print(numpy.__version__); print(torch.__version__); print(torch.cuda.is_available())"
```

如果当前环境已经反复混装过，最稳的做法是直接新建一个干净环境，例如：

```powershell
conda create -n ai-chat-gpu python=3.11 numpy=1.24.3 -c defaults -y
conda activate ai-chat-gpu
conda install pytorch::pytorch=2.3.1=py3.11_cuda12.1_cudnn8_0 pytorch::torchvision=0.18.1=py311_cu121 pytorch::torchaudio=2.3.1=py311_cu121 pytorch-cuda=12.1 -c pytorch -c nvidia -c defaults -y
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements.asr.txt
python -m pip install -r requirements.knowledge.txt
python -m pip install -r requirements.tts.txt --no-build-isolation
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git .\storage\vendor\CosyVoice
Copy-Item .env.example .env
```

## Phase 1-2 知识库 / RAG 依赖

```powershell
cd backend
conda activate ai-chat-gpu
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
conda activate ai-chat-gpu
python -m scripts.import_knowledge --source "..\data\20260323113204906 (1)\示范景区公开资料包" --reset
```

导入完成后会：

- 写入 `knowledge_docs` 表
- 按文档切片并生成 embedding
- 写入本地 `ChromaDB`

## Phase 2 RAG 配置

当前 `.env` 推荐切到：

- `CHAT_MODE=rag`
- `RAG_RERANKER_ENGINE=bge-reranker-v2-m3`
- `TTS_ENGINE=cosyvoice`

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
conda activate ai-chat-gpu
python -m scripts.evaluate_rag --dataset .\evals\phase2_rag_eval.sample.jsonl
```

如果你要跑 roadmap 里的 50 题准确率测试，可以直接使用仓库内置题集：

```powershell
cd backend
conda activate ai-chat-gpu
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
- `POST /api/v1/admin/auth/login`
- `GET /api/v1/admin/auth/me`
- `GET /api/v1/admin/avatar/models`
- `GET /api/v1/admin/avatar/config`
- `PUT /api/v1/admin/avatar/config`
- `POST /api/v1/admin/knowledge/upload`
- `GET /api/v1/admin/knowledge`
- `DELETE /api/v1/admin/knowledge/{doc_id}`
- `GET /api/v1/admin/voice-profiles`
- `POST /api/v1/admin/voice-profiles`
- `GET /api/v1/admin/voice-profiles/{profile_id}/audio`
- `DELETE /api/v1/admin/voice-profiles/{profile_id}`
- `POST /api/v1/admin/reports/daily/generate`
- `GET /api/v1/admin/reports/daily`
- `GET /api/v1/admin/reports/summary`
- `GET /api/v1/admin/dashboard/overview`
- `GET /api/v1/admin/dashboard/emotion`
- `WS /ws/chat/{session_id}`

## Phase 3 管理后台

当前已经补齐一套独立的前端管理入口 `frontend/admin.html`，对应能力如下：

- 管理员登录：使用简单 JWT，默认账号密码来自 `.env` 中的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`
- 知识库管理：上传、列表、处理状态、删除
- 数字人配置：切换 Live2D 模型、编辑系统 Prompt、调整参考音频/参考文本/语速/情感开关
- 音色资源库：上传参考音频、试听、删除，并将音色绑定到当前数字人配置
- 数据大屏：按 roadmap 的五项展示今日/本周服务人次折线、热门问答 Top10 条形图、游客满意度趋势折线、关注点词云、实时在线人数
- 感受度报告：按日期范围查看日报汇总、情绪分析与 LLM 摘要

推荐最小配置：

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_JWT_SECRET=change-me-admin-secret
ADMIN_KNOWLEDGE_UPLOAD_DIR=./storage/uploads/admin/knowledge
ADMIN_VOICE_UPLOAD_DIR=./storage/uploads/admin/voice_profiles
ADMIN_VOICE_MAX_BYTES=33554432
```

说明：

- 管理后台音色试听走受保护接口，因此前端会先带 Bearer Token 拉取音频，再用浏览器本地 `Blob URL` 播放
- 当你在管理后台选择某个 `voice_profile` 并保存后，后端会自动同步 `voice_id`、`tts_reference_audio_path`、`tts_reference_text`
- 数据大屏数据来自 `GET /api/v1/admin/dashboard/overview`，其中 `service_trend` 驱动服务人次折线，`satisfaction_trend` 驱动满意度折线，`keyword_cloud` 驱动关注点词云
- 感受度报告数据来自 `GET /api/v1/admin/reports/summary` 和 `GET /api/v1/admin/reports/daily`，后台可通过 `POST /api/v1/admin/reports/daily/generate` 手动生成指定日期日报
- `frontend/vite.config.ts` 已改为多页面构建，`npm run build` 会同时生成游客端与管理后台

## Phase 3 后端分析链路

当前已经补齐：

- 对话记录持久化：游客文本、ASR 转写、助手回复都会写入 `messages`
- 每日情感分析批处理：服务启动后会按 `ANALYTICS_SCHEDULER_*` 自动补跑最近日报
- 感受度报告 API：管理员可手动生成某日分析，并按日期范围读取汇总摘要

推荐配置：

```env
ANALYTICS_SCHEDULER_ENABLED=true
ANALYTICS_SCHEDULER_INTERVAL_SECONDS=3600
ANALYTICS_SCHEDULER_CATCHUP_DAYS=2
ANALYTICS_REPORT_SAMPLE_SESSIONS=8
```

说明：

- 日报优先复用 `messages.emotion` 和 `messages.latency_ms` 聚合
- 如果已经配置 `DASHSCOPE_API_KEY`，日报摘要会尝试调用 LLM 生成更自然的运营总结
- 如果 LLM 不可用，会自动降级为本地启发式摘要，不会阻塞实时对话
- 这条链路只服务后台分析，不会拖慢前端聊天响应

## Trace 与日志

- 结构化 reply trace 落盘在 `backend/logs/avatar_trace.log`
- 这是一行一条 JSON，适合后续脚本分析
- 语音链路现在会一起记录：
  - `asr_model_load_ms`
  - `asr_transcribe_ms`
  - `asr_total_ms`
  - `llm_first_delta_ms`
  - `tts_first_segment_ms`
  - `tts_first_audio_chunk_ms`
  - `audio_done_ms`
- 普通后端运行日志里仍会输出 `reply_metrics ...` 摘要，适合肉眼快速看

## 联调建议

- 如果本机暂时没有配置 Whisper，先保留 `ASR_ENGINE=mock`
- 如果暂时不走 Edge TTS，先把 `TTS_ENGINE=edge-tts` 改回 `TTS_ENGINE=mock`
- 如果知识库导入要使用 `bge-m3`，优先保证本地模型目录已下载完成
- 如果要验证 Phase 2 的生成式 RAG，记得配置 `DASHSCOPE_API_KEY`
## 测试服务器 Docker 部署

如果你要把后端连同前端、PostgreSQL 一起部署到测试服务器，请直接看：

- [测试服务器 Docker Compose 部署手册](../docs/deployment/test-server-docker.md)

部署版本的关键差异是：

- Compose 文件不直接在仓库根目录启动，而是放在 `/opt/ai-chat-live2d/deploy`
- 代码仓库放在 `/opt/ai-chat-live2d/app`
- 模型、CosyVoice、知识库通过宿主机目录挂载，不放进镜像
- 浏览器通过 `ssh -L 18080:127.0.0.1:8080 user@server` 访问，不要求服务器开放公网端口
