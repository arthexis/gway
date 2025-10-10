import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from build import ProjectBuilder
except ModuleNotFoundError:  # pragma: no cover - build is part of runtime deps
    ProjectBuilder = None

try:  # pragma: no cover - wheel may not be installed in minimal envs
    import wheel  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - handled via skip
    WHEEL_AVAILABLE = False
else:  # pragma: no cover - indicates wheel import worked
    WHEEL_AVAILABLE = True


class PackagingBuiltinsTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]
        builtins_dir = self.project_root / "gway" / "builtins"
        self.expected_files = {
            f"gway/builtins/{path.name}" for path in builtins_dir.glob("*.py")
        }
        self.assertTrue(
            self.expected_files,
            "expected to discover builtin modules in source tree",
        )

    @unittest.skipIf(ProjectBuilder is None, "build module not available")
    def test_sdist_includes_builtins_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = ProjectBuilder(str(self.project_root))
            sdist_path = Path(builder.build("sdist", Path(tmp)))
            self._assert_archive_contains(sdist_path, self.expected_files)

    @unittest.skipIf(ProjectBuilder is None, "build module not available")
    @unittest.skipUnless(WHEEL_AVAILABLE, "wheel module not installed")
    def test_wheel_includes_builtins_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = ProjectBuilder(str(self.project_root))
            wheel_path = Path(builder.build("wheel", Path(tmp)))
            self._assert_archive_contains(wheel_path, self.expected_files)

    def _assert_archive_contains(self, archive: Path, expected_files):
        if archive.suffix == ".whl":
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
        else:
            with tarfile.open(archive) as tf:
                names = tf.getnames()

        for relative_path in expected_files:
            if not any(name.endswith(relative_path) for name in names):
                self.fail(f"{relative_path} missing from {archive.name}")


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
