import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from gway import gw
from gway.projects import package


class PackageProjectHelpersTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(gw.context.clear)
        env_patch = mock.patch.dict(os.environ, {"GWAY_ROOT": self.tempdir.name}, clear=False)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def _read_log(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_log_cycle_uses_configured_prefix_and_log(self):
        config = package.UpgradeConfig(package="demo", context_prefix="demo", log_name="demo.log")

        with mock.patch.object(package, "_installed_version", return_value="0.9.0"):
            state = package.log_cycle(config, latest=True)

        self.addCleanup(lambda: state.log_path.unlink(missing_ok=True))
        self.assertTrue(state.latest)
        self.assertEqual(state.previous_version, "0.9.0")
        self.assertEqual(Path(state.log_path).name, "demo.log")
        self.assertIn("demo_previous_version", gw.context)
        contents = self._read_log(state.log_path)
        self.assertIn("CHECK", contents)
        self.assertIn("latest=true", contents)
        self.assertIn("installed=0.9.0", contents)

    def test_install_uses_config_package_and_mode(self):
        config = package.UpgradeConfig(package="demo", context_prefix="demo", install_mode="pip")

        with mock.patch.object(gw, "install", return_value=0) as install_mock:
            package.install(config, latest=False)

        install_mock.assert_called_once_with("demo", mode="pip", latest=False)

    def test_log_upgrade_invokes_broadcaster_with_template(self):
        config = package.UpgradeConfig(
            package="demo",
            context_prefix="demo",
            broadcast_template="{package}-{version}",
        )
        gw.context["demo_previous_version"] = "0.9.0"

        broadcaster = mock.Mock()
        with mock.patch.object(package, "_installed_version", return_value="1.0.0"):
            result = package.log_upgrade(config, broadcaster=broadcaster)

        self.addCleanup(lambda: Path(result["log"]).unlink(missing_ok=True))
        broadcaster.assert_called_once_with("demo-1.0.0")
        self.assertEqual(gw.context["demo_current_version"], "1.0.0")

    def test_notify_upgrade_uses_templates_and_release_helpers(self):
        config = package.UpgradeConfig(
            package="demo",
            context_prefix="demo",
            notify_title_template="{package}::{release}",
            notify_time_format="%H:%M",
            release_lookup=lambda length: "xyz987",
            release_normalizer=str.upper,
            fallback_release="NONE",
        )
        gw.context.update(
            {
                "demo_previous_version": "0.9.0",
                "demo_current_version": "1.0.0",
                "demo_latest": False,
            }
        )

        fixed_time = datetime(2024, 1, 1, 8, 30)
        with mock.patch.object(package.gw, "notify", return_value="gui") as notify_mock:
            result = package.notify_upgrade(config, timestamp=fixed_time)

        notify_mock.assert_called_once_with("08:30", title="demo::XYZ987", timeout=20)
        self.assertEqual(result["status"], "notified")
        self.assertEqual(result["release"], "XYZ987")
        self.assertIn("demo_notification", gw.context)

    def test_notify_upgrade_falls_back_when_release_missing(self):
        config = package.UpgradeConfig(
            package="demo",
            context_prefix="demo",
            notify_title_template="Demo {release}",
            fallback_release="MISSING",
            release_lookup=lambda length: "",
        )
        gw.context.update(
            {
                "demo_previous_version": "0.9.0",
                "demo_current_version": "1.0.0",
                "demo_latest": False,
            }
        )

        with mock.patch.object(package.gw, "notify", return_value="console") as notify_mock:
            summary = package.notify_upgrade(config)

        notify_mock.assert_called_once_with(mock.ANY, title="Demo MISSING", timeout=20)
        self.assertEqual(summary["release"], "MISSING")


if __name__ == "__main__":  # pragma: no cover - direct execution support
    unittest.main()
