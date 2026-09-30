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


def test_engine_validation_error_includes_bounded_candidate_excerpt(monkeypatch):
    from types import SimpleNamespace

    from gway import engine

    monkeypatch.setattr(
        engine.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stderr="nginx parse error",
            stdout="",
        ),
    )

    content = "\n".join(f"line-{index}" for index in range(1, 12))
    with pytest.raises(EngineValidationError) as raised:
        engine.validate_text("nginx", content)

    message = str(raised.value)
    assert "nginx parse error" in message
    assert "  1: line-1" in message
    assert "  8: line-8" in message
    assert "line-9" not in message
