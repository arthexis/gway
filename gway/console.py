# file: gway/console.py

import argparse
from contextlib import nullcontext
from collections.abc import Mapping
import json
import sys
from .gateway import Gateway
from .mutation import MUTATE_UNSET
from .recipe import execute_recipe, parse_recipe_context
from .dispatch import dispatch_program
from .tokens import statements


def _coerce_mutation_policy(value):
    """Coerce explicit CLI mutation policy values without restricting future modes."""
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return value


def _extract_mutation_policy(argv):
    """Extract unambiguous Gateway-global mutation flags from argv.

    Bare --mutate means True. Specific policies use --mutate=<value> so the
    first command token is never consumed accidentally. Once -M/--no-mutate
    appears, later flags cannot re-enable mutation in the same invocation.
    """
    policy = MUTATE_UNSET
    remaining = []
    for token in argv:
        if token in {"-M", "--no-mutate"}:
            policy = False
            continue
        if token == "--mutate":
            if policy is not False:
                policy = True
            continue
        if token.startswith("--mutate="):
            value = token.split("=", 1)[1]
            if not value:
                raise ValueError("--mutate requires a non-empty value after '='")
            if policy is not False:
                policy = _coerce_mutation_policy(value)
            continue
        remaining.append(token)
    return policy, remaining


_COMMAND_HELP_VALUE_OPTIONS = {
    "-L", "--log-level", "--logfile", "-r", "--recipe",
    "-e", "--expression", "--resume",
}
_COMMAND_HELP_MODE_OPTIONS = {"-r", "--recipe", "-e", "--expression", "--resume"}


def _extract_command_help(argv):
    """Route only trailing operation help through GWAY command help."""
    if not argv or argv[-1] not in {"--help", "-h"}:
        return False, argv
    preceding = argv[:-1]
    if "--" in preceding:
        return False, argv

    command_seen = False
    mode_seen = False
    consume_value = False
    for token in preceding:
        if consume_value:
            consume_value = False
            continue
        if token in _COMMAND_HELP_VALUE_OPTIONS:
            mode_seen = mode_seen or token in _COMMAND_HELP_MODE_OPTIONS
            consume_value = True
            continue
        matched_long = next(
            (
                option for option in _COMMAND_HELP_VALUE_OPTIONS
                if option.startswith("--") and token.startswith(f"{option}=")
            ),
            None,
        )
        if matched_long is not None:
            mode_seen = mode_seen or matched_long in _COMMAND_HELP_MODE_OPTIONS
            continue
        matched_short = next(
            (
                option for option in {"-L", "-r", "-e"}
                if token.startswith(option) and token != option
            ),
            None,
        )
        if matched_short is not None:
            mode_seen = mode_seen or matched_short in _COMMAND_HELP_MODE_OPTIONS
            continue
        if token.startswith("-"):
            continue
        command_seen = True

    if mode_seen or not command_seen:
        return False, argv
    return True, preceding


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
    mutation = parser.add_mutually_exclusive_group()
    mutation.add_argument(
        "-M",
        "--no-mutate",
        action="store_true",
        help="prohibit mutation for this invocation",
    )
    mutation.add_argument(
        "--mutate",
        action="store_true",
        help="enable mutation policy; use --mutate=<value> for a specific policy",
    )
    parser.add_argument("--resume", help=argparse.SUPPRESS)
    try:
        mutation_policy, argv = _extract_mutation_policy(sys.argv[1:])
    except ValueError as exception:
        parser.error(str(exception))
    command_help, argv = _extract_command_help(argv)
    args, unknown = parser.parse_known_args(argv)
    args.mutation_policy = mutation_policy
    args.command_help = command_help

    runtime = Gateway(
        debug=args.debug,
        interactive=args.interactive,
        timed=args.timed,
        verbose=args.verbose,
        silent=args.silent,
    )

    from . import log as gway_log

    log_kwargs = {
        "destination": args.logfile,
        "root": runtime.data_root(),
    }
    if args.log_level is not None:
        log_kwargs["level"] = args.log_level
    with gway_log.output_scope(**log_kwargs):
        return _run_cli(parser, args, unknown, runtime=runtime)


def _run_cli(parser, args, unknown, *, runtime=None):
    """Execute one parsed CLI invocation within its configured log scope."""
    runtime = runtime or Gateway(
        debug=args.debug,
        interactive=args.interactive,
        timed=args.timed,
        verbose=args.verbose,
        silent=args.silent,
    )

    from .reload import ReloadTransferred

    try:
        mutation_policy = getattr(args, "mutation_policy", MUTATE_UNSET)
        with runtime.mutation_scope(mutate=mutation_policy):
            state_scope = (
                runtime.observational_state_scope()
                if runtime.mutation_policy is False
                else nullcontext()
            )
            with state_scope:
                if args.resume:
                    if unknown:
                        parser.error("--resume does not accept additional arguments")
                    from .reload import resume

                    output = resume(args.resume)
                elif args.recipe:
                    _, output = execute_recipe(
                        runtime,
                        args.recipe,
                        context=parse_recipe_context(unknown),
                    )
                elif args.expression:
                    runtime.context.update(parse_recipe_context(unknown))
                    output = runtime.resolve(args.expression)
                elif unknown:
                    if getattr(args, "command_help", False):
                        output = runtime._command_help(*unknown, verbose=args.verbose)
                    else:
                        _, output = process([unknown], gw_instance=runtime)
                else:
                    parser.print_help()
                    return 0
    except ReloadTransferred as transfer:
        from .reload import ReloadSuccessorError, supervise_successor

        try:
            return supervise_successor(
                transfer.process,
                transfer.checkpoint,
                transfer.journal_root,
            )
        except ReloadSuccessorError as exception:
            return exception.returncode if exception.returncode > 0 else 1

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
