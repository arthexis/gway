from pathlib import Path
from types import SimpleNamespace

from gway.install.model import Installation
from gway.recipe_environment import recipe_environment
from gway.recipes import execute_recipe


def test_local_recipe_environment_uses_external_data_root(monkeypatch, tmp_path):
    data = tmp_path / "data"
    source = tmp_path / "source"
    source.mkdir()
    recipe = source / "demo.rx"
    recipe.write_text("clear\n", encoding="utf-8")
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    environment = recipe_environment(SimpleNamespace(_installed={}), recipe)

    assert environment.recipe == recipe.resolve()
    assert environment.scope == "user"
    assert environment.root.parent == data.resolve() / "recipes"
    assert environment.venv == environment.root / "venv"
    assert environment.metadata == environment.root / "metadata.json"
    assert not environment.root.exists()
    assert list(source.iterdir()) == [recipe]


def test_same_physical_recipe_keeps_identity_independent_of_call_surface(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "tree" / "nested" / "demo.rx"
    recipe.parent.mkdir(parents=True)
    recipe.write_text("clear\n", encoding="utf-8")
    runtime = SimpleNamespace(_installed={})

    direct = recipe_environment(runtime, recipe)
    relative = recipe_environment(runtime, recipe.parent / "." / "demo.rx")

    assert direct.key == relative.key
    assert direct.identity == relative.identity
    assert direct.root == relative.root


def test_managed_recipe_identity_uses_source_and_relative_path(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    installed = tmp_path / "projects" / "demo"
    recipe = installed / "sampler" / "mcp" / "serve.rx"
    recipe.parent.mkdir(parents=True)
    recipe.write_text("clear\n", encoding="utf-8")
    installation = Installation(
        name="demo",
        source="https://github.com/example/demo.git",
        install_path=installed,
        scope="user",
        requested_ref="main",
        resolved_revision="abc123",
    )
    runtime = SimpleNamespace(_installed={"demo": installation})

    environment = recipe_environment(runtime, recipe)

    assert environment.identity == (
        "managed:https://github.com/example/demo.git:sampler/mcp/serve.rx"
    )
    assert environment.source == installation.source
    assert environment.relative_path == Path("sampler/mcp/serve.rx")
    assert environment.resolved_revision == "abc123"


def test_managed_revision_change_reuses_recipe_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    installed = tmp_path / "projects" / "demo"
    recipe = installed / "sampler" / "mcp.rx"
    recipe.parent.mkdir(parents=True)
    recipe.write_text("clear\n", encoding="utf-8")

    def environment(revision):
        installation = Installation(
            name="demo",
            source="https://github.com/example/demo.git",
            install_path=installed,
            resolved_revision=revision,
        )
        return recipe_environment(
            SimpleNamespace(_installed={"demo": installation}),
            recipe,
        )

    first = environment("abc123")
    second = environment("def456")

    assert first.key == second.key
    assert first.root == second.root
    assert first.resolved_revision == "abc123"
    assert second.resolved_revision == "def456"


def test_recipe_frame_exposes_environment_identity(gateway, monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    recipe = tmp_path / "demo.rx"
    recipe.write_text("environment probe\n", encoding="utf-8")

    def probe():
        return gateway._recipe_frames[-1].environment

    gateway.wrap("environment probe", probe)
    _, environment = execute_recipe(gateway, recipe)

    assert environment.recipe == recipe.resolve()
    assert environment.root.parent == (tmp_path / "data" / "recipes").resolve()


def test_require_rejects_use_outside_recipe(gateway):
    import pytest

    with pytest.raises(RuntimeError, match="only available during recipe execution"):
        gateway("require fastmcp")


def test_require_records_multiple_python_packages(gateway, tmp_path):
    recipe = tmp_path / "demo.rx"
    recipe.write_text("require fastmcp cryptography\n", encoding="utf-8")

    captured = {}

    def probe():
        captured.update(gateway._recipe_frames[-1].requirements)
        return "ok"

    gateway.wrap("require probe", probe)
    recipe.write_text(
        "require fastmcp cryptography\nrequire probe\n",
        encoding="utf-8",
    )
    execute_recipe(gateway, recipe)

    assert captured == {"python": ["fastmcp", "cryptography"]}


def test_require_explicit_python_flag_matches_default(gateway, tmp_path):
    recipe = tmp_path / "demo.rx"
    captured = {}

    def probe():
        captured.update(gateway._recipe_frames[-1].requirements)
        return "ok"

    gateway.wrap("require probe", probe)
    recipe.write_text(
        "require fastmcp --python\nrequire probe\n",
        encoding="utf-8",
    )
    execute_recipe(gateway, recipe)

    assert captured == {"python": ["fastmcp"]}


def test_require_is_idempotent_within_recipe(gateway, tmp_path):
    recipe = tmp_path / "demo.rx"
    captured = {}

    def probe():
        captured.update(gateway._recipe_frames[-1].requirements)
        return "ok"

    gateway.wrap("require probe", probe)
    recipe.write_text(
        "require fastmcp\nrequire fastmcp cryptography\nrequire probe\n",
        encoding="utf-8",
    )
    execute_recipe(gateway, recipe)

    assert captured == {"python": ["fastmcp", "cryptography"]}


def test_require_rejects_missing_packages_inside_recipe(gateway, tmp_path):
    import pytest

    recipe = tmp_path / "demo.rx"
    recipe.write_text("require\n", encoding="utf-8")

    with pytest.raises(TypeError, match="at least one package"):
        execute_recipe(gateway, recipe)
