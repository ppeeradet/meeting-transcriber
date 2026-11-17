import unittest
from pathlib import Path

from app.services.downloader import DownloadOptions, build_command, parse_preview, platform_name, preview_command


class DownloaderTests(unittest.TestCase):
    def test_audio_profiles(self):
        mp3 = build_command("https://youtu.be/demo", Path("out"), "ชื่อ", DownloadOptions("audio", "mp3", "320", True))
        self.assertIn("320K", mp3)
        self.assertIn("--embed-thumbnail", mp3)
        original = build_command("https://soundcloud.com/demo/track", Path("out"), None, DownloadOptions("audio", "original", "v0", False))
        self.assertNotIn("--audio-format", original)
        self.assertNotIn("--embed-thumbnail", original)

    def test_video_profile_never_upscales(self):
        command = build_command("https://youtu.be/demo", Path("out"), None, DownloadOptions("video", "mp4", "720", False))
        self.assertIn("bv*[height<=720]+ba/b[height<=720]", command)
        self.assertIn("--merge-output-format", command)

    def test_invalid_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "คุณภาพ MP3"):
            DownloadOptions("audio", "mp3", "999", True).validate()

    def test_preview_is_metadata_only_and_sanitized(self):
        command = preview_command("https://vimeo.com/demo")
        self.assertIn("--skip-download", command)
        self.assertIn("--dump-single-json", command)
        result = parse_preview({
            "title": "Demo", "thumbnail": "https://img.example/a.jpg", "uploader": "Owner",
            "duration": 12, "formats": [{"format_id": "1", "ext": "mp4", "height": 720, "vcodec": "h264", "acodec": "aac", "url": "secret-signed-url"}],
        }, "https://vimeo.com/demo")
        self.assertEqual(result["platform"], "Vimeo")
        self.assertNotIn("url", result["formats"][0])

    def test_platform_detection(self):
        self.assertEqual(platform_name("https://www.youtube.com/watch?v=x"), "YouTube")
        self.assertEqual(platform_name("https://x.com/user/status/1"), "X / Twitter")
