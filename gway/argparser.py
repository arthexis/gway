import inspect
import logging

from typing import get_origin, get_args, Literal, Union, Optional

logger = logging.getLogger(__name__)


def parse_kwargs(kwargs_list):
    """Convert ['key=value', ...] into a dictionary."""
    kwargs = {}
    for kv in kwargs_list:
        if '=' in kv:
            key, value = kv.split('=', 1)
            kwargs[key] = value
        else:
            logger.warning(f"Invalid kwargs entry: {kv} (expected format key=value)")
    return kwargs

def get_arg_options(arg_name, param, resolver=None):
    """Infer argparse options from parameter signature."""
    opts = {}
    annotation = param.annotation
    default = param.default

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Default type fallback
    inferred_type = str

    if origin == Literal:
        opts["choices"] = args
        inferred_type = type(args[0]) if args else str

    elif origin == Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            # Union[T, None] → Optional[T]
            inner_param = type("param", (), {"annotation": non_none[0], "default": default})
            return get_arg_options(arg_name, inner_param, resolver)
        elif all(a in (str, int, float) for a in non_none):
            inferred_type = str  # generalize for user input

    elif annotation != inspect.Parameter.empty:
        inferred_type = annotation

    opts["type"] = inferred_type

    if default != inspect.Parameter.empty:
        if isinstance(default, str) and default.startswith("[") and default.endswith("]") and resolver:
            try:
                default = resolver.resolve(default)
            except Exception as e:
                logger.warning(f"Failed to resolve default for {arg_name}: {e}")
        opts["default"] = default
    else:
        opts["required"] = True

    return opts


def add_function_args(subparser, func_obj):
    """Add the function's arguments to the CLI subparser."""
    from gway import Gateway

    sig = inspect.signature(func_obj)
    logger.debug(f"Add function args for {func_obj.__name__} {sig}")
    resolver = Gateway()  

    for arg_name, param in sig.parameters.items():
        logger.debug(f"Inspecting {arg_name=} {param=} {param.kind=}")

        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            subparser.add_argument(arg_name, nargs='*', help=f"Variable positional arguments for {arg_name}")

        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            subparser.add_argument('--kwargs', nargs='*', help='Additional keyword arguments as key=value pairs')

        else:
            arg_name_cli = f"--{arg_name.replace('_', '-')}"
            
            if param.annotation == bool or isinstance(param.default, bool):
                # Add --flag and --no-flag mutually exclusive options
                group = subparser.add_mutually_exclusive_group(required=False)
                group.add_argument(arg_name_cli, dest=arg_name, action="store_true", help=f"Enable {arg_name}")
                group.add_argument(f"--no-{arg_name.replace('_', '-')}", dest=arg_name, action="store_false", help=f"Disable {arg_name}")
                subparser.set_defaults(**{arg_name: param.default})
                logger.debug(f"Subparser default for {arg_name=} set to {param.default=}")
            else:
                arg_opts = get_arg_options(arg_name, param, resolver)
                subparser.add_argument(arg_name_cli, **arg_opts)
                logger.debug(f"Subparser {arg_name=} argument added as {arg_name_cli=} {arg_opts=}")


def chunk_command(args_commands):
    """Split args.commands into logical chunks without breaking quoted arguments."""
    chunks = []
    current_chunk = []

    for token in args_commands:
        if token in ('-', ';'):  # command separator
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
        else:
            current_chunk.append(token)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
