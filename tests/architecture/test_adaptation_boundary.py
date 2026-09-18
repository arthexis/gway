import gway.adaptation as adaptation
import gway.dispatch as dispatch


def test_adaptation_module_owns_pipeline_mapping():
    assert callable(adaptation.adapt_pipeline)


def test_dispatch_delegates_pipeline_mapping_to_adaptation():
    names = set(dispatch.dispatch_stage.__code__.co_names)
    assert "adapt_pipeline" in names


def test_adaptation_is_parameter_aware():
    names = set(adaptation.adapt_pipeline.__code__.co_names)
    assert "_available_parameters" in names
    assert "_compatible" in names
