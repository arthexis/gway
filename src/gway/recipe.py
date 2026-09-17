from __future__ import annotations

import shlex
from collections.abc import Callable, Iterator, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .chain_context import current_chain_provenance
from .dispatcher import Dispatcher
from .explain import record
from .provenance import ContinuationPoint, ValueProvenance
from .runtime import GwayRuntime


@dataclass(frozen=True, slots=True)
class RecipeStatement:
    path: Path
    line: int
    tokens: tuple[str, ...]
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class _LogicalRecipeLine:
    line: int
    end_line: int
    text: str


class RecipeError(RuntimeError):
    def __init__(self, path: Path, message: str, *, line: int | None = None) -> None:
        self.path = path
        self.line = line
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"{location}: {message}")


class _LiveProvenance(MutableMapping[str, ValueProvenance]):
    """Sidecar provenance that invalidates entries when backing values change."""

    def __init__(
        self,
        values: MutableMapping[str, object],
        initial: Mapping[str, ValueProvenance] | None = None,
    ) -> None:
        self._values = values
        self._records: dict[str, tuple[ValueProvenance, object]] = {}
        for key, provenance in (initial or {}).items():
            if key in values:
                self._records[key] = (provenance, values[key])

    def _valid(self, key: str) -> bool:
        record = self._records.get(key)
        if record is None or key not in self._values:
            return False
        _, snapshot = record
        try:
            return self._values[key] == snapshot
        except Exception:
            return self._values[key] is snapshot

    def __getitem__(self, key: str) -> ValueProvenance:
        if not self._valid(key):
            self._records.pop(key, None)
            raise KeyError(key)
        return self._records[key][0]

    def __setitem__(self, key: str, value: ValueProvenance) -> None:
        if key not in self._values:
            self._records.pop(key, None)
            return
        self._records[key] = (value, self._values[key])

    def __delitem__(self, key: str) -> None:
        del self._records[key]

    def __iter__(self) -> Iterator[str]:
        for key in tuple(self._records):
            if self._valid(key):
                yield key
            else:
                self._records.pop(key, None)

    def __len__(self) -> int:
        return sum(1 for _ in self)


class RecipeContext(MutableMapping[str, object]):
    """Named recipe values backed by a live mapping with sidecar provenance."""

    def __init__(
        self,
        values: MutableMapping[str, object] | None = None,
        *,
        provenance: Mapping[str, ValueProvenance] | None = None,
    ) -> None:
        self._values: MutableMapping[str, object] = {} if values is None else values
        self.provenance: MutableMapping[str, ValueProvenance] = _LiveProvenance(
            self._values,
            provenance,
        )

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __setitem__(self, key: str, value: object) -> None:
        self._values[key] = value
        self.provenance.pop(key, None)

    def __delitem__(self, key: str) -> None:
        del self._values[key]
        self.provenance.pop(key, None)

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def _indent_width(text: str) -> int:
    """Return the number of leading whitespace characters in a physical recipe line."""
    return len(text) - len(text.lstrip())


def _tokenize_recipe_statement(path: Path, text: str, *, line: int) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(text, comments=False, posix=True))
    except ValueError as exc:
        raise RecipeError(path, str(exc), line=line) from exc


def _logical_recipe_lines_from_source(path: Path, source: str) -> tuple[_LogicalRecipeLine, ...]:
    """Group physical recipe lines without tokenizing statement contents.

    A trailing ``:`` introduces a continuation whose following non-empty,
    non-comment lines must be indented to one common level and must begin with
    an option token. The resulting text is still tokenized later by the normal
    GWAY statement path, preserving lazy tokenization and one execution model.
    """
    lines = source.splitlines()
    logical_lines: list[_LogicalRecipeLine] = []
    index = 0

    while index < len(lines):
        text = lines[index]
        line_number = index + 1
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        if not text.rstrip().endswith(":"):
            logical_lines.append(_LogicalRecipeLine(line_number, line_number, text))
            index += 1
            continue

        header_indent = _indent_width(text)
        header = text.rstrip()[:-1].rstrip()
        if not header.strip():
            raise RecipeError(path, "continuation header cannot be empty", line=line_number)

        continuation_parts: list[str] = []
        continuation_indent: int | None = None
        end_line = line_number
        cursor = index + 1

        while cursor < len(lines):
            continuation_text = lines[cursor]
            continuation_line = cursor + 1
            continuation_stripped = continuation_text.strip()

            if not continuation_stripped or continuation_stripped.startswith("#"):
                cursor += 1
                continue

            indent = _indent_width(continuation_text)
            if indent <= header_indent:
                break
            if continuation_indent is None:
                continuation_indent = indent
            elif indent != continuation_indent:
                raise RecipeError(
                    path,
                    "nested or inconsistent continuation indentation is not supported",
                    line=continuation_line,
                )
            if not continuation_stripped.startswith("-"):
                raise RecipeError(
                    path,
                    "continuation lines must contain arguments or modifiers beginning with '-'",
                    line=continuation_line,
                )

            continuation_parts.append(continuation_stripped)
            end_line = continuation_line
            cursor += 1

        if not continuation_parts:
            raise RecipeError(path, "continuation requires indented arguments", line=line_number)

        logical_lines.append(
            _LogicalRecipeLine(
                line_number,
                end_line,
                " ".join((header, *continuation_parts)),
            )
        )
        index = cursor

    return tuple(logical_lines)


def _recipe_statement_lines_from_source(source: str, *, path: Path | None = None) -> tuple[int, ...]:
    """Return starting physical lines for logical statements in a recipe snapshot."""
    recipe_path = path if path is not None else Path("<recipe>")
    return tuple(
        logical.line for logical in _logical_recipe_lines_from_source(recipe_path, source)
    )


def _recipe_statement_lines(path: Path) -> tuple[int, ...]:
    """Return starting physical lines for logical statements in a recipe."""
    return _recipe_statement_lines_from_source(
        path.read_text(encoding="utf-8"),
        path=path,
    )


def recipe_statements(
    path: str | Path,
    *,
    start_statement_index: int = 1,
    source: str | None = None,
) -> Iterator[RecipeStatement]:
    """Yield tokenized logical statements, optionally from an immutable source snapshot."""
    recipe_path = Path(path).resolve()
    if recipe_path.suffix != ".rx":
        raise RecipeError(recipe_path, "recipe files must use the .rx extension")
    if start_statement_index < 1:
        raise RecipeError(recipe_path, "start statement index must be positive")

    recipe_source = source if source is not None else recipe_path.read_text(encoding="utf-8")
    logical_lines = _logical_recipe_lines_from_source(recipe_path, recipe_source)
    for statement_index, logical in enumerate(logical_lines, start=1):
        if statement_index < start_statement_index:
            continue
        tokens = _tokenize_recipe_statement(recipe_path, logical.text, line=logical.line)
        if tokens:
            yield RecipeStatement(
                recipe_path,
                logical.line,
                tokens,
                logical.end_line,
            )


@dataclass(slots=True)
class RecipeSession:
    """Execute multiple GWAY statements against one persistent named context."""

    dispatcher: Dispatcher
    context: MutableMapping[str, object] = field(default_factory=dict)
    runtime: GwayRuntime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, RecipeContext):
            self.context = RecipeContext(self.context)
        if self.runtime is None:
            self.runtime = GwayRuntime(self.dispatcher)

    def run(
        self,
        tokens: Sequence[str],
        *,
        interactive: bool = False,
        prompt: Callable[[str], str] | None = None,
        recipe_path: str | Path | None = None,
        recipe_line: int | None = None,
    ) -> object:
        assert self.runtime is not None
        return self.runtime.execute(
            tokens,
            interactive=interactive,
            prompt=prompt,
            context=self.context,
            recipe_path=str(recipe_path) if recipe_path is not None else None,
            recipe_line=recipe_line,
        )


def child_recipe_context(
    parent: Mapping[str, object] | None = None,
    *,
    incoming: object = None,
    has_incoming: bool = False,
) -> RecipeContext:
    """Create an isolated child frame and explicitly publish chained input into it."""
    context = RecipeContext(dict(parent or {}), provenance=current_chain_provenance())
    if has_incoming:
        if isinstance(incoming, Mapping):
            context.update(incoming)
        context["result"] = incoming
    return context


def _run_recipe_body(
    recipe_path: Path,
    session: RecipeSession,
    *,
    interactive: bool,
    prompt: Callable[[str], str] | None,
    start_statement_index: int = 1,
    initial_result: object = None,
    has_initial_result: bool = False,
    source: str | None = None,
) -> object:
    """Execute recipe statements within an already-established recipe frame."""
    assert session.runtime is not None
    result: object = initial_result if has_initial_result else None
    statement_lines = (
        _recipe_statement_lines_from_source(source, path=recipe_path)
        if source is not None
        else _recipe_statement_lines(recipe_path)
    )
    record(
        "recipe.start",
        "executing recipe",
        path=str(recipe_path),
        start_statement_index=start_statement_index,
    )
    for statement_index, statement in enumerate(
        recipe_statements(
            recipe_path,
            start_statement_index=start_statement_index,
            source=source,
        ),
        start=start_statement_index,
    ):
        next_statement_index = statement_index + 1 if statement_index < len(statement_lines) else None
        next_line = statement_lines[statement_index] if statement_index < len(statement_lines) else None
        continuation = ContinuationPoint(
            recipe_path=str(statement.path),
            statement_index=statement_index,
            line=statement.line,
            next_statement_index=next_statement_index,
            next_line=next_line,
        )
        context_provenance = getattr(session.context, "provenance", None)
        with session.runtime.frames.continuation_scope(
            continuation,
            context=session.context,
            provenance=context_provenance,
        ):
            continuation_stack = [
                point.as_dict() for point in session.runtime.frames.continuations
            ]
            record(
                "recipe.statement.start",
                "executing recipe statement",
                path=str(statement.path),
                line=statement.line,
                end_line=statement.end_line,
                tokens=list(statement.tokens),
                continuation=continuation.as_dict(),
                continuation_stack=continuation_stack,
            )
            try:
                result = session.run(
                    statement.tokens,
                    interactive=interactive,
                    prompt=prompt,
                    recipe_path=statement.path,
                    recipe_line=statement.line,
                )
            except RecipeError:
                raise
            except SystemExit as exc:
                raise RecipeError(
                    statement.path,
                    f"statement exited with status {exc.code}",
                    line=statement.line,
                ) from exc
            except Exception as exc:
                raise RecipeError(statement.path, str(exc), line=statement.line) from exc
            record(
                "recipe.statement.result",
                "completed recipe statement",
                path=str(statement.path),
                line=statement.line,
                end_line=statement.end_line,
                result=result,
                continuation=continuation.as_dict(),
                continuation_stack=continuation_stack,
            )
    record("recipe.result", "recipe completed", path=str(recipe_path), result=result)
    return result


def _run_recipe_from(
    recipe_path: Path,
    session: RecipeSession,
    *,
    interactive: bool,
    prompt: Callable[[str], str] | None,
    start_statement_index: int,
    initial_result: object = None,
    has_initial_result: bool = False,
    source: str | None = None,
) -> object:
    """Run one recipe from a logical statement ordinal without duplicating recipe frames."""
    assert session.runtime is not None
    current = session.runtime.current_frame
    if current is not None and current.kind == "recipe" and current.recipe_path == str(recipe_path):
        return _run_recipe_body(
            recipe_path,
            session,
            interactive=interactive,
            prompt=prompt,
            start_statement_index=start_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )
    with session.runtime.frame_scope("recipe", recipe_path=str(recipe_path)):
        return _run_recipe_body(
            recipe_path,
            session,
            interactive=interactive,
            prompt=prompt,
            start_statement_index=start_statement_index,
            initial_result=initial_result,
            has_initial_result=has_initial_result,
            source=source,
        )


def run_recipe(
    path: str | Path,
    dispatcher: Dispatcher,
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    context: MutableMapping[str, object] | None = None,
    runtime: GwayRuntime | None = None,
) -> object:
    """Execute one .rx recipe with persistent named context and fail-fast semantics."""
    if isinstance(context, RecipeContext):
        recipe_context = RecipeContext(dict(context), provenance=context.provenance)
    else:
        recipe_context = RecipeContext(dict(context or {}))
    session = RecipeSession(dispatcher, context=recipe_context, runtime=runtime)
    return _run_recipe_from(
        Path(path),
        session,
        interactive=interactive,
        prompt=prompt,
        start_statement_index=1,
    )


__all__ = [
    "RecipeContext",
    "RecipeError",
    "RecipeSession",
    "RecipeStatement",
    "child_recipe_context",
    "recipe_statements",
    "run_recipe",
]
