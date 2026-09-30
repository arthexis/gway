import pytest


def test_structured_pipeline_and_catalog(gateway):
    result = gateway.execute('-j --timed builtins - filter --name version', mutate=False)
    assert [item['name'] for item in result] == ['version']
    assert result[0]['mutates'] is False
    assert gateway.call_timed is False


def test_filter_preserves_records_and_combines_predicates(gateway):
    records = [{'level': 'ERROR', 'delay': 12}, {'level': 'INFO', 'delay': 20}]
    gateway.wrap('records', lambda: records)
    result = gateway('records - filter --level ERROR --field delay --gt 10')
    assert result == [records[0]]
    assert result[0] is records[0]
    assert gateway.ops.resolve("filter")(records, level='missing') == []
    assert gateway.ops.resolve("filter")(['error one', 'fine'], 'error') == ['error one']


def test_filter_validates_fields_and_input(gateway):
    with pytest.raises(KeyError):
        gateway.ops.resolve("filter")([{'level': 'INFO'}], missing='x')
    with pytest.raises(ValueError, match='require --field'):
        gateway.ops.resolve("filter")([], gt=2)
    with pytest.raises(TypeError, match='sequence'):
        gateway.ops.resolve("filter")('text')
    with pytest.raises(Exception, match='[Aa]mbiguous'):
        gateway.ops.resolve("filter")([{'a-b': 1, 'a_b': 2}], **{'a b': 1})


def test_catalog_excludes_external_and_shadowed_operations(gateway):
    assert 'path' in {item['name'] for item in gateway.builtins()}
    gateway.wrap('external', lambda: 1)
    assert 'external' not in {item['name'] for item in gateway.builtins()}
    gateway.wrap('version', lambda: 'custom')
    assert 'version' not in {item['name'] for item in gateway.builtins()}
    with gateway.authorized(operations={'builtins', 'filter'}, environment=set()):
        assert {item['name'] for item in gateway.execute('builtins', mutate=False)} == {'builtins', 'filter'}
