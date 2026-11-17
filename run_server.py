from __future__ import annotations

import os
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.setdefault("MEETING_DEPLOYMENT_MODE", "tailnet")
os.environ.setdefault("MEETING_FFPROBE", str(ROOT / "tools" / "ffmpeg" / "ffprobe.exe"))
uvicorn.run("app.main:app", host="127.0.0.1", port=8765, log_level="info")

