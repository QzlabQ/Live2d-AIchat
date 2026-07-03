from __future__ import annotations

import base64
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db.models import AvatarConfig, Message, Session
from app.db.session import AsyncSessionFactory
from app.services.asr import get_asr_service
from app.services.chat import get_chat_service
from app.services.tts import get_tts_service

websocket_router = APIRouter()


async def send_error(websocket: WebSocket, code: str, message: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message})


async def get_avatar_config(session) -> AvatarConfig:
    result = await session.execute(select(AvatarConfig).limit(1))
    avatar = result.scalar_one_or_none()
    if avatar is None:
        raise RuntimeError("Avatar configuration has not been initialized.")
    return avatar


async def save_message(
    db_session,
    session_id: str,
    role: str,
    content: str,
    emotion: str | None = None,
    latency_ms: int | None = None,
) -> None:
    db_session.add(
        Message(
            session_id=session_id,
            role=role,
            content=content,
            emotion=emotion,
            latency_ms=latency_ms,
        )
    )
    await db_session.commit()


async def process_text_message(websocket: WebSocket, db_session, session_id: str, content: str) -> None:
    chat_service = get_chat_service()
    tts_service = get_tts_service()
    started_at = perf_counter()

    await save_message(db_session, session_id=session_id, role="user", content=content)
    avatar = await get_avatar_config(db_session)

    generated = await chat_service.generate_reply(content, persona=avatar.persona)
    await websocket.send_json(
        {
            "type": "emotion",
            "value": generated.emotion,
            "confidence": generated.emotion_meta.confidence,
            "keywords": generated.emotion_meta.keywords,
            "reason": generated.emotion_meta.reason,
            "source": generated.emotion_meta.source,
        }
    )

    for chunk in chat_service.chunk_text(generated.text):
        await websocket.send_json({"type": "text_delta", "content": chunk})

    spoken_text = generated.spoken_text or generated.text
    for seq, chunk in enumerate(chat_service.chunk_text(spoken_text)):
        tts_chunk = await tts_service.synthesize_chunk(chunk, seq=seq, voice_id=avatar.voice_id)
        if tts_chunk.audio_bytes:
            await websocket.send_json(
                {
                    "type": "audio",
                    "data": base64.b64encode(tts_chunk.audio_bytes).decode("utf-8"),
                    "mime_type": tts_chunk.mime_type,
                    "seq": seq,
                }
            )
        if tts_chunk.phonemes:
            await websocket.send_json({"type": "phonemes", "seq": seq, "data": tts_chunk.phonemes})

    if generated.sources:
        await websocket.send_json(
            {
                "type": "sources",
                "mode": generated.mode,
                "items": [
                    {
                        "filename": item.filename,
                        "title": item.title,
                        "category": item.category,
                        "chunk_index": item.chunk_index,
                        "retrieval_score": item.retrieval_score,
                        "rerank_score": item.rerank_score,
                    }
                    for item in generated.sources
                ],
            }
        )

    latency_ms = int((perf_counter() - started_at) * 1000)
    await save_message(
        db_session,
        session_id=session_id,
        role="assistant",
        content=generated.text,
        emotion=generated.emotion,
        latency_ms=latency_ms,
    )
    await websocket.send_json({"type": "done", "session_id": session_id})


async def process_audio_buffer(websocket: WebSocket, db_session, session_id: str, audio_buffer: bytearray) -> None:
    if not audio_buffer:
        await send_error(websocket, "ASR_FAILED", "未接收到可识别的音频数据。")
        return

    transcript = await get_asr_service().transcribe_pcm16(bytes(audio_buffer))
    audio_buffer.clear()
    if not transcript:
        await send_error(websocket, "ASR_FAILED", "语音识别未返回有效文本。")
        return

    await websocket.send_json({"type": "asr_result", "content": transcript})
    await process_text_message(websocket, db_session, session_id, transcript)


@websocket_router.websocket("/ws/chat/{session_id}")
async def chat_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    audio_buffer = bytearray()

    try:
        async with AsyncSessionFactory() as db_session:
            session_obj = await db_session.get(Session, session_id)
            if session_obj is None:
                await send_error(websocket, "SESSION_NOT_FOUND", "会话不存在，请先创建会话。")
                await websocket.close(code=4404)
                return

            while True:
                payload = await websocket.receive_json()
                message_type = payload.get("type")

                if message_type == "text":
                    content = str(payload.get("content", "")).strip()
                    if not content:
                        await send_error(websocket, "EMPTY_TEXT", "文本消息不能为空。")
                        continue
                    await process_text_message(websocket, db_session, session_id, content)
                    continue

                if message_type == "audio_chunk":
                    encoded = payload.get("data")
                    if not isinstance(encoded, str):
                        await send_error(websocket, "INVALID_AUDIO", "音频块必须为 base64 字符串。")
                        continue

                    try:
                        audio_buffer.extend(base64.b64decode(encoded))
                    except Exception:
                        await send_error(websocket, "INVALID_AUDIO", "音频块 base64 解码失败。")
                        continue

                    if bool(payload.get("is_final")):
                        await process_audio_buffer(websocket, db_session, session_id, audio_buffer)
                    continue

                if message_type == "audio_end":
                    await process_audio_buffer(websocket, db_session, session_id, audio_buffer)
                    continue

                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue

                await send_error(websocket, "UNSUPPORTED_MESSAGE", f"不支持的消息类型: {message_type}")
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await send_error(websocket, "INTERNAL_ERROR", str(exc))
        await websocket.close(code=1011)
