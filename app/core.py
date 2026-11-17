from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str, fallback: str = "meeting") -> str:
    cleaned = INVALID_FILENAME.sub("_", value).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned[:120] or fallback)


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def build_download_command(url: str, output_dir: Path, title: str | None) -> list[str]:
    template = f"{safe_name(title)}.%(ext)s" if title else "%(title).120B.%(ext)s"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
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
        "--no-playlist",
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
            for job in self.jobs.values():
                if job.status in {"downloading", "transcribing"}:
                    job.status = "interrupted"
                    job.progress = "หยุดระหว่างการรีสตาร์ต — กดเริ่มใหม่"
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
        self.queue: list[str] = []
        self.condition = threading.Condition()
        threading.Thread(target=self._loop, daemon=True, name="meeting-worker").start()

    def submit(self, job: Job) -> None:
        with self.condition:
            self.queue.append(job.id)
            self.condition.notify()

    def _loop(self) -> None:
        while True:
            with self.condition:
                while not self.queue:
                    self.condition.wait()
                job_id = self.queue.pop(0)
            job = self.store.jobs.get(job_id)
            if job:
                self._run(job)

    def _run(self, job: Job) -> None:
        directory = Path(job.output_dir)
        try:
            if job.input_path:
                audio_path = Path(job.input_path)
                if not audio_path.is_file():
                    raise RuntimeError("ไม่พบไฟล์ที่อัปโหลด")
            else:
                self.store.update(job, status="downloading", progress="กำลังดาวน์โหลดเสียงและภาพปก", error=None)
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
                assert process.stdout is not None
                log_path = directory / "download.log"
                with log_path.open("w", encoding="utf-8") as log:
                    for line in process.stdout:
                        log.write(line)
                        if "[download]" in line and "%" in line:
                            self.store.update(job, progress=line.strip()[-140:])
                if process.wait() != 0:
                    raise RuntimeError("ดาวน์โหลดไม่สำเร็จ กรุณาดู download.log")
                if job.media_mode == "video":
                    media_files = [*directory.glob("*.mp4"), *directory.glob("*.mkv"), *directory.glob("*.webm")]
                    if not media_files:
                        raise RuntimeError("ไม่พบไฟล์วิดีโอหลังดาวน์โหลด")
                    audio_path = media_files[0]
                else:
                    mp3s = list(directory.glob("*.mp3"))
                    if not mp3s:
                        raise RuntimeError("ไม่พบไฟล์ MP3 หลังดาวน์โหลด")
                    audio_path = mp3s[0]
            if job.transcribe:
                self._transcribe(job, audio_path)
            files = [p.name for p in directory.iterdir() if p.is_file()]
            self.store.update(job, status="completed", progress="เสร็จสมบูรณ์", files=sorted(files))
        except Exception as exc:  # worker boundary: retain error for UI
            self.store.update(job, status="failed", progress="งานล้มเหลว", error=str(exc))

    def _transcribe(self, job: Job, audio_path: Path) -> None:
        self.store.update(job, status="transcribing", progress="กำลังโหลดโมเดล Whisper")
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("ยังไม่ได้ติดตั้ง Faster Whisper; ติดตั้ง requirements.txt ก่อน") from exc
        model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), language=job.language, vad_filter=True)
        rows: list[dict[str, Any]] = []
        txt: list[str] = []
        srt: list[str] = []
        for index, segment in enumerate(segments, 1):
            text = segment.text.strip()
            rows.append({"start": segment.start, "end": segment.end, "text": text})
            txt.append(f"[{srt_timestamp(segment.start).replace(',', '.')}] {text}")
            srt.extend([str(index), f"{srt_timestamp(segment.start)} --> {srt_timestamp(segment.end)}", text, ""])
            if index % 10 == 0:
                self.store.update(job, progress=f"ถอดเสียงแล้ว {index} ช่วง")
        audio_path.with_name("transcript.txt").write_text("\n".join(txt), encoding="utf-8")
        audio_path.with_name("transcript.srt").write_text("\n".join(srt), encoding="utf-8")
        audio_path.with_name("transcript.json").write_text(
            json.dumps({"language": info.language, "segments": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_word_documents(job, rows)

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

