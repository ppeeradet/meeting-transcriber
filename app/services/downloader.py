from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core import safe_name


AUDIO_FORMATS = {"original", "mp3", "m4a", "wav", "flac"}
AUDIO_QUALITIES = {"v0", "320", "256", "192", "128"}
VIDEO_QUALITIES = {"best", "1080", "720", "480", "360"}


@dataclass(frozen=True)
class DownloadOptions:
    media_mode: str = "audio"
    output_format: str = "mp3"
    quality: str = "v0"
    embed_cover: bool = True

    def validate(self) -> None:
        if self.media_mode not in {"audio", "video"}:
            raise ValueError("media_mode ไม่ถูกต้อง")
        if self.media_mode == "audio" and self.output_format not in AUDIO_FORMATS:
            raise ValueError("รูปแบบเสียงไม่รองรับ")
        if self.media_mode == "audio" and self.output_format == "mp3" and self.quality not in AUDIO_QUALITIES:
            raise ValueError("คุณภาพ MP3 ไม่รองรับ")
        if self.media_mode == "video" and self.quality not in VIDEO_QUALITIES:
            raise ValueError("ความละเอียดวิดีโอไม่รองรับ")


def platform_name(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    mapping = (
        (("youtube.com", "youtu.be"), "YouTube"),
        (("facebook.com", "fb.watch"), "Facebook"),
        (("instagram.com",), "Instagram"),
        (("tiktok.com",), "TikTok"),
        (("x.com", "twitter.com"), "X / Twitter"),
        (("vimeo.com",), "Vimeo"),
        (("dailymotion.com", "dai.ly"), "Dailymotion"),
        (("soundcloud.com",), "SoundCloud"),
    )
    for hosts, label in mapping:
        if any(host == item or host.endswith(f".{item}") for item in hosts):
            return label
    return "Direct Media"


def _base_command(output_dir: Path, title: str | None) -> list[str]:
    template = f"{safe_name(title)}.%(ext)s" if title else "%(title).120B.%(ext)s"
    command = [
        sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
        "--socket-timeout", "30", "--newline", "--windows-filenames",
        "--add-metadata", "-o", str(output_dir / template),
    ]
    try:
        import imageio_ffmpeg

        command.extend(["--ffmpeg-location", imageio_ffmpeg.get_ffmpeg_exe()])
    except ImportError:
        pass
    return command


def build_command(url: str, output_dir: Path, title: str | None, options: DownloadOptions) -> list[str]:
    options.validate()
    command = _base_command(output_dir, title)
    if options.media_mode == "video":
        selector = "bv*+ba/b" if options.quality == "best" else f"bv*[height<={options.quality}]+ba/b[height<={options.quality}]"
        command.extend(["-f", selector, "--merge-output-format", "mp4", "--write-thumbnail", "--convert-thumbnails", "jpg"])
    elif options.output_format == "original":
        command.extend(["-f", "bestaudio/best", "--write-thumbnail", "--convert-thumbnails", "jpg"])
    else:
        audio_quality = "0" if options.quality == "v0" else f"{options.quality}K"
        command.extend(["-f", "bestaudio/best", "-x", "-k", "--audio-format", options.output_format])
        if options.output_format == "mp3":
            command.extend(["--audio-quality", audio_quality])
        command.extend(["--write-thumbnail", "--convert-thumbnails", "jpg"])
        if options.embed_cover and options.output_format in {"mp3", "m4a"}:
            command.append("--embed-thumbnail")
    command.append(url)
    return command


def preview_command(url: str) -> list[str]:
    return [
        sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist",
        "--socket-timeout", "20", "--skip-download", "--dump-single-json", url,
    ]


def parse_preview(payload: dict[str, Any], url: str) -> dict[str, Any]:
    formats = []
    for item in payload.get("formats") or []:
        if len(formats) >= 30:
            break
        formats.append({
            "id": item.get("format_id"),
            "ext": item.get("ext"),
            "height": item.get("height"),
            "audio_bitrate": item.get("abr"),
            "filesize": item.get("filesize") or item.get("filesize_approx"),
            "has_video": item.get("vcodec") not in {None, "none"},
            "has_audio": item.get("acodec") not in {None, "none"},
        })
    return {
        "title": payload.get("title"),
        "thumbnail": payload.get("thumbnail"),
        "platform": platform_name(url),
        "uploader": payload.get("uploader") or payload.get("channel"),
        "duration": payload.get("duration"),
        "formats": formats,
    }


def preview(url: str) -> dict[str, Any]:
    result = subprocess.run(
        preview_command(url), capture_output=True, text=True, encoding="utf-8",
        errors="replace", shell=False, timeout=45, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "Metadata preview failed"
        raise RuntimeError(message[-300:])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Metadata preview returned invalid JSON") from exc
    return parse_preview(payload, url)
