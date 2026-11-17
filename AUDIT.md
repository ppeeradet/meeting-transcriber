# Personal Media Hub v2.0 — Repository and Runtime Audit

Audit date: 2026-11-17 (Asia/Bangkok)  
Audited baseline: `origin/main` at `03d7a59`

## Verified repository state

- Repository: `ppeeradet/meeting-transcriber`
- Development branch: `codex/personal-media-hub`
- No open pull requests at the start of this audit.
- The repository is small and currently combines the job model, JSON persistence, queue, downloader, transcriber, and DOCX export in `app/core.py`.
- The API, authentication switch, CORS, upload handling, and static hosting are combined in `app/main.py`.
- Six unit tests existed and passed. They cover naming, timestamps, command construction, JSON round-trip, and local upload naming; they do not cover API security, recovery, retry/cancel, or real media processing.
- No repository-specific `OPERATIONS.md`, `GIT_WORKFLOW.md`, or `AGENTS.md` was present in this checkout.

## Verified Dell runtime

- Install root: `C:\MeetingTranscriber`
- Listener: `127.0.0.1:8765`
- Home Portal route: `/meeting-transcriber`
- Tailscale Serve is tailnet-only. Public Funnel is not enabled.
- Autostart currently uses the HKCU `Run` value `MeetingTranscriber`; the repository also contains a Scheduled Task installer, but a MeetingTranscriber Scheduled Task was not installed at audit time.
- Python 3.11.9; FastAPI 0.115.6; Uvicorn 0.34.0; Faster Whisper 1.1.1; yt-dlp 2026.10.26; python-docx 1.1.2.
- FFmpeg 7.1 is supplied by `imageio-ffmpeg`. FFprobe was not found and must be installed or bundled before content validation can be enforced.
- Node.js 24.20.0 and npm 11.19.0 are available.
- Drive C had approximately 160 GB free.
- Runtime queue contained three jobs: two completed and one failed. No queued or running job was present during the audit.

## Confirmed gaps and risks

1. Queued jobs are loaded from JSON but never re-enqueued after restart.
2. Running jobs become `interrupted` in memory during load, but that recovery state is not immediately persisted.
3. The queue is a list without duplicate-submission protection, cancellation, checkpoints, or a current-job record.
4. Batch URLs are validated and created sequentially, allowing partial submission before a later invalid URL fails.
5. URL validation accepts arbitrary HTTP(S), including private and loopback targets; redirects and DNS results are not checked.
6. `run_server.py` disables access-token enforcement. This is currently shielded by loopback binding and tailnet-only Serve, but it lacks explicit trusted-host/origin protection and is unsafe if routing changes.
7. CORS still names GitHub Pages even though Browser Edition no longer calls this backend.
8. Upload jobs are created before the upload completes. Empty files, actual media type, free space, reserved Windows names, and partial-upload state are not validated fully.
9. Health reports a constant OK and does not inspect the worker or dependencies.
10. Faster Whisper loads `large-v3` for every job, uses `"auto"` as a literal language, and has no resource/profile control or checkpointing.
11. Large downloads previously passed through a browser Blob. The development branch now streams to a selected file when supported and falls back to a direct download link.
12. GitHub Pages cancellation cannot interrupt `decodeAudioData`, long files can exhaust browser memory, missing SRT end timestamps are not normalized, and its Word-compatible `.doc` is not a true DOCX.

## Safety conclusion

Production should remain on the current merged release until each Phase 0 slice has tests, a PR review, a backup/rollback path, and focused Dell verification. Public Funnel must remain disabled. The existing three jobs and job directories must be preserved during JSON-to-SQLite migration.
