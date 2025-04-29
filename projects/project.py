import sys
import toml
from pathlib import Path
import subprocess


def build(bump: bool = False, dist: bool = False) -> None:
    """
    Build the project by generating a pyproject.toml file.

    Args:
        bump (bool): If True, increment the patch version in VERSION.
        dist (bool): If True, create a distribution package.
    """

    project_name = "gway"
    description = "Infrastructure for https://www.gelectriic.com"
    author_name = "arthexis"
    author_email = "arthexis@gmail.com"
    python_requires = ">=3.7"
    classifiers = [
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ]

    version_path = Path("VERSION")
    requirements_path = Path("requirements.txt")
    pyproject_path = Path("pyproject.toml")

    if not version_path.exists():
        raise FileNotFoundError("VERSION file not found.")
    if not requirements_path.exists():
        raise FileNotFoundError("requirements.txt file not found.")

    # If bump is True, increment the version
    if bump:
        current_version = version_path.read_text().strip()
        major, minor, patch = map(int, current_version.split("."))
        patch += 1
        new_version = f"{major}.{minor}.{patch}"
        version_path.write_text(new_version)
        print(f"Bumped version: {current_version} → {new_version}")

    # Read version after possible bump
    version = version_path.read_text().strip()

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
            }
        },
        "tool": {
            "setuptools": {
                "packages": ["gway"],  # Explicitly specify the packages to include
            }
        }
    }

    toml_string = toml.dumps(pyproject_content)
    pyproject_path.write_text(toml_string)
    print(f"Generated {pyproject_path}")

    # If dist is True, build the distribution package
    if dist:
        dist_dir = Path("dist")
        if dist_dir.exists():
            # Clean previous builds
            for item in dist_dir.iterdir():
                item.unlink()
            dist_dir.rmdir()

        print("Building distribution package...")
        subprocess.run([sys.executable, "-m", "build"], check=True)  # <-- build via Python
        print("Distribution package created in dist/")
