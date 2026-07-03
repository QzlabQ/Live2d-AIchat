# Backend Phase 1-2

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

如果你要在本项目里启用“本地 CosyVoice + 预置 speaker”模式，推荐下载 `CosyVoice-300M-SFT`，不要优先用 `CosyVoice2-0.5B`。
- `CosyVoice-300M-SFT` 自带预置 speaker，适合我们当前后端的 `inference_sft + spk_id` 接法
- `CosyVoice2-0.5B` 更偏向 `zero_shot / instruct` 用法，直接当固定 speaker SFT 模型会不匹配

推荐下载命令：

```powershell
conda activate ai-chat-gpu
python -c "from modelscope import snapshot_download; snapshot_download('iic/CosyVoice-300M-SFT', local_dir='E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice-300M-SFT')"
```

如果你用 Hugging Face：

```powershell
conda activate ai-chat-gpu
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='FunAudioLLM/CosyVoice-300M-SFT', local_dir='E:/2026spring/software contest/AI-chat-live2d/backend/storage/models/CosyVoice-300M-SFT')"
```

说明：

- `requirements.txt` 里故意不再包含 `numpy`
- `requirements.tts.txt` 是本项目为 CosyVoice 推理整理的最小运行时依赖集合
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

## Phase 2 口型同步 / CosyVoice

这一轮已经补上：

- 后端返回更真实的口型帧：`ph / start / end / openY / form`
- `edge-tts` 下用 `WordBoundary + 拼音嘴型估计` 生成口型时间轴
- 前端按真实音频 `currentTime` 驱动 Live2D 嘴型，而不是只靠本地计时器估算
- `cosyvoice` 模式下优先本地推理；如果运行时返回对齐信息会直接用，否则退化为“按总时长估算口型帧”

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
backend/storage/models/CosyVoice-300M-SFT
```

4. 把 `.env` 里的 TTS 配置改成：

```env
TTS_ENGINE=cosyvoice
TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice-300M-SFT
TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice
TTS_COSYVOICE_SPEAKER=中文女
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_SAMPLE_RATE=22050
```

- 当前项目更推荐 `CosyVoice-300M-SFT + 中文女` 这条链路，和官方 `example.py` / `runtime` 默认示例保持一致
- 如果你不确定本地模型里有哪些 speaker，可先运行 `python -c "from cosyvoice.cli.cosyvoice import CosyVoice; m=CosyVoice('./storage/models/CosyVoice-300M-SFT'); print(m.list_available_spks())"`

说明：

- 如果 `avatar_config.voice_id` 里还是 `zh-CN-XiaoxiaoNeural` 这类 Edge 音色，后端会自动回退到 `TTS_COSYVOICE_SPEAKER`
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
