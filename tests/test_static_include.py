import unittest
import tempfile
import types
from pathlib import Path
from unittest.mock import patch
from paste.fixture import TestApp
from gway import gw

class StaticIncludeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.base = base
        proj_dir = base / "projects"
        proj_dir.mkdir()
        static_dir = base / "data" / "static" / "myproj"
        static_dir.mkdir(parents=True)
        (static_dir / "test.css").write_text("body{}")
        (static_dir / "test.js").write_text("console.log('hi');")
        (static_dir / "index.css").write_text("body{}")
        (static_dir / "index.js").write_text("console.log('hi');")

    def tearDown(self):
        self.tmp.cleanup()
        gw._cache.pop('myproj', None)
        import sys
        sys.modules.pop('myproj', None)

    def test_links_present_without_bundles(self):
        orig_find = gw.find_project
        orig_resource = gw.resource

        def view_index():
            return '<h1>Hi</h1>'
        view_index.__module__ = 'myproj'
        view_index = gw.web.static.include(css='myproj/test.css', js='myproj/test.js')(view_index)

        module = types.SimpleNamespace(view_index=view_index)

        def fake_find(*names, root="projects"):
            if "myproj" in names:
                return module
            return orig_find(*names, root=root)

        def fake_res(*parts, **kw):
            if parts[:2] == ("data", "static"):
                return self.base.joinpath(*parts)
            return orig_resource(*parts, **kw)

        with patch.object(gw, 'find_project', side_effect=fake_find), \
             patch.object(gw, 'resource', side_effect=fake_res):
            app = gw.web.app.setup_app('myproj', css=None, js=None)
            client = TestApp(app)
            resp = client.get('/myproj')
            html = resp.body.decode()
            self.assertIn('/static/myproj/index.css', html)
            self.assertIn('/static/myproj/index.js', html)

    def test_default_names_used(self):
        orig_find = gw.find_project
        orig_resource = gw.resource

        def view_index():
            return '<h1>Hi</h1>'
        view_index.__module__ = 'myproj'
        view_index = gw.web.static.include()(view_index)

        module = types.SimpleNamespace(view_index=view_index)

        def fake_find(*names, root="projects"):
            if "myproj" in names:
                return module
            return orig_find(*names, root=root)

        def fake_res(*parts, **kw):
            if parts[:2] == ("data", "static"):
                return self.base.joinpath(*parts)
            return orig_resource(*parts, **kw)

        with patch.object(gw, 'find_project', side_effect=fake_find), \
             patch.object(gw, 'resource', side_effect=fake_res):
            app = gw.web.app.setup_app('myproj', css=None, js=None)
            client = TestApp(app)
            resp = client.get('/myproj')
            html = resp.body.decode()
            self.assertIn('/static/myproj/index.css', html)
            self.assertIn('/static/myproj/index.js', html)

if __name__ == '__main__':
    unittest.main()
