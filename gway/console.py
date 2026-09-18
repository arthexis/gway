# file: gway/console.py

import argparse
import inspect
import json
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .gateway import Gateway, Literal, gw
from .sigils import Sigil


@dataclass(frozen=True)
class Token:
    """A lexical token with optional quote provenance."""

    value: str
    quote: str | None = None

    @property
    def literal(self) -> bool:
        return self.quote == "single"

    def __str__(self) -> str:
        return self.value


def tokenize(text: str) -> list[Token]:
    """Split recipe text while preserving single/double quote provenance."""
    tokens: list[Token] = []
    current: list[str] = []
    quote: str | None = None
    token_quote: str | None = None
    escaped = False
    started = False

    def emit() -> None:
        nonlocal current, token_quote, started
        if started:
            tokens.append(Token("".join(current), token_quote))
        current = []
        token_quote = None
        started = False

    for char in text:
        if escaped:
            current.append(char)
            started = True
            escaped = False
            continue

        if quote == "double" and char == "\\":
            escaped = True
            started = True
            continue

        if quote is None:
            if char.isspace():
                emit()
                continue
            if char == "'":
                if not started:
                    token_quote = "single"
                elif token_quote != "single":
                    token_quote = None
                quote = "single"
                started = True
                continue
            if char == '"':
                if not started:
                    token_quote = "double"
                elif token_quote != "double":
                    token_quote = None
                quote = "double"
                started = True
                continue
            current.append(char)
            started = True
            continue

        if quote == "single":
            if char == "'":
                quote = None
            else:
                current.append(char)
            continue

        if quote == "double":
            if char == '"':
                quote = None
            else:
                current.append(char)
            continue

    if escaped:
        current.append("\\")
    if quote is not None:
        raise ValueError(f"Unterminated {quote}-quoted string")
    emit()
    return tokens


def _value(token) -> str:
    return token.value if isinstance(token, Token) else str(token)


def _literal(token) -> bool:
    return isinstance(token, Token) and token.literal


def parse_recipe_context(tokens):
    """Parse --key value tokens into a context mapping."""
    context = {}
    index = 0
    tokens = list(tokens)
    while index < len(tokens):
        token = _value(tokens[index])
        if _literal(tokens[index]) or not token.startswith("--") or token == "--":
            raise ValueError(f"Unexpected argument: {token}")
        key = token[2:].replace("-", "_")
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_value = _value(next_token)
            if _literal(next_token) or not next_value.startswith("--"):
                context[key] = next_value
                index += 2
                continue
        context[key] = True
        index += 1
    return context


def cli_main():
    """Run the minimal GWAY command-line interface."""
    parser = argparse.ArgumentParser(
        prog="gway",
        description="GWAY command-dispatch and composition core",
    )
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    parser.add_argument("-r", "--recipe")
    parser.add_argument("-t", "--timed", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-z", "--silent", action="store_true")
    parser.add_argument("-e", "--expression")
    args, unknown = parser.parse_known_args()

    runtime = Gateway(
        debug=args.debug,
        interactive=args.interactive,
        timed=args.timed,
        verbose=args.verbose,
        silent=args.silent,
    )

    if args.recipe:
        runtime.context.update(parse_recipe_context(unknown))
        commands, _ = load_recipe(args.recipe)
        _, output = process(commands, gw_instance=runtime)
    elif args.expression:
        runtime.context.update(parse_recipe_context(unknown))
        output = runtime.resolve(args.expression)
    elif unknown:
        _, output = process([unknown], gw_instance=runtime)
    else:
        parser.print_help()
        return 0

    if output is not None and not args.silent:
        if args.json:
            print(json.dumps(output, indent=2, default=str))
        else:
            print(output)
    return 0


def _resolve_operation(runtime, tokens):
    """Resolve the longest leading token sequence to a callable."""
    values = [_value(token) for token in tokens]
    for size in range(len(values), 0, -1):
        candidates = (
            " ".join(values[:size]),
            "_".join(token.replace("-", "_") for token in values[:size]),
            ".".join(token.replace("-", "_") for token in values[:size]),
        )
        for candidate in candidates:
            value = runtime.find_value(candidate)
            if callable(value):
                return value, tokens[size:], candidate

            obj = runtime
            try:
                for part in candidate.replace(" ", ".").split("."):
                    obj = getattr(obj, part)
            except AttributeError:
                continue
            if callable(obj):
                return obj, tokens[size:], candidate

    raise LookupError(f"Unable to resolve operation: {' '.join(values)}")


def _convert(token, parameter, runtime):
    literal = _literal(token)
    value = _value(token)
    annotation = parameter.annotation

    if literal:
        return Literal(value)

    if isinstance(value, str) and Sigil._pattern.search(value):
        value = runtime.resolve(value)

    if annotation in (inspect.Parameter.empty, str):
        return value
    if annotation is bool and isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if annotation in (int, float):
        return annotation(value)
    return value


def _bind_arguments(func, tokens, *, runtime, interactive=False):
    signature = inspect.signature(func)
    positional = []
    keywords = {}
    tokens = list(tokens)
    index = 0
    literal_mode = False

    while index < len(tokens):
        raw = tokens[index]
        token = _value(raw)

        if not literal_mode and not _literal(raw) and token == "--":
            literal_mode = True
            index += 1
            continue

        if not literal_mode and not _literal(raw) and token.startswith("--"):
            key = token[2:].replace("-", "_")
            parameter = signature.parameters.get(key)
            if parameter is None:
                raise TypeError(f"Unknown argument --{key.replace('_', '-')}")
            if parameter.annotation is bool or isinstance(parameter.default, bool):
                keywords[key] = True
                index += 1
                continue
            if index + 1 >= len(tokens):
                raise TypeError(f"Expected a value after {token}")
            keywords[key] = _convert(tokens[index + 1], parameter, runtime)
            index += 2
        else:
            positional.append(raw)
            index += 1

    positional_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]
    converted_positional = []
    for offset, token in enumerate(positional):
        if offset < len(positional_parameters):
            converted_positional.append(
                _convert(token, positional_parameters[offset], runtime)
            )
        else:
            converted_positional.append(_value(token))

    bound = signature.bind_partial(*converted_positional, **keywords)

    if interactive:
        for name, parameter in signature.parameters.items():
            if name in bound.arguments:
                continue
            if parameter.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            if parameter.default is not inspect.Parameter.empty:
                continue
            response = input(f"{name}: ")
            bound.arguments[name] = _convert(Token(response), parameter, runtime)

    return bound.args, bound.kwargs


def process(command_sources, *, gw_instance=None, **context):
    """Execute recipe/CLI stages against a Gateway instance."""
    runtime = gw_instance or Gateway(context=context)
    if context:
        runtime.context.update(context)

    results = []
    last_result = None

    for entry in command_sources:
        tokens = list(entry.get("tokens", [])) if isinstance(entry, dict) else list(entry)
        if not tokens:
            continue

        func, arguments, name = _resolve_operation(runtime, tokens)
        args, kwargs = _bind_arguments(
            func,
            arguments,
            runtime=runtime,
            interactive=runtime.interactive_enabled,
        )
        start = time.perf_counter() if runtime.timed_enabled else None
        result = func(*args, **kwargs)
        if start is not None:
            runtime.logger.info(
                "[timed] %s took %.3fs",
                name,
                time.perf_counter() - start,
            )
        results.append(result)
        last_result = result

    return results, last_result


def load_recipe(recipe_filename, *, strict=True, section=None):
    """Load a recipe from an explicit filesystem path.

    Blank lines and comments are ignored. A physical line beginning with --
    extends the previous operation. Quote provenance is retained so single
    quotes can mark opaque literal values.
    """
    path = Path(recipe_filename).expanduser()
    if not path.is_file():
        if strict:
            raise FileNotFoundError(f"Recipe not found: {path}")
        return [], []

    commands = []
    comments = []
    current = None
    active_section = section is None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            comments.append(stripped)
            if section is not None and stripped.startswith("# ") and not stripped.startswith("## "):
                active_section = stripped[2:].strip().casefold() == section.strip().casefold()
            continue

        if not active_section:
            continue

        tokens = tokenize(stripped)
        if stripped.startswith("--") and current is not None:
            current["tokens"].extend(tokens)
            continue

        current = {"tokens": tokens}
        commands.append(current)

    return commands, comments


def chunk(tokens):
    """Split command-line tokens on standalone unquoted stage separators."""
    chunks = []
    current = []
    for token in tokens:
        value = _value(token)
        if not _literal(token) and value in {"-", ";"}:
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(token)
    if current:
        chunks.append(current)
    return chunks
