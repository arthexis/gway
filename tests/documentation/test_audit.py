from gway import Gateway
from gway.dispatch import resolve_operation
from gway.documentation import describe
from gway.tokens import tokenize


PUBLIC_BUILTINS = (
    "env",
    "envs",
    "toml",
    "toml load",
    "toml loads",
    "log",
    "log config",
    "log debug",
    "log info",
    "log warning",
    "log error",
    "log critical",
    "log exception",
    "test",
    "test summary",
    "test count",
    "test list",
    "test collect",
    "test run",
    "install",
    "uninstall",
    "help",
    "clear",
)


def test_public_builtins_have_summary_docstrings():
    gateway = Gateway()

    missing = []
    for command in PUBLIC_BUILTINS:
        operation, remaining, _ = resolve_operation(gateway, tokenize(command))
        assert remaining == []
        if not describe(operation).summary:
            missing.append(command)

    assert missing == []
