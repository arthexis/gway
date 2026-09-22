import os

from gway.gateway import Gateway


def _recipe(path, text="env GWAY_TREE_TEST\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_ingest_recipe_tree_mounts_from_directory_basename(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    sampler = tmp_path / "sampler"
    _recipe(sampler / "wireguard" / "client.rx")
    _recipe(sampler / "wireguard" / "server.rx")

    runtime = Gateway()
    runtime.ingest(sampler)

    assert runtime("sampler wireguard client") == "ok"
    assert runtime("sampler wireguard server") == "ok"


def test_ingest_recipe_subtree_uses_last_directory_segment(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    wireguard = tmp_path / "sampler" / "network" / "wireguard"
    _recipe(wireguard / "client.rx")

    runtime = Gateway()
    runtime.ingest(wireguard)

    assert runtime("wireguard client") == "ok"
    assert runtime.ops.resolve("sampler.network.wireguard.client") is None


def test_recipe_tree_collapses_directory_entry_recipe(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    expose = tmp_path / "sampler" / "web" / "expose"
    _recipe(expose / "expose.rx")
    _recipe(expose / "http.rx")

    runtime = Gateway()
    runtime.ingest(tmp_path / "sampler")

    assert runtime("sampler web expose") == "ok"
    assert runtime("sampler web expose http") == "ok"
    assert runtime.ops.resolve("sampler.web.expose.expose") is None


def test_recipe_tree_collapses_dunder_main_recipe(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    wireguard = tmp_path / "sampler" / "wireguard"
    _recipe(wireguard / "__main__.rx")

    runtime = Gateway()
    runtime.ingest(wireguard)

    assert runtime("wireguard") == "ok"


def test_recipe_tree_aka_replaces_only_ingested_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    wireguard = tmp_path / "sampler" / "network" / "wireguard"
    _recipe(wireguard / "client.rx")
    _recipe(wireguard / "admin" / "status.rx")

    runtime = Gateway()
    runtime("ingest " + os.fspath(wireguard) + " --aka wg")

    assert runtime("wireguard client") == "ok"
    assert runtime("wireguard admin status") == "ok"
    assert runtime("wg client") == "ok"
    assert runtime("wg admin status") == "ok"


def test_ingesting_different_recipe_tree_depths_uses_each_selected_head(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    sampler = tmp_path / "sampler"
    web = sampler / "web"
    _recipe(web / "expose" / "http.rx")

    sampler_runtime = Gateway()
    sampler_runtime.ingest(sampler)
    assert sampler_runtime("sampler web expose http") == "ok"

    web_runtime = Gateway()
    web_runtime.ingest(web)
    assert web_runtime("web expose http") == "ok"


def test_recipe_tree_reingestion_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_TREE_TEST", "ok")
    sampler = tmp_path / "sampler"
    _recipe(sampler / "status.rx")

    runtime = Gateway()
    first = runtime.ingest(sampler)
    second = runtime.ingest(sampler)

    assert second == first
    assert runtime("sampler status") == "ok"
