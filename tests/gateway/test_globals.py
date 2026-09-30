import pytest
from gway.mutation import MutationError


def test_globals_are_idempotent_and_preserve_operation_flags(gateway):
    gateway.wrap('echo', lambda value, json=False: (value, json))
    assert gateway.execute('-j --json echo "a ; b" --json') == ('a ; b', True)
    assert gateway.execute("echo '--timed' --no-json") == ('--timed', False)


def test_call_timing_does_not_leak_on_failure(gateway, caplog):
    gateway.wrap('probe', lambda: gateway.call_timed)
    with caplog.at_level('INFO', logger='gway'):
        assert gateway.execute('--timed probe') is True
    assert any('[timed] operation probe' in record.message for record in caplog.records)
    assert gateway.execute('probe') is False
    with pytest.raises(LookupError):
        gateway.execute('--timed missing-operation')
    assert gateway.call_timed is False


@pytest.mark.parametrize('flag', ['--interactive', '-R', '--logfile', '--mutate', '--fuzzy'])
def test_unsupported_globals_refused_before_invocation(gateway, flag):
    calls = []
    gateway.wrap('probe', lambda: calls.append(True))
    with pytest.raises(ValueError, match='Unsupported global flag'):
        gateway.execute(f'{flag} probe')
    assert calls == []


def test_no_mutate_can_only_tighten(gateway):
    calls = []
    gateway.wrap('write', lambda: calls.append(True))
    with pytest.raises(MutationError):
        gateway.execute('-M write')
    with pytest.raises(ValueError):
        gateway.execute('--mutate write', mutate=False)
    assert calls == []


@pytest.mark.parametrize('surface', ['execute', '__call__'])
def test_call_surfaces_share_globals_and_inherited_policy(gateway, surface):
    call = getattr(gateway, surface)
    gateway.wrap('probe', lambda: gateway.call_timed)
    assert call('-j --timed probe') is True
    assert call('probe') is False
    gateway.wrap('write', lambda: True)
    with pytest.raises(MutationError):
        call('-M write')
    with gateway.mutation_scope(mutate=False):
        with pytest.raises(MutationError):
            call('write')
    assert gateway.call_timed is False


def test_manual_chain_head_accepts_globals(gateway):
    gateway.wrap('records', lambda: [{'name': 'one'}, {'name': 'two'}])
    with gateway.chain('-j --timed records') as chain:
        assert chain('filter --name one') == [{'name': 'one'}]
    assert gateway.call_timed is False
