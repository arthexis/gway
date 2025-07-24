import inspect
import textwrap
import ast
import os
import sqlite3
__all__ = [
    "help",
    "sample_cli",
]


def help(*args, full: bool = False, list_flags: bool = False):
    from gway import gw
    if list_flags:
        from .testing import list_flags as _list_flags
        return {"Test Flags": _list_flags()}
    gw.info(f"Help on {' '.join(args)} requested")

    def extract_gw_refs(source: str):
        refs = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return refs

        class GwVisitor(ast.NodeVisitor):
            def visit_Attribute(self, node):
                parts = []
                cur = node
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name) and cur.id == "gw":
                    parts.append("gw")
                    full_attr = ".".join(reversed(parts))[3:]
                    refs.add(full_attr)
                self.generic_visit(node)

        GwVisitor().visit(tree)
        return refs

    db_path = gw.resource("data", "help.sqlite")
    if not os.path.isfile(db_path):
        gw.help_db.build()

    joined_args = " ".join(args).strip().replace("-", "_")
    norm_args = [a.replace("-", "_").replace("/", ".") for a in args]

    conn = gw.sql.open_db(db_path, row_factory=True)
    try:
        cur0 = conn.cursor()
        cur0.execute("SELECT 1 FROM param_types LIMIT 1")
        cur0.execute("SELECT tests FROM help LIMIT 1")
    except sqlite3.OperationalError:
        gw.help_db.build(update=True)
        gw.sql.close_db(datafile=db_path)
        conn = gw.sql.open_db(db_path, row_factory=True)

    with conn as cur:
        if not args:
            cur.execute("SELECT DISTINCT project FROM help")
            return {"Available Projects": sorted([row["project"] for row in cur.fetchall()])}

        rows = []

        if len(norm_args) == 1 and "." in norm_args[0]:
            parts = norm_args[0].split(".")
            if len(parts) >= 2:
                project = ".".join(parts[:-1])
                function = parts[-1]
                cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, function))
                rows = cur.fetchall()
                if not rows:
                    try:
                        cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{norm_args[0]}"',))
                        rows = cur.fetchall()
                    except sqlite3.OperationalError as e:  # pragma: no cover - DB errors
                        gw.warning(f"FTS query failed for {norm_args[0]}: {e}")
            else:
                return {"error": f"Could not parse dotted input: {norm_args[0]}"}

        elif len(norm_args) >= 2:
            *proj_parts, maybe_func = norm_args
            project = ".".join(proj_parts)
            function = maybe_func
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, function))
            rows = cur.fetchall()
            if not rows:
                fuzzy_query = ".".join(norm_args)
                try:
                    cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{fuzzy_query}"',))
                    rows = cur.fetchall()
                except sqlite3.OperationalError as e:  # pragma: no cover
                    gw.warning(f"FTS fallback failed for {fuzzy_query}: {e}")

        if not rows and len(norm_args) == 1:
            name = norm_args[0]
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", ("builtin", name))
            rows = cur.fetchall()

        if not rows:
            fuzzy_query = ".".join(norm_args)
            try:
                cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{fuzzy_query}"',))
                rows = cur.fetchall()
            except sqlite3.OperationalError as e:  # pragma: no cover
                gw.warning(f"FTS final fallback failed for {fuzzy_query}: {e}")
                return {"error": f"No help found and fallback failed for: {joined_args}"}

        results = []
        for row in rows:
            project = row["project"]
            function = row["function"]
            prefix = (
                f"gway {project} {function.replace('_', '-')}" if project != "builtin" else f"gway {function.replace('_', '-')}"
            )
            entry = {
                "Project": project,
                "Function": function,
                "Sample CLI": prefix,
                "References": sorted(extract_gw_refs(row["source"])),
            }
            cur.execute(
                "SELECT name, type FROM param_types WHERE project=? AND function=?",
                (project, function),
            )
            params = [dict(name=r["name"], type=r["type"]) for r in cur.fetchall()]
            if params:
                for p in params:
                    cur.execute(
                        "SELECT project, function FROM providers WHERE type=? LIMIT 1",
                        (p["type"],),
                    )
                    prov = cur.fetchone()
                    if prov:
                        p["builder"] = f"{prov['project']}.{prov['function']}"
                entry["Parameters"] = params
            cur.execute(
                "SELECT type FROM return_types WHERE project=? AND function=?",
                (project, function),
            )
            r_row = cur.fetchone()
            if r_row:
                entry["Returns"] = r_row["type"]
                cur.execute(
                    "SELECT project, function FROM providers WHERE type=? LIMIT 1",
                    (r_row["type"],),
                )
                if cur.fetchone():
                    entry["Provides"] = r_row["type"]
            tests_raw = row["tests"].strip() if row["tests"] else ""
            tests_list = [t for t in tests_raw.splitlines() if t.strip()]
            entry["Tests"] = tests_list if tests_list else ["No tests found"]
            if full:
                entry["Full Code"] = row["source"]
            else:
                entry["Signature"] = textwrap.fill(row["signature"], 100).strip()
                entry["Docstring"] = row["docstring"].strip() if row["docstring"] else None
                entry["TODOs"] = row["todos"].strip() if row["todos"] else None
            results.append({k: v for k, v in entry.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


def sample_cli(func):
    """Generate a sample CLI string for a function."""
    from gway import gw
    if not callable(func):
        func = gw[str(func)]
    sig = inspect.signature(func)
    parts = []
    seen_kw_only = False

    for name, param in sig.parameters.items():
        kind = param.kind
        if kind == inspect.Parameter.VAR_POSITIONAL:
            parts.append(f"[{name}1 {name}2 ...]")
        elif kind == inspect.Parameter.VAR_KEYWORD:
            parts.append(f"[--{name}1 val1 --{name}2 val2 ...]")
        elif kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if not seen_kw_only:
                parts.append(f"<{name}>")
            else:
                parts.append(f"--{name.replace('_', '-')} <val>")
        elif kind == inspect.Parameter.KEYWORD_ONLY:
            seen_kw_only = True
            cli_name = f"--{name.replace('_', '-')}"
            if param.annotation is bool or isinstance(param.default, bool):
                parts.append(f"[{cli_name} | --no-{name.replace('_', '-')}]")
            else:
                parts.append(f"{cli_name} <val>")

    return " ".join(parts)
