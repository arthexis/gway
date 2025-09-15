"""Integration tests for the ``gway shell`` builtin."""

import os
import shutil
import subprocess
import sys
import unittest


class ShellBuiltinTests(unittest.TestCase):
    """Exercise the Bash shell integration and fallback behaviour."""

    @classmethod
    def setUpClass(cls):
        if shutil.which("bash") is None:
            raise unittest.SkipTest("bash is required for shell builtin tests")

    def run_shell(self, *args, env=None):
        command = [sys.executable, "-m", "gway", "shell", "--", *args]
        environment = os.environ.copy() if env is None else env
        environment.pop("BASH_ENV", None)
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_executes_regular_bash_command(self):
        result = self.run_shell("-c", "printf 'via bash\\n'")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "via bash\n")
        self.assertEqual(result.stderr, "")

    def test_falls_back_to_gway_command(self):
        result = self.run_shell("-c", "hello_world")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Hello, World!", result.stdout)
        self.assertNotIn("command not found", result.stderr)

    def test_propagates_gway_errors(self):
        result = self.run_shell("-c", "doesnotexist")
        self.assertEqual(result.returncode, 13)
        self.assertIn("Halting: Unable to find GWAY attribute", result.stdout)
        self.assertEqual(result.stderr.strip(), "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
