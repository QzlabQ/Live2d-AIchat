# 项目 Roadmap

> 总周期：8周（2026/07 - 2026/08）  
> 团队：建议3-4人（前端1、后端1、AI/算法1、全栈/文档1）

---

## 阶段总览

```
Week 1-2  │ Phase 1：基础骨架
Week 3-4  │ Phase 2：核心AI能力
Week 5-6  │ Phase 3：功能完整化
Week 7    │ Phase 4：数据大屏 + 体验打磨
Week 8    │ Phase 5：测试 + 文档 + 收尾
```

---

## Phase 1：基础骨架（Week 1-2）

### 目标

能看到数字人嘴巴动、能说话（哪怕口型不精准）

### 任务清单

**后端**

- [x] FastAPI 项目初始化，健康检查接口
- [x] PostgreSQL + SQLAlchemy 建表（sessions / messages / avatar_config）
- [x] WebSocket 通道搭建（接收音频块/文本，返回流式文本）
- [x] Whisper（faster-whisper）ASR 服务封装
- [x] Edge-TTS 接入（CosyVoice备用，先跑通流程）
- [x] `.env` 配置管理（DASHSCOPE_API_KEY 等）

**前端**

- [x] Vue3 + Vite + TypeScript 项目初始化
- [x] pixi-live2d-display 集成，载入示例 Live2D 模型
- [x] WebSocket 连接管理（心跳、断线重连）
- [x] 麦克风录音组件（MediaRecorder API，边录边传）
- [x] 文本输入框 + 发送逻辑

**知识库**

- [x] 下载示范景区资料包并解析（PDF/Word → 纯文本）
- [x] LangChain 文档切片（chunk_size=512, overlap=64）
- [x] bge-m3 Embedding 向量化入库（ChromaDB）

**里程碑验收**：语音输入 → 识别文字 → 数字人张嘴说话（Edge-TTS音频）

---

## Phase 2：核心AI能力（Week 3-4）

### 目标

数字人能准确回答景区问题，口型基本同步

### 任务清单

**RAG问答链**

- [x] LangChain RAG 链搭建（检索 → Rerank → 生成）
- [x] bge-reranker-v2-m3 重排序接入（提升准确率）
- [x] Prompt 工程：景区导游人设、引用原文作答、拒绝越界
- [x] 景区问答准确率测试（目标≥90%，构建50题测试集）
- [x] RAG 后结构化回复规划：将检索结果重写为导览式自然口语，避免直接拼接知识片段
- [x] 澄清追问状态管理：支持“先答再追问”、待澄清状态持久化、下一轮补充信息归并
- [x] 前端来源分离展示：主回答保持自然正文，资料依据通过独立来源区展示，不再拼进正文

**TTS 升级 & 口型同步**

> 决策：放弃 CosyVoice-300M-SFT（inference_sft 音质差、无情感控制），改用
> **CosyVoice2-0.5B + inference_instruct2**。RTX 4060 仅需约 3GB VRAM，完全可用。

- [x] 下载 CosyVoice2-0.5B 模型到 `./storage/models/CosyVoice2-0.5B`
      （HuggingFace: `FunAudioLLM/CosyVoice2-0.5B`，约 3.5GB）
- [x] 更新 `.env`：`TTS_COSYVOICE_MODEL_PATH=./storage/models/CosyVoice2-0.5B`
- [x] 修改 `backend/app/services/tts.py`：将 `inference_sft` 替换为 `inference_instruct2`，
      并添加情感指令映射：- `happy` → "用愉快活泼的语气介绍" - `excited` → "用热情兴奋的语气说" - `thinking` → "用平静思考的语气说" - `sad` → "用温柔低沉的语气说" - `neutral` → "用自然友好的语气说"
- [ ] 利用 CosyVoice2 输出的 `duration` 字段提取真实音素时长（替换现有 WordBoundary 近似算法）
      当前状态：非流式回退链路已支持 `duration/alignment/phoneme_alignment` 解析，默认流式链路仍以波形包络口型为主，需继续补齐“优先吃结构化 timing”的主链路实现。
- [x] Live2D 口型参数驱动（PARAM_MOUTH_OPEN_Y / PARAM_MOUTH_FORM），见 [lipsync.md](lipsync.md)
- [ ] 联调口型与音频时间轴对齐，目标误差 < 80ms
      当前状态：已经完成流式音频调度对齐与嘴型跟随，但缺少可复核的 `< 80ms` 量化验收记录，需补人工验收结果与测试口径。

**TTS / 口型同步收尾计划**

- [ ] 默认流式 TTS 链路优先消费 CosyVoice2 的 `duration/alignment`，仅在结构化 timing 缺失时回退到波形包络口型。
- [ ] 增加一轮口型对齐专项联调，记录“音频开始时间 / 嘴型开始时间 / 主观误差”，把 `< 80ms` 验收结果落到文档。

**表情系统**

- [x] 情感关键词提取（LLM分析回答情感）
- [x] 情感 → Live2D 表情参数映射表，（这里前端可以做一个情感熔岩灯，通过灯的颜色来判断其当前的情绪，也方便我们开发调试）
  - `happy` → 眉毛上扬 + 嘴角上扬
  - `thinking` → 眼神偏移 + 眉毛微蹙
  - `excited` → 眼睛睁大 + 手势
- [x] 动作协调：游客发问后先进入 `thinking`，首个真实音频 chunk 到达后切到 `speaking`，播放结束后 `cooldown -> idle`
- [x] 后端 reply trace：异步记录 `llm_first_delta_ms / tts_first_segment_ms / tts_first_audio_chunk_ms / text_done_ms / audio_done_ms / avatar_phase_*`，落盘到 `backend/logs/avatar_trace.log`

**里程碑验收**：问"这里有什么历史故事？"→ 口型同步回答，表情自然

---

## Phase 3：功能完整化（Week 5-6）

### 目标

游客端+管理后台功能完整，可端到端演示

### 任务清单

**游客端功能**

- [ ] 个性化推荐：兴趣标签选择UI + 路线推荐Prompt
- [ ] 多模态：拍照上传 → Qwen-VL-Max 识别景点 → 回答
- [ ] 对话历史展示（侧边栏）
- [ ] 数字人"思考中"动画（LLM响应期间）

**管理后台**

- [ ] 知识库管理：文件上传/列表/删除 + 处理状态显示
- [ ] 数字人配置：Live2D模型选择/声音ID/系统Prompt编辑 + 实时预览
- [ ] 用户登录（简单JWT，admin账户即可）
- [ ] 新增独立 voice_profile 表、音频资源管理、上传/校验/试听链路，下拉选择音色

**后端**

- [ ] 对话记录持久化（messages表）
- [ ] 情感分析批处理任务（每日定时，LLM分析当日对话）
- [ ] 感受度报告生成 API

**里程碑验收**：管理员能上传新文档、配置数字人；游客能拍照问景点

---

## Phase 4：数据大屏 + 体验打磨（Week 7）

### 目标

数据可视化到位，体验流畅，延迟稳定 < 5s

### 任务清单

**数据大屏**

- [ ] 今日/本周服务人次（折线图）
- [ ] 热门问答 Top10（条形图）
- [ ] 游客满意度趋势（情感评分折线）
- [ ] 关注点词云（高频实体词）
- [ ] 实时在线人数

**感受度报告**

- [ ] 报告页面：情感趋势图 + 关注点分析 + LLM生成文字摘要
- [ ] 支持按日期范围筛选

**体验优化**

- [ ] 口型平滑插值（避免突变，lerp过渡）
- [ ] TTS 分句并行合成（LLM 流式输出 → 按句触发合成 → pipeline，降低首句延迟）
- [ ] 初赛后迁移至 A100：开启 `stream=True` 流式合成，首句延迟目标 < 1.5s
- [ ] A100 阶段可选：`inference_zero_shot` + 专属导游音色录音（3~10s 参考音频），进一步提升辨识度
- [ ] 弱网环境降级处理（文字回复 + 简单口型）
- [ ] 数字人闲置动画（无对话时轻微摇头/眨眼）

**延迟基准测试**

- [ ] 10轮问答实测延迟，记录P50/P90
- [ ] 若 P90 > 5s，定位瓶颈并优化

---

## Phase 5：测试 + 文档 + 收尾（Week 8）

### 目标

准备好参赛提交材料

### 任务清单

**测试**

- [ ] 景区问答准确率最终测试（50题，目标≥90%）
- [ ] 稳定性测试（连续运行1小时，无崩溃）
- [ ] 边界测试：空输入、超长输入、无关话题

**提交材料**

- [ ] 源代码整理（删除敏感密钥、补充注释）
- [ ] `docker-compose.yml` 一键部署验证
- [ ] 部署和使用手册（含环境要求、启动步骤）
- [ ] 总体设计文档（基于 docs/ 整理）
- [ ] PPT（需求场景 → 方案设计 → 核心技术 → 演示 → 测试数据）
- [ ] 演示视频（≤7分钟，重点展示口型同步+问答+大屏）

---

## 人员分工建议

| 角色     | 主要职责                                        |
| -------- | ----------------------------------------------- |
| 前端开发 | Vue3界面、Live2D集成、口型动画驱动、ECharts大屏 |
| 后端开发 | FastAPI接口、数据库、WebSocket、TTS/ASR服务     |
| AI/算法  | RAG链搭建、Prompt工程、准确率调优、情感分析     |
| 全栈/PM  | 管理后台、联调、文档、PPT、演示视频             |

---

## 风险预案

| 风险               | 触发条件         | 预案                                                                     |
| ------------------ | ---------------- | ------------------------------------------------------------------------ |
| CosyVoice2显存不足 | VRAM < 4GB       | 降级 Edge-TTS + WordBoundary 近似口型；4060(8GB)已验证可用，触发概率极低 |
| RAG准确率 < 90%    | Week 4测试不达标 | 增加知识条目 + 加 reranker + 调整chunk策略                               |
| LLM延迟过高        | P90 > 3s         | 换qwen-plus（更快）+ 限制生成token数                                     |
| Live2D授权问题     | 商用模型版权     | 使用免费开源模型或自绘（pixi-live2d支持）                                |
| 示范资料包数据稀疏 | 问答覆盖率低     | 爬取景区官网补充，人工撰写FAQ                                            |
