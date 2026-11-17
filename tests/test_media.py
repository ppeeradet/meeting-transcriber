import unittest

from app.media import MediaValidationError, validate_probe_payload


class MediaTests(unittest.TestCase):
    def test_accepts_audio_video_probe_payload(self):
        info = validate_probe_payload({
            "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
            "format": {"duration": "12.5", "format_name": "mov,mp4"},
        })
        self.assertTrue(info["has_audio"])
        self.assertTrue(info["has_video"])
        self.assertEqual(info["duration"], 12.5)

    def test_rejects_non_media_payload(self):
        with self.assertRaisesRegex(MediaValidationError, "audio หรือ video"):
            validate_probe_payload({"streams": [{"codec_type": "data"}], "format": {}})
