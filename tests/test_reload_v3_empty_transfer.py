from collections.abc import Callable, Sequence

from gway.runtime import GwayRuntime
from gway.stage import Stage


class _Runtime(GwayRuntime):
    def execute_stage(
        self,
        stage: Stage,
        transfer: Sequence[object],
        *,
        interactive: bool,
        prompt: Callable[[str], str] | None = None,
        previous_result: object = None,
        has_previous_result: bool = False,
    ) -> object:
        assert transfer == []
        assert has_previous_result is False
        return "done"


def test_restored_first_stage_boundary_can_continue_without_previous_result() -> None:
    from gway.chain import run_statement

    runtime = _Runtime()
    tokens = ("reload", "-", "demo", "two")
    with runtime.frame_scope("statement", tokens=tokens):
        result = run_statement(
            runtime.dispatcher,
            tokens,
            runtime=runtime,
            start_stage_index=1,
            has_initial_result=False,
        )
    assert result == "done"
