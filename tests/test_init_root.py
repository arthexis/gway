import unittest
import tempfile
import subprocess
import os
import sys
from pathlib import Path
from gway import Gateway
import gway.gateway as gateway_module
import gway as gway_pkg

class InitRootTests(unittest.TestCase):
    def test_creates_expected_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            local_gw = Gateway()
            old_mod_gw = gateway_module.gw
            old_pkg_gw = gway_pkg.gw
            gateway_module.gw = local_gw
            gway_pkg.gw = local_gw
            try:
                result = local_gw.init_root(tmp)
            finally:
                gateway_module.gw = old_mod_gw
                gway_pkg.gw = old_pkg_gw
            old = gateway_module.gw
            gateway_module.gw = local_gw
            try:
                result = local_gw.init_root(tmp)
            finally:
                gateway_module.gw = old
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
            local_gw = Gateway()
            root_path = Path(local_gw.init_root(root_tmp))
            project_dir = root_path / 'projects'
            proj_file = project_dir / 'demo.py'
            proj_file.write_text('def say_hi(name="World"):\n    print(f"hello {name}")\n')

            env = os.environ.copy()
            env['GWAY_ROOT'] = str(root_path)

            cmd = [
                sys.executable,
                '-m',
                'gway',
                '-p', str(project_dir),
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
