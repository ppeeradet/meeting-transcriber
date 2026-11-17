import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document

from app.services.exporter import export_transcript


class TranscriptExporterTests(unittest.TestCase):
    def test_all_transcript_formats_and_real_docx_are_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rows = [
                {"start": 0.0, "end": 1.25, "text": "เริ่มประชุม"},
                {"start": 1.25, "end": 3.0, "text": "มติให้ดำเนินการภายในวันศุกร์"},
            ]
            files = export_transcript(root, "ประชุมทีม", "local://meeting.mp3", "th", rows, "2026-11-17T08:00:00+07:00")
            self.assertEqual(len(files), 7)
            self.assertTrue((root / "transcript.vtt").read_text(encoding="utf-8").startswith("WEBVTT"))
            self.assertIn("00:00:00.000 --> 00:00:01.250", (root / "transcript.vtt").read_text(encoding="utf-8"))
            self.assertEqual(len(json.loads((root / "transcript.json").read_text(encoding="utf-8"))["segments"]), 2)
            for filename in ("transcript_full.docx", "meeting_report.docx"):
                path = root / filename
                self.assertTrue(zipfile.is_zipfile(path))
                self.assertGreater(len(Document(path).paragraphs), 1)
            report_text = "\n".join(paragraph.text for paragraph in Document(root / "meeting_report.docx").paragraphs)
            self.assertIn("ฉบับรอตรวจทาน", report_text)


if __name__ == "__main__":
    unittest.main()
