from collections.abc import Callable, Sequence

from gway.runtime import GwayRuntime
from gway.stage import Stage


class _Runtime(GwayRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[tuple[str, ...], tuple[object, ...], object, bool]] = []

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
        self.calls.append(
            (tuple(stage.raw_tokens), tuple(transfer), previous_result, has_previous_result)
        )
        return "done"


def test_run_statement_resumes_at_saved_stage_with_previous_result() -> None:
    from gway.chain import run_statement

    runtime = _Runtime()
    tokens = ("demo", "one", "-", "demo", "two")
    with runtime.frame_scope("statement", tokens=tokens):
        result = run_statement(
            runtime.dispatcher,
            tokens,
            runtime=runtime,
            start_stage_index=1,
            initial_result="saved",
            has_initial_result=True,
        )
    assert result == "done"
    assert runtime.calls == [(('demo', 'two'), ('saved',), 'saved', True)]
