import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import builtins
import getpass

from gway import gw

class ReleaseBuildNotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.old = Path.cwd()
        os.chdir(self.base)
        Path("VERSION").write_text("0.0.1\n")
        Path("requirements.txt").write_text("requests\n")
        Path("README.rst").write_text("readme\n")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_notify_option_calls_notify(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", return_value=""), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch("subprocess.run", return_value=cp), \
             patch.object(gw, "notify") as mock_notify:
            gw.release.build(notify=True)
            mock_notify.assert_called_once()

    def test_all_enables_notify(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", return_value=""), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch.object(gw.release, "update_readme_links"), \
             patch("subprocess.run", return_value=cp), \
             patch("requests.get"), \
             patch.object(gw, "notify") as mock_notify:
            gw.release.build(all=True)
            mock_notify.assert_called_once()

    def test_interactive_prompts_for_token(self):
        cp = subprocess.CompletedProcess([], 0, "", "")

        def fake_resolve(key, *args, **kwargs):
            default = kwargs.get("default", None)
            if args:
                default = args[0]
            if key == "[PYPI_API_TOKEN]":
                return default if default is not None else ""
            if key in ("[PYPI_USERNAME]", "[PYPI_PASSWORD]"):
                if default is not None:
                    return default
                raise KeyError(key)
            return ""

        prompts = []
        inputs = iter(["token-value"])

        def fake_input(prompt):
            prompts.append(prompt)
            return next(inputs)

        original_interactive = gw.interactive_enabled
        gw.interactive_enabled = True
        try:
            with patch.object(gw, "test", return_value=True), \
                 patch.object(gw, "resolve", side_effect=fake_resolve), \
                 patch.object(gw.hub, "commit", return_value="abc"), \
                 patch.object(gw.release, "update_changelog"), \
                 patch("requests.get") as mock_get, \
                 patch("subprocess.run", return_value=cp), \
                 patch.object(builtins, "input", side_effect=fake_input), \
                 patch.object(getpass, "getpass") as mock_getpass:
                mock_get.return_value.ok = True
                mock_get.return_value.json.return_value = {"releases": {}}
                gw.release.build(dist=True, twine=True)
            mock_getpass.assert_not_called()
            assert prompts == ["PyPI API token (leave blank to provide username/password): "]
        finally:
            gw.interactive_enabled = original_interactive

    def test_wizard_failure_offers_clipboard(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        original_interactive = gw.interactive_enabled
        original_wizard = gw.wizard_enabled
        gw.interactive_enabled = True
        gw.wizard_enabled = True
        try:
            with patch.object(gw, "test", return_value=False), \
                 patch("subprocess.run", return_value=cp), \
                 patch.object(gw.studio.clip, "copy") as mock_copy, \
                 patch.object(builtins, "input", return_value="y") as mock_input:
                with self.assertRaises(SystemExit):
                    gw.release.build(all=True)
            mock_input.assert_called_once()
            mock_copy.assert_called_once()
        finally:
            gw.interactive_enabled = original_interactive
            gw.wizard_enabled = original_wizard

    def test_wizard_failure_auto_copy_without_interactive(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        original_interactive = gw.interactive_enabled
        original_wizard = gw.wizard_enabled
        gw.interactive_enabled = False
        gw.wizard_enabled = True
        try:
            with patch.object(gw, "test", return_value=False), \
                 patch("subprocess.run", return_value=cp), \
                 patch.object(gw.studio.clip, "copy") as mock_copy, \
                 patch.object(builtins, "input") as mock_input:
                with self.assertRaises(SystemExit):
                    gw.release.build(all=True)
            mock_input.assert_not_called()
            mock_copy.assert_called_once()
        finally:
            gw.interactive_enabled = original_interactive
            gw.wizard_enabled = original_wizard

    def test_missing_pypi_credentials_skip_upload(self):
        cp = subprocess.CompletedProcess([], 0, "", "")

        def fake_resolve(key, *args, **kwargs):
            default = kwargs.get("default", "")
            if key == "[PYPI_API_TOKEN]":
                return default
            if key in ("[PYPI_USERNAME]", "[PYPI_PASSWORD]"):
                if "default" in kwargs:
                    return default
                raise KeyError(key)
            return ""

        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", side_effect=fake_resolve), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch("requests.get") as mock_get, \
             patch("subprocess.run", return_value=cp) as mock_run, \
             patch.object(gw, "warning") as mock_warning:
            mock_get.return_value.ok = True
            mock_get.return_value.json.return_value = {"releases": {}}
            gw.release.build(dist=True, twine=True)

        mock_run.assert_any_call([sys.executable, "-m", "twine", "check", "dist/*"],
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 text=True)
        mock_warning.assert_any_call(
            "Twine upload skipped: missing PyPI token or username/password."
        )

if __name__ == "__main__":
    unittest.main()
