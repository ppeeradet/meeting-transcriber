from __future__ import annotations

import os
import secrets
import shutil
from importlib import metadata, util
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import JobStore, Worker
from .security import UnsafeMediaURL, UnsafeRequest, validate_batch, validate_request_context


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
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {ACCESS_TOKEN}"
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "ต้องใส่รหัสเข้าถึง")


class CreateJobs(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=120)
    transcribe: bool = False
    language: str = Field(default="th", max_length=10)
    media_mode: str = Field(default="audio", pattern="^(audio|video)$")


ALLOWED_UPLOADS = {".mp3", ".mp4", ".m4a", ".wav", ".webm", ".mov", ".mkv", ".aac", ".flac", ".ogg", ".opus", ".mpeg", ".mpg"}
MAX_UPLOAD_BYTES = 4 * 1024 * 1024 * 1024


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
    dependencies = {
        "ffmpeg": ffmpeg,
        "ffprobe": shutil.which("ffprobe") is not None,
        "yt_dlp": util.find_spec("yt_dlp") is not None,
        "whisper": util.find_spec("faster_whisper") is not None,
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
def jobs() -> list[dict]:
    return [asdict(job) for job in store.all()]


@app.post("/api/jobs", status_code=202, dependencies=[Depends(require_access)])
def create_jobs(request: CreateJobs) -> list[dict]:
    direct_hosts = {item.strip() for item in os.environ.get("MEETING_DIRECT_MEDIA_HOSTS", "").split(",") if item.strip()}
    try:
        urls = validate_batch(request.urls, direct_hosts=direct_hosts)
    except UnsafeMediaURL as exc:
        raise HTTPException(400, str(exc)) from exc
    created = []
    for url in urls:
        title = request.title if len(urls) == 1 else None
        job = store.add(url, title, request.transcribe, request.language, request.media_mode)
        worker.submit(job)
        created.append(asdict(job))
    return created


@app.post("/api/uploads", status_code=202, dependencies=[Depends(require_access)])
async def upload_media(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    language: str = Form(default="th"),
) -> dict:
    filename = file.filename or "upload"
    if Path(filename).suffix.lower() not in ALLOWED_UPLOADS:
        raise HTTPException(415, "รองรับไฟล์เสียง/วิดีโอทั่วไป เช่น MP3, MP4, M4A, WAV, WEBM, MOV, MKV, AAC, FLAC, OGG")
    job = store.add_local(filename, title, language)
    target = Path(job.input_path or "")
    size = 0
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "ไฟล์ใหญ่เกิน 4 GB")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    worker.submit(job)
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

