
from dataclasses import dataclass

__all__ = [
    "run_recipe",
    "run",
    "repeat",
]


@dataclass(frozen=True)
class _RepeatDirective:
    """Internal payload used to signal recipe/CLI repetition."""

    rest: float = 5.0
    times: int | None = None


def run_recipe(*scripts: str, **context):
    from gway import gw
    """Run commands parsed from .gwr files, falling back to the recipes bundle."""
    from .console import load_recipe, process

    if not scripts:
        raise ValueError("At least one script must be provided to run_recipe()")
    gw.debug(f"run_recipe called with scripts: {scripts!r}")

    results = []
    for script in scripts:
        command_sources, comments = load_recipe(script)
        if comments:
            gw.debug("Recipe comments:\n" + "\n".join(comments))
        result = process(command_sources, origin="recipe", **context)
        results.append(result)
    return results[-1] if len(results) == 1 else results


def run(*script: str, **context):
    from gway import gw
    """Run recipes or treat the input as the literal recipe."""
    import os
    import uuid
    from datetime import datetime

    try:
        return gw.run_recipe(*script, **context)
    except FileNotFoundError:
        gw.debug("run(): Could not find one or more recipes, treating script as raw lines")
        work_dir = gw.resource("work", check=True)
        unique_id = str(uuid.uuid4())
        recipe_name = f"run_{unique_id}.gwr"
        recipe_path = os.path.join(work_dir, recipe_name)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        context_lines = [
            "# GWAY ad-hoc script",
            f"# Created: {now} by {user}",
            f"# Args: {script!r}",
        ]
        if context:
            context_lines.append(f"# Context: {context!r}")
        script_lines = list(script)
        all_lines = context_lines + list(script_lines)

        with open(recipe_path, "w", encoding="utf-8") as f:
            for line in all_lines:
                f.write(line.rstrip("\n") + "\n")
        gw.debug(f"Wrote ad-hoc script to {recipe_path}")

        return gw.run_recipe(recipe_path, **context)


def repeat(*, rest: float = 5.0, times: int | None = None) -> _RepeatDirective:
    from gway import gw

    """Schedule the preceding commands to run again after ``rest`` seconds."""

    rest_value = float(rest)
    if rest_value < 0:
        raise ValueError("--rest must be a non-negative number")

    times_value = None if times is None else int(times)
    if times_value is not None and times_value < 0:
        raise ValueError("--times must be zero or a positive integer")

    gw.debug(
        "repeat() directive created",
        extra={"rest": rest_value, "times": times_value},
    )
    return _RepeatDirective(rest=rest_value, times=times_value)
