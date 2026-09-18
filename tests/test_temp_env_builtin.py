import pathlib
import shutil
import unittest

from gway import gw


class TempEnvBuiltinTests(unittest.TestCase):
    def test_runs_command_and_cleans_up(self):
        code = "import sys; print(sys.prefix)"
        result = gw.temp_env("python", "-c", code, packages="", capture_output=True)
        prefix = pathlib.Path(result["stdout"].strip())
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(prefix.parent, pathlib.Path(result["env"]))
        self.assertFalse(pathlib.Path(result["env"]).exists())

    def test_keep_true_preserves_environment(self):
        result = gw.temp_env(
            "python",
            "-c",
            "print('ok')",
            packages="",
            capture_output=True,
            keep=True,
        )
        env_root = pathlib.Path(result["env"])
        try:
            self.assertTrue(env_root.exists())
            self.assertEqual(result["stdout"].strip(), "ok")
        finally:
            shutil.rmtree(env_root, ignore_errors=True)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
