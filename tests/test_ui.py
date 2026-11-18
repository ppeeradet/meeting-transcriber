import unittest
from unittest.mock import patch

from app import main as main_module


class UiDeliveryTests(unittest.TestCase):
    def test_index_disables_cache_and_versions_assets(self):
        response = main_module.index()
        self.assertEqual(response.headers["cache-control"], "no-store, max-age=0")
        html = (main_module.BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("static/app.js?v=20261118-3", html)
        self.assertIn("static/job-actions.css?v=20261118-3", html)

    def test_each_eligible_job_has_an_individual_close_label(self):
        script = (main_module.BASE_DIR / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ปิดงานนี้", script)
        self.assertIn('data-job="${esc(job.id)}"', script)
        self.assertNotIn("archive-finished", script)

    def test_open_jobs_folder_uses_fixed_windows_explorer_target(self):
        with patch.object(main_module.os, "name", "nt"), patch.object(main_module.subprocess, "Popen") as launch:
            result = main_module.open_jobs_folder()
        launch.assert_called_once_with(
            ["explorer.exe", str(main_module.store.jobs_root.resolve())],
            shell=False,
            close_fds=True,
        )
        self.assertEqual(result["status"], "opened")
