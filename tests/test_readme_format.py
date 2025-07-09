import unittest
from pathlib import Path
from docutils.core import publish_parts


class ReadmeFormatTests(unittest.TestCase):
    def test_readme_parses_without_errors(self):
        content = Path("README.rst").read_text(encoding="utf-8")
        try:
            publish_parts(
                source=content,
                writer_name="html",
                settings_overrides={"halt_level": 2},
            )
        except Exception as exc:
            self.fail(f"README.rst contains formatting errors: {exc}")


if __name__ == "__main__":
    unittest.main()
