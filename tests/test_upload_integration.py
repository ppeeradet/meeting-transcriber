import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.core import JobStore

from app import main as main_module


class FakeUpload:
    def __init__(self, content: bytes, filename: str):
        self.content = content
        self.filename = filename
        self.sent = False

    async def read(self, size: int) -> bytes:
        if self.sent:
            return b""
        self.sent = True
        return self.content

    async def close(self) -> None:
        return None


def run_immediate(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("Test coroutine unexpectedly yielded to an event loop")


class UploadIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(tempfile.mkdtemp(prefix="media-hub-upload-test-"))
        self.original_store = main_module.store
        self.original_probe = main_module.probe_media
        self.original_submit = main_module.worker.submit
        main_module.store = JobStore(self.test_root)
        main_module.probe_media = lambda path: {"has_audio": True, "has_video": False, "duration": 1.0}
        main_module.worker.submit = lambda job: None

    def tearDown(self):
        main_module.store = self.original_store
        main_module.probe_media = self.original_probe
        main_module.worker.submit = self.original_submit
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_upload_creates_job_only_after_complete_file(self):
        self.assertEqual(main_module.store.root.resolve(), self.test_root.resolve())
        upload = FakeUpload(b"valid-media", "เสียงประชุม.mp3")
        payload = run_immediate(main_module.upload_media(upload, title="ประชุม", language="th", model_profile="balanced"))
        target = Path(payload["input_path"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), b"valid-media")
        self.assertEqual(payload["checkpoint"], "uploaded")

    def test_empty_upload_is_rejected_without_job(self):
        before = len(main_module.store.jobs)
        upload = FakeUpload(b"", "empty.mp3")
        with self.assertRaises(HTTPException) as caught:
            run_immediate(main_module.upload_media(upload, title=None, language="th", model_profile="balanced"))
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(len(main_module.store.jobs), before)
