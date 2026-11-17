from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class MediaValidationError(ValueError):
    pass


def validate_probe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    streams = payload.get("streams") or []
    media_streams = [stream for stream in streams if stream.get("codec_type") in {"audio", "video"}]
    if not media_streams:
        raise MediaValidationError("ไฟล์ไม่มี audio หรือ video stream ที่รองรับ")
    raw_duration = (payload.get("format") or {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": max(0.0, duration),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in media_streams),
        "has_video": any(stream.get("codec_type") == "video" for stream in media_streams),
        "format": (payload.get("format") or {}).get("format_name"),
    }


def probe_media(path: Path, ffprobe_path: str | None = None) -> dict[str, Any]:
    executable = ffprobe_path or os.environ.get("MEETING_FFPROBE") or shutil.which("ffprobe")
    if not executable or not Path(executable).is_file():
        raise MediaValidationError("FFprobe ยังไม่พร้อมใช้งาน")
    result = subprocess.run(
        [executable, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise MediaValidationError("ไฟล์ไม่ใช่สื่อที่ FFprobe อ่านได้")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaValidationError("ผลตรวจสอบสื่อไม่ถูกต้อง") from exc
    return validate_probe_payload(payload)
