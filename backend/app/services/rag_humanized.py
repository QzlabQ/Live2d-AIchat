from __future__ import annotations

import json
import re
from time import perf_counter

import app.services.rag as legacy_rag
from app.core.config import Settings


def parse_json_object(raw_text: str) -> dict[str, object] | None:
    cleaned = raw_text.strip()
    if not cleaned:
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()
    elif not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def sanitize_slot_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or list(fallback)


def sanitize_index_list(value: object, fallback: list[int]) -> list[int]:
    if not isinstance(value, list):
        return list(fallback)
    indexes: list[int] = []
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if index > 0:
            indexes.append(index)
    return indexes or list(fallback)


class ClarificationResolver:
    def __init__(
        self,
        settings: Settings,
        llm: legacy_rag.DashScopeChatCompletionsClient | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm or legacy_rag.DashScopeChatCompletionsClient(settings)

    async def resolve(
        self,
        *,
        original_question: str,
        assistant_followup_question: str,
        user_reply: str,
    ) -> legacy_rag.ClarificationResolution:
        normalized_reply = legacy_rag.normalize_question(user_reply)
        if not normalized_reply:
            return legacy_rag.ClarificationResolution(False, legacy_rag.normalize_question(user_reply))

        merged = self._resolve_heuristically(
            original_question=original_question,
            assistant_followup_question=assistant_followup_question,
            user_reply=normalized_reply,
        )
        if merged is not None:
            return legacy_rag.ClarificationResolution(True, merged)

        if self.settings.dashscope_api_key:
            try:
                llm_resolution = await self._resolve_with_llm(
                    original_question=original_question,
                    assistant_followup_question=assistant_followup_question,
                    user_reply=normalized_reply,
                )
                if llm_resolution is not None:
                    return llm_resolution
            except Exception:
                pass

        return legacy_rag.ClarificationResolution(False, normalized_reply)

    def _resolve_heuristically(
        self,
        *,
        original_question: str,
        assistant_followup_question: str,
        user_reply: str,
    ) -> str | None:
        reply = legacy_rag.normalize_question(user_reply)
        original = legacy_rag.normalize_question(original_question)
        followup = legacy_rag.normalize_question(assistant_followup_question)
        if not reply:
            return None

        combined_tokens = legacy_rag.meaningful_tokens(f"{original} {followup}")
        reply_tokens = legacy_rag.meaningful_tokens(reply)
        overlap = combined_tokens.intersection(reply_tokens)

        schedule_scope_map = {
            "景区整体": "景区整体开放时间是什么时候？",
            "景区": "景区整体开放时间是什么时候？",
            "商铺": "商铺营业时间是什么时候？",
            "店铺": "商铺营业时间是什么时候？",
            "夜游": "夜游时间是什么时候？",
            "演出": "演出时间是什么时候？",
            "餐饮": "餐饮营业时间是什么时候？",
        }
        if "开放时间" in original or "营业时间" in original:
            for token, merged in schedule_scope_map.items():
                if token in reply:
                    return merged

        route_profile_tokens = ("亲子", "家庭", "孩子", "半日", "半天", "夜游", "拍照", "老人", "历史", "文化")
        if any(token in original for token in ("怎么逛", "路线", "游览", "推荐")):
            if any(token in reply for token in route_profile_tokens):
                return f"{original}，补充信息：{reply}"

        if overlap and len(reply) <= 24:
            return f"{original}，补充信息：{reply}"

        return None

    async def _resolve_with_llm(
        self,
        *,
        original_question: str,
        assistant_followup_question: str,
        user_reply: str,
    ) -> legacy_rag.ClarificationResolution | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是景区导览助手的澄清归并器。"
                    "判断用户这句话是不是在补充回答上一轮追问。"
                    "只输出 JSON。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"原问题：{original_question}\n"
                    f"上一轮追问：{assistant_followup_question}\n"
                    f"用户补充：{user_reply}\n\n"
                    '输出格式：{"continues_clarification": true, "resolved_question": "合并后的完整问题"}'
                ),
            },
        ]
        raw = await self.llm.complete(messages)
        payload = parse_json_object(raw)
        if not payload:
            return None
        return legacy_rag.ClarificationResolution(
            continues_clarification=bool(payload.get("continues_clarification")),
            resolved_question=legacy_rag.normalize_question(
                str(payload.get("resolved_question", user_reply))
            ),
        )


class HumanizedScenicRAGService(legacy_rag.ScenicRAGService):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        self.clarification_resolver = ClarificationResolver(self.settings, self.llm)

    async def answer(
        self,
        question: str,
        persona: str | None = None,
        history: list[dict[str, str]] | None = None,
        response_language: str | None = None,
    ) -> legacy_rag.RAGAnswer:
        prepared = await self.prepare_stream_answer(
            question,
            persona=persona,
            history=history,
            response_language=response_language,
        )
        return legacy_rag.RAGAnswer(
            answer_text=prepared.answer_text,
            spoken_text=prepared.spoken_text,
            sources=prepared.sources,
            confidence=prepared.confidence,
            used_llm=prepared.used_llm,
            reply_kind=prepared.reply_kind,
            needs_followup=prepared.needs_followup,
            followup_question=prepared.followup_question,
            missing_slots=prepared.missing_slots,
            confidence_note=prepared.confidence_note,
        )

    async def prepare_stream_answer(
        self,
        question: str,
        persona: str | None = None,
        history: list[dict[str, str]] | None = None,
        response_language: str | None = None,
    ) -> legacy_rag.PreparedRAGAnswer:
        prepare_started_at = perf_counter()
        metrics: dict[str, int] = {
            "rag_retrieve_ms": 0,
            "rag_rerank_ms": 0,
            "rag_decision_llm_ms": 0,
            "rag_prepare_total_ms": 0,
        }

        def finish(prepared: legacy_rag.PreparedRAGAnswer) -> legacy_rag.PreparedRAGAnswer:
            metrics["rag_prepare_total_ms"] = int((perf_counter() - prepare_started_at) * 1000)
            prepared.metrics.update(metrics)
            return prepared

        query = legacy_rag.normalize_question(question)
        if not query:
            return finish(
                self._prepare_refusal(
                    legacy_rag.localized_text(
                        response_language,
                        "我刚才没有听清，你可以再说一遍吗？",
                        "I didn't catch that clearly. Could you say it again?",
                    )
                )
            )
        if legacy_rag.is_out_of_domain_question(query):
            return finish(
                self._prepare_refusal(
                    legacy_rag.localized_text(
                        response_language,
                        "这个问题超出了我当前的景区知识范围。你可以继续问我景点、历史、路线或参观建议。",
                        "That question is outside my current scenic-area knowledge. You can still ask me about spots, history, routes, or visit suggestions.",
                    )
                )
            )

        retrieve_started_at = perf_counter()
        candidates = await self.retrieve(query)
        retrieve_elapsed_ms = int((perf_counter() - retrieve_started_at) * 1000)
        metrics["rag_retrieve_ms"] = retrieve_elapsed_ms
        metrics["rag_rerank_ms"] = retrieve_elapsed_ms
        if not self._has_grounded_context(query, candidates):
            return finish(
                self._prepare_refusal(
                    legacy_rag.localized_text(
                        response_language,
                        "我现在还没法根据现有知识库确认这个问题。你可以换个更具体的问法，我再帮你细看。",
                        "I can't confirm that from the current knowledge base yet. If you make the question a bit more specific, I can check again.",
                    )
                )
            )

        selected = candidates[: self.settings.rag_context_docs]
        confidence = round(selected[0].rerank_score, 4) if selected else 0.0
        context = self._format_context(selected)

        fallback_decision = self._build_fallback_decision(
            query,
            selected,
            response_language=response_language,
        )
        fallback_text = self._compose_answer_text(fallback_decision)
        if not fallback_text:
            fallback_text = legacy_rag.localized_text(
                response_language,
                "我现在能确认的信息还不够充分，你可以换个更具体的问法，我再帮你细看。",
                "What I can confirm right now is still limited. If you ask in a more specific way, I can narrow it down for you.",
            )
            fallback_decision = legacy_rag.RAGReplyDecision(
                reply_kind="refuse",
                spoken_answer=fallback_text,
                confidence_note="uncertain",
                used_source_indexes=[1] if selected else [],
            )

        decision = fallback_decision
        used_llm = False
        fast_answer_allowed = self._can_use_fast_humanized_decision(query, selected, fallback_decision)
        if self.settings.dashscope_api_key and not fast_answer_allowed:
            try:
                decision_started_at = perf_counter()
                raw = await self.llm.complete(
                    self._build_decision_messages(
                        question=query,
                        persona=persona or self.settings.default_avatar_persona,
                        context=context,
                        history=history or [],
                        response_language=response_language,
                    )
                )
                metrics["rag_decision_llm_ms"] = int((perf_counter() - decision_started_at) * 1000)
                decision = self._parse_reply_decision(raw, fallback_decision=fallback_decision)
                used_llm = True
            except Exception:
                decision = fallback_decision

        answer_text = self._compose_answer_text(decision)
        if not answer_text:
            answer_text = fallback_text
            decision = fallback_decision
            used_llm = False

        prepared = legacy_rag.PreparedRAGAnswer(
            answer_text=answer_text,
            spoken_text=answer_text,
            sources=self._select_used_sources(selected, decision.used_source_indexes),
            confidence=confidence,
            used_llm=used_llm,
            fallback_text=fallback_text,
            reply_kind=decision.reply_kind,
            needs_followup=decision.needs_followup,
            followup_question=decision.followup_question,
            missing_slots=decision.missing_slots,
            confidence_note=decision.confidence_note,
        )
        return finish(prepared)

    def _build_decision_messages(
        self,
        *,
        question: str,
        persona: str,
        context: str,
        history: list[dict[str, str]],
        response_language: str | None,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": legacy_rag.localized_text(
                    response_language,
                    (
                        "你是景区 AI 数字导览员。"
                        "你必须只依据提供的参考资料作答，不能编造资料中没有的信息。"
                        f"{legacy_rag.build_humanized_language_instruction(response_language)}"
                        "如果信息只够回答一部分，可以先给结论，再补一句简短追问确认范围。"
                        "只输出 JSON。"
                    ),
                    (
                        "You are an AI guide for a scenic area. "
                        "You must answer only from the provided source material and must not invent facts that are not supported by it. "
                        f"{legacy_rag.build_humanized_language_instruction(response_language)} "
                        "If the evidence only supports a partial answer, give the most useful conclusion first, then add one short follow-up question to clarify scope. "
                        "Output JSON only."
                    ),
                ),
            },
            {
                "role": "user",
                "content": legacy_rag.localized_text(
                    response_language,
                    (
                        f"导览员人设：{persona}\n\n"
                        f"最近对话：\n{self._format_history(history, response_language=response_language)}\n\n"
                        f"用户问题：{question}\n\n"
                        f"参考资料：\n{context}\n\n"
                        f"{self._decision_output_instruction(response_language)}"
                    ),
                    (
                        f"Guide persona: {persona}\n\n"
                        f"Recent conversation:\n{self._format_history(history, response_language=response_language)}\n\n"
                        f"User question: {question}\n\n"
                        f"Source material:\n{context}\n\n"
                        f"{self._decision_output_instruction(response_language)}"
                    ),
                ),
            },
        ]

    def _parse_reply_decision(
        self,
        raw_text: str,
        *,
        fallback_decision: legacy_rag.RAGReplyDecision,
    ) -> legacy_rag.RAGReplyDecision:
        payload = parse_json_object(raw_text)
        if not payload:
            return fallback_decision

        reply_kind = str(payload.get("reply_kind", fallback_decision.reply_kind)).strip().lower()
        if reply_kind not in {"answer", "clarify", "refuse"}:
            reply_kind = fallback_decision.reply_kind

        spoken_answer = legacy_rag.sanitize_answer(
            str(payload.get("spoken_answer", fallback_decision.spoken_answer))
        )
        if not spoken_answer:
            spoken_answer = fallback_decision.spoken_answer

        followup_question = legacy_rag.sanitize_answer(
            str(payload.get("followup_question", fallback_decision.followup_question))
        )
        missing_slots = sanitize_slot_list(payload.get("missing_slots"), fallback_decision.missing_slots)
        used_source_indexes = sanitize_index_list(
            payload.get("used_source_indexes"),
            fallback_decision.used_source_indexes,
        )
        confidence_note = str(
            payload.get("confidence_note", fallback_decision.confidence_note)
        ).strip().lower()
        if confidence_note not in {"confirmed", "partial", "uncertain"}:
            confidence_note = fallback_decision.confidence_note

        needs_followup = bool(payload.get("needs_followup", fallback_decision.needs_followup))
        if not followup_question:
            needs_followup = False

        return legacy_rag.RAGReplyDecision(
            reply_kind=reply_kind,
            needs_followup=needs_followup,
            spoken_answer=spoken_answer,
            followup_question=followup_question,
            missing_slots=missing_slots,
            used_source_indexes=used_source_indexes,
            confidence_note=confidence_note,
        )

    def _prepare_refusal(self, message: str) -> legacy_rag.PreparedRAGAnswer:
        return legacy_rag.PreparedRAGAnswer(
            answer_text=message,
            spoken_text=message,
            sources=[],
            confidence=0.0,
            used_llm=False,
            reply_kind="refuse",
            confidence_note="uncertain",
        )

    def _build_fallback_decision(
        self,
        question: str,
        sources: list[legacy_rag.RetrievedChunk],
        response_language: str | None = None,
    ) -> legacy_rag.RAGReplyDecision:
        answer = self._humanize_fallback_answer(question, sources, response_language=response_language)
        intent = legacy_rag.detect_query_intent(question)
        if intent == "schedule" and self._needs_schedule_followup(question, sources):
            return legacy_rag.RAGReplyDecision(
                reply_kind="answer",
                needs_followup=True,
                spoken_answer=answer,
                followup_question=legacy_rag.localized_text(
                    response_language,
                    "如果你问的是商铺、夜游或演出时间，我也可以继续帮你细看。",
                    "If you mean shop hours, night events, or show times, I can narrow that down too.",
                ),
                missing_slots=["target_scope"],
                used_source_indexes=[1] if sources else [],
                confidence_note="partial",
            )
        if intent == "route" and self._needs_route_followup(question):
            return legacy_rag.RAGReplyDecision(
                reply_kind="answer",
                needs_followup=True,
                spoken_answer=answer,
                followup_question=legacy_rag.localized_text(
                    response_language,
                    "如果你偏亲子、夜游或半日游，我可以再帮你细化路线。",
                    "If you want a family-friendly, night-view, or half-day route, I can tailor it further.",
                ),
                missing_slots=["visitor_profile"],
                used_source_indexes=[1] if sources else [],
                confidence_note="partial",
            )
        return legacy_rag.RAGReplyDecision(
            reply_kind="answer",
            spoken_answer=answer,
            used_source_indexes=[1] if sources else [],
            confidence_note="confirmed",
        )

    def _can_use_fast_humanized_decision(
        self,
        question: str,
        sources: list[legacy_rag.RetrievedChunk],
        fallback_decision: legacy_rag.RAGReplyDecision,
    ) -> bool:
        if self.settings.rag_response_mode != "fast_humanized":
            return False
        if not fallback_decision.spoken_answer.strip():
            return False
        if not sources:
            return False
        intent = legacy_rag.detect_query_intent(question)
        if intent not in {"schedule", "route", "overview", "history"}:
            return False
        best_score = max(sources[0].rerank_score, sources[0].retrieval_score)
        return best_score >= 0.75

    def _humanize_fallback_answer(
        self,
        question: str,
        sources: list[legacy_rag.RetrievedChunk],
        *,
        response_language: str | None = None,
    ) -> str:
        answer = legacy_rag.sanitize_answer(self._build_extractive_answer(question, sources))
        if not answer and sources:
            answer = legacy_rag.sanitize_answer(legacy_rag.truncate_text(sources[0].text, 140))
        answer = re.sub(r"^(根据景区资料[，,:：]?|根据资料[，,:：]?|根据当前景区知识库[，,:：]?)", "", answer)
        answer = answer.strip()
        if not answer:
            return ""

        if legacy_rag.detect_query_intent(question) == "schedule":
            schedule_summary = self._summarize_schedule_sources(sources, response_language=response_language)
            if schedule_summary:
                return schedule_summary

        parts = [segment.strip() for segment in legacy_rag.split_sentences(answer) if segment.strip()]
        humanized = "".join(parts[:2]) if parts else answer
        if humanized and humanized[-1] not in "。！？!?":
            humanized += "。"
        return humanized

    def _summarize_schedule_sources(
        self,
        sources: list[legacy_rag.RetrievedChunk],
        *,
        response_language: str | None = None,
    ) -> str:
        for source in sources:
            text = " ".join(legacy_rag.split_lines(source.text))
            if "开放时间" in text:
                match = legacy_rag.TIME_RANGE_RE.search(text)
                if match:
                    return legacy_rag.localized_text(
                        response_language,
                        f"景区整体开放一般是 {match.group('time')}。",
                        f"The overall scenic area is generally open from {match.group('time')}.",
                    )
        return ""

    def _decision_output_instruction(self, response_language: str | None) -> str:
        if legacy_rag.normalize_response_language(response_language) == "en":
            return (
                "Output JSON only, with these exact fields: "
                '{"reply_kind":"answer|clarify|refuse",'
                '"needs_followup":true,'
                '"spoken_answer":"natural spoken English for visitors, 1 to 3 sentences, no citation wording",'
                '"followup_question":"one short follow-up question when needed, otherwise an empty string",'
                '"missing_slots":["target_scope"],'
                '"used_source_indexes":[1],'
                '"confidence_note":"confirmed|partial|uncertain"}'
            )
        return (
            "请输出 JSON，字段固定为："
            '{"reply_kind":"answer|clarify|refuse",'
            '"needs_followup":true,'
            '"spoken_answer":"面向游客的自然口语回答，1到3句，不要出现参考资料字样",'
            '"followup_question":"需要时的一句短追问，否则为空字符串",'
            '"missing_slots":["target_scope"],'
            '"used_source_indexes":[1],'
            '"confidence_note":"confirmed|partial|uncertain"}'
        )

    def _needs_schedule_followup(
        self,
        question: str,
        sources: list[legacy_rag.RetrievedChunk],
    ) -> bool:
        if any(token in question for token in ("商铺", "夜游", "演出", "餐饮", "景区整体", "景点")):
            return False
        combined = "\n".join(source.text for source in sources)
        scope_hits = sum(
            1
            for token in ("商铺", "夜游", "演出", "餐饮", "开放时间", "营业时间")
            if token in combined
        )
        return scope_hits >= 3

    def _needs_route_followup(self, question: str) -> bool:
        return any(token in question for token in ("怎么逛", "路线", "推荐", "第一次来")) and not any(
            token in question for token in ("亲子", "家庭", "孩子", "半日", "半天", "夜游", "拍照", "老人")
        )

    def _compose_answer_text(self, decision: legacy_rag.RAGReplyDecision) -> str:
        base = legacy_rag.sanitize_answer(decision.spoken_answer)
        followup = legacy_rag.sanitize_answer(decision.followup_question)
        if decision.needs_followup and followup:
            if base:
                return f"{base} {followup}".strip()
            return followup
        return base

    def _select_used_sources(
        self,
        sources: list[legacy_rag.RetrievedChunk],
        used_source_indexes: list[int],
    ) -> list[legacy_rag.RetrievedChunk]:
        if not sources:
            return []
        if not used_source_indexes:
            return sources
        selected: list[legacy_rag.RetrievedChunk] = []
        seen = set()
        for index in used_source_indexes:
            zero_index = index - 1
            if 0 <= zero_index < len(sources) and zero_index not in seen:
                selected.append(sources[zero_index])
                seen.add(zero_index)
        return selected or sources[:1]

    def _format_history(
        self,
        history: list[dict[str, str]],
        *,
        response_language: str | None = None,
    ) -> str:
        if not history:
            return legacy_rag.localized_text(response_language, "无", "None")

        lines: list[str] = []
        for item in history[-6:]:
            role = str(item.get("role", "")).strip().lower()
            content = legacy_rag.sanitize_answer(str(item.get("content", "")))
            if not content:
                continue
            speaker = legacy_rag.localized_text(
                response_language,
                "游客" if role == "user" else "导览助手",
                "Visitor" if role == "user" else "Guide",
            )
            lines.append(f"{speaker}：{content}")
        return "\n".join(lines) if lines else legacy_rag.localized_text(response_language, "无", "None")
