# file: gway/console.py

import argparse
import inspect
import json
import shlex
import sys
import time
from pathlib import Path

from .gateway import Gateway, gw
from .sigils import Sigil


def parse_recipe_context(tokens):
    """Parse --key value tokens into a context mapping."""
    context = {}
    index = 0
    tokens = list(tokens)
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--") or token == "--":
            raise ValueError(f"Unexpected argument: {token}")
        key = token[2:].replace("-", "_")
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("--"):
            context[key] = tokens[index + 1]
            index += 2
        else:
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
    for size in range(len(tokens), 0, -1):
        candidates = (
            " ".join(tokens[:size]),
            "_".join(token.replace("-", "_") for token in tokens[:size]),
            ".".join(token.replace("-", "_") for token in tokens[:size]),
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

    raise LookupError(f"Unable to resolve operation: {' '.join(tokens)}")


def _convert(value, parameter):
    annotation = parameter.annotation
    if isinstance(value, str) and Sigil._pattern.search(value):
        value = gw.resolve(value)

    if annotation in (inspect.Parameter.empty, str):
        return value
    if annotation is bool and isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if annotation in (int, float):
        return annotation(value)
    return value


def _bind_arguments(func, tokens, *, interactive=False):
    signature = inspect.signature(func)
    positional = []
    keywords = {}
    tokens = list(tokens)
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if token.startswith("--"):
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
            keywords[key] = _convert(tokens[index + 1], parameter)
            index += 2
        else:
            positional.append(token)
            index += 1

    bound = signature.bind_partial(*positional, **keywords)

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
            bound.arguments[name] = _convert(response, parameter)

    signature.bind(*bound.args, **bound.kwargs)
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

    Blank lines and comments are ignored. A line beginning with -- extends the
    previous operation, so ordinary argparse-style flags can span lines.
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

        tokens = shlex.split(stripped)
        if stripped.startswith("--") and current is not None:
            current["tokens"].extend(tokens)
            continue

        current = {"tokens": tokens}
        commands.append(current)

    return commands, comments


def chunk(tokens):
    """Split command-line tokens on standalone stage separators."""
    chunks = []
    current = []
    for token in tokens:
        if token in {"-", ";"}:
            if current:
                chunks.append(current)
                current = []
        else:
            current.append(token)
    if current:
        chunks.append(current)
    return chunks
