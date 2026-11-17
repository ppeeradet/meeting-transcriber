from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    template = f"{safe_name(title)}.%(ext)s" if title else "%(title).120B.%(ext)s"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--no-playlist",
        "--socket-timeout",
        "30",
        "--newline",
        "-f",
        "bestaudio/best",
        "-x",
        "-k",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--embed-thumbnail",
        "--add-metadata",
        "--windows-filenames",
        "-o",
        str(output_dir / template),
    ]
    try:
        import imageio_ffmpeg

        command.extend(["--ffmpeg-location", imageio_ffmpeg.get_ffmpeg_exe()])
    except ImportError:
        pass
    command.append(url)
    return command


def build_video_command(url: str, output_dir: Path, title: str | None) -> list[str]:
    template = f"{safe_name(title)}.%(ext)s" if title else "%(title).120B.%(ext)s"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--no-playlist",
        "--socket-timeout",
        "30",
        "--newline",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--add-metadata",
        "--windows-filenames",
        "-o",
        str(output_dir / template),
    ]
    try:
        import imageio_ffmpeg

        command.extend(["--ffmpeg-location", imageio_ffmpeg.get_ffmpeg_exe()])
    except ImportError:
        pass
    command.append(url)
    return command


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
        self.jobs: dict[str, Job] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self.jobs = {item["id"]: Job(**item) for item in payload}
            changed = False
            for job in self.jobs.values():
                if job.status in {"downloading", "transcribing"}:
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

    def add(self, url: str, title: str | None, transcribe: bool, language: str, media_mode: str = "audio") -> Job:
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

    def add_local_file(self, source: Path, filename: str, title: str | None, language: str) -> Job:
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
                transcribe=True,
                language=language,
                output_dir=str(directory),
                checkpoint="uploaded",
            )
            with self.lock:
                self.jobs[job.id] = job
                self._save()
            return job
        except Exception:
            target.unlink(missing_ok=True)
            directory.rmdir()
            raise

    def update(self, job: Job, **changes: Any) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = utc_now()
            self._save()

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

    def _whisper_model(self) -> Any:
        model_name = os.environ.get("MEETING_WHISPER_MODEL", "large-v3")
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
                        command = build_video_command(job.url, directory, job.title)
                    else:
                        command = build_download_command(job.url, directory, job.title)
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
                    with log_path.open("w", encoding="utf-8") as log:
                        for line in process.stdout:
                            if self._cancelled(job):
                                process.terminate()
                                raise JobCancelled()
                            log.write(line)
                            if "[download]" in line and "%" in line:
                                self.store.update(job, progress=line.strip()[-140:])
                    if process.wait() != 0:
                        if self._cancelled(job):
                            raise JobCancelled()
                        raise RuntimeError("ดาวน์โหลดไม่สำเร็จ กรุณาดู download.log")
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

    def _transcribe(self, job: Job, audio_path: Path) -> None:
        self.store.update(job, status="transcribing", checkpoint="transcribing", progress="กำลังโหลดโมเดล Whisper")
        try:
            model = self._whisper_model()
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
        txt: list[str] = []
        srt: list[str] = []
        for row in rows:
            txt.append(f"[{srt_timestamp(row['start']).replace(',', '.')}] {row['text']}")
            srt.extend([str(len(srt) // 4 + 1), f"{srt_timestamp(row['start'])} --> {srt_timestamp(row['end'])}", row["text"], ""])
        for index, segment in enumerate(segments, len(rows) + 1):
            if self._cancelled(job):
                raise JobCancelled()
            text = segment.text.strip()
            rows.append({"start": segment.start, "end": segment.end, "text": text})
            txt.append(f"[{srt_timestamp(segment.start).replace(',', '.')}] {text}")
            srt.extend([str(index), f"{srt_timestamp(segment.start)} --> {srt_timestamp(segment.end)}", text, ""])
            temp = partial_path.with_suffix(".tmp")
            temp.write_text(json.dumps({"segments": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(partial_path)
            if index % 10 == 0:
                self.store.update(job, progress=f"ถอดเสียงแล้ว {index} ช่วง")
        audio_path.with_name("transcript.txt").write_text("\n".join(txt), encoding="utf-8")
        audio_path.with_name("transcript.srt").write_text("\n".join(srt), encoding="utf-8")
        audio_path.with_name("transcript.json").write_text(
            json.dumps({"language": info.language, "segments": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_word_documents(job, rows)
        partial_path.unlink(missing_ok=True)

    def _write_word_documents(self, job: Job, rows: list[dict[str, Any]]) -> None:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Inches, Pt

        directory = Path(job.output_dir)
        title = job.title or "รายงานการประชุม"

        transcript = Document()
        section = transcript.sections[0]
        section.top_margin = section.bottom_margin = Inches(0.7)
        heading = transcript.add_heading(title, 0)
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        transcript.add_paragraph(f"ต้นทาง: {job.url}")
        transcript.add_paragraph(f"ภาษา: {job.language} | สร้างเมื่อ: {utc_now()}")
        transcript.add_heading("ถอดเสียงฉบับเต็ม", level=1)
        for row in rows:
            paragraph = transcript.add_paragraph()
            timestamp = paragraph.add_run(f"[{srt_timestamp(row['start']).replace(',', '.')}] ")
            timestamp.bold = True
            timestamp.font.size = Pt(9)
            paragraph.add_run(row["text"])
        transcript.save(directory / "transcript_full.docx")

        report = Document()
        report.sections[0].top_margin = report.sections[0].bottom_margin = Inches(0.7)
        report_heading = report.add_heading("รายงานการประชุม", 0)
        report_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        table = report.add_table(rows=5, cols=2)
        table.style = "Table Grid"
        metadata = [
            ("ชื่อการประชุม", title),
            ("วันและเวลา", "กรุณาตรวจสอบ/กรอกข้อมูล"),
            ("สถานที่/ช่องทาง", job.url),
            ("ประธาน/ผู้จัด", "กรุณาตรวจสอบ/กรอกข้อมูล"),
            ("ผู้เข้าร่วม", "กรุณาตรวจสอบ/กรอกข้อมูล"),
        ]
        for row, (label, value) in zip(table.rows, metadata):
            row.cells[0].text = label
            row.cells[1].text = value
        decisions = [r["text"] for r in rows if any(k in r["text"] for k in ("มติ", "ตกลง", "สรุปว่า"))]
        actions = [r["text"] for r in rows if any(k in r["text"] for k in ("มอบหมาย", "ดำเนินการ", "รับผิดชอบ", "ภายใน", "กำหนด"))]
        for heading_text, items in (("วาระและประเด็นสำคัญ", []), ("มติที่ประชุม (รอตรวจทาน)", decisions), ("งานที่มอบหมาย (รอตรวจทาน)", actions)):
            report.add_heading(heading_text, level=1)
            if items:
                for item in items:
                    report.add_paragraph(item, style="List Bullet")
            else:
                report.add_paragraph("กรุณาตรวจสอบและสรุปจากถอดเสียงฉบับเต็ม")
        report.add_heading("ภาคผนวก: ถอดเสียงพร้อมเวลา", level=1)
        for row in rows:
            report.add_paragraph(f"[{srt_timestamp(row['start']).replace(',', '.')}] {row['text']}")
        report.save(directory / "meeting_report.docx")

