
# projects/release.py

import os
import sys
import toml
import inspect
import importlib
import subprocess
from pathlib import Path

from gway import gw


def build(*,
    bump: bool = False,
    dist: bool = False,
    twine: bool = False,
    help_db: bool = True,
    user: str = "[PYPI_USERNAME]",
    password: str = "[PYPI_PASSWORD]",
    token: str = "[PYPI_API_TOKEN]",
    projects: bool = False,
    git: bool = False,
    all: bool = False
) -> None:
    """Build the project and optionally upload to PyPI.
    Args:
        bump (bool): Increment patch version if True.
        dist (bool): Build distribution package if True.
        twine (bool): Upload to PyPI if True.
        user (str): PyPI username (default: [PYPI_USERNAME]).
        password (str): PyPI password (default: [PYPI_PASSWORD]).
        token (str): PyPI API token (default: [PYPI_API_TOKEN]).
        git (bool): Require a clean git repo and commit/push after release if True.
        vscode (bool): Build the vscode extension.
    """
    if all:
        bump = True
        dist = True
        twine = True
        help_db = True
        git = True
        projects = True

    gw.info(f"Running tests before project build.")
    test_result = gw.test()
    if not test_result:
        gw.abort("Tests failed, build aborted.")

    if git:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            gw.abort("Git repository is not clean. Commit or stash changes before building.")

    if help_db:
        build_help_db()

    if projects:
        project_dir = gw.resource("projects")
        collect_projects(project_dir)

    project_name = "gway"
    description = "Software Project Infrastructure by https://www.gelectriic.com"
    author_name = "Rafael J. Guillén-Osorio"
    author_email = "tecnologia@gelectriic.com"
    python_requires = ">=3.7"
    license_expression = "MIT"
    readme_file = Path("README.rst")

    classifiers = [
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ]

    version_path = Path("VERSION")
    requirements_path = Path("requirements.txt")
    pyproject_path = Path("pyproject.toml")

    if not version_path.exists():
        raise FileNotFoundError("VERSION file not found.")
    if not requirements_path.exists():
        raise FileNotFoundError("requirements.txt file not found.")
    if not readme_file.exists():
        raise FileNotFoundError("README.rst file not found.")

    if bump:
        current_version = version_path.read_text().strip()
        major, minor, patch = map(int, current_version.split("."))
        patch += 1
        new_version = f"{major}.{minor}.{patch}"
        version_path.write_text(new_version)
        gw.info(f"\nBumped version: {current_version} → {new_version}")
    else:
        new_version = version_path.read_text().strip()

    version = new_version

    dependencies = [
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    pyproject_content = {
        "build-system": {
            "requires": ["setuptools", "wheel"],
            "build-backend": "setuptools.build_meta",
        },
        "project": {
            "name": project_name,
            "version": version,
            "description": description,
            "requires-python": python_requires,
            "license": license_expression,
            "readme": {
                "file": "README.rst",
                "content-type": "text/x-rst"
            },
            "classifiers": classifiers,
            "dependencies": dependencies,
            "authors": [
                {
                    "name": author_name,
                    "email": author_email,
                }
            ],
            "scripts": {
                project_name: f"{project_name}:cli_main",
            },
            "urls": {
                "Repository": "https://github.com/arthexis/gway.git",
                "Homepage": "https://arthexis.com",
                "Sponsor": "https://www.gelectriic.com/",
            }
        },
        "tool": {
            "setuptools": {
                "packages": ["gway"],
            }
        }
    }

    pyproject_path.write_text(toml.dumps(pyproject_content), encoding="utf-8")
    gw.info(f"Generated {pyproject_path}")

    manifest_path = Path("MANIFEST.in")
    if not manifest_path.exists():
        manifest_path.write_text(
            "include README.rst\n"
            "include VERSION\n"
            "include requirements.txt\n"
            "include pyproject.toml\n"
        )
        gw.info("Generated MANIFEST.in")

    if dist:
        dist_dir = Path("dist")
        if dist_dir.exists():
            for item in dist_dir.iterdir():
                item.unlink()
            dist_dir.rmdir()

        gw.info("Building distribution package...")
        subprocess.run([sys.executable, "-m", "build"], check=True)
        gw.info("Distribution package created in dist/")

        if twine:
            gw.info("Validating distribution with twine check...")
            check_result = subprocess.run(
                [sys.executable, "-m", "twine", "check", "dist/*"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            if check_result.returncode != 0:
                gw.error("PyPI README rendering check failed, aborting upload:\n{check_result.stdout}")
                return

            gw.info("Twine check passed. Uploading to PyPI...")
            upload_command = [
                sys.executable, "-m", "twine", "upload", "dist/*"
            ]

            if token:
                upload_command += ["--username", "__token__", "--password", token]
            elif user and password:
                upload_command += ["--username", user, "--password", password]
            else:
                gw.abort("Must provide either a PyPI API token or both username and password for Twine upload.")

            subprocess.run(upload_command, check=True)
            gw.info("Package uploaded to PyPI successfully.")

    if git:
        files_to_add = ["VERSION", "pyproject.toml"]
        if help_db:
            files_to_add.append("data/help.sqlite")
        if projects:
            files_to_add.append("README.rst")
        subprocess.run(["git", "add"] + files_to_add, check=True)
        commit_msg = f"PyPI Release v{version}" if twine else f"Release v{version}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
        gw.info(f"Committed and pushed: {commit_msg}")


def build_help_db():
    with gw.sql.open_connection(datafile="data/help.sqlite") as cursor:
        cursor.execute("DROP TABLE IF EXISTS help")
        cursor.execute("""
            CREATE VIRTUAL TABLE help USING fts5(
                project, function, signature, docstring, source, todos, tokenize='porter')
        """)

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
                    cursor.execute("INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                                   (dotted_path, fname, sig, doc, source, "\n".join(todos)))
            except Exception as e:
                gw.warning(f"Skipping project {dotted_path}: {e}")

        # Add builtin functions under synthetic project "builtin"
        for name, func in gw._builtins.items():
            raw_func = getattr(func, "__wrapped__", func)
            doc = inspect.getdoc(raw_func) or ""
            sig = str(inspect.signature(raw_func))
            try:
                source = "".join(inspect.getsourcelines(raw_func)[0])
            except OSError:
                source = ""
            todos = _extract_todos(source)

            cursor.execute("INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)",
                           ("builtin", name, sig, doc, source, "\n".join(todos)))

        cursor.execute("COMMIT")


def _walk_projects(base="projects"):
    """Yield all project modules as dotted paths."""
    for dirpath, _, filenames in os.walk(base):
        for fname in filenames:
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            rel_path = os.path.relpath(os.path.join(dirpath, fname), base)
            dotted = rel_path.replace(os.sep, ".").removesuffix(".py")
            yield dotted


def _extract_todos(source):
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


def loc(*paths):
    """
    Counts Python lines of code in the given directories, ignoring hidden files and directories.
    Defaults to everything in the current GWAY release.
    """
    file_counts = {}
    total_lines = 0

    paths = paths if paths else ("projects", "gway", "tests")
    for base_path in paths:
        base_dir = gw.resource(base_path)
        for root, dirs, files in os.walk(base_dir):
            # Modify dirs in-place to skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('_')]
            for file in files:
                if file.startswith('.') or file.startswith('_'):
                    continue
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            line_count = len(lines)
                            file_counts[file_path] = line_count
                            total_lines += line_count
                    except (UnicodeDecodeError, FileNotFoundError):
                        # Skip files that can't be read
                        continue

    file_counts['total'] = total_lines
    return file_counts


def create_shortcut(
    name="Launch GWAY",
    target=r"gway.bat",
    hotkey="Ctrl+Alt+G",
    output_dir=None,
    icon=None,
):
    from win32com.client import Dispatch

    # Resolve paths
    base_dir = Path(__file__).resolve().parent
    target_path = base_dir / target
    output_dir = output_dir or Path.home() / "Desktop"
    shortcut_path = Path(output_dir) / f"{name}.lnk"

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(base_dir)
    shortcut.WindowStyle = 1  # Normal window
    if icon:
        shortcut.IconLocation = str(icon)
    shortcut.Hotkey = hotkey  # e.g. Ctrl+Alt+G
    shortcut.Description = "Launch GWAY from anywhere"
    shortcut.Save()

    print(f"Shortcut created at: {shortcut_path}")


def collect_projects(project_dir: str = 'projects', *, readme: str = "README.rst"):
    """
    Recursively scan `project_dir` for all valid modules and packages,
    collect public functions, and update the INCLUDED PROJECTS section of `readme`.

    Args:
        project_dir: path to the GWAY projects directory.
        readme: path to the README file to update.
    """
    projects = {}
    base_path = str(gw.resource(project_dir))
    base_path_len = len(base_path.rstrip(os.sep)) + 1  # for dotted module name

    for root, dirs, files in os.walk(base_path):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith("_")]

        # Detect __init__.py (package)
        if "__init__.py" in files:
            rel_path = root[base_path_len:]
            modname = rel_path.replace(os.sep, ".")
            module_file = os.path.join(root, "__init__.py")
        else:
            # Detect individual .py modules
            py_files = [f for f in files if f.endswith(".py") and not f.startswith("_")]
            for py_file in py_files:
                rel_path = os.path.join(root, py_file)[base_path_len:]
                modname = rel_path[:-3].replace(os.sep, ".")
                module_file = os.path.join(root, py_file)
                break  # handle each .py individually
            else:
                continue  # no usable .py files here

        try:
            spec = importlib.util.spec_from_file_location(modname, module_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            gw.warning(f"Skipping project {modname}: failed to import: {e}")
            continue

        funcs = []
        for fname, obj in inspect.getmembers(module, inspect.isfunction):
            if fname.startswith("_"):
                continue
            doc = inspect.getdoc(obj) or "(no description)"
            cli_path = ' '.join(modname.replace('_', ' ').split('.'))
            cli_func = fname.replace('_', '-')
            funcs.append({
                "name": fname,
                "doc": doc,
                "cli": f"gway {cli_path} {cli_func}"
            })
        if funcs:
            projects[modname] = funcs

    # Build RST
    lines = ["INCLUDED PROJECTS\n", "=================\n\n"]
    for name, funcs in sorted(projects.items()):
        lines.append(f".. rubric:: {name}\n\n")
        for f in funcs:
            lines.append(f"- ``{f['name']}`` — {f['doc'].splitlines()[0]}\n\n")
            lines.append(f"  > ``{f['cli']}``\n\n")
        lines.append("\n")

    # Replace section in README
    with open(readme, 'r', encoding='utf-8') as f:
        content = f.readlines()

    license_idx = next((i for i, l in enumerate(content) if l.strip().upper() == 'LICENSE'), len(content))
    start_idx = next((i for i, l in enumerate(content) if l.strip() == 'INCLUDED PROJECTS'), None)
    if start_idx is not None:
        content = content[:start_idx] + content[license_idx:]
        license_idx = start_idx

    new_content = content[:license_idx] + lines + ['\n'] + content[license_idx:]
    with open(readme, 'w', encoding='utf-8') as f:
        f.writelines(new_content)

    gw.log(f"Updated {readme} with {len(projects)} projects.")


if __name__ == "__main__":
    build()
