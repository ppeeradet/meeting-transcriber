# Personal Media Hub v2.0 — Adjusted Implementation Plan

This plan is based on the verified `03d7a59` repository and Dell runtime, not on the earlier handoff alone.

## Delivery strategy

Use one development branch, `codex/personal-media-hub`, with small commits and reviewable PR checkpoints. Do not deploy an incomplete database or queue migration. Preserve port `8765`, route `/meeting-transcriber/`, job IDs, source files, and output directories.

## Phase 0A — Safe core and regression harness

- Split configuration and security helpers out of `main.py` without changing runtime behavior.
- Add tests for URL parsing, platform detection, SSRF rejection, batch atomicity, Windows filenames, queue recovery, and API access policy.
- Add dependency-aware health reporting with no private paths or credentials.
- Bundle or install FFprobe before enabling upload content validation.

Acceptance gate: tests pass; existing two completed and one failed job remain readable; backend still binds only to loopback.

## Phase 0B — Persistent queue, retry, cancel, and checkpoints

- Re-enqueue persisted `queued` jobs once, persist interrupted transitions, and track the current job.
- Add deduplicated queue submission and explicit job checkpoints.
- Add cooperative cancellation for yt-dlp/FFmpeg and between transcription segments.
- Add retry/resume APIs without deleting prior outputs or redownloading a valid source.
- Use indeterminate UI progress when a real percentage is unavailable.

Acceptance gate: restart, retry, cancel, duplicate prevention, and retained-output tests pass.

## Phase 0C — Atomic batch, URL and upload security

- Validate and deduplicate the complete batch before creating any job.
- Allow only supported HTTPS platforms and configured direct-media domains.
- Reject credentials, unapproved ports, loopback/private/link-local/metadata targets, unsafe DNS answers, and unsafe redirects.
- Receive uploads into a temporary file, enforce size/free-space limits, inspect with FFprobe, then create/activate the job atomically.
- Remove backend CORS for GitHub Pages and enforce trusted host/origin plus deployment-mode authentication.

Acceptance gate: SSRF, redirects, partial batch, empty/spoofed upload, and cross-site tests pass.

## Phase 1 — Universal Media Downloader

- Metadata-only preview service and platform adapters around yt-dlp.
- Audio/video format and quality profiles, cover-art controls, collision-safe naming, mixed-platform batches, and error classification.
- Test only with media the user owns or is authorized to use. Mark a platform supported only after a live test succeeds.

## Phase 2 — Media Converter

- FFprobe-based media inventory and FFmpeg command builder.
- Stream copy where possible; explicit re-encode profiles otherwise.
- Preserve sources, report before/after sizes, and route outputs to Transcriber.

## Phase 3 — SQLite library and migration

- Introduce versioned SQLite schema and idempotent migration.
- Back up `jobs.json` and the database, import existing IDs and paths, compare job/file counts, and retain `jobs.json` for rollback.
- Add search, filters, deduplication, previews, and library actions.

## Phase 4 — Transcriber

- Cache Faster Whisper models and benchmark Small, Medium, and Large v3 on Dell under a CPU budget that protects MT5 and other jobs.
- Fix auto language to `None`, add segment checkpoints, VTT/Markdown/true DOCX exports, and the transcript editor.

## Phase 5 — Responsive product UI

- Product name: Personal Media Hub; tagline: Download · Convert · Transcribe · Organize.
- Dell edition: vivid burgundy gradient shell with pastel module cards so it is visually distinct from Browser Edition.
- Browser Edition: bright pastel theme with a clear Browser Edition badge.
- Mobile-first navigation, real/indeterminate progress, recent jobs, queue counts, disk status, and touch-sized actions.

## Phase 6 — Browser Edition hardening

- Keep it fully separate from the Dell backend.
- Add decode cancellation guards, memory limits, codec errors, correct missing timestamps, real progress, and true-format export labeling.
- Test Android, iPad, and desktop; document browser-specific save-location behavior.

## Deployment

- Standardize on one autostart mechanism after verifying reboot recovery; remove the other only after the selected mechanism passes.
- Deploy only merged and tested checkpoints with a dated runtime backup and rollback instructions.
- Verify loopback listener, tailnet-only Serve, closed Funnel, Home Portal card, queue integrity, and resource impact after every deployment.
