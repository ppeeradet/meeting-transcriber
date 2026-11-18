import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import JobStore
from app import main as main_module
from fastapi import HTTPException


class MediaLibraryTests(unittest.TestCase):
    def test_job_listing_uses_actual_files_and_marks_missing_records(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "งาน", False, "th")
            actual = Path(job.output_dir) / "actual.mp3"
            actual.write_bytes(b"media")
            store.update(job, status="completed", files=["deleted.mp3"])
            with patch.object(main_module, "store", store):
                result = main_module.jobs()[0]
            self.assertEqual(result["files"], ["actual.mp3"])
            self.assertEqual(result["missing_files"], ["deleted.mp3"])
            self.assertTrue(result["folder_exists"])

    def test_copy_move_and_delete_file_use_allowlisted_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = JobStore(root / "data")
            job = store.add("https://youtu.be/demo", "งาน", False, "th")
            source = Path(job.output_dir) / "result.mp3"
            source.write_bytes(b"media")
            destination = root / "downloads"
            request = main_module.FileDestination(destination="downloads")
            allowed = {"downloads": ("Downloads", destination)}
            with patch.object(main_module, "store", store), patch.object(main_module, "FILE_DESTINATIONS", allowed):
                copied = main_module.copy_job_file(job.id, source.name, request)
                moved = main_module.move_job_file(job.id, source.name, request)
                moved_path = Path(moved["destination"])
                replacement = Path(job.output_dir) / "delete.mp3"
                replacement.write_bytes(b"delete")
                deleted = main_module.delete_job_file(job.id, replacement.name)
            self.assertTrue(Path(copied["destination"]).is_file())
            self.assertTrue(moved_path.is_file())
            self.assertFalse(source.exists())
            self.assertEqual(deleted["status"], "deleted")
            self.assertFalse(replacement.exists())

    def test_delete_empty_job_record_removes_json_and_sqlite_record(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = JobStore(root)
            job = store.add("https://youtu.be/demo", "งาน", False, "th")
            store.update(job, status="completed")
            with patch.object(main_module, "store", store):
                result = main_module.delete_job_record(job.id)
            self.assertEqual(result["status"], "deleted")
            self.assertNotIn(job.id, store.jobs)
            self.assertNotIn(job.id, JobStore(root).jobs)

    def test_delete_job_record_rejects_jobs_that_still_have_files(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "งาน", False, "th")
            (Path(job.output_dir) / "keep.mp3").write_bytes(b"media")
            store.update(job, status="completed")
            with patch.object(main_module, "store", store), self.assertRaises(HTTPException) as caught:
                main_module.delete_job_record(job.id)
            self.assertEqual(caught.exception.status_code, 409)

    def test_archived_jobs_are_hidden_by_default_and_can_be_filtered(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            active = store.add("https://youtu.be/active", "งานเปิด", False, "th")
            closed = store.add("https://youtu.be/closed", "งานปิด", False, "th")
            store.update(closed, status="completed", checkpoint="completed")
            store.set_archived(closed, True)
            with patch.object(main_module, "store", store):
                self.assertEqual([item["id"] for item in main_module.jobs()], [active.id])
                self.assertEqual([item["id"] for item in main_module.jobs(archived="closed")], [closed.id])
                self.assertEqual({item["id"] for item in main_module.jobs(archived="all")}, {active.id, closed.id})

    def test_close_and_restore_job_preserve_output_files(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "งานเสร็จ", False, "th")
            output = Path(job.output_dir) / "result.mp3"
            output.write_bytes(b"media")
            store.update(job, status="completed", checkpoint="completed", files=[output.name])
            with patch.object(main_module, "store", store):
                closed = main_module.archive_job(job.id)
                self.assertTrue(closed["archived"])
                self.assertTrue(output.is_file())
                restored = main_module.restore_job(job.id)
                self.assertFalse(restored["archived"])
                self.assertTrue(output.is_file())

    def test_close_queued_job_cancels_it_first(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add("https://youtu.be/demo", "งานรอ", False, "th")
            with patch.object(main_module, "store", store), patch.object(main_module.worker, "cancel", return_value=True) as cancel:
                result = main_module.archive_job(job.id)
            cancel.assert_called_once_with(job)
            self.assertTrue(result["archived"])

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
