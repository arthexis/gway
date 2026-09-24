from types import ModuleType

from gway import Gateway
from gway import builtin
from gway.dispatch import resolve_operation
from gway.documentation import describe
from gway.tokens import tokenize


def _public_builtin_commands():
    commands = set()

    def visit(module, prefix=()):
        public = getattr(module, "__all__", None)
        for name, value in vars(module).items():
            if name.startswith("_") or (public is not None and name not in public):
                continue
            if isinstance(value, ModuleType) and value.__name__.startswith("gway."):
                visit(value, (*prefix, name))
                continue
            if callable(value):
                commands.add(" ".join((*prefix, name)))

        main = getattr(module, "__main__", None)
        if callable(main) and prefix:
            commands.add(" ".join(prefix))

    visit(builtin)
    commands.update(
        {
            "help",
            "clear",
            "security oauth client create",
            "security oauth client show",
            "security oauth client list",
            "security oauth client delete",
            "security oauth client disable",
            "security oauth client enable",
        }
    )
    return sorted(commands)


def test_public_builtins_have_summary_docstrings():
    gateway = Gateway()

    missing = []
    for command in _public_builtin_commands():
        operation, remaining, _ = resolve_operation(gateway, tokenize(command))
        assert remaining == []
        if not describe(operation).summary:
            missing.append(command)

    assert missing == []
