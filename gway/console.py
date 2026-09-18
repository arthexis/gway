# file: gway/console.py

import argparse
import json
from .gateway import Gateway, gw
from .recipes import load_recipe
from .dispatch import dispatch_stage
from .tokens import Token, is_literal, token_value


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


def process(command_sources, *, gw_instance=None, **context):
    """Execute recipe/CLI stages through the unified dispatcher."""
    runtime = gw_instance or Gateway(context=context)
    if context:
        runtime.context.update(context)

    results = []
    last_result = None

    for entry in command_sources:
        tokens = list(entry.get("tokens", [])) if isinstance(entry, dict) else list(entry)
        if not tokens:
            continue

        result = dispatch_stage(runtime, tokens)
        results.append(result)
        last_result = result

    return results, last_result
