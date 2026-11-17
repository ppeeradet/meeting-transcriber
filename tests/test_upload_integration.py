import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException


TEST_ROOT = Path(tempfile.mkdtemp(prefix="media-hub-upload-test-"))
os.environ["MEETING_TRANSCRIBER_DATA"] = str(TEST_ROOT)

from app import main as main_module  # noqa: E402


def tearDownModule():
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


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
        self.original_probe = main_module.probe_media
        self.original_submit = main_module.worker.submit
        main_module.probe_media = lambda path: {"has_audio": True, "has_video": False, "duration": 1.0}
        main_module.worker.submit = lambda job: None

    def tearDown(self):
        main_module.probe_media = self.original_probe
        main_module.worker.submit = self.original_submit

    def test_upload_creates_job_only_after_complete_file(self):
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
