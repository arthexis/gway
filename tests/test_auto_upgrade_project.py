import os
import tempfile
import unittest
from datetime import datetime
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

    def test_install_delegates_to_builtin(self):
        with mock.patch.object(gw, "install", return_value=0) as install_mock:
            auto_upgrade.install(latest=True)

        install_mock.assert_called_once_with("gway", mode="pip", latest=True)

        gw.context["auto_upgrade_latest"] = True
        with mock.patch.object(gw, "install", return_value=0) as install_mock:
            auto_upgrade.install()

        install_mock.assert_called_once_with("gway", mode="pip", latest=True)

    def test_log_upgrade_records_change_and_notifies(self):
        gw.context["auto_upgrade_previous_version"] = "1.0.0"

        with mock.patch.object(auto_upgrade.package, "_installed_version", return_value="1.1.0"), mock.patch.object(
            auto_upgrade, "_broadcast"
        ) as broadcast_mock:
            result = auto_upgrade.log_upgrade(log_name="change.log")

        contents = self._read_log(result["log"])
        self.addCleanup(lambda: Path(result["log"]).unlink(missing_ok=True))
        self.assertIn("UPGRADE | version=1.1.0 from=1.0.0", contents)
        broadcast_mock.assert_called_once_with("gway upgraded to 1.1.0")

    def test_log_upgrade_skips_notification_when_version_unchanged(self):
        gw.context["auto_upgrade_previous_version"] = "2.0.0"

        with mock.patch.object(auto_upgrade.package, "_installed_version", return_value="2.0.0"), mock.patch.object(
            auto_upgrade, "_broadcast"
        ) as broadcast_mock:
            result = auto_upgrade.log_upgrade(log_name="skip.log")

        contents = self._read_log(result["log"])
        self.addCleanup(lambda: Path(result["log"]).unlink(missing_ok=True))
        self.assertIn("UPGRADE-SKIPPED | version=2.0.0", contents)
        broadcast_mock.assert_not_called()

    def test_notify_upgrade_emits_gui_or_lcd_message(self):
        gw.context.update(
            {
                "auto_upgrade_previous_version": "1.0.0",
                "auto_upgrade_current_version": "1.2.3",
                "auto_upgrade_latest": False,
            }
        )
        fixed_time = datetime(2024, 2, 3, 14, 15)

        with mock.patch.object(auto_upgrade, "_current_release", return_value="27AACE"), mock.patch.object(
            auto_upgrade.gw, "notify", return_value="lcd"
        ) as notify_mock:
            result = auto_upgrade.notify_upgrade(timestamp=fixed_time)

        notify_mock.assert_called_once_with("20240203 14:15", title="gway v1.2.3 r27AACE", timeout=20)
        self.assertEqual(result["status"], "notified")
        self.assertEqual(result["channel"], "lcd")
        self.assertEqual(result["release"], "27AACE")
        self.assertEqual(result["message"], "20240203 14:15")
        self.assertIn("auto_upgrade_notification", gw.context)

    def test_notify_upgrade_skips_when_version_unchanged(self):
        gw.context.update(
            {
                "auto_upgrade_previous_version": "2.5.0",
                "auto_upgrade_current_version": "2.5.0",
                "auto_upgrade_latest": False,
            }
        )

        with mock.patch.object(auto_upgrade.gw, "notify") as notify_mock:
            result = auto_upgrade.notify_upgrade()

        notify_mock.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "version-unchanged")


if __name__ == "__main__":  # pragma: no cover - direct execution support
    unittest.main()

