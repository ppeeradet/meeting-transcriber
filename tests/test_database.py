import json
import tempfile
import unittest
from pathlib import Path

from app.database import JobDatabase


class DatabaseMigrationTests(unittest.TestCase):
    def test_json_migration_is_idempotent_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "jobs" / "abc"
            payload = [{
                "id": "abc",
                "status": "completed",
                "operation": "download",
                "media_mode": "audio",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:01:00+00:00",
                "output_dir": str(output),
                "input_path": str(output / "source.mp3"),
                "files": ["result.mp3"],
            }]
            (root / "jobs.json").write_text(json.dumps(payload), encoding="utf-8")
            database = JobDatabase(root)
            first = database.migrate_json()
            second = database.migrate_json()
            self.assertEqual(first.database_jobs, 1)
            self.assertEqual(second.database_jobs, 1)
            self.assertEqual(second.database_files, 2)
            self.assertTrue((root / "jobs.json.pre-sqlite.bak").is_file())
            self.assertEqual(database.load()[0]["id"], "abc")

    def test_save_updates_existing_job_without_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            database = JobDatabase(Path(temp))
            payload = {
                "id": "job-1", "status": "queued", "operation": "convert", "media_mode": "audio",
                "created_at": "2026-01-01", "updated_at": "2026-01-01", "files": [],
            }
            database.save([payload])
            payload["status"] = "completed"
            database.save([payload])
            loaded = database.load()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
