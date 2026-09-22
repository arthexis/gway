"""Managed runtime identity and paths for recipe-owned environments."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

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
        scope=provenance["scope"],
        source=provenance["source"],
        relative_path=provenance["relative_path"],
        resolved_revision=provenance["resolved_revision"],
    )
