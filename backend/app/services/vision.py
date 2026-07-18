from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import status

from app.core.config import Settings, get_settings

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}

CANONICAL_SPOT_NAMES = (
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

CANONICAL_SPOT_ALIASES: dict[str, tuple[str, ...]] = {
    "五印坛城": (
        "五印坛城",
        "白塔",
        "藏式白塔",
        "白色佛塔",
        "五层佛塔",
        "藏式佛塔",
        "the white pagoda",
        "white pagoda",
        "white stupa",
        "five-storeyed stupa",
        "five-storied stupa",
        "five-storeyed pagoda",
        "five-storied pagoda",
        "lingshan white pagoda",
    ),
    "灵山大佛": (
        "灵山大佛",
        "大佛",
        "佛像",
        "giant buddha",
        "lingshan buddha",
        "grand buddha at ling shan",
    ),
    "灵山梵宫": (
        "灵山梵宫",
        "梵宫",
        "brahma palace",
        "fan gong palace",
    ),
    "九龙灌浴": (
        "九龙灌浴",
        "九龙灌浴广场",
        "baby buddha bathing",
        "nine dragons bathing",
    ),
    "祥符禅寺": (
        "祥符禅寺",
        "祥符寺",
        "xiangfu temple",
        "xiangfu chan temple",
    ),
    "佛手广场": (
        "佛手广场",
        "天下第一掌",
        "buddha hand square",
    ),
    "百子戏弥勒": (
        "百子戏弥勒",
        "百子戏弥勒雕塑",
    ),
    "灵山精舍": (
        "灵山精舍",
        "精舍",
    ),
    "曼飞龙塔": (
        "曼飞龙塔",
        "曼飞龙佛塔",
        "manfeilong pagoda",
    ),
}

GENERIC_SPOT_NAMES = {
    "灵山胜境",
    "灵山景区",
    "景区",
    "园区",
    "寺庙",
    "佛教景区",
    "旅游景区",
}


class VisitorVisionError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        super().__init__(message)


class VisitorVisionValidationError(VisitorVisionError):
    status_code = status.HTTP_400_BAD_REQUEST


class VisitorVisionUnsupportedMediaTypeError(VisitorVisionValidationError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


class VisitorVisionPayloadTooLargeError(VisitorVisionValidationError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


class VisitorVisionUpstreamError(VisitorVisionError):
    status_code = status.HTTP_502_BAD_GATEWAY


class VisitorVisionServiceNotConfiguredError(VisitorVisionError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class VisitorVisionResponseFormatError(VisitorVisionError):
    status_code = status.HTTP_502_BAD_GATEWAY


@dataclass(slots=True)
class VisitorVisionResult:
    recognized_spot: str
    recognition_summary: str
    resolved_question: str
    stored_image_path: str
    is_canonical_spot: bool = False


class VisitorVisionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_preview_url(self, session_id: str, filename: str) -> str:
        return f"/api/v1/sessions/{session_id}/photos/{filename}"

    async def store_photo(
        self,
        *,
        session_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, str, str]:
        normalized_content_type = self._validate_image_bytes(
            content_type=content_type,
            data=data,
        )
        stored_key, stored_path = self._store_image(
            session_id=session_id,
            filename=filename,
            content_type=normalized_content_type,
            data=data,
        )
        return stored_key, stored_path.name, normalized_content_type

    async def recognize_stored_photo(
        self,
        *,
        session_id: str,
        stored_image_path: str,
        interest_tags: list[str],
        user_prompt: str | None = None,
    ) -> VisitorVisionResult:
        if not self.settings.dashscope_api_key:
            raise VisitorVisionServiceNotConfiguredError(
                "DASHSCOPE_API_KEY is not configured."
            )
        stored_key, stored_path = self._resolve_stored_image_path(
            session_id=session_id,
            stored_image_path=stored_image_path,
        )
        data = stored_path.read_bytes()
        content_type = self._guess_content_type(stored_path)
        normalized_content_type = self._validate_image_bytes(
            content_type=content_type,
            data=data,
        )
        data_url = self._build_data_url(normalized_content_type, data)
        payload = await self._request_recognition_payload(
            data_url=data_url,
            interest_tags=self._normalize_interest_tags(interest_tags),
            user_prompt=user_prompt,
        )
        return self._build_result_from_payload(payload=payload, stored_key=stored_key)

    def resolve_preview_file(
        self,
        *,
        session_id: str,
        filename: str,
    ) -> tuple[Path, str]:
        cleaned_name = Path(filename).name
        if not cleaned_name or cleaned_name in {".", ".."}:
            raise VisitorVisionValidationError("Invalid photo filename.")
        stored_key = f"{session_id}/{cleaned_name}"
        _stored_key, stored_path = self._resolve_stored_image_path(
            session_id=session_id,
            stored_image_path=stored_key,
        )
        return stored_path, self._guess_content_type(stored_path)

    async def recognize(
        self,
        session_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        interest_tags: list[str],
        user_prompt: str | None = None,
    ) -> VisitorVisionResult:
        if not self.settings.dashscope_api_key:
            raise VisitorVisionServiceNotConfiguredError(
                "DASHSCOPE_API_KEY is not configured."
            )

        normalized_content_type = self._validate_image_bytes(
            content_type=content_type,
            data=data,
        )
        stored_key, _stored_path = self._store_image(
            session_id=session_id,
            filename=filename,
            content_type=normalized_content_type,
            data=data,
        )
        data_url = self._build_data_url(normalized_content_type, data)
        payload = await self._request_recognition_payload(
            data_url=data_url,
            interest_tags=self._normalize_interest_tags(interest_tags),
            user_prompt=user_prompt,
        )
        return self._build_result_from_payload(payload=payload, stored_key=stored_key)

    def _store_image(
        self,
        session_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> tuple[str, Path]:
        extension = IMAGE_EXTENSIONS.get(content_type) or mimetypes.guess_extension(content_type) or ".bin"

        storage_root = Path(self.settings.visitor_upload_dir).resolve()
        storage_root.mkdir(parents=True, exist_ok=True)
        session_dir = (storage_root / session_id).resolve()
        if not session_dir.is_relative_to(storage_root):
            raise VisitorVisionValidationError("Invalid session storage path.")
        session_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}{extension}"
        stored_key = f"{session_id}/{stored_name}"
        stored_path = session_dir / stored_name
        stored_path.write_bytes(data)
        return stored_key, stored_path

    def _build_data_url(self, content_type: str, data: bytes) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def _validate_image_bytes(self, *, content_type: str, data: bytes) -> str:
        normalized_content_type = (content_type or "").strip().lower()
        if normalized_content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise VisitorVisionUnsupportedMediaTypeError("Unsupported image content type.")
        if not data:
            raise VisitorVisionValidationError("Image file is empty.")
        if len(data) > self.settings.visitor_image_max_bytes:
            raise VisitorVisionPayloadTooLargeError(
                "Image file exceeds the configured size limit."
            )
        if not self._matches_image_signature(normalized_content_type, data):
            raise VisitorVisionValidationError(
                "Image file content does not match the declared image type."
            )
        return normalized_content_type

    def _resolve_stored_image_path(
        self,
        *,
        session_id: str,
        stored_image_path: str,
    ) -> tuple[str, Path]:
        storage_root = Path(self.settings.visitor_upload_dir).resolve()
        raw_key = " ".join(str(stored_image_path or "").split())
        relative_path = Path(raw_key)
        if (
            not raw_key
            or relative_path.is_absolute()
            or ".." in relative_path.parts
            or not relative_path.parts
            or relative_path.parts[0] != session_id
        ):
            raise VisitorVisionValidationError("Invalid stored image path.")
        stored_path = (storage_root / relative_path).resolve()
        if not stored_path.is_relative_to(storage_root):
            raise VisitorVisionValidationError("Invalid stored image path.")
        if not stored_path.exists() or not stored_path.is_file():
            raise VisitorVisionValidationError("Stored image file not found.")
        return raw_key, stored_path

    def _guess_content_type(self, stored_path: Path) -> str:
        guessed = (mimetypes.guess_type(stored_path.name)[0] or "").strip().lower()
        if guessed in ALLOWED_IMAGE_CONTENT_TYPES:
            return guessed
        raise VisitorVisionUnsupportedMediaTypeError("Unsupported image content type.")

    def _build_result_from_payload(
        self,
        *,
        payload: dict[str, Any],
        stored_key: str,
    ) -> VisitorVisionResult:
        raw_spot = self._required_text(payload, "recognized_spot")
        normalized_spot = self._normalize_recognized_spot(raw_spot)
        is_canonical_spot = self._is_canonical_spot_name(normalized_spot)
        return VisitorVisionResult(
            recognized_spot=normalized_spot,
            recognition_summary=self._required_text(payload, "recognition_summary"),
            resolved_question=self._required_text(payload, "resolved_question"),
            stored_image_path=stored_key,
            is_canonical_spot=is_canonical_spot,
        )

    def _matches_image_signature(self, content_type: str, data: bytes) -> bool:
        if content_type == "image/webp":
            return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"

        signatures = IMAGE_SIGNATURES.get(content_type, ())
        return any(data.startswith(signature) for signature in signatures)

    async def _request_recognition_payload(
        self,
        *,
        data_url: str,
        interest_tags: list[str],
        user_prompt: str | None,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(interest_tags=interest_tags, user_prompt=user_prompt)
        url = f"{self.settings.dashscope_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.dashscope_vl_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是江苏无锡灵山胜境的景点识图助手。"
                        "必须使用简体中文输出。"
                        "只返回 JSON，不要输出任何额外说明。"
                        "JSON 字段固定为 recognized_spot, recognition_summary, resolved_question, is_canonical_spot。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds * 3) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                response_data = response.json()
            except httpx.HTTPStatusError as exc:
                raise VisitorVisionUpstreamError("Vision model request failed.") from exc
            except httpx.HTTPError as exc:
                raise VisitorVisionUpstreamError("Vision model request failed.") from exc
            except ValueError as exc:
                raise VisitorVisionResponseFormatError(
                    "Vision model response is not valid JSON."
                ) from exc

        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisitorVisionResponseFormatError(
                "Vision model response missing required content."
            ) from exc
        text = self._extract_content_text(content)
        parsed = self._parse_json_object(text)
        if parsed is None:
            raise VisitorVisionResponseFormatError(
                "Vision recognition payload is not valid JSON."
            )
        return parsed

    def _build_prompt(self, interest_tags: list[str], user_prompt: str | None) -> str:
        joined_tags = "、".join(interest_tags) if interest_tags else "无"
        prompt = (user_prompt or "").strip() or "请帮我看看这张图片。"
        return (
            "请识别这张游客上传的灵山胜境景点照片。"
            f"游客兴趣标签：{joined_tags}。"
            f"游客当前问题：{prompt}。"
            "请优先判断它是否对应灵山胜境的标准景点名，如灵山大佛、灵山梵宫、九龙灌浴、五印坛城、祥符禅寺、佛手广场、百子戏弥勒、灵山精舍、曼飞龙塔。"
            "如果能可靠命中标准景点名，recognized_spot 直接填写标准景点中文名，is_canonical_spot 设为 true。"
            "如果不能可靠命中标准景点名，recognized_spot 也必须用简体中文填写当前最合理的景点名称或场景描述，is_canonical_spot 设为 false。"
            "recognition_summary 用1到2句简体中文概括画面线索。"
            "resolved_question 用简体中文给出更完整的单轮提问句子，便于后续导览问答继续使用。"
        )

    def _normalize_interest_tags(self, interest_tags: list[str]) -> list[str]:
        normalized: list[str] = []
        seen = set()
        for tag in interest_tags:
            cleaned = " ".join(str(tag).strip().split())
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _extract_content_text(self, content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict)
            )
        return ""

    def _parse_json_object(self, raw_text: str) -> dict[str, Any] | None:
        cleaned = raw_text.strip()
        if not cleaned:
            return None

        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _required_text(self, payload: dict[str, Any], key: str) -> str:
        value = " ".join(str(payload.get(key, "")).strip().split())
        if not value:
            raise VisitorVisionResponseFormatError(
                f"Vision recognition payload missing required field: {key}"
            )
        return value

    def _normalize_recognized_spot(self, raw_spot: str) -> str:
        cleaned = " ".join(raw_spot.strip().split())
        lowered = cleaned.casefold()
        for canonical_name in CANONICAL_SPOT_NAMES:
            if cleaned == canonical_name:
                return canonical_name
            aliases = CANONICAL_SPOT_ALIASES.get(canonical_name, ())
            if any(lowered == alias.casefold() for alias in aliases):
                return canonical_name
            if any(alias.casefold() in lowered for alias in aliases):
                return canonical_name
        if cleaned in GENERIC_SPOT_NAMES:
            return cleaned
        return cleaned

    def _is_canonical_spot_name(self, spot_name: str) -> bool:
        return spot_name in CANONICAL_SPOT_NAMES


@lru_cache
def get_visitor_vision_service() -> VisitorVisionService:
    return VisitorVisionService(get_settings())
