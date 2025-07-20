# file: projects/help_db.py
"""Helper utilities for building the `gw.help` database."""

import os
from gway import gw
import re


def build(*, update: bool = False):
    """Build or update the help database used by :func:`gw.help`."""
    import inspect

    db_path = gw.resource("data", "help.sqlite")
    if not update and os.path.isfile(db_path):
        gw.info("Help database already exists; skipping build.")
        return db_path

    with gw.sql.open_db(datafile="data/help.sqlite") as cursor:
        cursor.execute("DROP TABLE IF EXISTS help")
        cursor.execute("DROP TABLE IF EXISTS param_types")
        cursor.execute("DROP TABLE IF EXISTS return_types")
        cursor.execute("DROP TABLE IF EXISTS providers")
        cursor.execute(
            """
            CREATE VIRTUAL TABLE help USING fts5(
                project, function, signature, docstring, source, todos, tokenize='porter')
            """
        )
        cursor.execute(
            """CREATE TABLE param_types (project TEXT, function TEXT, name TEXT, type TEXT)"""
        )
        cursor.execute(
            """CREATE TABLE return_types (project TEXT, function TEXT, type TEXT)"""
        )
        cursor.execute(
            """CREATE TABLE providers (type TEXT, project TEXT, function TEXT)"""
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
                    param_types, return_type, provides = _parse_doc(doc)
                    try:
                        source = "".join(inspect.getsourcelines(raw_func)[0])
                    except OSError:
                        source = ""
                    todos = _extract_todos(source)
                    cursor.execute(
                        "INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                        (dotted_path, fname, sig, doc, source, "\n".join(todos)),
                    )
                    for p, t in param_types.items():
                        cursor.execute(
                            "INSERT INTO param_types VALUES (?, ?, ?, ?)",
                            (dotted_path, fname, p, t),
                        )
                    if return_type:
                        cursor.execute(
                            "INSERT INTO return_types VALUES (?, ?, ?)",
                            (dotted_path, fname, return_type),
                        )
                    provider_type = provides or (
                        return_type if return_type and not _is_builtin_type(return_type) else None
                    )
                    if provider_type:
                        cursor.execute(
                            "INSERT INTO providers VALUES (?, ?, ?)",
                            (provider_type, dotted_path, fname),
                        )
            except Exception as e:
                gw.warning(f"Skipping project {dotted_path}: {e}")

        for name, func in gw._builtins.items():
            raw_func = getattr(func, "__wrapped__", func)
            doc = inspect.getdoc(raw_func) or ""
            sig = str(inspect.signature(raw_func))
            param_types, return_type, provides = _parse_doc(doc)
            try:
                source = "".join(inspect.getsourcelines(raw_func)[0])
            except OSError:
                source = ""
            todos = _extract_todos(source)
            cursor.execute(
                "INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                ("builtin", name, sig, doc, source, "\n".join(todos)),
            )
            for p, t in param_types.items():
                cursor.execute(
                    "INSERT INTO param_types VALUES (?, ?, ?, ?)",
                    ("builtin", name, p, t),
                )
            if return_type:
                cursor.execute(
                    "INSERT INTO return_types VALUES (?, ?, ?)",
                    ("builtin", name, return_type),
                )
            provider_type = provides or (
                return_type if return_type and not _is_builtin_type(return_type) else None
            )
            if provider_type:
                cursor.execute(
                    "INSERT INTO providers VALUES (?, ?, ?)",
                    (provider_type, "builtin", name),
                )

        cursor.execute("COMMIT")
    gw.sql.close_connection(all=True)
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


_BUILTIN_TYPES = {
    "int",
    "float",
    "str",
    "bool",
    "list",
    "tuple",
    "dict",
    "set",
    "None",
}


def _is_builtin_type(t: str) -> bool:
    return t in _BUILTIN_TYPES


def _parse_doc(doc: str):
    """Return (param_types, return_type, provides) parsed from docstring."""
    param_types = {}
    return_type = None
    provides = None
    for line in doc.splitlines():
        m = re.match(r"\s*:type\s+(\w+)\s*:\s*(.+)", line)
        if m:
            param_types[m.group(1)] = m.group(2).strip()
        m = re.match(r"\s*:rtype:\s*(.+)", line)
        if m:
            return_type = m.group(1).strip()
        m = re.match(r"\s*:provides:\s*(.+)", line)
        if m:
            provides = m.group(1).strip()
    return param_types, return_type, provides
