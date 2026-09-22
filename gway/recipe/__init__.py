"""Recipe loading, resolution, dependency management, and execution."""

from .frame import RecipeFrame
from .loading import load_recipe
from .path import companion_path, parse_recipe_context, recipe_base, recipe_path
from .require import collect_recipe_requirements, prepare_required_companion
from .runtime import execute_recipe, ingest_companion

__all__ = (
    "RecipeFrame",
    "collect_recipe_requirements",
    "companion_path",
    "execute_recipe",
    "ingest_companion",
    "load_recipe",
    "parse_recipe_context",
    "prepare_required_companion",
    "recipe_base",
    "recipe_path",
)
