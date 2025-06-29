# file: projects/release.py

import os
import inspect
from pathlib import Path

from gway import gw


def build(
    *,
    bump: bool = False,
    dist: bool = False,
    twine: bool = False,
    help_db: bool = True,
    projects: bool = False,
    git: bool = False,
    all: bool = False,
    force: bool = False
) -> None:
    """
    Build the project and optionally upload to PyPI.

    Args:
        bump (bool): Increment patch version if True.
        dist (bool): Build distribution package if True.
        twine (bool): Upload to PyPI if True.
        force (bool): Skip version-exists check on PyPI if True.
        git (bool): Require a clean git repo and commit/push after release if True.
        vscode (bool): Build the vscode extension.
    """
    from pathlib import Path
    import sys
    import subprocess
    import toml

    if not (token := gw.resolve("[PYPI_API_TOKEN]", "")):
        user = gw.resolve("[PYPI_USERNAME]")
        password = gw.resolve("[PYPI_PASSWORD]")

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

    project_name = "gway"
    description = "Software Project Infrastructure by https://www.gelectriic.com"
    author_name = "Rafael J. Guillén-Osorio"
    author_email = "tecnologia@gelectriic.com"
    python_requires = ">=3.11"
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
            # ======= Safeguard: Abort if version already on PyPI unless --force =======
            if not force:
                releases = []
                try:
                    # Use JSON API instead of deprecated XML-RPC
                    import requests
                    url = f"https://pypi.org/pypi/{project_name}/json"
                    resp = requests.get(url, timeout=5)
                    if resp.ok:
                        data = resp.json()
                        releases = list(data.get("releases", {}).keys())
                    else:
                        gw.warning(f"Could not fetch releases for {project_name} from PyPI: HTTP {resp.status_code}")
                except Exception as e:
                    gw.warning(f"Could not verify existing PyPI versions: {e}")
                if new_version in releases:
                    gw.abort(
                        f"Version {new_version} is already on PyPI. "
                        "Use --force to override."
                    )
            # ===========================================================================

            gw.info("Validating distribution with twine check...")
            check_result = subprocess.run(
                [sys.executable, "-m", "twine", "check", "dist/*"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            if check_result.returncode != 0:
                gw.error(f"PyPI README rendering check failed, aborting upload:\n{check_result.stdout}")
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


def changes(*, files=None, staged=False, context=3, max_bytes=200_000, clip=False):
    """
    Returns a unified diff of all recent textual changes in the git repo.

    - Shows added/removed lines (ignores binary files).
    - Includes unstaged (working directory) by default. Use staged=True to see only staged.
    - 'files': Optionally filter by path(s) or file glob(s).
    - 'context': Number of context lines in the diff (default 3).
    - 'max_bytes': Truncate diff if too large (default 200,000).
    """
    import subprocess

    cmd = ["git", "diff", "--unified=%d" % context]
    if staged:
        cmd.insert(2, "--staged")
    if files:
        if isinstance(files, str):
            files = [files]
        cmd += list(files)

    try:
        diff = subprocess.check_output(cmd, encoding="utf-8", errors="replace")
    except subprocess.CalledProcessError as e:
        return f"[ERROR] Unable to get git diff: {e}"
    except FileNotFoundError:
        return "[ERROR] git command not found. Are you in a git repo?"

    # Remove any diff blocks for binary files
    filtered = []
    skip = False
    for line in diff.splitlines(keepends=True):
        # Exclude blocks marking a binary difference
        if line.startswith("Binary files "):
            continue
        if line.startswith("diff --git"):
            skip = False  # new file block
        if "GIT binary patch" in line:
            skip = True
        if skip:
            continue
        filtered.append(line)

    result = "".join(filtered)
    if len(result) > max_bytes:
        return result[:max_bytes] + "\n[...Diff truncated at %d bytes...]" % max_bytes
    
    if clip: 
        gw.clip.copy(result)
    if not gw.silent:
        return result or "[No changes detected]"


if __name__ == "__main__":
    build()
