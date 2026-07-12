from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct
import wave

from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings

ALLOWED_VOICE_SUFFIXES = {".wav"}


def build_voice_profile_storage_path(settings: Settings, profile_id: str, filename: str) -> Path:
    upload_root = Path(settings.admin_voice_upload_dir).expanduser()
    if not upload_root.is_absolute():
        upload_root = Path(__file__).resolve().parents[2] / upload_root
    upload_root.mkdir(parents=True, exist_ok=True)
    return upload_root / f"{profile_id}-{Path(filename).name}"


async def read_upload_limited(
    file: UploadFile,
    max_bytes: int,
    *,
    chunk_size: int = 64 * 1024,
) -> bytes:
    buffer = bytearray()
    limit_mb = max_bytes / (1024 * 1024)
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"音色参考音频超过大小限制（当前上限 {limit_mb:.0f} MB）。",
            )
    return bytes(buffer)


def _read_wav_duration_ms(payload: bytes) -> int:
    try:
        with wave.open(BytesIO(payload), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            sample_rate = max(wav_file.getframerate(), 1)
            return int(frame_count / sample_rate * 1000)
    except wave.Error:
        pass

    try:
        if len(payload) < 44 or payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
            raise ValueError("Not a RIFF/WAVE file.")

        fmt_chunk: bytes | None = None
        data_chunk_size: int | None = None
        offset = 12
        while offset + 8 <= len(payload):
            chunk_id = payload[offset : offset + 4]
            chunk_size = int.from_bytes(payload[offset + 4 : offset + 8], "little")
            chunk_data_start = offset + 8
            chunk_data_end = chunk_data_start + chunk_size
            if chunk_data_end > len(payload):
                raise ValueError("Invalid wav chunk size.")

            if chunk_id == b"fmt ":
                fmt_chunk = payload[chunk_data_start:chunk_data_end]
            elif chunk_id == b"data":
                data_chunk_size = chunk_size

            offset = chunk_data_end + (chunk_size % 2)

        if fmt_chunk is None or data_chunk_size is None or len(fmt_chunk) < 16:
            raise ValueError("Missing wav fmt/data chunk.")

        _, channels, sample_rate, _, block_align, _ = struct.unpack("<HHIIHH", fmt_chunk[:16])
        if channels <= 0 or sample_rate <= 0 or block_align <= 0:
            raise ValueError("Invalid wav format metadata.")

        frame_count = int(data_chunk_size // block_align)
        return int(frame_count / sample_rate * 1000)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传的 wav 音频无法解析。",
        ) from exc


def validate_voice_profile_audio(filename: str, payload: bytes) -> tuple[str, int, str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_VOICE_SUFFIXES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前仅支持上传 wav 参考音频。",
        )

    duration_ms = _read_wav_duration_ms(payload)
    if duration_ms <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传的参考音频为空。",
        )

    return suffix, duration_ms, "audio/wav"
