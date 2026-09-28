from pathlib import Path


def repository_root():
    return Path(__file__).resolve().parents[2]


def test_sampler_has_one_canonical_repository_recipe_root():
    root = repository_root()
    sampler = root / "sampler"
    recipe_sampler_roots = [
        path
        for path in root.rglob("sampler")
        if path.is_dir() and any(path.rglob("*.rx"))
    ]

    assert sampler.is_dir()
    assert any(sampler.rglob("*.rx"))
    assert sampler.parent == root
    assert recipe_sampler_roots == [sampler]


def test_sampler_is_not_implemented_as_a_bundled_recipe_tree():
    root = repository_root()

    assert not (root / "gway" / "bundled").exists()
    assert not (root / "gway" / "bundled.py").exists()


def test_sampler_contains_gway_and_arthexis_recipe_families():
    root = repository_root() / "sampler"

    assert (root / "web" / "expose" / "expose.rx").is_file()
    assert (root / "arthexis" / "setup.rx").is_file()
    assert (root / "arthexis" / "expose.rx").is_file()


def test_sampler_tree_can_be_ingested_as_one_command_namespace(gateway):
    sampler = repository_root() / "sampler"

    gateway.ingest(sampler)

    assert gateway.ops.resolve("sampler.web.expose") is not None
    assert gateway.ops.resolve("sampler.web.expose.http") is not None
    assert gateway.ops.resolve("sampler.arthexis.setup") is not None


def _is_under(path, root):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def test_all_repository_recipes_live_under_sampler():
    root = repository_root()
    sampler = root / "sampler"

    recipes = sorted(path for path in root.rglob("*.rx") if path.is_file())
    misplaced = [path.relative_to(root) for path in recipes if not _is_under(path, sampler)]

    assert misplaced == []


def test_all_recipe_companions_live_beside_recipes_under_sampler():
    root = repository_root()
    sampler = root / "sampler"

    companions = []
    for recipe in sampler.rglob("*.rx"):
        companion = recipe.with_suffix(".py")
        if companion.is_file():
            companions.append(companion)

    misplaced = [
        path.relative_to(root)
        for path in companions
        if not _is_under(path, sampler) or path.with_suffix(".rx").parent != path.parent
    ]

    assert misplaced == []


def test_no_recipe_companion_pair_exists_outside_sampler():
    root = repository_root()
    sampler = root / "sampler"

    misplaced = []
    for python_file in root.rglob("*.py"):
        if _is_under(python_file, sampler):
            continue
        recipe = python_file.with_suffix(".rx")
        if recipe.is_file():
            misplaced.append(python_file.relative_to(root))

    assert misplaced == []


def test_sampler_recipe_inventory_collapses_directory_entry_recipes(tmp_path, monkeypatch):
    from gway import sampler

    root = tmp_path / "sampler"
    (root / "web" / "expose").mkdir(parents=True)
    (root / "web" / "expose" / "expose.rx").write_text("clear\n", encoding="utf-8")
    (root / "remote").mkdir(parents=True)
    (root / "remote" / "__main__.rx").write_text("clear\n", encoding="utf-8")
    (root / "logs").mkdir(parents=True)
    (root / "logs" / "read.rx").write_text("clear\n", encoding="utf-8")
    monkeypatch.setattr(sampler, "root", lambda: root)

    assert sampler.recipes() == (
        "logs/read",
        "remote",
        "web/expose",
    )
