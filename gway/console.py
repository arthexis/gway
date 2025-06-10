# gway/console.py

import os
import sys
import json
import time
import inspect
import argparse
import csv
import io
from typing import get_origin, get_args, Literal, Union

from .logging import setup_logging
from .builtins import abort
from .gateway import Gateway, gw


def cli_main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Dynamic Project CLI")

    # Primary behavior flags
    add = parser.add_argument
    add("-a", dest="all", action="store_true", help="Show all text results, not just the last")
    add("-b", dest="base_path", type=str, help="Specify a different base path for GWAY.")
    add("-c", dest="client", type=str, help="Specify client environment")
    add("-d", dest="debug", action="store_true", help="Enable debug logging")
    add("-e", dest="expression", type=str, help="Return resolved sigil at the end")
    add("-f", dest="fuzzy", action="store_true", help="Reserved for fuzzy matching")
    add("-g", dest="global_mode", action="store_true", help="Reserved for future global_mode")
    # -h is reserved for --help by argparse, and we leave it like that
    add("-i", dest="interact", action="store_true", help="Reserved for interactive shell mode")
    add("-j", dest="json", nargs="?", const=True, default=False, help="Output result(s) as JSON")
    add("-l", dest="local", action="store_true", help="Set base_path to current directory")
    add("-m", dest="memory", action="store_true", help="Memory mode: Save or reuse last arguments")
    add("-n", dest="name", type=str, help="Name for app instances and logger (default: gw).")
    add("-o", dest="outfile", type=str, help="Write text output(s) to this file")
    add("-p", dest="project_path", type=str, help="Root project path for custom functions.")
    add("-q", dest="quantity", type=int, default=1, help="Max items from generator outputs")
    add("-r", dest="recipe", type=str, help="Execute a GWAY recipe (.gwr) file.")
    add("-s", dest="server", type=str, help="Override server environment configuration")
    add("-t", dest="timed", action="store_true", help="Enable timing of operations")
    # There is no -u in team (until implemented)
    add("-v", dest="verbose", action="store_true", help="Verbose mode (where supported)")
    add("-w", dest="wizard", action="store_true", help="Request wizard mode if available")
    add("-x", dest="callback", type=str, help="Execute a callback per command or standalone")
    add("-z", dest="silent", action="store_true", help="Suppress all non-critical output")
    add("commands", nargs=argparse.REMAINDER, help="Project/Function command(s)")
    
    args = parser.parse_args()
    memory_file = "work/memory.txt"

    # Handle memory mode: clear, save, or restore
    if args.memory:
        if not args.commands and not args.callback:
            if os.path.exists(memory_file):
                os.remove(memory_file)
                print("Memory cleared.")
            else:
                print("Memory already clear.")
            sys.exit(0)
        else:
            os.makedirs(os.path.dirname(memory_file), exist_ok=True)
            with open(memory_file, "w") as f:
                f.write(" ".join(sys.argv[1:]))

    elif not args.commands and not args.callback and os.path.exists(memory_file):
        with open(memory_file) as f:
            saved_args = f.read().strip().split()
        sys.argv.extend(saved_args)
        return cli_main()  # Restart CLI with extended arguments

    # Handle local mode: override base_path to current dir
    if args.local:
        args.base_path = os.getcwd()

    # Setup logging
    setup_logging(logfile="gway.log", loglevel="DEBUG" if args.debug else "INFO")
    start_time = time.time() if args.timed else None

    # Silent and verbose are allowed together. It means:
    # Suppress all non-critical output; but if its critical, explain as much as possible.

    # Init Gateway instance
    gw_local = Gateway(
        client=args.client,
        server=args.server,
        verbose=args.verbose,
        silent=args.silent,
        name=args.name or "gw",
        project_path=args.project_path,
        base_path=args.base_path,
        debug=args.debug,
        quantity=args.quantity,
    )

    gw_local.verbose(f"Saving detailed logs to logs/gway.log") 

    # Load command sources
    if args.recipe:
        command_sources, comments = load_recipe(args.recipe)
        gw_local.debug(f"Comments in recipe:\n{chr(10).join(comments)}")
    elif args.commands:
        command_sources = chunk_command(args.commands)
    elif args.callback:
        command_sources = []
    else:
        parser.print_help()
        sys.exit(1)

    # Run commands or callback
    if command_sources:
        callback = gw_local[args.callback] if args.callback else None
        all_results, last_result = process_commands(command_sources, callback=callback)
    elif args.callback:
        result = gw_local[args.callback]()
        all_results, last_result = [result], result
    else:
        all_results, last_result = [], None

    # Resolve expression if requested
    if args.expression:
        output = Gateway(**last_result).resolve(args.expression)
    else:
        output = last_result

    # Convert generators to lists
    def realize(val):
        if hasattr(val, "__iter__") and not isinstance(val, (str, bytes, dict)):
            try:
                return list(val)[:args.quantity] if args.quantity else list(val)
            except Exception:
                return val
        return val

    all_results = [realize(r) for r in all_results]
    output = realize(output)

    # Emit result(s)
    def emit(data):
        if args.json:
            print(json.dumps(data, indent=2, default=str))
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            csv_str = _rows_to_csv(data)
            print(csv_str or data)
        elif data is not None:
            print(data)

    if args.all:
        for result in all_results:
            emit(result)
    else:
        emit(output)

    # Write to file if needed
    if args.outfile:
        with open(args.outfile, "w") as f:
            if args.json:
                json.dump(all_results if args.all else output, f, indent=2, default=str)
            elif isinstance(output, list) and output and isinstance(output[0], dict):
                f.write(_rows_to_csv(output))
            else:
                f.write(str(output))

    if start_time:
        print(f"\nElapsed: {time.time() - start_time:.4f} seconds")



def process_commands(command_sources, callback=None, **context):
    """Shared logic for executing CLI or recipe commands with optional per-node callback."""
    from gway import gw as _global_gw, Gateway
    from .builtins import abort

    all_results = []
    last_result = None

    gw = Gateway(**context) if context else _global_gw

    def resolve_nested_object(root, tokens):
        """Resolve a sequence of command tokens to a nested object (e.g. gw.project.module.func)."""
        path = []
        obj = root

        while tokens:
            normalized = normalize_token(tokens[0])
            if hasattr(obj, normalized):
                obj = getattr(obj, normalized)
                path.append(tokens.pop(0))
            else:
                # Try to resolve composite function names from remaining tokens
                for i in range(len(tokens), 0, -1):
                    joined = "_".join(normalize_token(t) for t in tokens[:i])
                    if hasattr(obj, joined):
                        obj = getattr(obj, joined)
                        path.extend(tokens[:i])
                        tokens[:] = tokens[i:]
                        return obj, tokens, path
                break  # No match found; exit lookup loop

        return obj, tokens, path

    for chunk in command_sources:
        if not chunk:
            continue

        gw.debug(f"Processing chunk: {chunk}")

        # Invoke callback if provided
        if callback:
            callback_result = callback(chunk)
            if callback_result is False:
                gw.debug(f"Skipping chunk due to callback: {chunk}")
                continue
            elif isinstance(callback_result, list):
                gw.debug(f"Callback replaced chunk: {callback_result}")
                chunk = callback_result
            elif callback_result is None or callback_result is True:
                pass
            else:
                abort(f"Invalid callback return value for chunk: {callback_result}")

        if not chunk:
            continue

        # Resolve nested project/function path
        resolved_obj, func_args, path = resolve_nested_object(gw, list(chunk))

        if not callable(resolved_obj):
            if hasattr(resolved_obj, '__functions__'):
                show_functions(resolved_obj.__functions__)
            else:
                gw.error(f"Object at path {' '.join(path)} is not callable.")
            abort(f"No project with name '{chunk[0]}'")

        # Parse function arguments
        func_parser = argparse.ArgumentParser(prog=".".join(path))
        add_function_args(func_parser, resolved_obj)
        parsed_args = func_parser.parse_args(func_args)

        # Prepare and invoke
        final_args, final_kwargs = prepare_arguments(parsed_args, resolved_obj)
        try:
            result = resolved_obj(*final_args, **final_kwargs)
            last_result = result
            all_results.append(result)
        except Exception as e:
            gw.exception(e)
            name = getattr(resolved_obj, "__name__", str(resolved_obj))
            abort(f"Unhandled {type(e).__name__} in {name}")

    return all_results, last_result


def prepare_arguments(parsed_args, func_obj):
    """Prepare *args and **kwargs for a function call."""
    func_args = []
    func_kwargs = {}
    extra_kwargs = {}

    for name, value in vars(parsed_args).items():
        param = inspect.signature(func_obj).parameters.get(name)
        if param is None:
            continue
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            func_args.extend(value or [])
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            if value:
                for item in value:
                    if '=' not in item:
                        abort(f"Invalid kwarg format '{item}'. Expected key=value.")
                    k, v = item.split("=", 1)
                    extra_kwargs[k] = v
        else:
            func_kwargs[name] = value

    return func_args, {**func_kwargs, **extra_kwargs}


def chunk_command(args_commands):
    """Split args.commands into logical chunks without breaking quoted arguments."""
    chunks = []
    current_chunk = []

    for token in args_commands:
        if token in ('-', ';'):
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
        else:
            current_chunk.append(token)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def show_functions(functions: dict):
    """Display a formatted view of available functions."""
    from .builtins import sample_cli_args

    print("Available functions:")
    for name, func in functions.items():
        name_cli = name.replace("_", "-")
        sample_cli_args = sample_cli_args(func)
        doc = ""
        if func.__doc__:
            doc_lines = [line.strip() for line in func.__doc__.splitlines()]
            doc = next((line for line in doc_lines if line), "")

        print(f"  > {name_cli} {sample_cli_args}")
        if doc:
            print(f"      {doc}")


def add_function_args(subparser, func_obj):
    """Add the function's arguments to the CLI subparser."""
    sig = inspect.signature(func_obj)
    seen_kw_only = False

    for arg_name, param in sig.parameters.items():
        # VAR_POSITIONAL: e.g. *args
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            subparser.add_argument(
                arg_name,
                nargs='*',
                help=f"Variable positional arguments for {arg_name}"
            )

        # VAR_KEYWORD: e.g. **kwargs
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            subparser.add_argument(
                '--kwargs',
                nargs='*',
                help='Additional keyword arguments as key=value pairs'
            )

        # regular args or keyword-only
        else:
            is_positional = not seen_kw_only and param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD
            )

            # before the first kw-only marker (*) → positional
            if is_positional:
                opts = get_arg_options(arg_name, param, gw)
                # argparse forbids 'required' on positionals:
                opts.pop('required', None)

                if param.default is not inspect.Parameter.empty:
                    # optional positional
                    subparser.add_argument(
                        arg_name,
                        nargs='?',
                        **opts
                    )
                else:
                    # required positional
                    subparser.add_argument(
                        arg_name,
                        **opts
                    )

            # after * or keyword-only → flags
            else:
                seen_kw_only = True
                cli_name = f"--{arg_name.replace('_', '-')}"
                if param.annotation is bool or isinstance(param.default, bool):
                    grp = subparser.add_mutually_exclusive_group(required=False)
                    grp.add_argument(
                        cli_name,
                        dest=arg_name,
                        action="store_true",
                        help=f"Enable {arg_name}"
                    )
                    grp.add_argument(
                        f"--no-{arg_name.replace('_', '-')}",
                        dest=arg_name,
                        action="store_false",
                        help=f"Disable {arg_name}"
                    )
                    subparser.set_defaults(**{arg_name: param.default})
                else:
                    opts = get_arg_options(arg_name, param, gw)
                    subparser.add_argument(cli_name, **opts)


def get_arg_options(arg_name, param, gw=None):
    """Infer argparse options from parameter signature."""
    opts = {}
    annotation = param.annotation
    default = param.default

    origin = get_origin(annotation)
    args = get_args(annotation)
    inferred_type = str

    if origin == Literal:
        opts["choices"] = args
        inferred_type = type(args[0]) if args else str
    elif origin == Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            inner_param = type("param", (), {"annotation": non_none[0], "default": default})
            return get_arg_options(arg_name, inner_param, gw)
        elif all(a in (str, int, float) for a in non_none):
            inferred_type = str
    elif annotation != inspect.Parameter.empty:
        inferred_type = annotation

    opts["type"] = inferred_type

    if default != inspect.Parameter.empty:
        if isinstance(default, str) and default.startswith("[") and default.endswith("]") and gw:
            try:
                default = gw.resolve(default)
            except Exception as e:
                print(f"Failed to resolve default for {arg_name}: {e}")
        opts["default"] = default
    else:
        opts["required"] = True

    return opts


...

# We keep recipe functions in console.py because anything that changes cli_main
# typically has an impact in the recipe parsing, and must be reviewed together.


def load_recipe(recipe_filename):
    """Load commands and comments from a .gwr file."""
    commands = []
    comments = []

    if not os.path.isabs(recipe_filename):
        candidate_names = [recipe_filename]
        if not os.path.splitext(recipe_filename)[1]:
            candidate_names += [f"{recipe_filename}.gwr", f"{recipe_filename}.txt"]
        for name in candidate_names:
            recipe_path = gw.resource("recipes", name)
            if os.path.isfile(recipe_path):
                break
        else:
            abort(f"Recipe not found in recipes/: tried {candidate_names}")
    else:
        recipe_path = recipe_filename
        if not os.path.isfile(recipe_path):
            raise FileNotFoundError(f"Recipe not found: {recipe_path}")

    gw.info(f"Loading commands from recipe: {recipe_path}")

    with open(recipe_path) as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line.startswith("#"):
                comments.append(stripped_line)
            elif stripped_line:
                commands.append(stripped_line.split())

    return commands, comments


def normalize_token(token):
    return token.replace("-", "_").replace(" ", "_").replace(".", "_")


def _rows_to_csv(rows):
    if not rows:
        return ""
    try:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
    except Exception:
        return None