import os
import sys
import json
import time
import inspect
import argparse
from typing import get_origin, get_args, Literal, Union

from .logging import setup_logging
from .builtins import abort
from .environs import load_env, get_base_client, get_base_server
from .gateway import gw, Gateway


def cli_main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-a", dest="all", action="store_true", help="Return all results, not just the last one")
    parser.add_argument("-b", dest="batch", type=str, help="Run commands from a batch script")
    parser.add_argument("-c", dest="client", type=str, help="Specify client environment")
    parser.add_argument("-d", dest="debug", action="store_true", help="Enable debug logging")
    parser.add_argument("-e", dest="expression", type=str, help="Return resolved sigil at the end")
    parser.add_argument("-j", dest="json", nargs="?", const=True, default=False, 
                              help="Output result(s) as JSON, optionally to a file.")
    parser.add_argument("-s", dest="server", type=str, help="Specify server environment")
    parser.add_argument("-t", dest="timed", action="store_true", help="Enable timing")
    parser.add_argument("-v", dest="verbose", action="store_true", help="Verbose mode")
    parser.add_argument("-x", dest="callback", type=str, help="Execute a callback per command")
    parser.add_argument("commands", nargs=argparse.REMAINDER, help="Project/Function command(s)")
    args = parser.parse_args()

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel)
    start_time = time.time() if args.timed else None

    env_root = os.path.join(gw.base_path, "envs")
    client_name = args.client or get_base_client()
    server_name = args.server or get_base_server()

    load_env("client", client_name, env_root)
    load_env("server", server_name, env_root)

    if args.batch:
        command_sources, comments = load_batch(args.batch)
        gw.info(f"Comments in batch script:\n{chr(10).join(comments)}")
    else:
        if not args.commands:
            parser.print_help()
            sys.exit(1)
        command_sources = chunk_command(args.commands)

    if args.callback:
        callback = gw[args.callback]
        all_results, last_result = process_commands(command_sources, callback=callback)
    else:
        all_results, last_result = process_commands(command_sources)

    # Print all results immediately if --all is set
    if args.all:
        for result in all_results:
            if args.json:
                json_output = json.dumps(result, indent=2, default=str)
                if isinstance(args.json, str):
                    with open(args.json, "a") as f:
                        f.write(json_output + "\n")
                else:
                    print(json_output)
            elif result is not None:
                gw.info(f"Result:\n{result}")
                print(result)

    # Final result resolution (in expression mode only)
    output = Gateway(**last_result).resolve(args.expression) if args.expression else last_result

    # Only print final result if --all wasn't used
    if not args.all:
        if args.json:
            json_output = json.dumps(output, indent=2, default=str)
            if isinstance(args.json, str):
                with open(args.json, "w") as f:
                    f.write(json_output + "\n")
            else:
                print(json_output)
        elif output is not None:
            gw.info(f"Last function result:\n{output}")
            print(output)
        else:
            gw.info("No results returned.")

    if start_time:
        print(f"\nElapsed: {time.time() - start_time:.4f} seconds")


def process_commands(command_sources, callback=None, **context):
    """Shared logic for executing CLI or batch commands with optional per-node callback."""
    from gway import gw, Gateway

    all_results = []
    last_result = None

    gw = Gateway(**context) if context else gw

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
                pass  # continue with original chunk
            else:
                abort(f"Invalid callback return value for chunk: {callback_result}")

        if not chunk:
            continue

        raw_first_token = chunk[0]
        normalized_first_token = raw_first_token.replace("-", "_")
        remaining_tokens = chunk[1:]

        current_project_obj = None
        func_tokens = []
        project_functions = {}

        try:
            current_project_obj = getattr(gw, normalized_first_token)
            if callable(current_project_obj):
                project_functions = {raw_first_token: current_project_obj}
                func_tokens = [raw_first_token] + remaining_tokens
            else:
                project_functions = {
                    name: func for name, func in vars(current_project_obj).items()
                    if callable(func) and not name.startswith("_")
                }
                func_tokens = remaining_tokens or abort(f"No function specified for project '{raw_first_token}'")
        except AttributeError:
            try:
                builtin_func = getattr(gw.builtin, normalized_first_token)
                if callable(builtin_func):
                    project_functions = {raw_first_token: builtin_func}
                    func_tokens = [raw_first_token] + remaining_tokens
                else:
                    abort(f"Unknown command or project: {raw_first_token}")
            except AttributeError:
                if current_project_obj:
                    project_functions = {
                        name: func for name, func in vars(current_project_obj).items()
                        if callable(func) and not name.startswith("_")
                    }
                    func_tokens = [raw_first_token] + remaining_tokens
                else:
                    abort(f"Unknown project, builtin, or function: {raw_first_token}")

        raw_func_name = func_tokens[0]
        normalized_func_name = raw_func_name.replace("-", "_")
        func_args = func_tokens[1:]

        func_obj = project_functions.get(raw_func_name) or project_functions.get(normalized_func_name)
        if not func_obj:
            abort(f"Function '{raw_func_name}' not found.")

        func_parser = argparse.ArgumentParser(prog=raw_func_name)
        add_function_args(func_parser, func_obj)
        parsed_args = func_parser.parse_args(func_args)

        final_args, final_kwargs = prepare_arguments(parsed_args, func_obj)

        try:
            result = func_obj(*final_args, **final_kwargs)
            last_result = result
            all_results.append(result)
        except Exception as e:
            gw.exception(e)
            abort(f"Unhandled {type(e).__name__} in {func_obj.__name__}")

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


def load_batch(batch_filename):
    """Load commands and comments from a .gws file."""
    commands = []
    comments = []

    if not os.path.isabs(batch_filename):
        candidate_names = [batch_filename]
        if not os.path.splitext(batch_filename)[1]:
            candidate_names += [f"{batch_filename}.gws", f"{batch_filename}.txt"]
        for name in candidate_names:
            batch_path = gw.resource("scripts", name)
            if os.path.isfile(batch_path):
                break
        else:
            abort(f"Batch script not found in scripts/: tried {candidate_names}")
    else:
        batch_path = batch_filename
        if not os.path.isfile(batch_path):
            abort(f"Batch file not found: {batch_path}")

    gw.info(f"Loading commands from batch: {batch_path}")

    with open(batch_path) as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line.startswith("#"):
                comments.append(stripped_line)
            elif stripped_line:
                commands.append(stripped_line.split())

    return commands, comments


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
    print("Available functions:")
    for name, func in functions.items():
        args_list = []
        for param in inspect.signature(func).parameters.values():
            if param.default != inspect.Parameter.empty:
                args_list.append(f"--{param.name} {param.default}")
            else:
                args_list.append(f"--{param.name} <required>")
        args_preview = " ".join(args_list)

        doc = ""
        if func.__doc__:
            doc_lines = [line.strip() for line in func.__doc__.splitlines()]
            doc = next((line for line in doc_lines if line), "")

        print(f"  > {name} {args_preview}")
        if doc:
            print(f"      {doc}")


def add_function_args(subparser, func_obj):
    """Add the function's arguments to the CLI subparser."""
    sig = inspect.signature(func_obj)
    for arg_name, param in sig.parameters.items():
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            subparser.add_argument(arg_name, nargs='*', help=f"Variable positional arguments for {arg_name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            subparser.add_argument('--kwargs', nargs='*', help='Additional keyword arguments as key=value pairs')
        else:
            arg_name_cli = f"--{arg_name.replace('_', '-')}"
            if param.annotation == bool or isinstance(param.default, bool):
                group = subparser.add_mutually_exclusive_group(required=False)
                group.add_argument(arg_name_cli, dest=arg_name, action="store_true", help=f"Enable {arg_name}")
                group.add_argument(f"--no-{arg_name.replace('_', '-')}", dest=arg_name, action="store_false", help=f"Disable {arg_name}")
                subparser.set_defaults(**{arg_name: param.default})
            else:
                arg_opts = get_arg_options(arg_name, param, gw)
                subparser.add_argument(arg_name_cli, **arg_opts)


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
