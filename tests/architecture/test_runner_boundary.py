import gway.runner as runner


def test_runner_module_owns_invocation_contract():
    assert callable(runner.invoke)
