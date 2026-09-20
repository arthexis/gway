import pytest


@pytest.fixture
def rollback_paths(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"
    return source, destination
