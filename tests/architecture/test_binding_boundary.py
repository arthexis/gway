import inspect

import gway.binding as binding


def test_binding_module_owns_argument_binding_contract():
    assert callable(binding.bind_arguments)
    assert callable(binding.convert_argument)
    assert inspect.isclass(binding.BoundCall)
