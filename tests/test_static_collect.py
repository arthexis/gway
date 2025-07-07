import unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# Dynamically import the static helpers
spec = importlib.util.spec_from_file_location(
    "webstatic", Path(__file__).resolve().parents[1] / "projects" / "web" / "static.py"
)
webstatic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webstatic)

class StaticCollectTests(unittest.TestCase):
    def test_collect_concatenates_files(self):
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            static_root = tmp_path / "data" / "static"
            proj_dir = static_root / "web" / "site"
            proj_dir.mkdir(parents=True)
            css1 = proj_dir / "a.css"
            css2 = proj_dir / "b.css"
            css1.write_text("body{color:red}")
            css2.write_text("p{font-weight:bold}")
            js1 = proj_dir / "a.js"
            js2 = proj_dir / "b.js"
            js1.write_text("console.log('a');")
            js2.write_text("console.log('b');")
            target_dir = tmp_path / "work" / "shared"
            target_dir.mkdir(parents=True)

            def fake_resource(*parts, **kw):
                return tmp_path.joinpath(*parts)

            with patch.object(webstatic.gw, "resource", fake_resource), \
                 patch.object(webstatic.gw.web.app, "enabled_projects", lambda: {"web.site"}):
                report = webstatic.collect(root="data/static", target="work/shared")

            self.assertEqual(
                {Path(rel).as_posix() for _, rel, _ in report["css"]},
                {"web/site/a.css", "web/site/b.css"},
            )
            self.assertEqual(
                {Path(rel).as_posix() for _, rel, _ in report["js"]},
                {"web/site/a.js", "web/site/b.js"},
            )

            css_bundle = Path(report["css_bundle"]).read_text()
            expected_css = "".join(
                f"/* --- {proj}:{rel} --- */\n" + Path(full).read_text() + "\n\n"
                for proj, rel, full in reversed(report["css"])
            )
            self.assertEqual(css_bundle, expected_css)

            js_bundle = Path(report["js_bundle"]).read_text()
            expected_js = "".join(
                f"// --- {proj}:{rel} ---\n" + Path(full).read_text() + "\n\n"
                for proj, rel, full in report["js"]
            )
            self.assertEqual(js_bundle, expected_js)

    def test_collect_includes_monitor_tabs_script(self):
        """net_monitors.js is bundled when monitor project is enabled."""
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            monitor_dir = tmp_path / "data" / "static" / "monitor"
            monitor_dir.mkdir(parents=True)
            js_file = monitor_dir / "net_monitors.js"
            js_file.write_text("console.log('tabs');")
            css_file = monitor_dir / "net_monitors.css"
            css_file.write_text(".tabs{}")
            target_dir = tmp_path / "work" / "shared"
            target_dir.mkdir(parents=True)

            def fake_resource(*parts, **kw):
                return tmp_path.joinpath(*parts)

            with patch.object(webstatic.gw, "resource", fake_resource), \
                 patch.object(webstatic.gw.web.app, "enabled_projects", lambda: {"monitor"}):
                report = webstatic.collect(root="data/static", target="work/shared")

            js_files = {Path(rel).as_posix() for _, rel, _ in report["js"]}
            self.assertIn("monitor/net_monitors.js", js_files)
            js_bundle = Path(report["js_bundle"]).read_text()
            self.assertIn("net_monitors.js", js_bundle)

if __name__ == "__main__":
    unittest.main()
