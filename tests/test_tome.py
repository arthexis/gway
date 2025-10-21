from gway import gw

from projects import tome


def test_shuffle_handles_extremely_long_names(tmp_path, monkeypatch):
    tomes_dir = tmp_path / "work" / "tomes"

    def fake_resource(*parts, **kwargs):
        assert parts == ("work", "tomes")
        if kwargs.get("dir"):
            tomes_dir.mkdir(parents=True, exist_ok=True)
        return tomes_dir

    monkeypatch.setattr(gw, "resource", fake_resource)

    long_name = "available functions " * 20
    normalized = long_name.strip()

    result = tome.shuffle(long_name, all=True)

    slug = tome._slugify(normalized)
    tome_path = tomes_dir / f"{slug}.json"

    assert result["tome"] == normalized
    assert tome_path.exists()
    assert len(slug) <= tome._MAX_TOME_SLUG_LENGTH
    assert len(tome_path.name) < 128
