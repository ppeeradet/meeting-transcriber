from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .database import JobDatabase


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str, fallback: str = "meeting") -> str:
    cleaned = INVALID_FILENAME.sub("_", value).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned[:120] or fallback
    stem = cleaned.split(".", 1)[0].upper()
    return f"_{cleaned}" if stem in WINDOWS_RESERVED else cleaned


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def transcription_language(value: str) -> str | None:
    return None if value.strip().lower() == "auto" else value.strip().lower()


def build_download_command(url: str, output_dir: Path, title: str | None) -> list[str]:
    from .services.downloader import DownloadOptions, build_command

    return build_command(url, output_dir, title, DownloadOptions())


def build_video_command(url: str, output_dir: Path, title: str | None) -> list[str]:
    from .services.downloader import DownloadOptions, build_command

    return build_command(url, output_dir, title, DownloadOptions(media_mode="video", output_format="mp4", quality="best", embed_cover=False))


@dataclass
class Job:
    id: str
    url: str
    input_path: str | None = None
    media_mode: str = "audio"
    title: str | None = None
    transcribe: bool = False
    language: str = "th"
    status: str = "queued"
    progress: str = "รอประมวลผล"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    output_dir: str = ""
    error: str | None = None
    files: list[str] = field(default_factory=list)
    checkpoint: str = "created"
    output_format: str = "mp3"
    quality: str = "v0"
    embed_cover: bool = True
    operation: str = "download"
    conversion_bitrate: str = "192"
    conversion_resolution: str = "original"
    model_profile: str = "balanced"
    source_size_bytes: int | None = None
    result_size_bytes: int | None = None
    archived: bool = False
    archived_at: str | None = None


class JobCancelled(RuntimeError):
    pass


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self.jobs_root = root / "jobs"
        self.path = root / "jobs.json"
        self.lock = threading.Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.database = JobDatabase(root)
        self.migration_report = self.database.migrate_json()
        self.jobs: dict[str, Job] = {}
        self._load()

    def _load(self) -> None:
        try:
            payload = self.database.load()
            self.jobs = {item["id"]: Job(**item) for item in payload}
            changed = False
            for job in self.jobs.values():
                if job.status in {"downloading", "converting", "transcribing", "exporting"}:
                    job.checkpoint = job.status
                    job.status = "interrupted"
                    job.progress = "หยุดระหว่างการรีสตาร์ต — กดเริ่มใหม่"
                    job.updated_at = utc_now()
                    changed = True
            if changed:
                self._save()
        except (OSError, ValueError, TypeError, KeyError):
            self.jobs = {}

    def _save(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps([asdict(j) for j in self.jobs.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)
        self.database.save(asdict(j) for j in self.jobs.values())

    def add(self, url: str, title: str | None, transcribe: bool, language: str, media_mode: str = "audio", output_format: str = "mp3", quality: str = "v0", embed_cover: bool = True, model_profile: str = "balanced") -> Job:
        job_id = uuid.uuid4().hex[:12]
        directory = self.jobs_root / job_id
        directory.mkdir(parents=True)
        job = Job(
            id=job_id,
            url=url,
            media_mode=media_mode,
            title=title or None,
            transcribe=transcribe,
            language=language,
            output_dir=str(directory),
            output_format=output_format,
            quality=quality,
            embed_cover=embed_cover,
            model_profile=model_profile,
        )
        with self.lock:
            self.jobs[job.id] = job
            self._save()
        return job

    def add_local(self, filename: str, title: str | None, language: str) -> Job:
        job_id = uuid.uuid4().hex[:12]
        directory = self.jobs_root / job_id
        directory.mkdir(parents=True)
        target = directory / safe_name(filename, "upload")
        job = Job(
            id=job_id,
            url=f"local://{target.name}",
            input_path=str(target),
            title=title or Path(filename).stem,
            transcribe=True,
            language=language,
            output_dir=str(directory),
        )
        with self.lock:
            self.jobs[job.id] = job
            self._save()
        return job

    def add_local_file(self, source: Path, filename: str, title: str | None, language: str, operation: str = "transcribe", output_format: str = "mp3", bitrate: str = "192", resolution: str = "original", model_profile: str = "balanced") -> Job:
        job_id = uuid.uuid4().hex[:12]
        directory = self.jobs_root / job_id
        directory.mkdir(parents=True)
        target = directory / safe_name(Path(filename).name, "upload")
        try:
            shutil.move(str(source), str(target))
            job = Job(
                id=job_id,
                url=f"local://{target.name}",
                input_path=str(target),
                title=title or Path(filename).stem,
                transcribe=operation == "transcribe",
                language=language,
                output_dir=str(directory),
                checkpoint="uploaded",
                operation=operation,
                output_format=output_format,
                conversion_bitrate=bitrate,
                conversion_resolution=resolution,
                model_profile=model_profile,
                source_size_bytes=target.stat().st_size,
            )
            with self.lock:
                self.jobs[job.id] = job
                self._save()
            return job
        except Exception:
            target.unlink(missing_ok=True)
            directory.rmdir()
            raise

    def add_existing_file(
        self,
        source: Path,
        title: str | None,
        language: str,
        model_profile: str = "balanced",
        operation: str = "transcribe",
        output_format: str = "mp3",
        bitrate: str = "192",
        resolution: str = "original",
    ) -> Job:
        source = source.resolve()
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError("ไม่พบไฟล์สื่อที่เลือก")
        job_id = uuid.uuid4().hex[:12]
        directory = self.jobs_root / job_id
        directory.mkdir(parents=True)
        job = Job(
            id=job_id,
            url=f"library://{source.name}",
            input_path=str(source),
            title=title or source.stem,
            transcribe=operation == "transcribe",
            language=language,
            output_dir=str(directory),
            checkpoint="linked",
            operation=operation,
            model_profile=model_profile,
            source_size_bytes=source.stat().st_size,
            output_format=output_format,
            conversion_bitrate=bitrate,
            conversion_resolution=resolution,
        )
        with self.lock:
            self.jobs[job.id] = job
            self._save()
        return job

    def update(self, job: Job, **changes: Any) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = utc_now()
            self._save()

    def set_archived(self, job: Job, archived: bool) -> None:
        self.update(job, archived=archived, archived_at=utc_now() if archived else None)

    def remove(self, job_id: str) -> None:
        with self.lock:
            if job_id not in self.jobs:
                return
            del self.jobs[job_id]
            self._save()
            self.database.delete(job_id)

    def all(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)


class Worker:
    def __init__(self, store: JobStore):
        self.store = store
        self.queue: list[str] = [job.id for job in store.all() if job.status == "queued"]
        self.enqueued: set[str] = set(self.queue)
        self.current_job_id: str | None = None
        self.current_process: subprocess.Popen[str] | None = None
        self.cancel_events: dict[str, threading.Event] = {}
        self.whisper_models: dict[str, Any] = {}
        self.condition = threading.Condition()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="meeting-worker")
        self.thread.start()

    def submit(self, job: Job) -> None:
        with self.condition:
            if job.status != "queued" or job.id in self.enqueued or job.id == self.current_job_id:
                return
            self.queue.append(job.id)
            self.enqueued.add(job.id)
            self.condition.notify()

    def snapshot(self) -> dict[str, Any]:
        with self.condition:
            return {"alive": self.thread.is_alive(), "queue_depth": len(self.queue), "current_job": self.current_job_id}

    def retry(self, job: Job) -> bool:
        if job.status not in {"failed", "interrupted", "cancelled"}:
            return False
        self.store.update(job, status="queued", progress="รอลองใหม่", error=None)
        self.submit(job)
        return True

    def cancel(self, job: Job) -> bool:
        with self.condition:
            if job.id in self.enqueued:
                self.queue = [item for item in self.queue if item != job.id]
                self.enqueued.discard(job.id)
                self.store.update(job, status="cancelled", progress="ยกเลิกแล้ว")
                return True
            if job.id == self.current_job_id:
                self.cancel_events.setdefault(job.id, threading.Event()).set()
                if self.current_process and self.current_process.poll() is None:
                    self.current_process.terminate()
                return True
        return False

    def _loop(self) -> None:
        while True:
            with self.condition:
                while not self.queue:
                    self.condition.wait()
                job_id = self.queue.pop(0)
                self.enqueued.discard(job_id)
                self.current_job_id = job_id
                self.cancel_events[job_id] = threading.Event()
            job = self.store.jobs.get(job_id)
            try:
                if job and job.status == "queued":
                    self._run(job)
            finally:
                with self.condition:
                    self.cancel_events.pop(job_id, None)
                    self.current_process = None
                    self.current_job_id = None

    def _cancelled(self, job: Job) -> bool:
        return self.cancel_events.get(job.id, threading.Event()).is_set()

    def _existing_media(self, job: Job, directory: Path) -> Path | None:
        patterns = ("*.mp4", "*.mkv", "*.webm") if job.media_mode == "video" else ("*.mp3", "*.m4a", "*.wav", "*.flac")
        for pattern in patterns:
            for path in directory.glob(pattern):
                if path.is_file() and path.stat().st_size > 0:
                    return path
        return None

    def _whisper_model(self, profile: str) -> Any:
        profiles = {"fast": "small", "balanced": "medium", "high": "large-v3"}
        if profile not in profiles:
            raise RuntimeError("โปรไฟล์ Whisper ไม่รองรับ")
        model_name = os.environ.get("MEETING_WHISPER_MODEL", profiles[profile])
        if model_name not in self.whisper_models:
            from faster_whisper import WhisperModel

            cpu_threads = int(os.environ.get("MEETING_WHISPER_CPU_THREADS", "4"))
            self.whisper_models[model_name] = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, cpu_threads),
            )
        return self.whisper_models[model_name]

    def _run(self, job: Job) -> None:
        directory = Path(job.output_dir)
        try:
            if self._cancelled(job):
                raise JobCancelled()
            if job.input_path:
                audio_path = Path(job.input_path)
                if not audio_path.is_file():
                    raise RuntimeError("ไม่พบไฟล์ที่อัปโหลด")
                if job.operation == "convert":
                    self._convert(job, audio_path)
                    files = [p.name for p in directory.iterdir() if p.is_file()]
                    self.store.update(job, status="completed", checkpoint="completed", progress="แปลงไฟล์เสร็จสมบูรณ์", files=sorted(files))
                    return
            else:
                audio_path = self._existing_media(job, directory) if job.checkpoint in {"downloaded", "transcribing"} else None
                if audio_path is None:
                    from .security import UnsafeMediaURL, validate_media_url

                    direct_hosts = {item.strip() for item in os.environ.get("MEETING_DIRECT_MEDIA_HOSTS", "").split(",") if item.strip()}
                    try:
                        validate_media_url(job.url, direct_hosts=direct_hosts)
                    except UnsafeMediaURL as exc:
                        raise RuntimeError(f"URL ไม่ผ่านการตรวจสอบก่อนดาวน์โหลด: {exc}") from exc
                    self.store.update(job, status="downloading", checkpoint="downloading", progress="กำลังดาวน์โหลดเสียงและภาพปก", error=None)
                    if job.media_mode == "video":
                        self.store.update(job, progress="กำลังดาวน์โหลดวิดีโอและเสียงคุณภาพสูงสุด")
                        from .services.downloader import DownloadOptions, build_command

                        command = build_command(job.url, directory, job.title, DownloadOptions("video", job.output_format, job.quality, job.embed_cover))
                    else:
                        from .services.downloader import DownloadOptions, build_command

                        command = build_command(job.url, directory, job.title, DownloadOptions("audio", job.output_format, job.quality, job.embed_cover))
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    with self.condition:
                        self.current_process = process
                    assert process.stdout is not None
                    log_path = directory / "download.log"
                    recent_output: deque[str] = deque(maxlen=80)
                    with log_path.open("w", encoding="utf-8") as log:
                        for line in process.stdout:
                            if self._cancelled(job):
                                process.terminate()
                                raise JobCancelled()
                            log.write(line)
                            recent_output.append(line)
                            if "[download]" in line and "%" in line:
                                self.store.update(job, progress=line.strip()[-140:])
                    if process.wait() != 0:
                        if self._cancelled(job):
                            raise JobCancelled()
                        from .services.downloader import classify_download_error

                        raise RuntimeError(classify_download_error("".join(recent_output)))
                    audio_path = self._existing_media(job, directory)
                    if audio_path is None:
                        raise RuntimeError("ไม่พบไฟล์สื่อหลังดาวน์โหลด")
                    self.store.update(job, checkpoint="downloaded")
            if job.transcribe:
                self._transcribe(job, audio_path)
            files = [p.name for p in directory.iterdir() if p.is_file()]
            self.store.update(job, status="completed", checkpoint="completed", progress="เสร็จสมบูรณ์", files=sorted(files))
        except JobCancelled:
            self.store.update(job, status="cancelled", progress="ยกเลิกแล้ว", error=None)
        except Exception as exc:  # worker boundary: retain error for UI
            self.store.update(job, status="failed", progress="งานล้มเหลว", error=str(exc))

    def _convert(self, job: Job, source: Path) -> None:
        from .services.converter import ConversionOptions, build_conversion_command, output_path

        options = ConversionOptions(job.output_format, job.conversion_bitrate, job.conversion_resolution)
        target = output_path(source, Path(job.output_dir), job.output_format)
        self.store.update(job, status="converting", checkpoint="converting", progress="กำลังแปลงไฟล์", error=None)
        process = subprocess.Popen(
            build_conversion_command(source, target, options),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with self.condition:
            self.current_process = process
        log_path = Path(job.output_dir) / "conversion.log"
        assert process.stdout is not None
        with log_path.open("w", encoding="utf-8") as log:
            for line in process.stdout:
                if self._cancelled(job):
                    process.terminate()
                    target.unlink(missing_ok=True)
                    raise JobCancelled()
                log.write(line)
        if process.wait() != 0:
            target.unlink(missing_ok=True)
            raise RuntimeError("แปลงไฟล์ไม่สำเร็จ กรุณาดู conversion.log")
        if not target.is_file() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise RuntimeError("ไม่พบไฟล์ผลลัพธ์หลังแปลง")
        self.store.update(job, checkpoint="converted", progress="แปลงไฟล์แล้ว", result_size_bytes=target.stat().st_size)

    def _transcribe(self, job: Job, audio_path: Path) -> None:
        self.store.update(job, status="transcribing", checkpoint="transcribing", progress="กำลังโหลดโมเดล Whisper")
        try:
            model = self._whisper_model(job.model_profile)
        except ImportError as exc:
            raise RuntimeError("ยังไม่ได้ติดตั้ง Faster Whisper; ติดตั้ง requirements.txt ก่อน") from exc
        partial_path = Path(job.output_dir) / "transcript.partial.json"
        rows: list[dict[str, Any]] = []
        if partial_path.is_file():
            try:
                rows = json.loads(partial_path.read_text(encoding="utf-8")).get("segments", [])
            except (OSError, ValueError, TypeError):
                rows = []
        resume_at = float(rows[-1]["end"]) if rows else 0.0
        segments, info = model.transcribe(
            str(audio_path),
            language=transcription_language(job.language),
            vad_filter=True,
            clip_timestamps=[resume_at] if resume_at > 0 else "0",
        )
        for index, segment in enumerate(segments, len(rows) + 1):
            if self._cancelled(job):
                raise JobCancelled()
            text = segment.text.strip()
            rows.append({"start": segment.start, "end": segment.end, "text": text})
            temp = partial_path.with_suffix(".tmp")
            temp.write_text(json.dumps({"segments": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(partial_path)
            if index % 10 == 0:
                self.store.update(job, progress=f"ถอดเสียงแล้ว {index} ช่วง")
        from .services.exporter import export_transcript

        export_transcript(Path(job.output_dir), job.title or "รายงานการประชุม", job.url, info.language, rows, utc_now())
        partial_path.unlink(missing_ok=True)

