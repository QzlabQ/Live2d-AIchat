from __future__ import annotations

import asyncio
import json
import math
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from time import perf_counter

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
ROUTE_PLAN_RE = re.compile(
    r"(?:(?P<label>[^\n：:]{2,40}路线(?:（[^）]+）)?)\s*\n)?路线规划[:：]\s*(?P<plan>[^\n]+)"
)
TIME_RANGE_RE = re.compile(r"(?P<time>\d{1,2}:\d{2}(?:\s*[-~至到]\s*\d{1,2}:\d{2})?)")
SPOKEN_GUIDANCE_RE = re.compile(
    r"用(?P<style>[^。！？!?；;]{0,36}?)(?:语言|语气|方式|口吻|话术)"
    r"(?:来)?(?:讲述|介绍|说明|解释|表达)(?P<object>[^。！？!?；;，,、]{0,80})"
)
VISITOR_PEDAGOGY_RE = re.compile(
    r"[，,、]\s*(?:让|帮助|引导|带领|激发|方便)(?:游客|孩子|小朋友|大家|观众|用户)"
    r"[^。！？!?；;]*"
)
GENERIC_TTS_OBJECTS = {"", "这段内容", "这句话", "一句话", "内容", "文本", "回答"}
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
OVERVIEW_SPOT_PRIORITY = (
    "灵山大佛",
    "灵山梵宫",
    "九龙灌浴",
    "五印坛城",
    "祥符禅寺",
    "佛手广场",
    "百子戏弥勒",
    "灵山精舍",
    "曼飞龙塔",
)
OUT_OF_DOMAIN_HINTS = (
    "天气",
    "下雨",
    "气温",
    "温度",
    "微积分",
    "导数",
    "积分",
    "线性代数",
    "股票",
    "基金",
    "高考",
    "考研",
)


def normalize_response_language(value: str | None) -> str:
    normalized = str(value or "zh").strip().lower()
    return "en" if normalized.startswith("en") else "zh"


def localized_text(response_language: str | None, zh_text: str, en_text: str) -> str:
    return en_text if normalize_response_language(response_language) == "en" else zh_text


def build_answer_language_instruction(response_language: str | None) -> str:
    if normalize_response_language(response_language) == "en":
        return (
            "Please answer in natural spoken English for visitors. "
            "Do not switch to Chinese unless the user explicitly asks for Chinese."
        )
    return "请给出一段面向游客的中文回答。除非用户明确要求其他语言，否则不要切换成英文。"


def build_humanized_language_instruction(response_language: str | None) -> str:
    if normalize_response_language(response_language) == "en":
        return (
            "Your job is not to copy the source material. "
            "Rewrite it into natural, concise spoken English that visitors can understand directly."
        )
    return "你的任务不是复述资料，而是把资料整理成游客能直接听懂的自然中文。"


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
    reply_kind: str = "answer"
    needs_followup: bool = False
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    confidence_note: str = "confirmed"


@dataclass(slots=True)
class PreparedRAGAnswer:
    answer_text: str
    spoken_text: str
    sources: list[RetrievedChunk]
    confidence: float
    used_llm: bool
    llm_messages: list[dict[str, str]] | None = None
    fallback_text: str = ""

    reply_kind: str = "answer"
    needs_followup: bool = False
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    confidence_note: str = "confirmed"
    metrics: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class RAGReplyDecision:
    reply_kind: str = "answer"
    needs_followup: bool = False
    spoken_answer: str = ""
    followup_question: str = ""
    missing_slots: list[str] = field(default_factory=list)
    used_source_indexes: list[int] = field(default_factory=list)
    confidence_note: str = "confirmed"


@dataclass(slots=True)
class ClarificationResolution:
    continues_clarification: bool
    resolved_question: str


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
        requested_device = str(device or "cpu").strip()
        wants_cuda = requested_device.lower().startswith("cuda")
        self.device = requested_device if wants_cuda and torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        model_kwargs: dict[str, object] = {}
        if self.device != "cpu":
            model_kwargs["torch_dtype"] = torch.float16
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name, **model_kwargs)
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

            with self._torch.inference_mode():
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
            "enable_thinking": self.settings.dashscope_enable_thinking,
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
        text = self._extract_content_text(content)
        if text:
            return text.strip()

        raise RuntimeError("DashScope response content is empty.")

    async def stream_complete(self, messages: list[dict[str, str]]):
        if not self.settings.dashscope_api_key:
            raise RuntimeError("DASHSCOPE_API_KEY is not configured.")

        url = f"{self.settings.dashscope_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.dashscope_model,
            "messages": messages,
            "temperature": self.settings.rag_generation_temperature,
            "max_tokens": self.settings.rag_generation_max_tokens,
            "stream": True,
            "enable_thinking": self.settings.dashscope_enable_thinking,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data = line[5:].strip()
                    if data == "[DONE]":
                        break

                    payload_obj = json.loads(data)
                    choices = payload_obj.get("choices")
                    if not isinstance(choices, list):
                        continue

                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta")
                        if not isinstance(delta, dict):
                            continue

                        text = self._extract_content_text(delta.get("content"))
                        if text:
                            yield text

    def _extract_content_text(self, content: object) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts = [str(item.get("text", "")) for item in content if isinstance(item, dict)]
            return "".join(parts)

        return ""


class ScenicRAGService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.vector_store = KnowledgeVectorStore(self.settings)
        self.embedder = build_embedding_service(self.settings)
        self._retrieve_metrics: ContextVar[dict[str, int] | None] = ContextVar(
            "rag_retrieve_metrics",
            default=None,
        )
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
                        "{language_instruction}"
                        "不要直接说“根据上下文”。"
                        "如果可以回答，优先先给结论，再补充细节。"
                    ),
                ),
            ]
        )

    async def answer(
        self,
        question: str,
        persona: str | None = None,
        response_language: str | None = None,
    ) -> RAGAnswer:
        prepared = await self.prepare_stream_answer(
            question,
            persona=persona,
            response_language=response_language,
        )
        if prepared.llm_messages:
            try:
                answer_body = await self.llm.complete(prepared.llm_messages)
            except Exception:
                answer_body = prepared.fallback_text
        else:
            answer_body = prepared.answer_text

        answer_body = sanitize_answer(answer_body)
        if not answer_body:
            return self._refuse(
                "鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘涔熷彲浠ユ崲涓洿鍏蜂綋鐨勯棶娉曘€?"
            )

        display_text = append_citations(answer_body, prepared.sources)
        return RAGAnswer(
            answer_text=display_text,
            spoken_text=answer_body,
            sources=prepared.sources,
            confidence=prepared.confidence,
            used_llm=prepared.used_llm,
        )

        query = normalize_question(question)
        if not query:
            return self._refuse("我刚刚没有听清，你可以再说一次吗？")
        if is_out_of_domain_question(query):
            return self._refuse(
                "根据当前景区知识库，暂时无法确认这个问题。你可以继续问我景点、历史、游览路线或参观建议。"
            )

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
                    response_language=response_language,
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

    async def prepare_stream_answer(
        self,
        question: str,
        persona: str | None = None,
        response_language: str | None = None,
    ) -> PreparedRAGAnswer:
        query = normalize_question(question)
        if not query:
            return PreparedRAGAnswer(
                answer_text="鎴戝垰鍒氭病鏈夊惉娓咃紝浣犲彲浠ュ啀璇翠竴娆″悧锛?",
                spoken_text="鎴戝垰鍒氭病鏈夊惉娓咃紝浣犲彲浠ュ啀璇翠竴娆″悧锛?",
                sources=[],
                confidence=0.0,
                used_llm=False,
            )
        if is_out_of_domain_question(query):
            return PreparedRAGAnswer(
                answer_text="鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘鍙互缁х画闂垜鏅偣銆佸巻鍙层€佹父瑙堣矾绾挎垨鍙傝寤鸿銆?",
                spoken_text="鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘鍙互缁х画闂垜鏅偣銆佸巻鍙层€佹父瑙堣矾绾挎垨鍙傝寤鸿銆?",
                sources=[],
                confidence=0.0,
                used_llm=False,
            )

        candidates = await self.retrieve(query)
        if not self._has_grounded_context(query, candidates):
            return PreparedRAGAnswer(
                answer_text="鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘鍙互缁х画闂垜鏅偣銆佸巻鍙层€佹父瑙堣矾绾挎垨鍙傝寤鸿銆?",
                spoken_text="鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘鍙互缁х画闂垜鏅偣銆佸巻鍙层€佹父瑙堣矾绾挎垨鍙傝寤鸿銆?",
                sources=[],
                confidence=0.0,
                used_llm=False,
            )

        selected = candidates[: self.settings.rag_context_docs]
        confidence = round(selected[0].rerank_score, 4) if selected else 0.0
        context = self._format_context(selected)
        fallback_text = sanitize_answer(self._build_extractive_answer(query, selected))
        if not fallback_text:
            fallback_text = "鏍规嵁褰撳墠鏅尯鐭ヨ瘑搴擄紝鏆傛椂鏃犳硶纭杩欎釜闂銆備綘涔熷彲浠ユ崲涓洿鍏蜂綋鐨勯棶娉曘€?"

        if self.settings.dashscope_api_key:
            return PreparedRAGAnswer(
                answer_text="",
                spoken_text="",
                sources=selected,
                confidence=confidence,
                used_llm=True,
                llm_messages=self._build_llm_messages(
                    question=query,
                    persona=persona or self.settings.default_avatar_persona,
                    response_language=response_language,
                    context=context,
                ),
                fallback_text=fallback_text,
            )

        return PreparedRAGAnswer(
            answer_text=fallback_text,
            spoken_text=fallback_text,
            sources=selected,
            confidence=confidence,
            used_llm=False,
        )

    async def retrieve(self, question: str) -> list[RetrievedChunk]:
        metrics = {
            "rag_embed_ms": 0,
            "rag_vector_search_ms": 0,
            "rag_retrieve_ms": 0,
            "rag_rerank_ms": 0,
            "rag_retrieve_total_ms": 0,
        }

        embed_started_at = perf_counter()
        query_embedding = self.embedder.embed_documents([question])[0]
        metrics["rag_embed_ms"] = int((perf_counter() - embed_started_at) * 1000)

        vector_search_started_at = perf_counter()
        raw_hits = self.vector_store.query_chunks(
            query_embedding=query_embedding,
            n_results=self.settings.rag_retrieval_top_k,
        )
        metrics["rag_vector_search_ms"] = int((perf_counter() - vector_search_started_at) * 1000)
        metrics["rag_retrieve_ms"] = metrics["rag_embed_ms"] + metrics["rag_vector_search_ms"]
        if not raw_hits:
            metrics["rag_retrieve_total_ms"] = metrics["rag_retrieve_ms"]
            self._retrieve_metrics.set(metrics)
            return []

        rerank_started_at = perf_counter()
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
        metrics["rag_rerank_ms"] = int((perf_counter() - rerank_started_at) * 1000)
        metrics["rag_retrieve_total_ms"] = metrics["rag_retrieve_ms"] + metrics["rag_rerank_ms"]

        ranked: list[RetrievedChunk] = []
        intent = detect_query_intent(question)
        for index, hit in enumerate(raw_hits):
            metadata = hit.metadata
            retrieval_score = distance_to_similarity(hit.distance)
            rerank_score = rerank_scores[index] if index < len(rerank_scores) else retrieval_score
            rerank_score += structured_rank_bonus(
                intent=intent,
                text=hit.text,
                title=str(metadata.get("title", metadata.get("filename", ""))),
                category=str(metadata.get("category", "scenery")),
            )
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
        self._retrieve_metrics.set(metrics)
        return limit_ranked_sources(ranked, self.settings.rag_rerank_top_n)

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

    async def _generate_with_llm(
        self,
        question: str,
        persona: str,
        response_language: str | None,
        context: str,
    ) -> str:
        messages = self._build_llm_messages(
            question=question,
            persona=persona,
            response_language=response_language,
            context=context,
        )
        return await self.llm.complete(messages)

    def _build_llm_messages(
        self,
        question: str,
        persona: str,
        response_language: str | None,
        context: str,
    ) -> list[dict[str, str]]:
        return [
            {"role": message.type, "content": message.content}
            for message in self.prompt.format_messages(
                persona=persona,
                question=question,
                language_instruction=build_answer_language_instruction(response_language),
                context=context,
            )
        ]

    def _build_extractive_answer(self, question: str, sources: list[RetrievedChunk]) -> str:
        structured_answer = build_structured_answer(question, sources)
        if structured_answer:
            return structured_answer

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
            cleaned_source_text = sanitize_source_text_for_answer(source.text)
            blocks.append(
                "\n".join(
                    [
                        f"[{index}] 标题：{source.title}",
                        f"文件：{source.filename}",
                        f"分类：{source.category}",
                        f"相关度：retrieval={source.retrieval_score:.3f}, rerank={source.rerank_score:.3f}",
                        f"内容：{truncate_text(cleaned_source_text, self.settings.rag_context_chars_per_chunk)}",
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


def detect_query_intent(text: str) -> str:
    if any(token in text for token in ("几点", "营业", "演出时间", "开放时间", "场次")):
        return "schedule"
    if any(token in text for token in ("什么时候", "哪一年", "哪一期", "何时", "开光", "奠基", "开放")):
        return "timeline"
    if any(token in text for token in ("路线", "推荐", "先去", "怎么逛", "游览", "第一次来")):
        return "route"
    if any(token in text for token in ("核心景点", "有哪些景点", "必看", "主要景点", "代表景点")):
        return "overview"
    if any(token in text for token in ("历史", "故事", "由来", "文化", "渊源", "兴衰")):
        return "history"
    if any(token in text for token in ("停车", "交通", "酒店", "厕所", "导游", "门票")):
        return "facility"
    return "general"


def build_structured_answer(question: str, sources: list[RetrievedChunk]) -> str:
    intent = detect_query_intent(question)
    if intent == "timeline":
        return build_timeline_answer(question, sources)
    if intent == "route":
        return build_route_answer(question, sources)
    if intent == "overview":
        return build_overview_answer(sources)
    if intent == "schedule":
        return build_schedule_answer(sources)
    return ""


def build_route_answer(question: str, sources: list[RetrievedChunk]) -> str:
    route_candidates: list[tuple[float, str, str]] = []
    for source in sources:
        for label, plan in extract_route_plans(source.text):
            score = score_route_plan(question, label, plan, source)
            route_candidates.append((score, label, normalize_route_text(plan)))

    if not route_candidates:
        return ""

    _, label, plan = max(route_candidates, key=lambda item: item[0])
    if any(token in question for token in ("亲子", "家庭", "孩子")):
        prefix = "如果是亲子或家庭出游，推荐这条轻松路线。路线规划："
    elif any(token in question for token in ("自然", "风光", "拍照")):
        prefix = "如果你更偏好自然风光，可以这样走。路线规划："
    elif any(token in question for token in ("历史", "文化", "典故")):
        prefix = "如果你想重点看历史文化，推荐这条深度路线。路线规划："
    elif any(token in question for token in ("第一次", "初次")):
        prefix = "如果你是第一次来，建议优先走核心景点主线。路线规划："
    else:
        prefix = "可以参考这条游览路线。路线规划："

    answer = f"{prefix}{plan}"
    if label and "第一次" in question and "历史文化" in label:
        answer += " 这条路线覆盖了大照壁、祥符禅寺、灵山大佛和梵宫等代表性景点。"
    return answer


def build_overview_answer(sources: list[RetrievedChunk]) -> str:
    spot_names = collect_spot_names(sources)
    if len(spot_names) < 3:
        return ""

    primary = "、".join(spot_names[:5])
    focus = "、".join(spot_names[:3])
    return f"灵山胜境的核心景点通常包括{primary}。如果时间有限，可以优先看{focus}。"


def build_schedule_answer(sources: list[RetrievedChunk]) -> str:
    candidates: list[str] = []
    for source in sources:
        for line in split_lines(source.text):
            normalized = normalize_sentence_candidate(line, source.title)
            if len(normalized) < 6:
                continue
            if TIME_RANGE_RE.search(normalized) or any(
                token in normalized for token in ("开放时间", "营业时间", "演出时间", "开放", "场次")
            ):
                candidates.append(normalized)

    picked = dedupe_preserve_order(candidates)[:2]
    if not picked:
        return ""
    return " ".join(picked)


def build_timeline_answer(question: str, sources: list[RetrievedChunk]) -> str:
    relevant_lines: list[str] = []
    question_tokens = meaningful_tokens(question)
    for source in sources:
        for line in split_sentences(source.text):
            normalized = normalize_sentence_candidate(line, source.title)
            if len(normalized) < 8:
                continue
            if not re.search(r"\d{4}年|[一二三]期工程|奠基|开光|开放", normalized):
                continue
            overlap = sum(1 for token in question_tokens if token in normalized)
            if overlap == 0 and not any(token in normalized for token in ("一期", "二期", "三期", "开放", "开光")):
                continue
            relevant_lines.append(normalized)

    picked = dedupe_preserve_order(relevant_lines)[:2]
    if not picked:
        return ""
    answer = " ".join(picked)
    if not answer.startswith(("根据", "灵山")):
        answer = f"根据景区资料，{answer}"
    return answer


def extract_route_plans(text: str) -> list[tuple[str, str]]:
    plans: list[tuple[str, str]] = []
    for match in ROUTE_PLAN_RE.finditer(text):
        label = normalize_route_text(match.group("label") or "")
        plan = normalize_route_text(match.group("plan") or "")
        if plan:
            plans.append((label, plan))
    return plans


def score_route_plan(question: str, label: str, plan: str, source: RetrievedChunk) -> float:
    score = max(source.rerank_score, source.retrieval_score)
    lowered = f"{label}\n{plan}"
    if source.category == "route":
        score += 0.3
    if "→" in plan:
        score += 0.2
    if any(token in question for token in ("亲子", "家庭", "孩子")) and "亲子" in lowered:
        score += 1.0
    if any(token in question for token in ("历史", "文化", "典故")) and "历史文化" in lowered:
        score += 1.0
    if any(token in question for token in ("自然", "风光", "拍照")) and "自然风光" in lowered:
        score += 1.0
    if any(token in question for token in ("第一次", "初次")):
        if "历史文化" in lowered:
            score += 0.5
        if any(token in plan for token in ("灵山大佛", "灵山梵宫", "九龙灌浴")):
            score += 0.4
    return score


def collect_spot_names(sources: list[RetrievedChunk]) -> list[str]:
    available: set[str] = set()
    ordered_names: list[str] = []
    seen = set()
    for source in sources:
        for name in extract_spot_names_from_text(source.text):
            if name == "灵山胜境":
                continue
            available.add(name)
            if name not in seen:
                seen.add(name)
                ordered_names.append(name)

    prioritized = [name for name in OVERVIEW_SPOT_PRIORITY if name in available]
    extras = [name for name in ordered_names if name not in prioritized]
    return prioritized + extras


def extract_spot_names_from_text(text: str) -> list[str]:
    generic_names = {
        "项目",
        "详细信息",
        "基本数据",
        "建造工艺",
        "佛教意义",
        "最佳体验",
        "核心艺术",
        "特色体验",
        "文化地位",
        "景区名称",
        "景点名称",
        "路线规划",
        "讲解重点",
        "数据集说明",
        "其他特色景点",
        "实用游览贴士",
    }
    candidates: list[str] = []
    for line in split_lines(text):
        cleaned = line.strip().strip("：:")
        if not cleaned or cleaned in generic_names:
            continue
        if cleaned.startswith("LS-"):
            continue
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{2,16}", cleaned):
            candidates.append(cleaned)
            continue
        heading = re.match(r"(?P<name>[\u4e00-\u9fffA-Za-z0-9]{2,16})[:：]", cleaned)
        if heading and heading.group("name") not in generic_names:
            candidates.append(heading.group("name"))
    return dedupe_preserve_order(candidates)


def structured_rank_bonus(intent: str, text: str, title: str, category: str) -> float:
    bonus = 0.0
    if intent == "route":
        if category == "route":
            bonus += 0.22
        if "路线规划" in text:
            bonus += 0.5
        if "→" in text:
            bonus += 0.18
    elif intent == "overview":
        if "核心景点" in text or "特色景点" in text:
            bonus += 0.32
        bonus += min(len(extract_spot_names_from_text(text)), 5) * 0.08
    elif intent == "timeline":
        if re.search(r"\d{4}年|[一二三]期工程|奠基|开光|正式开放", text):
            bonus += 0.4
        if any(token in text for token in ("1994年", "1997年", "2003年", "2009年")):
            bonus += 0.18
    elif intent == "schedule":
        if TIME_RANGE_RE.search(text):
            bonus += 0.28
        if any(token in text for token in ("开放时间", "营业时间", "演出时间", "开放", "场次")):
            bonus += 0.2
    elif intent == "history":
        if category == "history":
            bonus += 0.16
        if any(token in text for token in ("玄奘", "贞观", "祥符禅寺", "1994年", "1997年")):
            bonus += 0.22
    elif intent == "facility":
        if any(token in text for token in ("停车", "交通", "酒店", "厕所", "导游", "门票")):
            bonus += 0.24
    if "参考资料" in title:
        bonus -= 0.05
    return bonus


def limit_ranked_sources(ranked: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    if len(ranked) <= limit:
        return ranked

    selected: list[RetrievedChunk] = []
    remaining: list[RetrievedChunk] = []
    seen_filenames = set()

    for item in ranked:
        if item.filename not in seen_filenames and len(selected) < limit:
            selected.append(item)
            seen_filenames.add(item.filename)
        else:
            remaining.append(item)

    for item in remaining:
        if len(selected) >= limit:
            break
        selected.append(item)

    return selected


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def normalize_route_text(text: str) -> str:
    return " ".join(text.strip().split())


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def is_out_of_domain_question(text: str) -> bool:
    return any(token in text for token in OUT_OF_DOMAIN_HINTS)


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


def strip_spoken_guidance(text: str) -> str:
    def replace_directive(match: re.Match[str]) -> str:
        obj = match.group("object").strip(" ：:，,、")
        if obj in GENERIC_TTS_OBJECTS:
            return ""
        return obj

    cleaned = text.replace("<|endofprompt|>", "")
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = SPOKEN_GUIDANCE_RE.sub(replace_directive, cleaned)
        cleaned = VISITOR_PEDAGOGY_RE.sub("", cleaned)
    return cleaned


def sanitize_source_text_for_answer(text: str) -> str:
    lines: list[str] = []
    for line in split_lines(text):
        cleaned = sanitize_answer(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines) or sanitize_answer(text)


def sanitize_answer(text: str) -> str:
    cleaned = text.strip()
    cleaned = strip_spoken_guidance(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"(参考资料[:：].*)$", "", cleaned, flags=re.IGNORECASE)
    if re.fullmatch(r"[。！？!?；;，,、.:\s：]+", cleaned):
        return ""
    return cleaned.strip()


def normalize_sentence_candidate(sentence: str, title: str) -> str:
    cleaned = " ".join(sentence.strip().split())
    if title:
        cleaned = cleaned.replace(title, "").strip(" ：:")

    if " " in cleaned:
        prefix, suffix = cleaned.split(" ", 1)
        if len(prefix) <= 14 and not re.search(r"[，。！？!?；;：:（）()]", prefix):
            cleaned = suffix.strip()

    return sanitize_answer(cleaned).strip(" ：:")


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


from app.services.rag_humanized import (  # noqa: E402
    ClarificationResolver,
    HumanizedScenicRAGService,
)

ScenicRAGService = HumanizedScenicRAGService


@lru_cache
def get_rag_service() -> ScenicRAGService:
    return ScenicRAGService(get_settings())
