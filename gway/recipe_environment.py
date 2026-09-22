"""Managed runtime identity and paths for recipe-owned environments."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import json
import os
import subprocess

from .install.paths import data_root


@dataclass(frozen=True)
class RecipeEnvironment:
    """Stable external runtime location owned by one physical recipe."""

    key: str
    identity: str
    recipe: Path
    root: Path
    venv: Path
    metadata: Path
    requirements_file: Path
    scope: str = "user"
    source: str | None = None
    relative_path: Path | None = None
    resolved_revision: str | None = None


def _managed_source(runtime, recipe):
    """Return the most specific managed installation containing a recipe."""
    matches = []
    for installation in getattr(runtime, "_installed", {}).values():
        try:
            root = installation.install_path.expanduser().resolve()
            relative = recipe.relative_to(root)
        except (AttributeError, OSError, RuntimeError, ValueError):
            continue
        matches.append((len(root.parts), installation, relative))

    if not matches:
        return None
    _, installation, relative = max(matches, key=lambda item: item[0])
    return installation, relative


def recipe_identity(runtime, recipe_filename):
    """Return stable provenance identity for one physical recipe.

    Managed installations use source provenance plus the recipe's path relative
    to the installed project. Arbitrary local recipes fall back to their
    canonical absolute filesystem path.
    """
    recipe = Path(recipe_filename).expanduser().resolve()
    managed = _managed_source(runtime, recipe)
    if managed is None:
        return {
            "recipe": recipe,
            "identity": f"local:{recipe}",
            "scope": "user",
            "source": None,
            "relative_path": None,
            "resolved_revision": None,
        }

    installation, relative = managed
    return {
        "recipe": recipe,
        "identity": f"managed:{installation.source}:{relative.as_posix()}",
        "scope": installation.scope,
        "source": installation.source,
        "relative_path": relative,
        "resolved_revision": installation.resolved_revision,
    }


def recipe_environment(runtime, recipe_filename):
    """Return the external managed environment paths for one recipe.

    This function is pure with respect to the filesystem: it computes paths but
    never creates or mutates the recipe tree or the managed data directory.
    """
    provenance = recipe_identity(runtime, recipe_filename)
    identity = provenance["identity"]
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    root = (
        data_root(system=provenance["scope"] == "system").expanduser().resolve()
        / "recipes"
        / key
    )
    return RecipeEnvironment(
        key=key,
        identity=identity,
        recipe=provenance["recipe"],
        root=root,
        venv=root / "venv",
        metadata=root / "metadata.json",
        requirements_file=root / "requirements.txt",
        scope=provenance["scope"],
        source=provenance["source"],
        relative_path=provenance["relative_path"],
        resolved_revision=provenance["resolved_revision"],
    )


def environment_python(environment):
    """Return the Python executable path inside one managed recipe venv."""
    if os.name == "nt":
        return environment.venv / "Scripts" / "python.exe"
    return environment.venv / "bin" / "python"


def _metadata_payload(environment, requirements):
    """Return durable desired-state metadata for one recipe environment."""
    return {
        "identity": environment.identity,
        "recipe": str(environment.recipe),
        "scope": environment.scope,
        "source": environment.source,
        "relative_path": (
            environment.relative_path.as_posix()
            if environment.relative_path is not None
            else None
        ),
        "resolved_revision": environment.resolved_revision,
        "requirements": {
            "python": list(requirements),
        },
    }


def load_environment_metadata(environment):
    """Return persisted recipe-environment metadata, if valid and present."""
    try:
        return json.loads(environment.metadata.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return None


def _write_environment_metadata(environment, payload):
    """Atomically persist recipe-environment desired state."""
    environment.root.mkdir(parents=True, exist_ok=True)
    temporary = environment.metadata.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(environment.metadata)


def sync_python_environment(environment, uv, requirements):
    """Converge one recipe-owned Python environment with uv.

    The recipe source tree is never mutated. The venv and metadata live only
    under Gway's durable data root.
    """
    requirements = tuple(dict.fromkeys(str(item).strip() for item in requirements))
    if not requirements or any(not item for item in requirements):
        raise ValueError("Python environment requires non-empty package specs")
    if any("\n" in item or "\r" in item for item in requirements):
        raise ValueError("Python package specs cannot contain newlines")

    desired = _metadata_payload(environment, requirements)
    python = environment_python(environment)
    current = load_environment_metadata(environment)

    if current == desired and python.is_file():
        return python

    environment.root.mkdir(parents=True, exist_ok=True)
    if not python.is_file():
        subprocess.run(
            [str(uv), "venv", str(environment.venv)],
            check=True,
        )

    temporary_requirements = environment.requirements_file.with_suffix(".tmp")
    temporary_requirements.write_text(
        "".join(f"{item}\n" for item in requirements),
        encoding="utf-8",
    )
    temporary_requirements.replace(environment.requirements_file)

    subprocess.run(
        [
            str(uv),
            "pip",
            "sync",
            "--python",
            str(python),
            str(environment.requirements_file),
        ],
        check=True,
    )
    _write_environment_metadata(environment, desired)
    return python
