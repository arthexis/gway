"""Leading call options for programmatic and connector execution."""

from .tokens import is_unquoted, token_value, tokenize


def command_options(command):
    """Consume only supported leading globals, retaining token quote provenance."""
    if not isinstance(command, str):
        return command, {}
    tokens = tokenize(command)
    options = {}
    index = 0
    flags = {
        "-j": "json", "--json": "json",
        "-t": "timed", "--timed": "timed",
        "-M": "no_mutate", "--no-mutate": "no_mutate",
    }
    while index < len(tokens):
        token = tokens[index]
        value = token_value(token)
        if not is_unquoted(token) or not value.startswith("-"):
            break
        if value == "--":
            index += 1
            break
        if value not in flags:
            raise ValueError(f"Unsupported global flag for Gateway calls: {value}")
        options[flags[value]] = True
        index += 1
    if index and index == len(tokens):
        raise ValueError("Global flags require an operation")
    return tokens[index:], options
