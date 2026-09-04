import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitoring.config import Settings


class SettingsTests(unittest.TestCase):
    def test_runtime_secrets_are_required(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ValueError, "MONITOR_SHARED_SECRET"),
        ):
            Settings.from_env(Path(directory))

    def test_wildcard_cors_origin_is_rejected(self) -> None:
        environment = {
            "MONITOR_SHARED_SECRET": "c" * 32,
            "MONITOR_DASHBOARD_TOKEN": "d" * 32,
            "MONITOR_FRONTEND_ORIGINS": "*",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, environment, clear=True
        ), self.assertRaisesRegex(ValueError, "Wildcard"):
            Settings.from_env(Path(directory))

    def test_client_and_dashboard_credentials_must_be_different(self) -> None:
        credential = "same-credential-" + "x" * 32
        environment = {
            "MONITOR_SHARED_SECRET": credential,
            "MONITOR_DASHBOARD_TOKEN": credential,
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, environment, clear=True),
            self.assertRaisesRegex(ValueError, "must be different"),
        ):
            Settings.from_env(Path(directory))


if __name__ == "__main__":
    unittest.main()
