from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


OUTPUT_FORMATS = {"mp3", "wav", "m4a", "flac", "mp4"}
BITRATES = {"320", "256", "192", "128"}
RESOLUTIONS = {"original", "1080", "720", "480", "360"}


@dataclass(frozen=True)
class ConversionOptions:
    output_format: str
    bitrate: str = "192"
    resolution: str = "original"

    def validate(self) -> None:
        if self.output_format not in OUTPUT_FORMATS:
            raise ValueError("รูปแบบปลายทางไม่รองรับ")
        if self.bitrate not in BITRATES:
            raise ValueError("Bitrate ไม่รองรับ")
        if self.resolution not in RESOLUTIONS:
            raise ValueError("ความละเอียดไม่รองรับ")


def ffmpeg_executable() -> str:
    configured = os.environ.get("MEETING_FFMPEG")
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("FFmpeg ยังไม่พร้อมใช้งาน") from exc


def output_path(source: Path, output_dir: Path, extension: str) -> Path:
    candidate = output_dir / f"{source.stem}-converted.{extension}"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"{source.stem}-converted-{counter}.{extension}"
        counter += 1
    return candidate


def build_conversion_command(source: Path, target: Path, options: ConversionOptions) -> list[str]:
    options.validate()
    command = [ffmpeg_executable(), "-hide_banner", "-nostdin", "-y", "-i", str(source)]
    if options.output_format in {"mp3", "wav", "m4a", "flac"}:
        command.extend(["-vn"])
        if options.output_format == "mp3":
            command.extend(["-c:a", "libmp3lame", "-b:a", f"{options.bitrate}k"])
        elif options.output_format == "m4a":
            command.extend(["-c:a", "aac", "-b:a", f"{options.bitrate}k"])
        elif options.output_format == "wav":
            command.extend(["-c:a", "pcm_s16le"])
        else:
            command.extend(["-c:a", "flac"])
    elif source.suffix.lower() == ".mp4" and options.resolution == "original":
        command.extend(["-c", "copy"])
    else:
        command.extend(["-c:v", "libx264", "-preset", "medium", "-c:a", "aac"])
        if options.resolution != "original":
            command.extend(["-vf", f"scale=-2:'min({options.resolution},ih)'"])
    command.append(str(target))
    return command
