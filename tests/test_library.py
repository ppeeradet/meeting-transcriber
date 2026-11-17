import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import JobStore
from app import main as main_module
from fastapi import HTTPException


class MediaLibraryTests(unittest.TestCase):
    def test_search_and_status_filters(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            first = store.add("https://www.youtube.com/watch?v=demo", "ประชุมทีม", False, "th")
            second = store.add("https://vimeo.com/123", "คลิปอื่น", False, "th", media_mode="video")
            store.update(second, status="failed")
            with patch.object(main_module, "store", store):
                self.assertEqual([item["id"] for item in main_module.jobs(search="ประชุม")], [first.id])
                self.assertEqual([item["id"] for item in main_module.jobs(status="failed")], [second.id])
                self.assertEqual(main_module.jobs(platform="YouTube")[0]["platform"], "YouTube")
                self.assertEqual(main_module.jobs(media_type="video")[0]["id"], second.id)

    def test_library_media_can_be_sent_to_transcriber_without_download(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            source_job = store.add("https://youtu.be/demo", "ประชุม", False, "th")
            media = Path(source_job.output_dir) / "result.mp3"
            media.write_bytes(b"media")
            request = main_module.LibraryTranscription(filename="result.mp3", language="th", model_profile="fast")
            with patch.object(main_module, "store", store), patch.object(main_module, "probe_media", return_value={"has_audio": True}), patch.object(main_module.worker, "submit") as submit:
                result = main_module.transcribe_library_file(source_job.id, request)
            self.assertEqual(Path(result["input_path"]), media.resolve())
            self.assertEqual(result["model_profile"], "fast")
            submit.assert_called_once()

    def test_library_transcription_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            source_job = store.add("https://youtu.be/demo", "ประชุม", False, "th")
            request = main_module.LibraryTranscription(filename="../outside.mp3", language="th", model_profile="fast")
            with patch.object(main_module, "store", store), self.assertRaises(HTTPException) as caught:
                main_module.transcribe_library_file(source_job.id, request)
            self.assertEqual(caught.exception.status_code, 404)

    def test_library_media_can_be_converted_without_copying_source(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            source_job = store.add("https://youtu.be/demo", "ประชุม", False, "th")
            media = Path(source_job.output_dir) / "result.mp4"
            media.write_bytes(b"media")
            request = main_module.LibraryConversion(filename="result.mp4", output_format="mp3", bitrate="256", resolution="original")
            with patch.object(main_module, "store", store), patch.object(main_module, "probe_media", return_value={"has_audio": True, "has_video": True}), patch.object(main_module.worker, "submit") as submit:
                result = main_module.convert_library_file(source_job.id, request)
            self.assertEqual(Path(result["input_path"]), media.resolve())
            self.assertEqual(result["operation"], "convert")
            self.assertEqual(result["output_format"], "mp3")
            self.assertEqual(result["conversion_bitrate"], "256")
            self.assertTrue(media.is_file())
            submit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
