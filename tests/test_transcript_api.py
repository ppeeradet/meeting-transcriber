import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app import main as main_module
from app.core import JobStore


class TranscriptApiTests(unittest.TestCase):
    def test_editor_saves_segments_and_regenerates_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "ประชุม", True, "th")
            request = main_module.TranscriptUpdate(
                language="th",
                segments=[main_module.TranscriptSegment(start=0, end=1.5, text="แก้ไขข้อความแล้ว")],
            )
            with patch.object(main_module, "store", store):
                result = main_module.update_transcript(job.id, request)
                loaded = main_module.get_transcript(job.id)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(loaded["segments"][0]["text"], "แก้ไขข้อความแล้ว")
            self.assertTrue((Path(job.output_dir) / "meeting_report.docx").is_file())
            self.assertIn("transcript.vtt", result["files"])

    def test_editor_rejects_invalid_segment_time(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "ประชุม", True, "th")
            request = main_module.TranscriptUpdate(
                language="th",
                segments=[main_module.TranscriptSegment(start=2, end=1, text="เวลาไม่ถูกต้อง")],
            )
            with patch.object(main_module, "store", store), self.assertRaises(HTTPException) as caught:
                main_module.update_transcript(job.id, request)
            self.assertEqual(caught.exception.status_code, 400)
            self.assertFalse((Path(job.output_dir) / "transcript.json").exists())

    def test_get_transcript_rejects_corrupt_json(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "ประชุม", True, "th")
            (Path(job.output_dir) / "transcript.json").write_text("not-json", encoding="utf-8")
            with patch.object(main_module, "store", store), self.assertRaises(HTTPException) as caught:
                main_module.get_transcript(job.id)
            self.assertEqual(caught.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()
