import pytest

from gway.recipes import execute_recipe


def _record_finalization(gateway, monkeypatch):
    calls = []

    def finalize(primary=None):
        calls.append((gateway.execution_depth, primary))

    monkeypatch.setattr(gateway, "_finalize_execution", finalize)
    return calls


def test_dispatch_finalizes_once_at_outer_boundary(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)

    result = gateway(["env", "PATH"])

    assert result is not None
    assert calls == [(0, None)]
    assert gateway.execution_depth == 0


def test_nested_dispatch_does_not_finalize_inner_call(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    depths = []

    def nested():
        depths.append(gateway.execution_depth)
        result = gateway(["env", "PATH"])
        depths.append(gateway.execution_depth)
        return result

    gateway.nested = gateway.wrap("nested", nested)

    result = gateway(["nested"])

    assert result is not None
    assert depths == [1, 1]
    assert calls == [(0, None)]


def test_nested_dispatch_can_share_open_journal_until_outer_program_commits(
    gateway,
    tmp_path,
    monkeypatch,
):
    calls = _record_finalization(gateway, monkeypatch)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    destination = tmp_path / "destination.txt"

    def nested():
        gateway.copy(str(source), to=str(destination), rollback="deploy")
        return "nested"

    gateway.nested = gateway.wrap("nested", nested)

    gateway("nested ; commit deploy")

    assert destination.read_text(encoding="utf-8") == "source"
    assert gateway.journal.get("deploy") is None
    assert calls == [(0, None)]


def test_recipe_execution_uses_same_outer_boundary(gateway, tmp_path, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    recipe = tmp_path / "nested.rx"
    recipe.write_text("env PATH\n", encoding="utf-8")

    result = gateway([recipe])

    assert result is not None
    assert calls == [(0, None)]


def test_direct_recipe_execution_owns_boundary(gateway, tmp_path, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    recipe = tmp_path / "direct.rx"
    recipe.write_text("env PATH\n", encoding="utf-8")

    _, result = execute_recipe(gateway, recipe)

    assert result is not None
    assert calls == [(0, None)]


def test_chain_holds_outer_scope_until_context_exit(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)

    with gateway.chain("env PATH") as chain:
        assert gateway.execution_depth == 1
        assert calls == []
        chain("env HOME")
        assert gateway.execution_depth == 1
        assert calls == []

    assert gateway.execution_depth == 0
    assert calls == [(0, None)]


def test_outer_boundary_receives_primary_exception(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    primary = RuntimeError("boom")

    def fail():
        raise primary

    gateway.fail_boundary = gateway.wrap("fail_boundary", fail)

    with pytest.raises(RuntimeError) as raised:
        gateway(["fail_boundary"])

    assert raised.value is primary
    assert calls == [(0, primary)]
    assert gateway.execution_depth == 0


def test_chain_failure_finalizes_once_with_primary(gateway, monkeypatch):
    calls = _record_finalization(gateway, monkeypatch)
    primary = RuntimeError("chain failed")

    def fail():
        raise primary

    gateway.fail_chain = gateway.wrap("fail_chain", fail)

    with pytest.raises(RuntimeError) as raised:
        with gateway.chain("env PATH") as chain:
            chain("fail_chain")

    assert raised.value is primary
    assert calls == [(0, primary)]
    assert gateway.execution_depth == 0
