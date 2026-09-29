from pathlib import Path

from gway.sampler import recipes


def test_sampler_reference_lists_every_maintained_recipe():
    reference = Path("docs/SAMPLER.md").read_text(encoding="utf-8")

    missing = [
        name
        for name in recipes()
        if f"`{name}`" not in reference
    ]

    assert missing == []


def test_docs_index_links_sampler_reference():
    index = Path("docs/README.md").read_text(encoding="utf-8")

    assert "[Sampler](SAMPLER.md)" in index
