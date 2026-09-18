import inspect

import gway.binding as binding
import gway.console as console


def test_binding_module_owns_argument_binding_contract():
    assert callable(binding.bind_arguments)
    assert callable(binding.convert_argument)
    assert inspect.isclass(binding.BoundCall)


def test_console_no_longer_defines_private_binding_helpers():
    assert not hasattr(console, "_bind_arguments")
    assert not hasattr(console, "_convert")
