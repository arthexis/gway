import sys
import toml
from pathlib import Path
import subprocess

from gway import Gateway


def build(
    bump: bool = False,
    dist: bool = False,
    twine: bool = False,
    user: str = "[PYPI_USERNAME]",
    password: str = "[PYPI_PASSWORD]",
    token: str = "[PYPI_API_TOKEN]",
    git: bool = False,
) -> None:
    """
    Build the project and optionally upload to PyPI.

    Args:
        bump (bool): Increment patch version if True.
        dist (bool): Build distribution package if True.
        twine (bool): Upload to PyPI if True.
        user (str): PyPI username (default: [PYPI_USERNAME]).
        password (str): PyPI password (default: [PYPI_PASSWORD]).
        token (str): PyPI API token (default: [PYPI_API_TOKEN]).
        git (bool): Require a clean git repo and commit/push after release if True.
    """
    gway = Gateway()
    test_result = gway.run_tests()
    if not test_result:
        gway.abort("Tests failed, build aborted.")

    if git:
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            gway.abort("Git repository is not clean. Commit or stash changes before building.")

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
        print(f"\nBumped version: {current_version} → {new_version}")
    else:
        new_version = version_path.read_text().strip()

    version = new_version

    dependencies = [
        line.strip()
        for line in requirements_path.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    # TODO: Can we get the repository URL string directly from the local git repo itself?

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
                "repository": "https://github.com/arthexis/gway.git"
            }
        },
        "tool": {
            "setuptools": {
                "packages": ["gway"],
            }
        }
    }

    pyproject_path.write_text(toml.dumps(pyproject_content), encoding="utf-8")
    print(f"Generated {pyproject_path}")

    manifest_path = Path("MANIFEST.in")
    if not manifest_path.exists():
        manifest_path.write_text(
            "include README.rst\n"
            "include VERSION\n"
            "include requirements.txt\n"
            "include pyproject.toml\n"
        )
        print("Generated MANIFEST.in")

    if dist:
        dist_dir = Path("dist")
        if dist_dir.exists():
            for item in dist_dir.iterdir():
                item.unlink()
            dist_dir.rmdir()

        print("Building distribution package...")
        subprocess.run([sys.executable, "-m", "build"], check=True)
        print("Distribution package created in dist/")

        if twine:
            print("Validating distribution with twine check...")
            check_result = subprocess.run(
                [sys.executable, "-m", "twine", "check", "dist/*"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            if check_result.returncode != 0:
                print("PyPI README rendering check failed:")
                print(check_result.stdout)
                print("Aborting upload.")
                return

            print("Twine check passed. Uploading to PyPI...")

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
            print("Package uploaded to PyPI successfully.")

    if git:
        subprocess.run(["git", "add", "VERSION", "pyproject.toml"], check=True)

        commit_msg = f"PyPI Release v{version}" if twine else f"Release v{version}"

        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "push"], check=True)
        print(f"Committed and pushed: {commit_msg}")
