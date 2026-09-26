from gway import Gateway
from gway.install import Installation, InstallState, install_paths


def test_products_lists_only_product_installations(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(tmp_path / "system-data"))

    paths = install_paths(root=data, home=tmp_path / "home")
    state = InstallState(paths.state)
    product = paths.products / "arthexis"
    product.mkdir(parents=True)
    (product / "pyproject.toml").write_text(
        "[project]\nname = \"arthexis\"\n",
        encoding="utf-8",
    )
    extension = paths.projects / "demo-extension"
    extension.mkdir(parents=True)
    (extension / "pyproject.toml").write_text(
        "[project]\nname = \"demo-extension\"\n",
        encoding="utf-8",
    )
    state.put(
        Installation(
            name="arthexis",
            source="https://github.com/arthexis/arthexis.git",
            install_path=product,
            kind="product",
        )
    )
    state.put(
        Installation(
            name="demo-extension",
            source="file:///demo-extension",
            install_path=extension,
            kind="extension",
        )
    )

    result = Gateway()("products")

    assert [item["name"] for item in result] == ["arthexis"]
    assert result[0]["kind"] == "product"
