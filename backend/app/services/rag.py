from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass
from functools import lru_cache

import httpx
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import Settings, get_settings
from app.services.knowledge_base import (
    KnowledgeDependencyError,
    KnowledgeVectorStore,
    VectorStoreHit,
    build_embedding_service,
)

SENTENCE_RE = re.compile(r"(?<=[。！？!?；;\n])")
TOKEN_RE = re.compile("\\w+|[\u4e00-\u9fff]")
STOP_TOKENS = {
    "请",
    "一下",
    "介绍",
    "这里",
    "这里有",
    "这里有什么",
    "那个",
    "这个",
    "景区",
    "景点",
    "吗",
    "呢",
    "呀",
    "啊",
    "和",
    "与",
    "及",
    "的",
    "了",
    "有",
    "什么",
    "有什么",
    "怎么",
    "如何",
    "能否",
}


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    filename: str
    title: str
    category: str
    text: str
    chunk_index: int
    retrieval_score: float
    rerank_score: float


@dataclass(slots=True)
class RAGAnswer:
    answer_text: str
    spoken_text: str
    sources: list[RetrievedChunk]
    confidence: float
    used_llm: bool


class LexicalReranker:
    async def score_pairs(self, query: str, documents: list[str]) -> list[float]:
        query_tokens = meaningful_tokens(query)
        intent_tokens = intent_keywords(query)
        if not query_tokens:
            return [0.0 for _ in documents]

        scores: list[float] = []
        for document in documents:
            overlap = sum(1 for token in query_tokens if token in document)
            ratio = overlap / max(len(query_tokens), 1)
            intent_hits = sum(1 for token in intent_tokens if token in document)
            length_penalty = min(len(document) / 600.0, 1.0)
            scores.append(ratio + intent_hits * 0.24 + length_penalty * 0.08)
        return scores


class BgeRerankerService:
    def __init__(self, model_name: str, device: str, batch_size: int) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - dependency based
            raise KnowledgeDependencyError(
                "bge-reranker-v2-m3 requires transformers and torch."
            ) from exc

        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.device = device if device != "cpu" and torch.cuda.is_available() else "cpu"
        if self.device != "cpu":
            self.model = self.model.to(self.device)
        self.model.eval()
        self.batch_size = batch_size

    async def score_pairs(self, query: str, documents: list[str]) -> list[float]:
        return await asyncio.to_thread(self._score_pairs_sync, query, documents)

    def _score_pairs_sync(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        scores: list[float] = []
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start : start + self.batch_size]
            pairs = [(query, document) for document in batch]
            encoded = self.tokenizer(
                pairs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            encoded = {
                key: value.to(self.device) if hasattr(value, "to") and self.device != "cpu" else value
                for key, value in encoded.items()
            }

            with self._torch.no_grad():
                logits = self.model(**encoded, return_dict=True).logits.view(-1).float()

            scores.extend(logits.cpu().tolist())
        return scores


def build_reranker(settings: Settings) -> LexicalReranker | BgeRerankerService:
    engine = settings.rag_reranker_engine.strip().lower()
    if engine == "lexical":
        return LexicalReranker()
    if engine == "bge-reranker-v2-m3":
        return BgeRerankerService(
            model_name=settings.rag_reranker_model,
            device=settings.rag_reranker_device,
            batch_size=settings.rag_reranker_batch_size,
        )
    raise ValueError(f"Unsupported reranker engine: {settings.rag_reranker_engine}")


class DashScopeChatCompletionsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def complete(self, messages: list[dict[str, str]]) -> str:
        if not self.settings.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured.")

        url = f"{self.settings.dashscope_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.dashscope_model,
            "messages": messages,
            "temperature": self.settings.rag_generation_temperature,
            "max_tokens": self.settings.rag_generation_max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds * 3) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts = [str(item.get("text", "")).strip() for item in content if isinstance(item, dict)]
            return "".join(parts).strip()

        raise RuntimeError("DashScope response content is empty.")


class ScenicRAGService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.vector_store = KnowledgeVectorStore(self.settings)
        self.embedder = build_embedding_service(self.settings)
        self._reranker = None
        self._reranker_error: str | None = None
        self.llm = DashScopeChatCompletionsClient(self.settings)
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是一名景区 AI 数字导览员。"
                        "你必须仅依据提供的参考资料回答问题，不能编造资料中没有的信息。"
                        "如果资料不足以支持回答，请明确说明“根据当前景区知识库，暂时无法确认”。"
                        "回答要简洁、自然、适合游客咨询场景。"
                        "如果用户的问题明显超出景区知识范围，也要礼貌拒答并引导回景区相关问题。"
                    ),
                ),
                (
                    "human",
                    (
                        "导览员人设：{persona}\n\n"
                        "用户问题：{question}\n\n"
                        "参考资料：\n{context}\n\n"
                        "请给出一段面向游客的中文回答。"
                        "不要直接说“根据上下文”。"
                        "如果可以回答，优先先给结论，再补充细节。"
                    ),
                ),
            ]
        )

    async def answer(self, question: str, persona: str | None = None) -> RAGAnswer:
        query = normalize_question(question)
        if not query:
            return self._refuse("我刚刚没有听清，你可以再说一次吗？")

        candidates = await self.retrieve(query)
        if not self._has_grounded_context(query, candidates):
            return self._refuse(
                "根据当前景区知识库，暂时无法确认这个问题。你可以继续问我景点、历史、游览路线或参观建议。"
            )

        selected = candidates[: self.settings.rag_context_docs]
        context = self._format_context(selected)

        used_llm = False
        if self.settings.dashscope_api_key:
            try:
                answer_body = await self._generate_with_llm(
                    question=query,
                    persona=persona or self.settings.default_avatar_persona,
                    context=context,
                )
                used_llm = True
            except Exception:
                answer_body = self._build_extractive_answer(query, selected)
        else:
            answer_body = self._build_extractive_answer(query, selected)

        answer_body = sanitize_answer(answer_body)
        if not answer_body:
            return self._refuse(
                "根据当前景区知识库，暂时无法确认这个问题。你也可以换个更具体的问法。"
            )

        display_text = append_citations(answer_body, selected)
        confidence = round(selected[0].rerank_score, 4) if selected else 0.0
        return RAGAnswer(
            answer_text=display_text,
            spoken_text=answer_body,
            sources=selected,
            confidence=confidence,
            used_llm=used_llm,
        )

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        query_embedding = self.embedder.embed_documents([question])[0]
        raw_hits = self.vector_store.query_chunks(
            query_embedding=query_embedding,
            n_results=self.settings.rag_retrieval_top_k,
        )
        if not raw_hits:
            return []

        reranker = self._get_reranker()
        documents = [
            f"{hit.metadata.get('title', '')}\n{hit.metadata.get('category', '')}\n{hit.text}"
            for hit in raw_hits
        ]
        try:
            rerank_scores = await reranker.score_pairs(question, documents)
        except Exception as exc:
            self._reranker_error = str(exc)
            reranker = LexicalReranker()
            rerank_scores = await reranker.score_pairs(question, documents)

        ranked: list[RetrievedChunk] = []
        for index, hit in enumerate(raw_hits):
            metadata = hit.metadata
            retrieval_score = distance_to_similarity(hit.distance)
            rerank_score = rerank_scores[index] if index < len(rerank_scores) else retrieval_score
            ranked.append(
                RetrievedChunk(
                    chunk_id=hit.chunk_id,
                    doc_id=str(metadata.get("doc_id", "")),
                    filename=str(metadata.get("filename", "unknown")),
                    title=str(metadata.get("title", metadata.get("filename", "unknown"))),
                    category=str(metadata.get("category", "scenery")),
                    text=hit.text,
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    retrieval_score=retrieval_score,
                    rerank_score=rerank_score,
                )
            )

        ranked.sort(
            key=lambda item: (
                item.rerank_score,
                item.retrieval_score,
                -item.chunk_index,
            ),
            reverse=True,
        )
        return ranked[: self.settings.rag_rerank_top_n]

    def _get_reranker(self) -> LexicalReranker | BgeRerankerService:
        if self._reranker is not None:
            return self._reranker
        if self._reranker_error is not None:
            return LexicalReranker()

        try:
            self._reranker = build_reranker(self.settings)
        except Exception as exc:
            self._reranker_error = str(exc)
            self._reranker = LexicalReranker()
        return self._reranker

    async def _generate_with_llm(self, question: str, persona: str, context: str) -> str:
        messages = [
            {"role": message.type, "content": message.content}
            for message in self.prompt.format_messages(
                persona=persona,
                question=question,
                context=context,
            )
        ]
        return await self.llm.complete(messages)

    def _build_extractive_answer(self, question: str, sources: list[RetrievedChunk]) -> str:
        query_tokens = meaningful_tokens(question)
        intent_tokens = intent_keywords(question)
        scored_sentences: list[tuple[float, str]] = []

        for source in sources:
            sentences = split_sentences(source.text)
            for sentence in sentences:
                sentence = normalize_sentence_candidate(sentence, source.title)
                if len(sentence) < 8:
                    continue
                if not re.search(r"[，。！？!?；;：:]", sentence) and len(sentence) <= 18:
                    continue
                overlap = sum(1 for token in query_tokens if token in sentence)
                intent_hits = sum(1 for token in intent_tokens if token in sentence or token in source.title)
                score = (
                    overlap * 0.18
                    + intent_hits * 0.45
                    + max(source.rerank_score, source.retrieval_score)
                )
                if source.category in {"history", "route", "facility"}:
                    score += 0.08
                scored_sentences.append((score, sentence))

        scored_sentences.sort(key=lambda item: item[0], reverse=True)
        chosen: list[str] = []
        seen = set()
        for _, sentence in scored_sentences:
            normalized = sentence.strip()
            if normalized in seen:
                continue
            chosen.append(normalized)
            seen.add(normalized)
            if len(chosen) >= 2:
                break

        if not chosen and sources:
            chosen.append(truncate_text(sources[0].text, 140))

        if not chosen:
            return ""

        answer = " ".join(chosen)
        if not answer.startswith(("根据", "景区", "灵山")):
            answer = f"根据景区资料，{answer}"
        return answer

    def _format_context(self, sources: list[RetrievedChunk]) -> str:
        blocks: list[str] = []
        for index, source in enumerate(sources, start=1):
            blocks.append(
                "\n".join(
                    [
                        f"[{index}] 标题：{source.title}",
                        f"文件：{source.filename}",
                        f"分类：{source.category}",
                        f"相关度：retrieval={source.retrieval_score:.3f}, rerank={source.rerank_score:.3f}",
                        f"内容：{truncate_text(source.text, self.settings.rag_context_chars_per_chunk)}",
                    ]
                )
            )
        return "\n\n".join(blocks)

    def _has_grounded_context(self, question: str, sources: list[RetrievedChunk]) -> bool:
        if not sources:
            return False

        query_tokens = meaningful_tokens(question)
        best = sources[0]
        overlap_found = False

        for source in sources:
            overlap = sum(1 for token in query_tokens if token in source.text or token in source.title)
            if overlap > 0:
                overlap_found = True
                break

        if overlap_found:
            return True

        return best.retrieval_score >= max(self.settings.rag_min_retrieval_score, 0.55)

    def _refuse(self, message: str) -> RAGAnswer:
        return RAGAnswer(
            answer_text=message,
            spoken_text=message,
            sources=[],
            confidence=0.0,
            used_llm=False,
        )


def normalize_question(text: str) -> str:
    return " ".join(text.strip().split())


def meaningful_tokens(text: str) -> set[str]:
    normalized = text.lower()
    tokens = {token for token in re.findall(r"[a-z0-9]+", normalized)}

    for block in re.findall("[\u4e00-\u9fff]{2,}", text):
        if block not in STOP_TOKENS:
            tokens.add(block)
        for size in (2, 3, 4):
            for index in range(0, max(len(block) - size + 1, 0)):
                token = block[index : index + size]
                if token not in STOP_TOKENS:
                    tokens.add(token)

    return {token for token in tokens if token and token not in STOP_TOKENS}


def intent_keywords(text: str) -> set[str]:
    hints: set[str] = set()
    if any(token in text for token in ("历史", "故事", "由来", "文化", "渊源", "兴衰")):
        hints.update({"历史", "故事", "文化", "由来", "渊源", "兴衰", "千年"})
    if any(token in text for token in ("路线", "推荐", "先去", "怎么逛", "游览")):
        hints.update({"路线", "游览", "推荐", "核心景点", "参观", "顺序"})
    if any(token in text for token in ("时间", "营业", "开放", "几点")):
        hints.update({"开放时间", "营业时间", "开放", "几点", "时段"})
    if any(token in text for token in ("停车", "交通", "酒店", "厕所", "导游", "门票")):
        hints.update({"停车", "交通", "酒店", "厕所", "导游", "门票"})
    return hints


def split_sentences(text: str) -> list[str]:
    parts = [item.strip() for item in SENTENCE_RE.split(text) if item.strip()]
    return parts if parts else [text]


def distance_to_similarity(distance: float | None) -> float:
    if distance is None:
        return 0.0
    similarity = 1.0 - float(distance)
    return max(-1.0, min(1.0, similarity))


def truncate_text(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def sanitize_answer(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(参考资料[:：].*)$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_sentence_candidate(sentence: str, title: str) -> str:
    cleaned = " ".join(sentence.strip().split())
    if title:
        cleaned = cleaned.replace(title, "").strip(" ：:")

    if " " in cleaned:
        prefix, suffix = cleaned.split(" ", 1)
        if len(prefix) <= 14 and not re.search(r"[，。！？!?；;：:（）()]", prefix):
            cleaned = suffix.strip()

    return cleaned.strip(" ：:")


def append_citations(answer: str, sources: list[RetrievedChunk]) -> str:
    if not sources:
        return answer

    lines = [answer, "", "参考资料："]
    used = set()
    for index, source in enumerate(sources, start=1):
        key = (source.filename, source.title)
        if key in used:
            continue
        used.add(key)
        lines.append(f"[{index}] {source.title}（{source.filename}）")
    return "\n".join(lines)


@lru_cache
def get_rag_service() -> ScenicRAGService:
    return ScenicRAGService(get_settings())
