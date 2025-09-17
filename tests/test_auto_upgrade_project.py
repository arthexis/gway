import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gway import gw
from gway.projects import auto_upgrade


class AutoUpgradeProjectTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(gw.context.clear)
        self._env_patch = mock.patch.dict(os.environ, {"GWAY_ROOT": self.tempdir.name}, clear=False)
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def _read_log(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_log_cycle_creates_log_and_updates_context(self):
        state = auto_upgrade.log_cycle(latest=True, log_name="test.log")
        self.addCleanup(lambda: state.log_path.unlink(missing_ok=True))
        self.assertTrue(state.latest)
        self.assertIn("auto_upgrade_previous_version", gw.context)
        contents = self._read_log(state.log_path)
        self.assertIn("CHECK", contents)
        self.assertIn("latest=true", contents)

    def test_install_honours_latest_flag(self):
        result = mock.Mock(returncode=0)
        with mock.patch.object(auto_upgrade.subprocess, "run", return_value=result) as run_mock:
            auto_upgrade.install(latest=True)

        called_args = run_mock.call_args[0][0]
        self.assertIn("--force-reinstall", called_args)

        with mock.patch.object(auto_upgrade.subprocess, "run", return_value=result) as run_mock:
            auto_upgrade.install(latest=False)

        called_args = run_mock.call_args[0][0]
        self.assertNotIn("--force-reinstall", called_args)

    def test_log_upgrade_records_change_and_notifies(self):
        gw.context["auto_upgrade_previous_version"] = "1.0.0"

        with mock.patch.object(auto_upgrade, "_installed_version", return_value="1.1.0"), mock.patch.object(
            auto_upgrade, "_broadcast"
        ) as broadcast_mock:
            result = auto_upgrade.log_upgrade(log_name="change.log")

        contents = self._read_log(result["log"])
        self.addCleanup(lambda: Path(result["log"]).unlink(missing_ok=True))
        self.assertIn("UPGRADE | version=1.1.0 from=1.0.0", contents)
        broadcast_mock.assert_called_once_with("gway upgraded to 1.1.0")

    def test_log_upgrade_skips_notification_when_version_unchanged(self):
        gw.context["auto_upgrade_previous_version"] = "2.0.0"

        with mock.patch.object(auto_upgrade, "_installed_version", return_value="2.0.0"), mock.patch.object(
            auto_upgrade, "_broadcast"
        ) as broadcast_mock:
            result = auto_upgrade.log_upgrade(log_name="skip.log")

        contents = self._read_log(result["log"])
        self.addCleanup(lambda: Path(result["log"]).unlink(missing_ok=True))
        self.assertIn("UPGRADE-SKIPPED | version=2.0.0", contents)
        broadcast_mock.assert_not_called()


if __name__ == "__main__":  # pragma: no cover - direct execution support
    unittest.main()

