import gway.adaptation as adaptation
import gway.dispatch as dispatch


def test_adaptation_module_owns_pipeline_mapping():
    assert callable(adaptation.adapt_pipeline)


def test_dispatch_delegates_pipeline_mapping_to_adaptation():
    names = set(dispatch.dispatch_stage.__code__.co_names)
    assert "adapt_pipeline" in names
