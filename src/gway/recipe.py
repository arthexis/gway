from __future__ import annotations

import shlex
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .chain import run_chain
from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher import Dispatcher
from .expression import MANAGED_CHAIN_PROJECT, normalize_managed_args
from .explain import record

_RECIPE_SUFFIX = ".rx"
_CORE_COMMANDS = frozenset(
    {
        "list",
        "info",
        "path",
        "register",
        "install",
        "uninstall",
        "upgrade",
        "service",
        "shell",
        "solve",
        "recipe",
    }
)


class RecipeError(ValueError):
    """Raised when a GWAY recipe is malformed or a statement fails."""


def _tokens(line: str, *, line_number: int | None = None) -> tuple[bool, list[str]]:
    try:
        values = shlex.split(line, comments=True, posix=True)
    except ValueError as exc:
        prefix = f"line {line_number}: " if line_number is not None else ""
        raise RecipeError(f"{prefix}{exc}") from exc
    if not values:
        return False, []
    chained = values[0] == "-"
    if chained:
        values = values[1:]
        if not values:
            prefix = f"line {line_number}: " if line_number is not None else ""
            raise RecipeError(f"{prefix}chain continuation requires a command")
    return chained, values


def _render(result: object, *, json_output: bool) -> None:
    from .cli import _render_result

    _render_result(result, json_output=json_output)


def _default_core_runner(tokens: Sequence[str]) -> int:
    from .bootstrap import main

    return main(tokens)


class RecipeSession:
    """Execute recipe statements against one shared named context."""

    def __init__(
        self,
        *,
        dispatcher: Dispatcher | None = None,
        core_runner: Callable[[Sequence[str]], int] | None = None,
        json_output: bool = False,
    ) -> None:
        self.dispatcher = dispatcher or Dispatcher()
        self.core_runner = core_runner or _default_core_runner
        self.json_output = json_output
        self.context: dict[str, object] = {}
        self.last_result: object = None
        self._has_chain_source = False

    def execute(self, tokens: Sequence[str], *, chained: bool = False) -> object:
        if not tokens:
            return self.last_result
        if tokens[0] == "recipe":
            raise RecipeError("recipes cannot recursively invoke the recipe command")

        if tokens[0] in _CORE_COMMANDS:
            if chained:
                raise RecipeError("core commands cannot receive '-' positional transfer")
            record("recipe.statement", "executing core recipe statement", tokens=list(tokens))
            status = self.core_runner(tokens)
            if status:
                raise RecipeError(f"command exited with status {status}: {shlex.join(tokens)}")
            self.last_result = None
            self._has_chain_source = False
            return None

        if chained and not self._has_chain_source:
            raise RecipeError("'-' requires a previous managed recipe result")

        record(
            "recipe.statement",
            "executing managed recipe statement",
            tokens=list(tokens),
            chained=chained,
        )
        if chained:
            result = run_chain(
                self.dispatcher,
                tokens,
                context=self.context,
                initial_result=self.last_result,
            )
        else:
            project_name, project_args = normalize_managed_args(tokens)
            if project_name == MANAGED_CHAIN_PROJECT:
                result = run_chain(self.dispatcher, project_args, context=self.context)
            else:
                result = self.dispatcher.run(project_name, project_args)
                publish_chain_result(result)

        self.last_result = result
        self._has_chain_source = True
        _render(result, json_output=self.json_output)
        return result


def run_recipe_lines(
    lines: Iterable[str],
    *,
    dispatcher: Dispatcher | None = None,
    core_runner: Callable[[Sequence[str]], int] | None = None,
    json_output: bool = False,
) -> object:
    session = RecipeSession(
        dispatcher=dispatcher,
        core_runner=core_runner,
        json_output=json_output,
    )
    with chain_context_scope(session.context):
        for line_number, line in enumerate(lines, start=1):
            chained, tokens = _tokens(line, line_number=line_number)
            if not tokens:
                continue
            try:
                session.execute(tokens, chained=chained)
            except Exception as exc:
                if isinstance(exc, RecipeError) and str(exc).startswith("line "):
                    raise
                raise RecipeError(f"line {line_number}: {exc}") from exc
    return session.last_result


def run_recipe_file(
    path: str | Path,
    *,
    dispatcher: Dispatcher | None = None,
    core_runner: Callable[[Sequence[str]], int] | None = None,
    json_output: bool = False,
) -> object:
    recipe = Path(path)
    if recipe.suffix.lower() != _RECIPE_SUFFIX:
        raise RecipeError(f"recipe files must use the {_RECIPE_SUFFIX} extension: {recipe}")
    try:
        text = recipe.read_text(encoding="utf-8")
    except OSError as exc:
        raise RecipeError(f"cannot read recipe {recipe}: {exc}") from exc
    record("recipe.start", "executing recipe file", path=str(recipe))
    result = run_recipe_lines(
        text.splitlines(),
        dispatcher=dispatcher,
        core_runner=core_runner,
        json_output=json_output,
    )
    record("recipe.result", "recipe file completed", path=str(recipe), result=result)
    return result


def run_recipe_repl(
    *,
    dispatcher: Dispatcher | None = None,
    core_runner: Callable[[Sequence[str]], int] | None = None,
    json_output: bool = False,
) -> int:
    session = RecipeSession(
        dispatcher=dispatcher,
        core_runner=core_runner,
        json_output=json_output,
    )
    with chain_context_scope(session.context):
        while True:
            try:
                line = input("rx> ")
            except EOFError:
                print()
                return 0
            except KeyboardInterrupt:
                print(file=sys.stderr)
                continue

            if line.strip() in {"exit", "quit"}:
                return 0
            try:
                chained, tokens = _tokens(line)
                if tokens:
                    session.execute(tokens, chained=chained)
            except Exception as exc:
                print(f"gway: {exc}", file=sys.stderr)


__all__ = [
    "RecipeError",
    "RecipeSession",
    "run_recipe_file",
    "run_recipe_lines",
    "run_recipe_repl",
]
