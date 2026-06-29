# 知识库建设方案

## 总体思路

```
示范景区资料包（PDF/Word/图片说明）
        ↓
   文档解析 & 清洗
        ↓
   文本切片（Chunking）
        ↓
   bge-m3 向量化
        ↓
   ChromaDB 存储
        ↓
   查询时：Embedding检索 → Reranker重排 → 喂给LLM
```

---

## 文档解析

### 支持格式

| 格式 | 解析库 | 注意事项 |
|------|------|---------|
| PDF | `pymupdf` (fitz) | 优先用，速度快；扫描版PDF需加OCR |
| Word (.docx) | `python-docx` | 提取段落+表格 |
| 纯文本 (.txt) | 直接读取 | 注意编码（UTF-8） |
| 图片说明 | Qwen-VL-Max OCR | 景区图片配文字说明 |

### 清洗规则

```python
# 需要过滤的内容
NOISE_PATTERNS = [
    r'第\s*\d+\s*页',          # 页码
    r'版权所有.*',              # 版权声明
    r'\s{3,}',                  # 连续空白（替换为单空格）
    r'_{5,}',                   # 分隔线
]
```

---

## 切片策略（Chunking）

### 推荐参数

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,        # 中文约512字，适合bge-m3 512token上限
    chunk_overlap=64,      # 64字重叠，避免语义截断
    separators=["\n\n", "\n", "。", "；", "，", " "],
)
```

### 元数据设计

每个 chunk 存储以下元数据，用于过滤和引用：

```python
{
    "doc_id": "uuid",
    "filename": "景区历史沿革.pdf",
    "category": "history",       # history|scenery|faq|route|facility
    "page": 3,                   # 原文页码
    "chunk_index": 5,
}
```

### 特殊处理：FAQ文档

FAQ类文档（问题+答案对）**不切片**，整对存储：

```python
# 向量化"问题"文本，答案作为 metadata 存储
{
    "text": "景区门票多少钱？",    # 用于向量检索
    "metadata": {
        "answer": "成人票80元，学生票40元...",
        "category": "faq"
    }
}
```

---

## 检索策略

### 混合检索（Hybrid Search）

bge-m3 同时支持稠密（dense）和稀疏（sparse）检索，混合使用效果更好：

```python
from langchain_community.vectorstores import Chroma
from FlagEmbedding import BGEM3FlagModel

# 稠密检索：语义相似
dense_results = vectorstore.similarity_search(query, k=10)

# 稀疏检索（BM25）：关键词匹配，景区专有名词命中率高
from rank_bm25 import BM25Okapi
sparse_results = bm25.get_top_n(query_tokens, corpus, n=10)

# 合并去重（RRF融合）
merged = reciprocal_rank_fusion([dense_results, sparse_results])
```

### Reranker 重排序

```python
from FlagEmbedding import FlagReranker

reranker = FlagReranker("BAAI/bge-reranker-v2-m3", use_fp16=True)

# 对 top-10 结果重排，取 top-3 送入 LLM
pairs = [(query, doc.page_content) for doc in candidates]
scores = reranker.compute_score(pairs)
top3 = sorted(zip(scores, candidates), reverse=True)[:3]
```

> **为何加 Reranker**：向量检索召回的是"语义相似"，但不一定是"最有用"的片段。Reranker 对 query-doc 对逐一打分，准确率显著提升（测试集上 +5~10%）。

---

## Prompt 工程

### 系统 Prompt（景区导游人设）

```
你是「云溪」，{景区名称}的专属AI导游。你温柔、博学、热情，对景区的历史文化如数家珍。

【回答规则】
1. 只回答与景区相关的问题。对于无关问题，礼貌引导游客关注景区。
2. 回答必须基于以下参考资料，不得编造。若资料中无相关信息，如实告知。
3. 回答用自然口语，避免念文章感，适当使用"哦"、"呢"等语气词。
4. 回答长度控制在100-200字，适合语音播报。

【参考资料】
{retrieved_chunks}

【对话历史】
{chat_history}
```

### 个性化推荐 Prompt

```
游客兴趣标签：{tags}
已游览景点：{visited}
景区总景点列表：{all_spots}

请为该游客推荐一条游览路线，包含3-5个景点，说明每个景点的亮点和游览时间。
用自然语言描述，不要用列表格式，像真人导游介绍那样。
```

---

## 准确率评测方案

### 构建测试集

从示范景区资料中提取50个典型问题，覆盖：
- 历史类（15题）："这里的历史有多久？"
- 景点特色（15题）："XX景点有什么特别之处？"
- 实用信息（10题）："门票/开放时间/停车"
- 路线推荐（5题）
- 边界问题（5题）："请问附近有什么餐厅？"（应引导而非乱答）

### 评测脚本

```python
# 自动评测（语义相似度）
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("BAAI/bge-m3")

def evaluate_accuracy(test_set, rag_chain):
    scores = []
    for item in test_set:
        response = rag_chain.invoke(item["question"])
        sim = util.cos_sim(
            model.encode(response),
            model.encode(item["reference_answer"])
        ).item()
        scores.append(sim > 0.75)   # 0.75为及格线
    return sum(scores) / len(scores)
```

---

## 知识库扩充建议

官方资料包可能不够全面，建议补充：

| 来源 | 内容 |
|------|------|
| 景区官网 | 最新票价、活动公告、开放时间 |
| 百度百科/维基 | 景区历史背景、文化典故 |
| 小红书/大众点评 | 游客常见问题（转化为FAQ） |
| 人工撰写 | 针对测试集中答错的问题补写答案 |
