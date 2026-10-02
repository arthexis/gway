import sys
from pathlib import Path

from gway import Gateway
from gway.recipe.companion import CompanionWorker
from gway.recipe.runtime import execute_recipe, ingest_companion


def _directory_recipe(tmp_path, *, require=False):
    recipe_dir = tmp_path / "demo"
    recipe_dir.mkdir()
    recipe = recipe_dir / "__main__.rx"
    lines = []
    if require:
        lines.append("require example-package")
    lines.append("demo report")
    recipe.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (recipe_dir / "__main__.py").write_text(
        "def report():\n"
        "    return 'directory-companion-ok'\n",
        encoding="utf-8",
    )
    return recipe


def test_directory_companion_uses_public_recipe_namespace(tmp_path):
    recipe = _directory_recipe(tmp_path)
    runtime = Gateway()

    wrapped = ingest_companion(runtime, recipe)

    assert wrapped
    assert runtime.ops.resolve("demo.report") is not None
    assert runtime.ops.resolve("__main__.report") is None


def test_directory_recipe_can_call_its_companion_child(tmp_path):
    recipe = _directory_recipe(tmp_path)
    runtime = Gateway()

    _, result = execute_recipe(runtime, recipe)

    assert result == "directory-companion-ok"


def test_required_directory_companion_uses_public_recipe_namespace(
    tmp_path,
    monkeypatch,
):
    recipe = _directory_recipe(tmp_path, require=True)
    runtime = Gateway()

    class FakeWorker:
        def __init__(self, recipe_path, companion_path, python):
            self.recipe = Path(recipe_path).resolve()
            self.companion = Path(companion_path).resolve()
            self.python = Path(python)
            self.operations = ({"name": "report", "parameters": []},)

        def call(self, runtime, name, args, kwargs):
            assert name == "report"
            assert args == ()
            assert kwargs == {}
            return "managed-directory-companion-ok"

        def close(self):
            return None

    def fake_start(cls, recipe_path, companion_path, python):
        return FakeWorker(recipe_path, companion_path, python)

    monkeypatch.setattr(CompanionWorker, "start", classmethod(fake_start))
    monkeypatch.setattr(
        "gway.recipe.uv.ensure_uv",
        lambda **kwargs: tmp_path / "uv",
    )
    monkeypatch.setattr(
        "gway.recipe.environment.sync_python_environment",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "gway.recipe.environment.environment_python",
        lambda environment: Path(sys.executable),
    )

    _, result = execute_recipe(runtime, recipe)

    assert result == "managed-directory-companion-ok"
    assert runtime.ops.resolve("demo.report") is None
    assert runtime.ops.resolve("__main__.report") is None
