import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from gway import gw

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

            with patch.object(gw, "resource", fake_resource), \
                 patch.object(gw.web.app, "enabled_projects", lambda: {"web.site"}):
                report = gw.web.static.collect(root="data/static", target="work/shared")

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

            with patch.object(gw, "resource", fake_resource), \
                 patch.object(gw.web.app, "enabled_projects", lambda: {"monitor"}):
                report = gw.web.static.collect(root="data/static", target="work/shared")

            js_files = {Path(rel).as_posix() for _, rel, _ in report["js"]}
            self.assertIn("monitor/net_monitors.js", js_files)
            js_bundle = Path(report["js_bundle"]).read_text()
            self.assertIn("net_monitors.js", js_bundle)

    def test_collect_full_option_gathers_all_files(self):
        """--full ignores enabled projects and scans the entire tree."""
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dir1 = tmp_path / "data" / "static" / "one"
            dir2 = tmp_path / "data" / "static" / "two"
            dir1.mkdir(parents=True)
            dir2.mkdir(parents=True)
            (dir1 / "a.css").write_text("a{}")
            (dir1 / "a.js").write_text("console.log('a')")
            (dir2 / "b.css").write_text("b{}")
            (dir2 / "b.js").write_text("console.log('b')")
            target_dir = tmp_path / "work" / "shared"
            target_dir.mkdir(parents=True)

            def fake_resource(*parts, **kw):
                return tmp_path.joinpath(*parts)

            with patch.object(gw, "resource", fake_resource), \
                 patch.object(gw.web.app, "enabled_projects", lambda: set()):
                report = gw.web.static.collect(root="data/static", target="work/shared", full=True)

            css_files = {Path(rel).as_posix() for _, rel, _ in report["css"]}
            js_files = {Path(rel).as_posix() for _, rel, _ in report["js"]}
            self.assertEqual(css_files, {"one/a.css", "two/b.css"})
            self.assertEqual(js_files, {"one/a.js", "two/b.js"})

if __name__ == "__main__":
    unittest.main()
