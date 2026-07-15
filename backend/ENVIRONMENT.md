# 后端 Python 环境交接说明

这份说明以当前已经跑通的 `conda` 环境 `ai-chat-gpu` 为基线，适用于本项目现阶段的 Windows + NVIDIA GPU 开发/验收环境。

## 推荐结论

当前交接方案推荐使用：

1. `conda` 管理 Python、CUDA、PyTorch 这类二进制基础环境
2. `requirements*.txt` 管理项目 Python 依赖
3. `environment.ai-chat-gpu.yml` 作为团队交接的最小可复现基线

当前**不建议把 `pixi` 作为主方案**，原因是：

- 现有项目已经稳定运行在 `conda` 环境上，迁移到 `pixi` 会增加一层额外变量
- 当前依赖里有 `CUDA + PyTorch + onnxruntime-gpu + CosyVoice 本地仓库 + 本地模型目录`，这套组合用 `conda` 更稳
- 团队当前实际交付环境就是 `ai-chat-gpu`，交接优先保证“别人拿到后能直接跑”

如果后续团队希望做跨平台统一任务管理，再单独评估 `pixi` 更合适。

## 当前推荐文件

- [environment.ai-chat-gpu.yml](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/environment.ai-chat-gpu.yml)
  - 固定 Python / NumPy / CUDA / PyTorch 基线
- [requirements.runtime.txt](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/requirements.runtime.txt)
  - 聚合当前后端运行所需依赖
- 现有的：
  - [requirements.txt](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/requirements.txt)
  - [requirements.asr.txt](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/requirements.asr.txt)
  - [requirements.knowledge.txt](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/requirements.knowledge.txt)
  - [requirements.tts.txt](/abs/E:/2026spring/software%20contest/AI-chat-live2d/backend/requirements.tts.txt)

## 一次性安装

```powershell
cd backend
conda env create -f environment.ai-chat-gpu.yml
conda activate ai-chat-gpu
python -m pip install --upgrade pip
python -m pip install -r requirements.runtime.txt --no-build-isolation
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install onnxruntime-gpu==1.18.0 --no-build-isolation
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
Copy-Item .env.example .env
```

如果环境已经存在，可以更新为：

```powershell
cd backend
conda activate ai-chat-gpu
conda env update -f environment.ai-chat-gpu.yml --prune
python -m pip install -r requirements.runtime.txt --no-build-isolation
python -m pip uninstall -y onnxruntime onnxruntime-gpu
python -m pip install onnxruntime-gpu==1.18.0 --no-build-isolation
python - <<'PY'
import onnxruntime as ort
print(ort.get_available_providers())
PY
```

如果输出里没有 `CUDAExecutionProvider`，不要继续启动 CosyVoice GPU。

## 当前经过验证的基础版本

- Python: `3.11`
- PyTorch: `2.3.1`
- CUDA Runtime: `12.1`
- torchvision: `0.18.1`
- torchaudio: `2.3.1`
- NumPy 基线: `1.24.3`

说明：

- `environment.ai-chat-gpu.yml` 固定的是基础二进制环境
- 实际 `pip` 安装阶段仍会补齐项目运行依赖
- 项目当前真实可运行环境来自 `conda + pip` 混合方案，不是纯 `pip venv`
- `chromadb` 和 `faster-whisper` 的依赖链会重新装回 CPU 版 `onnxruntime`
- 只要你重新安装过知识库 / ASR 依赖，就要再次执行一次 provider 校验

## 当前功能所需本地资源

除了 Python 包，还需要这些本地资源：

- `backend/storage/vendor/CosyVoice`
  - 需要完整仓库，建议使用 `--recursive` 拉取
- `backend/storage/models/CosyVoice2-0.5B`
- `backend/storage/models/faster-whisper-small`
- `backend/storage/models/bge-m3`
- `backend/storage/models/bge-reranker-v2-m3`

其中：

- TTS 依赖 `CosyVoice` 仓库和 `CosyVoice2-0.5B`
- ASR 依赖 `faster-whisper-small`
- 知识库导入依赖 `bge-m3`
- RAG 重排依赖 `bge-reranker-v2-m3`

## 当前推荐 `.env` 方向

以当前 4060 本机验收方案为准，推荐保持：

```env
ASR_ENGINE=faster-whisper
ASR_MODEL_NAME=./storage/models/faster-whisper-small
ASR_DEVICE=cpu

TTS_ENGINE=cosyvoice
TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B
TTS_COSYVOICE_CODE_PATH=./storage/vendor/CosyVoice
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_ONNX_PROVIDER=cpu

CHAT_MODE=rag
RAG_RERANKER_ENGINE=bge-reranker-v2-m3
RAG_RERANKER_MODEL=./storage/models/bge-reranker-v2-m3
RAG_RERANKER_DEVICE=cpu

KNOWLEDGE_EMBEDDING_ENGINE=bge-m3
KNOWLEDGE_EMBEDDING_MODEL=./storage/models/bge-m3
KNOWLEDGE_EMBEDDING_DEVICE=cpu
```

## 为什么当前不把 RAG 默认切到 GPU

当前后端链路是先 `RAG / LLM`，再 `TTS`，所以它们**推理时序基本串行**。  
但这不代表 RAG 放到 GPU 就没有代价，因为 `get_rag_service()` 和 `get_tts_service()` 都会长期持有模型对象。

我们在这台 `RTX 4060 8GB` 机器上做过实测：

- `TTS` 单独常驻后，显存剩余大约 `3.1GB`
- `TTS + BGE reranker on GPU` 后，显存只剩大约 `430MB`
- `TTS + reranker + embedding 全上 GPU` 后，显存几乎归零

所以当前交接基线仍然建议：

- `TTS` 走 `cuda`
- `ASR` 先走 `cpu`
- `RAG reranker` 走 `cpu`
- `knowledge embedding` 走 `cpu`

如果后续换成更大显存卡，再考虑把 RAG 逐步切到 GPU。

## 启动与验证

启动后端：

```powershell
cd backend
conda activate ai-chat-gpu
python -m uvicorn main:app --reload
```

基础验证：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO_GPU')"
python -c "import fastapi, sqlalchemy, sentence_transformers; print('ok')"
```

服务地址：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

## 交接建议

如果是给新同学交接，推荐按下面顺序：

1. 先恢复 `conda` 基础环境
2. 再安装 `requirements.runtime.txt`
3. 再确认本地模型目录是否齐全
4. 最后再复制 `.env` 并启动

这样比直接让别人手动拼 `pip install` 命令更稳，也比现在就切 `pixi` 风险更低。
