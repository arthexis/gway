import pytest

from gway.engine import EngineValidationError
from gway.gateway import Gateway


def test_render_validation_uses_resolved_text_before_mutation(tmp_path, monkeypatch):
    template = tmp_path / "candidate.conf"
    template.write_text(
        "listen [[::]]:80;\nserver_name [domain];\n",
        encoding="utf-8",
    )
    destination = tmp_path / "live.conf"
    destination.write_text("known-good\n", encoding="utf-8")

    gateway = Gateway(
        context={"domain": "example.test"},
        cache=tmp_path / "cache",
    )
    seen = {}

    def reject(engine, content, *, executable=None, identity=None):
        seen["engine"] = engine
        seen["content"] = content
        raise EngineValidationError("candidate rejected")

    monkeypatch.setattr("gway.rendering.validate_text", reject)

    with pytest.raises(EngineValidationError, match="candidate rejected"):
        gateway._renderer.render(
            str(template),
            str(destination),
            validate="nginx",
        )

    assert seen == {
        "engine": "nginx",
        "content": "listen [::]:80;\nserver_name example.test;\n",
    }
    assert destination.read_text(encoding="utf-8") == "known-good\n"
