# 显卡升级说明

本文面向当前仓库的 `Phase 2 / 本地 CosyVoice2-0.5B + WebSocket 流式播放` 链路，说明：

- 现在从 `RTX 4060` 升级到更强显卡，当前代码是否可以直接用
- 后续切到 `4070 / 4080 / 4090 / A100 / V100` 时，需要改哪些配置
- 哪些卡顿会明显改善，哪些问题不会因为单纯换卡而自动消失

## 一句话结论

当前代码没有把 GPU 型号写死在业务逻辑里，所以只要新显卡能被 `PyTorch + CUDA` 正常识别，通常不需要改代码，直接就能用。

换到更强显卡后，当前项目里最直接受益的是 `CosyVoice2` 的 TTS 推理速度，因此：

- `TTS 首包延迟`
- `句间音频断流`
- `流式播放时的 buffer underrun`

通常都会明显改善。

但下面这些问题，不会因为单纯换卡就 100% 自动消失：

- `DashScope / Qwen` 的首字返回延迟
- 文本切分策略带来的自然停顿
- 前端缓冲策略过于保守造成的“先等一会再播”
- 网络抖动或远程部署链路问题

所以更强显卡是“强力加速”，不是“万能修复”。

## 当前代码对 GPU 的依赖方式

当前仓库里，真正默认吃 GPU 的主要是 `CosyVoice2`：

- `TTS_COSYVOICE_DEVICE=cuda`

为了给 TTS 留更多显存，下面这些模块现在默认还是 CPU：

- `TTS_COSYVOICE_ONNX_PROVIDER=cpu`
- `RAG_RERANKER_DEVICE=cpu`
- `KNOWLEDGE_EMBEDDING_DEVICE=cpu`
- `ASR_DEVICE=cpu`

这意味着：

1. 现在换更强显卡，首先受益的是 TTS。
2. 如果后续显存非常充足，再考虑把 `ASR` 或 `RAG reranker` 迁到 GPU。
3. 知识库导入属于离线任务，默认继续走 CPU 更稳，不必为了“统一”强行上 GPU。

## 能否直接接更好的消费级显卡

可以。对当前代码来说，`4070 / 4070 Ti Super / 4080 / 4090` 都属于“直接替换后优先验证环境即可”的范围。

推荐顺序：

- 先保留当前 `.env` 不变
- 先确认 `torch.cuda.is_available()` 为 `True`
- 跑一轮真实问答，观察首包延迟和中途断流是否下降
- 稳定后再决定是否把 `ASR_DEVICE` 或 `RAG_RERANKER_DEVICE` 切到 `cuda`

### 预期改善

如果只是把 `4060 8GB` 升到更强的消费级卡，通常能直接改善：

- CosyVoice2 每段音频的合成耗时
- 前端等待下一段 chunk 的概率
- 长句下的句间停顿
- 多轮连续对话时的稳定性

但文字首字返回如果仍依赖远程模型 API，改善不会像 TTS 那么明显。

## 能否直接接 A100 / V100

也可以，当前代码同样没有限制只能用消费级显卡。

对 `A100 / V100` 来说，业务代码层面通常不需要改动，关键在运行环境：

- `A100` 通常部署在 Linux 服务器，建议直接用 Linux + conda
- `V100` 也更常见于 Linux 服务器
- 只要 `PyTorch` 能识别 CUDA 设备，当前 `CosyVoice2` 路径就能复用

### A100 / V100 的实际意义

- `A100`：显存和吞吐都更强，当前本机链路会更稳，后续也更适合尝试更激进的并行、JIT、TRT 或外部化 TTS 服务
- `V100`：也能明显强于 4060，但它是更老一代卡，吞吐和新特性不如 A100；对当前项目依然能直接跑

### 需要注意的点

1. `A100 / V100` 多数不在 Windows 桌面环境下使用，建议把后端迁到 Linux 服务器。
2. 当前仓库路径、命令和 `.env` 可以继续沿用，但部署方式通常会从“本机前后端都在一台机器”变成“前端本机，后端远程”。
3. 如果后端迁移到远程服务器，要同步检查：
   - `CORS_ORIGINS`
   - WebSocket 连接地址
   - 模型目录挂载路径
   - 服务器上的 NVIDIA 驱动和 CUDA 运行时

## 哪些地方不需要改代码

下面这些是当前代码已经做成“按运行时环境自适应”的：

- `torch.cuda.is_available()` 检测
- `TTS_COSYVOICE_DEVICE=cuda / auto / cpu`
- CosyVoice 本地模型路径配置
- CPU / GPU 分工通过 `.env` 控制

所以从代码层面说：

- 换 `4060 -> 4090`，通常不需要改代码
- 换 `4060 -> A100 / V100`，通常也不需要改代码

更常见的工作是“重装或校准环境”，而不是改业务逻辑。

## 哪些地方可能需要改配置

### 保守方案

先保持当前 `.env` 不变：

```env
TTS_ENGINE=cosyvoice
TTS_COSYVOICE_DEVICE=cuda
TTS_COSYVOICE_ONNX_PROVIDER=cpu
ASR_DEVICE=cpu
RAG_RERANKER_DEVICE=cpu
KNOWLEDGE_EMBEDDING_DEVICE=cpu
```

这是最稳的升级方式，适合先验证“换卡本身带来的纯收益”。

### 显存很充足后的可选方案

如果后续换成 `4090 / A100` 这类余量很大的卡，可以再逐步尝试：

```env
ASR_DEVICE=cuda
RAG_RERANKER_DEVICE=cuda
```

是否把下面这个也切到 `cuda`，建议单独测试后再决定：

```env
TTS_COSYVOICE_ONNX_PROVIDER=cuda
```

当前默认保留 `cpu`，原因是它更稳，也更不容易和 CosyVoice 主模型抢显存。

## 推荐的升级验收流程

### 1. 先看驱动是否正常

```powershell
nvidia-smi
```

### 2. 验证 conda 环境里的 PyTorch 是否能识别新卡

```powershell
conda activate ai-chat-gpu
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO_GPU')"
```

预期结果：

- `torch.cuda.is_available()` 为 `True`
- 显示出新显卡名称

### 3. 启动后端

```powershell
cd backend
conda activate ai-chat-gpu
python -m uvicorn main:app --reload
```

### 4. 做一轮真实联调

建议至少验证三类场景：

- 短句问答：看首包是否更快
- 长句导览：看句间是否还容易断流
- 连续多轮对话：看 GPU 是否稳定、是否出现 OOM

## 什么时候换卡就能解决大部分问题

如果当前瓶颈主要来自下面这些现象，那么换卡通常很有效：

- 后端日志里 TTS 每段 `model_chunk_ready_ms` 明显偏大
- 前端 `underrun_count` 偶发升高
- 文本已经出来，但音频还要再等明显一段时间
- 一旦句子稍长，下一段音频跟不上

这是典型的“当前链路已经基本打通，但模型推理速度不够富余”的情况。

## 什么时候换卡也不能彻底解决

如果问题来自下面这些方向，换卡只能部分改善：

- LLM 首字慢：这更多取决于模型 API 和网络
- 切句过碎或过长：这是切分策略问题
- 前端缓冲阈值过高：这是播放策略问题
- 远程部署网络抖动：这是传输链路问题

换句话说：

- 更强显卡能让“算得更快”
- 但不能替代“链路设计更合理”

## 推荐的团队决策

如果你们下一步只是想先把当前方案跑得更顺，我建议：

1. 先直接换更强显卡，不改业务代码。
2. 保持当前 `.env` 的 CPU / GPU 分工不变，先测纯硬件收益。
3. 如果换卡后卡顿显著下降，再考虑把 `ASR` 或 `RAG reranker` 迁到 GPU。
4. 如果换到 `A100` 这类服务器卡，再评估是否把后端独立部署，并进一步尝试更激进的流式 TTS 优化。

## 常见结论

### 结论 1

`4060 -> 4090`：大概率可以直接提升当前版本体验，不需要改代码。

### 结论 2

`4060 -> A100 / V100`：也可以直接接，但更适合放到 Linux 服务器环境里运行。

### 结论 3

换卡可以明显缓解当前 TTS 断流问题，但不会自动解决所有延迟来源。
