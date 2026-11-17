import tempfile
import threading
import unittest
from pathlib import Path

from app.core import JobStore, Worker, build_download_command, build_video_command, safe_name, srt_timestamp, transcription_language


class RecordingWorker(Worker):
    def __init__(self, store):
        self.ran = threading.Event()
        self.ran_job = None
        super().__init__(store)

    def _run(self, job):
        self.ran_job = job.id
        self.store.update(job, status="completed", checkpoint="completed")
        self.ran.set()


class CoreTests(unittest.TestCase):
    def make_paused_worker(self, store, queued=None):
        worker = Worker.__new__(Worker)
        worker.store = store
        worker.queue = list(queued or [])
        worker.enqueued = set(worker.queue)
        worker.current_job_id = None
        worker.current_process = None
        worker.cancel_events = {}
        worker.condition = threading.Condition()
        return worker

    def test_safe_name_removes_windows_invalid_chars(self):
        self.assertEqual(safe_name('  ประชุม: ทีม/ขาย?  '), 'ประชุม_ ทีม_ขาย_')
        self.assertEqual(safe_name('CON.mp3'), '_CON.mp3')

    def test_timestamp(self):
        self.assertEqual(srt_timestamp(3661.234), '01:01:01,234')
        self.assertIsNone(transcription_language('auto'))
        self.assertEqual(transcription_language('TH'), 'th')

    def test_download_command_keeps_original_and_cover(self):
        command = build_download_command('https://example.com/video', Path('out'), 'ชื่อประชุม')
        self.assertIn('-k', command)
        self.assertIn('--embed-thumbnail', command)
        self.assertEqual(command[-1], 'https://example.com/video')

    def test_video_command_uses_best_video_and_audio(self):
        command = build_video_command('https://example.com/video', Path('out'), 'คลิปเต็ม')
        self.assertIn('bv*+ba/b', command)
        self.assertIn('--merge-output-format', command)
        self.assertIn('mp4', command)

    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add('https://example.com/video', 'demo', False, 'th')
            loaded = JobStore(Path(temp))
            self.assertEqual(loaded.jobs[job.id].title, 'demo')

    def test_worker_recovers_queued_job_once(self):
        with tempfile.TemporaryDirectory() as temp:
            first = JobStore(Path(temp))
            job = first.add('https://youtu.be/demo', 'demo', False, 'th')
            loaded = JobStore(Path(temp))
            worker = RecordingWorker(loaded)
            self.assertTrue(worker.ran.wait(2))
            self.assertEqual(worker.ran_job, job.id)
            worker.submit(loaded.jobs[job.id])
            self.assertEqual(worker.snapshot()["queue_depth"], 0)

    def test_interrupted_transition_is_persisted(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add('https://youtu.be/demo', 'demo', False, 'th')
            store.update(job, status='downloading', checkpoint='downloading')
            recovered = JobStore(Path(temp))
            self.assertEqual(recovered.jobs[job.id].status, 'interrupted')
            reloaded = JobStore(Path(temp))
            self.assertEqual(reloaded.jobs[job.id].status, 'interrupted')

    def test_cancel_queued_job_and_retry_without_deleting_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add('https://youtu.be/demo', 'demo', False, 'th')
            output = Path(job.output_dir) / 'existing.mp3'
            output.write_bytes(b'audio')
            worker = self.make_paused_worker(store, [job.id])
            self.assertTrue(worker.cancel(job))
            self.assertEqual(job.status, 'cancelled')
            self.assertTrue(output.exists())
            self.assertTrue(worker.retry(job))
            self.assertEqual(job.status, 'queued')
            self.assertEqual(worker.queue, [job.id])
            self.assertTrue(output.exists())

    def test_local_upload_job_has_safe_target(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add_local('bad:name.mp4', None, 'th')
            self.assertTrue(job.input_path.endswith('bad_name.mp4'))
            self.assertTrue(job.transcribe)

    def test_local_file_job_is_created_after_move(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'incoming.part'
            source.write_bytes(b'media')
            store = JobStore(root / 'data')
            job = store.add_local_file(source, 'CON.mp3', None, 'th')
            self.assertFalse(source.exists())
            self.assertTrue(Path(job.input_path).is_file())
            self.assertEqual(Path(job.input_path).name, '_CON.mp3')


if __name__ == '__main__':
    unittest.main()
