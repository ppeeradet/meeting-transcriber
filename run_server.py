from __future__ import annotations

import os
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent


def main() -> None:
    os.chdir(ROOT)
    os.environ.setdefault("MEETING_DEPLOYMENT_MODE", "tailnet")
    os.environ.setdefault("MEETING_FFPROBE", str(ROOT / "tools" / "ffmpeg" / "ffprobe.exe"))
    # pythonw has no console streams. Disabling Uvicorn's console log config keeps
    # the Registry autostart process alive without requiring redirected handles.
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8765,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()

