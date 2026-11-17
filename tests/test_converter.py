import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.converter import ConversionOptions, build_conversion_command, output_path


class ConverterTests(unittest.TestCase):
    @patch("app.services.converter.ffmpeg_executable", return_value="ffmpeg")
    def test_mp4_to_mp3_preserves_source_and_sets_bitrate(self, _):
        command = build_conversion_command(Path("source.mp4"), Path("out.mp3"), ConversionOptions("mp3", "320"))
        self.assertEqual(command[0], "ffmpeg")
        self.assertIn("-vn", command)
        self.assertIn("320k", command)
        self.assertEqual(command[-1], "out.mp3")

    @patch("app.services.converter.ffmpeg_executable", return_value="ffmpeg")
    def test_mp4_remux_uses_stream_copy(self, _):
        command = build_conversion_command(Path("source.mp4"), Path("copy.mp4"), ConversionOptions("mp4"))
        self.assertIn("copy", command)

    @patch("app.services.converter.ffmpeg_executable", return_value="ffmpeg")
    def test_webm_to_mp4_and_resolution_reencode(self, _):
        command = build_conversion_command(Path("source.webm"), Path("out.mp4"), ConversionOptions("mp4", resolution="720"))
        self.assertIn("libx264", command)
        self.assertIn("scale=-2:'min(720,ih)'", command)

    def test_collision_safe_output_name(self):
        with patch.object(Path, "exists", side_effect=[True, False]):
            result = output_path(Path("source.mp4"), Path("out"), "mp3")
        self.assertEqual(result.name, "source-converted-2.mp3")
