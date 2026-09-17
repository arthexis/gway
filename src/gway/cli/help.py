from __future__ import annotations

import textwrap

from ..dispatcher import Dispatcher
from . import shutil


def _print_project_help(dispatcher: Dispatcher, project_name: str) -> None:
    project = dispatcher.registry.require(project_name)
    commands = dispatcher.commands(project_name)
    print(f"usage: gway {project.name} <command> [arguments]")
    print()
    print("commands:")

    rows = [(" ".join(command.path), command.summary) for command in commands]
    if not rows:
        return

    terminal_width = max(1, shutil.get_terminal_size(fallback=(100, 24)).columns)
    left_indent = 2 if terminal_width >= 4 else 0
    gap = 2
    name_width = max(len(name) for name, _ in rows)
    description_column = left_indent + name_width + gap
    description_width = terminal_width - description_column

    for name, summary in rows:
        if not summary:
            for line in textwrap.wrap(
                name,
                width=max(1, terminal_width - left_indent),
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]:
                print(f"{' ' * left_indent}{line}")
            continue

        if description_width < 20:
            available = max(1, terminal_width - left_indent)
            for line in textwrap.wrap(
                name,
                width=available,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]:
                print(f"{' ' * left_indent}{line}")
            detail_indent = min(left_indent * 2, max(0, terminal_width - 1))
            detail_width = max(1, terminal_width - detail_indent)
            for line in textwrap.wrap(summary, width=detail_width) or [""]:
                print(f"{' ' * detail_indent}{line}")
            continue

        wrapped = textwrap.wrap(summary, width=description_width) or [""]
        print(f"{' ' * left_indent}{name:<{name_width}}{' ' * gap}{wrapped[0]}")
        continuation = " " * description_column
        for line in wrapped[1:]:
            print(f"{continuation}{line}")
