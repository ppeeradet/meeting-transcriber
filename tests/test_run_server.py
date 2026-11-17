import os
import unittest
from unittest.mock import patch

import run_server


class ServerLauncherTests(unittest.TestCase):
    def test_pythonw_safe_uvicorn_configuration(self):
        with patch.object(run_server.uvicorn, "run") as run, patch.object(os, "chdir"):
            run_server.main()
        _, kwargs = run.call_args
        self.assertEqual(kwargs["host"], "127.0.0.1")
        self.assertEqual(kwargs["port"], 8765)
        self.assertIsNone(kwargs["log_config"])
        self.assertFalse(kwargs["access_log"])
        self.assertEqual(os.environ["MEETING_DEPLOYMENT_MODE"], "tailnet")


if __name__ == "__main__":
    unittest.main()
