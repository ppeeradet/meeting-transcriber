import tempfile
import unittest
from pathlib import Path

from app.core import JobStore, build_download_command, build_video_command, safe_name, srt_timestamp


class CoreTests(unittest.TestCase):
    def test_safe_name_removes_windows_invalid_chars(self):
        self.assertEqual(safe_name('  ประชุม: ทีม/ขาย?  '), 'ประชุม_ ทีม_ขาย_')

    def test_timestamp(self):
        self.assertEqual(srt_timestamp(3661.234), '01:01:01,234')

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

    def test_local_upload_job_has_safe_target(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(Path(temp))
            job = store.add_local('bad:name.mp4', None, 'th')
            self.assertTrue(job.input_path.endswith('bad_name.mp4'))
            self.assertTrue(job.transcribe)


if __name__ == '__main__':
    unittest.main()
