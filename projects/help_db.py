# file: projects/help_db.py
"""Helper utilities for building the `gw.help` database."""

import os
from gway import gw


def build(*, update: bool = False):
    """Build or update the help database used by :func:`gw.help`."""
    import inspect

    db_path = gw.resource("data", "help.sqlite")
    if not update and os.path.isfile(db_path):
        gw.info("Help database already exists; skipping build.")
        return db_path

    with gw.sql.open_connection(datafile="data/help.sqlite") as cursor:
        cursor.execute("DROP TABLE IF EXISTS help")
        cursor.execute(
            """
            CREATE VIRTUAL TABLE help USING fts5(
                project, function, signature, docstring, source, todos, tokenize='porter')
            """
        )

        for dotted_path in _walk_projects("projects"):
            try:
                project_obj = gw.load_project(dotted_path)
                for fname in dir(project_obj):
                    if fname.startswith("_"):
                        continue
                    func = getattr(project_obj, fname, None)
                    if not callable(func):
                        continue
                    raw_func = getattr(func, "__wrapped__", func)
                    doc = inspect.getdoc(raw_func) or ""
                    sig = str(inspect.signature(raw_func))
                    try:
                        source = "".join(inspect.getsourcelines(raw_func)[0])
                    except OSError:
                        source = ""
                    todos = _extract_todos(source)
                    cursor.execute(
                        "INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                        (dotted_path, fname, sig, doc, source, "\n".join(todos)),
                    )
            except Exception as e:
                gw.warning(f"Skipping project {dotted_path}: {e}")

        for name, func in gw._builtins.items():
            raw_func = getattr(func, "__wrapped__", func)
            doc = inspect.getdoc(raw_func) or ""
            sig = str(inspect.signature(raw_func))
            try:
                source = "".join(inspect.getsourcelines(raw_func)[0])
            except OSError:
                source = ""
            todos = _extract_todos(source)
            cursor.execute(
                "INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                ("builtin", name, sig, doc, source, "\n".join(todos)),
            )

        cursor.execute("COMMIT")
    gw.info(f"Help database built at {db_path}")
    return db_path


def _walk_projects(base: str = "projects"):
    for dirpath, _, filenames in os.walk(base):
        for fname in filenames:
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            rel_path = os.path.relpath(os.path.join(dirpath, fname), base)
            dotted = rel_path.replace(os.sep, ".").removesuffix(".py")
            yield dotted


def _extract_todos(source: str):
    todos = []
    lines = source.splitlines()
    current = []
    for line in lines:
        stripped = line.strip()
        if "# TODO" in stripped:
            if current:
                todos.append("\n".join(current))
            current = [stripped]
        elif current and (stripped.startswith("#") or not stripped):
            current.append(stripped)
        elif current:
            todos.append("\n".join(current))
            current = []
    if current:
        todos.append("\n".join(current))
    return todos
