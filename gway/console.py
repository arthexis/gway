# file: gway/console.py

import argparse
import json
import time
from .binding import bind_arguments
from .gateway import Gateway, gw
from .recipes import load_recipe
from .tokens import Token, chunk, is_literal, token_value, tokenize


def parse_recipe_context(tokens):
    """Parse --key value tokens into a context mapping."""
    context = {}
    index = 0
    tokens = list(tokens)
    while index < len(tokens):
        token = token_value(tokens[index])
        if is_literal(tokens[index]) or not token.startswith("--") or token == "--":
            raise ValueError(f"Unexpected argument: {token}")
        key = token[2:].replace("-", "_")
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_value = token_value(next_token)
            if is_literal(next_token) or not next_value.startswith("--"):
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
    values = [token_value(token) for token in tokens]
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
        bound = bind_arguments(
            func,
            arguments,
            runtime=runtime,
            interactive=runtime.interactive_enabled,
        )
        start = time.perf_counter() if runtime.timed_enabled else None
        result = func(*bound.args, **bound.kwargs)
        if start is not None:
            runtime.logger.info(
                "[timed] %s took %.3fs",
                name,
                time.perf_counter() - start,
            )
        results.append(result)
        last_result = result

    return results, last_result
