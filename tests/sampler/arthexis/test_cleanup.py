from pathlib import Path


def test_cleanup_removes_exposure_before_project(recipe_values):
    values = recipe_values("cleanup.rx")

    assert values[0] == [
        "default",
        "--site",
        "arthexis.com",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    assert values[1] == ["../web/expose/cleanup-http"]
    assert values[2] == ["uninstall", "arthexis"]


def test_default_cleanup_does_not_delete_dns():
    text = Path("sampler/arthexis/cleanup.rx").read_text(encoding="utf-8")

    assert "dns delete" not in text
    assert "../web/expose/cleanup\n" not in text


def test_dns_cleanup_is_explicit(recipe_values):
    assert recipe_values("dns-cleanup.rx") == [
        ["../web/expose/cleanup"],
        ["uninstall", "arthexis"],
    ]
