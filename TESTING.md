# Verification record

This file distinguishes checks that were run from checks that remain pending.

## 17 November 2026 — development branch

### Passed

- Automated tests: 42 passed with the Dell Python 3.11 runtime.
- JavaScript syntax: `static/app.js` and `docs/app.js` pass `node --check`.
- Converter smoke test with installed FFmpeg:
  - MP4 to MP3 produced a valid MP3 audio stream.
  - MP4 to MP4 preserved streams with stream copy.
  - 1280x720 input was downscaled to 640x360.
- SQLite migration rehearsal against a copy of production `jobs.json`:
  - 3 job IDs imported.
  - 8 file references imported.
  - Re-running migration did not duplicate records.
- Microsoft Word verification:
  - Word opened `meeting_report.docx` read-only and exported it to PDF.
  - Word reported 1 page, 26 paragraphs and 1 table for the sample report.
  - The rendered PDF was visually inspected; Thai text, headings and the table were legible and did not overflow.
- Browser Edition local Chrome QA:
  - Desktop layout loaded with no console errors or warnings.
  - A 390x844 mobile viewport used the single-column layout without horizontal overflow.
  - Empty-file validation displayed the expected message and progress state.

### Not yet verified

- Browser Edition transcription with a real media file and downloaded Transformers.js model.
- Physical Android and iPad browsers. A mobile Chrome viewport is not equivalent to device testing.
- Live download on Facebook, Instagram, TikTok, X, Vimeo, Dailymotion and SoundCloud.
- End-to-end transcription timing and accuracy for Small, Medium and Large v3 on Dell.
- Restart recovery and resource impact with the branch deployed as the Dell runtime.
- Home Portal route after deployment. Production remains on the previous release.
