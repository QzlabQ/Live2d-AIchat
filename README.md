# 景区导览服务AI数字人

> 第十五届中国软件杯 A5 赛题 | 出题企业：锐捷网络（苏州）有限公司

一个具备多模态交互能力的景区AI数字人导览系统，支持语音/文本对话、口型同步、个性化路线推荐，并提供管理后台和数据大屏。

---

## 快速导航

| 文档 | 说明 |
|------|------|
| [技术选型](docs/tech-stack.md) | 各模块技术方案与选型理由 |
| [系统架构](docs/architecture.md) | 整体架构设计、模块划分、数据流 |
| [项目Roadmap](docs/roadmap.md) | 开发阶段计划与里程碑 |
| [API设计](docs/api-design.md) | 前后端接口规范 |
| [知识库建设](docs/knowledge-base.md) | RAG知识库构建与调优方案 |
| [口型同步方案](docs/lipsync.md) | Live2D口型驱动技术细节 |

---

## 项目结构

```
ai-tour-guide/
├── frontend/                # Vue3 前端
│   ├── src/
│   │   ├── visitor/         # 游客交互端（数字人对话）
│   │   └── admin/           # 管理后台
│   └── package.json
├── backend/                 # Python FastAPI 后端
│   ├── api/                 # 路由层
│   ├── services/
│   │   ├── rag/             # RAG检索问答
│   │   ├── llm/             # 大模型调用
│   │   ├── asr/             # 语音识别
│   │   ├── tts/             # 语音合成
│   │   └── emotion/         # 情感分析
│   ├── models/              # 数据库模型
│   ├── knowledge/           # 知识库文档处理
│   └── main.py
├── live2d/                  # Live2D模型资源
├── docker-compose.yml       # 一键启动
└── docs/                    # 设计文档
```

---

## 核心功能

### 游客端
- **多模态交互**：语音输入（Whisper）+ 文本输入，数字人语音+口型+表情同步回答
- **智能问答**：基于景区知识库RAG，事实性问答准确率≥90%
- **个性化推荐**：根据兴趣标签（历史/自然/美食等）推荐游览路线

### 管理后台
- **知识库管理**：上传PDF/Word/文本，自动切片入库
- **数字人配置**：外观、声音、人设Prompt自定义
- **游客感受度报告**：情感趋势、关注点分析
- **数据大屏**：服务人次、热门问答、满意度实时看板

---

## 环境要求

| 组件 | 最低要求 |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| VRAM（可选本地模型） | 8GB（Whisper large-v3 + CosyVoice） |
| 磁盘 | 20GB+ |

---

## 快速启动

```bash
# 1. 后端
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入 DASHSCOPE_API_KEY 等
uvicorn main:app --reload

# 2. 前端
cd frontend
npm install
npm run dev
```

或使用 Docker：

```bash
docker-compose up -d
```

---

## 评分对照

| 评分项 | 分值 | 对应模块 |
|--------|------|---------|
| 功能完整度 | 40 | 全部功能模块 |
| 技术与创新性 | 30 | 口型同步、RAG+大模型 |
| 行业实用与体验性 | 20 | 交互流畅度、数字人表现力 |
| 文档质量 | 10 | docs/ + PPT + 演示视频 |
