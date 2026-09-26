from gway import Gateway
from gway.install import Installation, InstallState, install_paths


def test_products_lists_only_product_installations(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(tmp_path / "system-data"))

    paths = install_paths(root=data, home=tmp_path / "home")
    state = InstallState(paths.state)
    state.put(
        Installation(
            name="arthexis",
            source="https://github.com/arthexis/arthexis.git",
            install_path=paths.products / "arthexis",
            kind="product",
        )
    )
    state.put(
        Installation(
            name="demo-extension",
            source="file:///demo-extension",
            install_path=paths.projects / "demo-extension",
            kind="extension",
        )
    )

    result = Gateway()("products")

    assert [item["name"] for item in result] == ["arthexis"]
    assert result[0]["kind"] == "product"
