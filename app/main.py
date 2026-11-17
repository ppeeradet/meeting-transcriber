from __future__ import annotations

import os
import secrets
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .core import JobStore, Worker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MEETING_TRANSCRIBER_DATA", BASE_DIR / "data"))
TOKEN_PATH = DATA_DIR / "access-token.txt"
DATA_DIR.mkdir(parents=True, exist_ok=True)
if not TOKEN_PATH.exists():
    TOKEN_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
ACCESS_TOKEN = os.environ.get("MEETING_TRANSCRIBER_TOKEN", TOKEN_PATH.read_text(encoding="utf-8").strip())
REQUIRE_ACCESS = os.environ.get("MEETING_REQUIRE_ACCESS", "1").strip().lower() not in {"0", "false", "no"}
store = JobStore(DATA_DIR)
worker = Worker(store)
app = FastAPI(title="Meeting Transcriber", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ppeeradet.github.io", "https://dell-pc.tail187694.ts.net"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def require_access(request: Request) -> None:
    if not REQUIRE_ACCESS:
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
def health() -> dict[str, str]:
    return {"status": "ok", "service": "meeting-transcriber", "version": "1.0.0"}


@app.get("/api/jobs", dependencies=[Depends(require_access)])
def jobs() -> list[dict]:
    return [asdict(job) for job in store.all()]


@app.post("/api/jobs", status_code=202, dependencies=[Depends(require_access)])
def create_jobs(request: CreateJobs) -> list[dict]:
    created = []
    for index, raw_url in enumerate(request.urls, 1):
        url = raw_url.strip()
        if not url.startswith(("https://", "http://")):
            raise HTTPException(400, f"URL ลำดับที่ {index} ไม่ถูกต้อง")
        title = request.title if len(request.urls) == 1 else None
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

