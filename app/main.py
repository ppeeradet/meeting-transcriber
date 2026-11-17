from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import uuid
import importlib
import json
from importlib import metadata
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .core import JobStore, Worker, utc_now
from .media import MediaValidationError, probe_media
from .security import UnsafeMediaURL, UnsafeRequest, validate_batch, validate_bearer_token, validate_request_context
from .services.downloader import DownloadOptions, platform_name, preview
from .services.converter import ConversionOptions


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MEETING_TRANSCRIBER_DATA", BASE_DIR / "data"))
TOKEN_PATH = DATA_DIR / "access-token.txt"
DATA_DIR.mkdir(parents=True, exist_ok=True)
if not TOKEN_PATH.exists():
    TOKEN_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
ACCESS_TOKEN = os.environ.get("MEETING_TRANSCRIBER_TOKEN", TOKEN_PATH.read_text(encoding="utf-8").strip())
DEPLOYMENT_MODE = os.environ.get("MEETING_DEPLOYMENT_MODE", "token").strip().lower()
PUBLIC_ORIGIN = os.environ.get("MEETING_PUBLIC_ORIGIN", "https://dell-pc.tail187694.ts.net")
store = JobStore(DATA_DIR)
worker = Worker(store)
app = FastAPI(title="Personal Media Hub", version="2.0.0-dev")
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "dell-pc.tail187694.ts.net", "testserver"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def require_access(request: Request) -> None:
    try:
        validate_request_context(
            DEPLOYMENT_MODE,
            request.client.host if request.client else "",
            request.headers.get("host", ""),
            request.headers.get("origin"),
            PUBLIC_ORIGIN,
        )
    except UnsafeRequest as exc:
        raise HTTPException(403, str(exc)) from exc
    if DEPLOYMENT_MODE == "tailnet":
        return
    try:
        validate_bearer_token(request.headers.get("authorization", ""), ACCESS_TOKEN)
    except UnsafeRequest as exc:
        raise HTTPException(401, str(exc)) from exc


class CreateJobs(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=120)
    transcribe: bool = False
    language: str = Field(default="th", max_length=10)
    media_mode: str = Field(default="audio", pattern="^(audio|video)$")
    output_format: str = Field(default="mp3", pattern="^(original|mp3|m4a|wav|flac|mp4)$")
    quality: str = Field(default="v0", pattern="^(v0|320|256|192|128|best|1080|720|480|360)$")
    embed_cover: bool = True
    model_profile: str = Field(default="balanced", pattern="^(fast|balanced|high)$")


class PreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class TranscriptSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=20_000)


class TranscriptUpdate(BaseModel):
    language: str = Field(default="auto", max_length=20)
    segments: list[TranscriptSegment] = Field(max_length=100_000)


class LibraryTranscription(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    language: str = Field(default="th", pattern="^(th|en|auto)$")
    model_profile: str = Field(default="balanced", pattern="^(fast|balanced|high)$")


ALLOWED_UPLOADS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".mov", ".mkv", ".aac", ".flac", ".ogg", ".opus", ".mpeg", ".mpg"}
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024
MIN_FREE_RESERVE_BYTES = 2 * 1024 * 1024 * 1024


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, Any]:
    ffmpeg = False
    try:
        import imageio_ffmpeg

        ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
    except (ImportError, RuntimeError):
        pass
    def import_ready(module: str) -> bool:
        try:
            importlib.import_module(module)
            return True
        except Exception:
            return False

    dependencies = {
        "ffmpeg": ffmpeg,
        "ffprobe": bool((probe := os.environ.get("MEETING_FFPROBE") or shutil.which("ffprobe")) and Path(probe).is_file()),
        "yt_dlp": import_ready("yt_dlp"),
        "whisper": import_ready("faster_whisper"),
        "javascript_runtime": shutil.which("node") is not None,
    }
    disk = shutil.disk_usage(DATA_DIR)
    queue = worker.snapshot()
    return {
        "status": "ok" if all(dependencies.values()) else "degraded",
        "backend": True,
        "worker": queue["alive"],
        "dependencies": dependencies,
        "free_disk_bytes": disk.free,
        "queue_depth": queue["queue_depth"],
        "current_job": queue["current_job"],
        "version": app.version,
        "yt_dlp_version": metadata.version("yt-dlp") if dependencies["yt_dlp"] else None,
    }


@app.get("/api/jobs", dependencies=[Depends(require_access)])
def jobs(
    search: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    media_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    results: list[dict] = []
    needle = (search or "").strip().casefold()
    for job in store.all():
        item = asdict(job)
        item_platform = "Local File" if job.url.startswith("local://") else platform_name(job.url)
        if needle and needle not in f"{job.title or ''} {job.url}".casefold():
            continue
        if status and job.status != status:
            continue
        if platform and item_platform.casefold() != platform.casefold():
            continue
        if media_type and job.media_mode != media_type and job.operation != media_type:
            continue
        if date_from and job.created_at[:10] < date_from:
            continue
        if date_to and job.created_at[:10] > date_to:
            continue
        item["platform"] = item_platform
        results.append(item)
    return results


@app.post("/api/jobs", status_code=202, dependencies=[Depends(require_access)])
def create_jobs(request: CreateJobs) -> list[dict]:
    direct_hosts = {item.strip() for item in os.environ.get("MEETING_DIRECT_MEDIA_HOSTS", "").split(",") if item.strip()}
    try:
        urls = validate_batch(request.urls, direct_hosts=direct_hosts)
    except UnsafeMediaURL as exc:
        raise HTTPException(400, str(exc)) from exc
    try:
        DownloadOptions(request.media_mode, request.output_format, request.quality, request.embed_cover).validate()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    created = []
    for url in urls:
        title = request.title if len(urls) == 1 else None
        job = store.add(url, title, request.transcribe, request.language, request.media_mode, request.output_format, request.quality, request.embed_cover, request.model_profile)
        worker.submit(job)
        created.append(asdict(job))
    return created


@app.post("/api/preview", dependencies=[Depends(require_access)])
def preview_media(request: PreviewRequest) -> dict:
    direct_hosts = {item.strip() for item in os.environ.get("MEETING_DIRECT_MEDIA_HOSTS", "").split(",") if item.strip()}
    try:
        url = validate_batch([request.url], direct_hosts=direct_hosts)[0]
        return preview(url)
    except UnsafeMediaURL as exc:
        raise HTTPException(400, str(exc)) from exc
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(422, f"ไม่สามารถ Preview ได้: {exc}") from exc


@app.post("/api/uploads", status_code=202, dependencies=[Depends(require_access)])
async def upload_media(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    language: str = Form(default="th"),
    model_profile: str = Form(default="balanced"),
) -> dict:
    if model_profile not in {"fast", "balanced", "high"}:
        raise HTTPException(400, "โปรไฟล์ Whisper ไม่รองรับ")
    filename = file.filename or "upload"
    if Path(filename).suffix.lower() not in ALLOWED_UPLOADS:
        raise HTTPException(415, "รองรับไฟล์เสียง/วิดีโอทั่วไป เช่น MP3, MP4, M4A, WAV, WEBM, MOV, MKV, AAC, FLAC, OGG")
    upload_root = DATA_DIR / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / f"{uuid.uuid4().hex}.part"
    size = 0
    try:
        if shutil.disk_usage(DATA_DIR).free <= MIN_FREE_RESERVE_BYTES:
            raise HTTPException(507, "พื้นที่ดิสก์เหลือน้อยเกินไป")
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "ไฟล์ใหญ่เกิน 4 GB")
                if shutil.disk_usage(DATA_DIR).free <= MIN_FREE_RESERVE_BYTES:
                    raise HTTPException(507, "พื้นที่ดิสก์ไม่เพียงพอสำหรับไฟล์นี้")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "ไม่รับไฟล์ว่าง")
        try:
            probe_media(target)
        except MediaValidationError as exc:
            raise HTTPException(415, str(exc)) from exc
        job = store.add_local_file(target, filename, title, language, model_profile=model_profile)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    worker.submit(job)
    return asdict(job)


@app.get("/api/jobs/{job_id}/transcript", dependencies=[Depends(require_access)])
def get_transcript(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    path = Path(job.output_dir) / "transcript.json"
    if not path.is_file():
        raise HTTPException(404, "งานนี้ยังไม่มีผลถอดเสียง")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(500, "ไฟล์ถอดเสียงเสียหาย") from exc


@app.put("/api/jobs/{job_id}/transcript", dependencies=[Depends(require_access)])
def update_transcript(job_id: str, request: TranscriptUpdate) -> dict:
    from .services.exporter import export_transcript

    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    rows = [segment.model_dump() for segment in request.segments]
    for index, row in enumerate(rows, 1):
        if row["end"] < row["start"]:
            raise HTTPException(400, f"ช่วงที่ {index}: เวลาสิ้นสุดต้องไม่น้อยกว่าเวลาเริ่ม")
    store.update(job, status="exporting", checkpoint="exporting", progress="กำลังสร้างไฟล์จากข้อความที่แก้ไข")
    try:
        export_transcript(Path(job.output_dir), job.title or "รายงานการประชุม", job.url, request.language, rows, utc_now())
        files = sorted(path.name for path in Path(job.output_dir).iterdir() if path.is_file())
        store.update(job, status="completed", checkpoint="completed", progress="บันทึกข้อความและสร้างเอกสารแล้ว", files=files)
    except Exception as exc:
        store.update(job, status="failed", progress="สร้างเอกสารไม่สำเร็จ", error=str(exc))
        raise HTTPException(500, "สร้างเอกสารไม่สำเร็จ") from exc
    return asdict(job)


@app.post("/api/conversions", status_code=202, dependencies=[Depends(require_access)])
async def convert_media(
    file: UploadFile = File(...),
    output_format: str = Form(...),
    bitrate: str = Form(default="192"),
    resolution: str = Form(default="original"),
    title: str | None = Form(default=None),
) -> dict:
    try:
        ConversionOptions(output_format, bitrate, resolution).validate()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    filename = file.filename or "upload"
    if Path(filename).suffix.lower() not in ALLOWED_UPLOADS:
        raise HTTPException(415, "ชนิดไฟล์ต้นทางไม่รองรับ")
    upload_root = DATA_DIR / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / f"{uuid.uuid4().hex}.part"
    size = 0
    try:
        if shutil.disk_usage(DATA_DIR).free <= MIN_FREE_RESERVE_BYTES:
            raise HTTPException(507, "พื้นที่ดิสก์เหลือน้อยเกินไป")
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "ไฟล์ใหญ่เกิน 4 GB")
                if shutil.disk_usage(DATA_DIR).free <= MIN_FREE_RESERVE_BYTES:
                    raise HTTPException(507, "พื้นที่ดิสก์ไม่เพียงพอสำหรับไฟล์นี้")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "ไม่รับไฟล์ว่าง")
        try:
            probe_media(target)
        except MediaValidationError as exc:
            raise HTTPException(415, str(exc)) from exc
        job = store.add_local_file(target, filename, title, "auto", "convert", output_format, bitrate, resolution)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    worker.submit(job)
    return asdict(job)


@app.post("/api/jobs/{job_id}/retry", status_code=202, dependencies=[Depends(require_access)])
def retry_job(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    if not worker.retry(job):
        raise HTTPException(409, "งานสถานะนี้ไม่สามารถลองใหม่ได้")
    return asdict(job)


@app.post("/api/jobs/{job_id}/transcribe", status_code=202, dependencies=[Depends(require_access)])
def transcribe_library_file(job_id: str, request: LibraryTranscription) -> dict:
    source_job = store.jobs.get(job_id)
    if not source_job:
        raise HTTPException(404, "ไม่พบงานต้นทาง")
    source_root = Path(source_job.output_dir).resolve()
    source = (source_root / request.filename).resolve()
    if source.parent != source_root or source.suffix.lower() not in ALLOWED_UPLOADS or not source.is_file():
        raise HTTPException(404, "ไม่พบไฟล์สื่อที่เลือก")
    try:
        probe_media(source)
        job = store.add_existing_file(source, source_job.title or source.stem, request.language, request.model_profile)
    except (MediaValidationError, ValueError) as exc:
        raise HTTPException(415, str(exc)) from exc
    worker.submit(job)
    return asdict(job)


@app.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(require_access)])
def cancel_job(job_id: str) -> dict:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    if not worker.cancel(job):
        raise HTTPException(409, "งานนี้ไม่ได้อยู่ในคิวหรือกำลังทำงาน")
    return asdict(job)


@app.get("/api/jobs/{job_id}/files/{filename}", dependencies=[Depends(require_access)])
def download_file(job_id: str, filename: str) -> FileResponse:
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "ไม่พบงาน")
    target = (Path(job.output_dir) / filename).resolve()
    if target.parent != Path(job.output_dir).resolve() or not target.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    return FileResponse(target, filename=target.name)

