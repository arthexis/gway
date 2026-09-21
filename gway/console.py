# file: gway/console.py

import argparse
from collections.abc import Mapping
import json
from .gateway import Gateway
from .recipes import execute_recipe, parse_recipe_context
from .dispatch import dispatch_program
from .tokens import statements


def cli_main():
    """Run the minimal GWAY command-line interface."""
    parser = argparse.ArgumentParser(
        prog="gway",
        description="GWAY command-dispatch and composition core",
    )
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    parser.add_argument("-L", "--log-level")
    parser.add_argument("--logfile")
    parser.add_argument("-r", "--recipe")
    parser.add_argument("-t", "--timed", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-z", "--silent", action="store_true")
    parser.add_argument("-e", "--expression")
    args, unknown = parser.parse_known_args()

    from . import log as gway_log

    log_kwargs = {"destination": args.logfile or "file"}
    if args.log_level is not None:
        log_kwargs["level"] = args.log_level
    gway_log.configure_output(**log_kwargs)

    runtime = Gateway(
        debug=args.debug,
        interactive=args.interactive,
        timed=args.timed,
        verbose=args.verbose,
        silent=args.silent,
    )

    if args.recipe:
        _, output = execute_recipe(
            runtime,
            args.recipe,
            context=parse_recipe_context(unknown),
        )
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
    """Execute recipe/CLI sources through the shared stage sequence executor."""
    runtime = gw_instance or Gateway(context=context)
    if context:
        runtime.context.update(context)

    statement_list = []
    for entry in command_sources:
        tokens = (
            list(entry.get("tokens", [])) if isinstance(entry, Mapping) else list(entry)
        )
        statement_list.extend(statements(tokens))

    if not statement_list:
        return [], None
    return dispatch_program(runtime, statement_list)
