import os
import sys
import toml
import time
import base64
import logging
import inspect
import textwrap
import subprocess
from pathlib import Path

from gway import Gateway, requires

gway = Gateway()
logger = logging.getLogger(__name__)


def build(
    bump: bool = False,
    dist: bool = False,
    twine: bool = False,
    help_db: bool = True,
    user: str = "[PYPI_USERNAME]",
    password: str = "[PYPI_PASSWORD]",
    token: str = "[PYPI_API_TOKEN]",
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
    """
    if all:
        bump = True
        dist = True
        twine = True
        help_db = True
        git = True
    logger.info(f"Running tests before project build.")
    test_result = gway.run_tests()
    if not test_result:
        gway.abort("Tests failed, build aborted.")

    if git:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            gway.abort("Git repository is not clean. Commit or stash changes before building.")

    if help_db:
        build_help_db()

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
        logger.info(f"\nBumped version: {current_version} → {new_version}")
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
    logger.info(f"Generated {pyproject_path}")

    manifest_path = Path("MANIFEST.in")
    if not manifest_path.exists():
        manifest_path.write_text(
            "include README.rst\n"
            "include VERSION\n"
            "include requirements.txt\n"
            "include pyproject.toml\n"
        )
        logger.info("Generated MANIFEST.in")

    if dist:
        dist_dir = Path("dist")
        if dist_dir.exists():
            for item in dist_dir.iterdir():
                item.unlink()
            dist_dir.rmdir()

        logger.info("Building distribution package...")
        subprocess.run([sys.executable, "-m", "build"], check=True)
        logger.info("Distribution package created in dist/")

        if twine:
            logger.info("Validating distribution with twine check...")
            check_result = subprocess.run(
                [sys.executable, "-m", "twine", "check", "dist/*"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            if check_result.returncode != 0:
                logger.error("PyPI README rendering check failed, aborting upload:\n{check_result.stdout}")
                return

            logger.info("Twine check passed. Uploading to PyPI...")
            upload_command = [
                sys.executable, "-m", "twine", "upload", "dist/*"
            ]

            if token:
                upload_command += ["--username", "__token__", "--password", token]
            elif user and password:
                upload_command += ["--username", user, "--password", password]
            else:
                raise ValueError("Must provide either token or both user and password for Twine upload.")

            subprocess.run(upload_command, check=True)
            logger.info("Package uploaded to PyPI successfully.")

    if git:
        subprocess.run(["git", "add", "VERSION", "pyproject.toml"], check=True)
        if help_db:
            subprocess.run(["git", "add", "data/help.sqlite"], check=True)
        commit_msg = f"PyPI Release v{version}" if twine else f"Release v{version}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
        logger.info(f"Committed and pushed: {commit_msg}")


def build_help_db():
    from gway.functions import load_project

    with gway.database.connect("data", "help.sqlite") as cursor:
        cursor.execute("DROP TABLE IF EXISTS help")
        cursor.execute("""
            CREATE VIRTUAL TABLE help USING fts5(
                project, function, signature, docstring, source, todos, tokenize='porter')   
        """)

        projects_dir = os.path.join(gway.root, "projects")
        for entry in os.scandir(projects_dir):
            if entry.name.startswith("_"):
                continue
            name = entry.name[:-3] if entry.name.endswith(".py") else entry.name
            try:
                module, funcs = load_project(name, gway.root)
                for fname, func in funcs.items():
                    doc = inspect.getdoc(func)
                    sig = str(inspect.signature(func))
                    source = "".join(inspect.getsourcelines(func)[0])
                    todos = extract_todos(source)

                    cursor.execute("INSERT INTO help VALUES (?, ?, ?, ?, ?, ?)", 
                                (name, fname, sig, doc, source, "\n".join(todos)))
            except Exception as e:
                logger.warning(f"Skipping project {name}: {e}")

        cursor.execute("COMMIT")


def extract_todos(source):
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


@requires("requests")
def watch_pypi_package(package_name, on_change, poll_interval=300.0, logger=None):
    import threading
    import requests

    url = f"https://pypi.org/pypi/{package_name}/json"
    logger.info(f"Watching PyPI package: {package_name}")
    stop_event = threading.Event()

    def _watch():
        last_version = None
        while not stop_event.is_set():
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                data = response.json()
                current_version = data["info"]["version"]
                logger.debug(f"Current PyPI version: {current_version}")

                if last_version is not None and current_version != last_version:
                    if logger:
                        logger.warning(f"New version detected for {package_name}: {current_version}")
                    on_change()
                    os._exit(1)

                last_version = current_version
            except Exception as e:
                if logger:
                    logger.warning(f"Error watching PyPI package {package_name}: {e}")
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


_qr_code_cache = set()

@requires("qrcode[pil]")
def generate_qr_code(value):
    """Return the URL for a QR code image for a given value, generating it if needed."""
    import qrcode
    safe_filename = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=") + ".png"
    if not safe_filename in _qr_code_cache:
        qr_path = gway.resource("temp", "shared", "qr_codes", safe_filename)
        if not os.path.exists(qr_path):
            img = qrcode.make(value)
            img.save(qr_path)
        _qr_code_cache.add(safe_filename)
    return f"/temp/qr_codes/{safe_filename}"
