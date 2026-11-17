import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core import JobStore
from app import main as main_module


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


if __name__ == "__main__":
    unittest.main()
