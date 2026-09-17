from __future__ import annotations

import shlex
from collections.abc import Iterator
from pathlib import Path

from .model import RecipeError, RecipeStatement, _LogicalRecipeLine


def _indent_width(text: str) -> int:
    """Return the number of leading whitespace characters in a physical recipe line."""
    return len(text) - len(text.lstrip())


def _tokenize_recipe_statement(path: Path, text: str, *, line: int) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(text, comments=False, posix=True))
    except ValueError as exc:
        raise RecipeError(path, str(exc), line=line) from exc


def _split_fitness_tokens(
    path: Path,
    tokens: tuple[str, ...],
    *,
    line: int,
) -> tuple[tuple[str, ...], tuple[str, ...] | None]:
    """Split one recipe statement into operation and optional fitness tokens."""
    separators = [index for index, token in enumerate(tokens) if token == "-->"]
    if not separators:
        return tokens, None
    if len(separators) > 1:
        raise RecipeError(path, "fitness syntax accepts exactly one '-->' operator", line=line)

    separator = separators[0]
    operation_tokens = tokens[:separator]
    fitness_tokens = tokens[separator + 1 :]
    if not operation_tokens:
        raise RecipeError(path, "fitness syntax requires an operation before '-->'", line=line)
    if not fitness_tokens:
        raise RecipeError(path, "fitness syntax requires a fitness function after '-->'", line=line)
    if any(token.startswith("-") for token in fitness_tokens):
        raise RecipeError(
            path,
            "fitness functions inside '-->' do not accept inline flags; use semantic context instead",
            line=line,
        )
    return operation_tokens, fitness_tokens


def _logical_recipe_lines_from_source(path: Path, source: str) -> tuple[_LogicalRecipeLine, ...]:
    """Group physical recipe lines without tokenizing statement contents.

    A trailing ``:`` introduces a continuation whose following non-empty,
    non-comment lines must be indented to one common level and must begin with
    an option token. Header text and continuation arguments remain structurally
    separate so ``operation --> fitness:`` attaches continued options to the
    operation rather than to the fitness predicate.
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
                header,
                tuple(continuation_parts),
            )
        )
        index = cursor

    return tuple(logical_lines)


def _recipe_statement_lines_from_source(
    source: str,
    *,
    path: Path | None = None,
) -> tuple[int, ...]:
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
        header_tokens = _tokenize_recipe_statement(recipe_path, logical.text, line=logical.line)
        if header_tokens:
            operation_tokens, fitness_tokens = _split_fitness_tokens(
                recipe_path,
                header_tokens,
                line=logical.line,
            )
            continuation_tokens = tuple(
                token
                for part in logical.continuation_parts
                for token in _tokenize_recipe_statement(recipe_path, part, line=logical.line)
            )
            yield RecipeStatement(
                recipe_path,
                logical.line,
                operation_tokens + continuation_tokens,
                logical.end_line,
                fitness_tokens,
            )


__all__ = ["recipe_statements"]
