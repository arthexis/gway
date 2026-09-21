import gway.adaptation as adaptation
import gway.dispatch as dispatch


def test_adaptation_module_owns_pipeline_mapping():
    assert callable(adaptation.plan_pipeline)
    assert callable(adaptation.apply_plan)
    assert callable(adaptation.adapt_pipeline)


def test_dispatch_delegates_pipeline_mapping_to_adaptation():
    names = set(dispatch.dispatch_stage.__code__.co_names)
    assert "adapt_pipeline" in names


def test_adaptation_planning_is_separate_from_application():
    plan_names = set(adaptation.plan_pipeline.__code__.co_names)
    adapt_names = set(adaptation.adapt_pipeline.__code__.co_names)

    assert "_pipeline_args" in plan_names
    assert "AdaptationPlan" in plan_names
    assert "apply_plan" in adapt_names
