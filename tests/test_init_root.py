import unittest
import tempfile
import subprocess
import os
from pathlib import Path
from gway import gw

class InitRootTests(unittest.TestCase):
    def test_creates_expected_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = gw.init_root(tmp)
            root_path = Path(result)
            expected = [
                'envs/clients',
                'envs/servers',
                'projects',
                'data/static',
                'logs',
                'work',
                'recipes',
            ]
            for sub in expected:
                self.assertTrue((root_path / sub).is_dir(), f"missing {sub}")
            self.assertTrue((root_path / 'README.rst').is_file())

    def test_cli_runs_project_from_anywhere(self):
        with tempfile.TemporaryDirectory() as root_tmp, tempfile.TemporaryDirectory() as cwd_tmp:
            root_path = Path(gw.init_root(root_tmp))
            project_dir = root_path / 'projects'
            proj_file = project_dir / 'demo.py'
            proj_file.write_text('def say_hi(name="World"):\n    print(f"hello {name}")\n')

            env = os.environ.copy()
            env['GWAY_ROOT'] = str(root_path)

            cmd = [
                'gway',
                'demo',
                'say-hi',
                'Codex'
            ]
            result = subprocess.run(
                cmd,
                cwd=cwd_tmp,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10
            )
            self.assertIn('hello Codex', result.stdout)

if __name__ == '__main__':
    unittest.main()
