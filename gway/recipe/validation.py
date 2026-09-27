"""Static validation for GWAY recipe source trees."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..dispatch import OperationLookupError, resolve_operation
from ..tokens import is_unquoted, statements, token_value
from .loading import load_recipe
from .path import companion_path


class RecipeValidationError(RuntimeError):
    """Raised when one or more recipe validation errors are found."""


@dataclass(frozen=True)
class Finding:
    path: Path
    statement: int
    level: str
    message: str

    def render(self, root: Path) -> str:
        try:
            display = self.path.relative_to(root)
        except ValueError:
            display = self.path
        return f"{display}:{self.statement}: {self.level}: {self.message}"


def _target_path(target) -> Path:
    if target is None:
        from ..sampler import root

        return root().resolve()

    path = Path(str(target)).expanduser()
    if path.exists():
        return path.resolve()

    from ..sampler import resolve

    return resolve(str(target)).resolve()


def _recipe_paths(target: Path) -> tuple[Path, ...]:
    if target.is_file():
        if target.suffix != ".rx":
            raise RecipeValidationError(f"Recipe target must be a .rx file: {target}")
        return (target,)
    if not target.is_dir():
        raise RecipeValidationError(f"Recipe target does not exist: {target}")
    return tuple(sorted(path for path in target.rglob("*.rx") if path.is_file()))


def _split_pipeline(tokens) -> list[list]:
    stages = [[]]
    for token in tokens:
        if is_unquoted(token) and token_value(token) == "-":
            stages.append([])
        else:
            stages[-1].append(token)
    return stages


def _explicit_recipe_path(source: str, parent: Path) -> Path | None:
    if not (source.startswith("./") or source.startswith("../")):
        return None

    target = (parent / source).resolve()
    candidates = [target]
    if target.suffix != ".rx":
        candidates.extend(
            (
                target.with_suffix(".rx"),
                target / f"{target.name}.rx",
                target / "__main__.rx",
            )
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def _validate_repeat(stage, *, path, statement, findings):
    options = [token_value(token) for token in stage[1:]]
    controls = {"--times", "--while", "--until", "--interval", "--max", "--rollback"}
    seen = {}
    index = 0
    if options and not options[0].startswith("--"):
        index = 1
    while index < len(options):
        option = options[index]
        if option not in controls:
            findings.append(
                Finding(path, statement, "error", f"unknown repeat option {option!r}")
            )
            return
        if index + 1 >= len(options):
            findings.append(
                Finding(path, statement, "error", f"missing value after {option}")
            )
            return
        seen[option] = seen.get(option, 0) + 1
        index += 2

    if seen.get("--while") and seen.get("--until"):
        findings.append(
            Finding(path, statement, "error", "repeat cannot combine --while and --until")
        )
    if seen.get("--times") and (seen.get("--while") or seen.get("--until")):
        findings.append(
            Finding(
                path,
                statement,
                "error",
                "repeat --times cannot combine with --while or --until",
            )
        )
    for option, count in seen.items():
        if count > 1 and option in {"--while", "--until", "--rollback", "--times", "--max"}:
            findings.append(
                Finding(path, statement, "error", f"repeat repeats {option}")
            )


def _validate_check(stage, *, path, statement, findings):
    if len(stage) == 1:
        findings.append(Finding(path, statement, "error", "check has no assertions"))
        return
    values = [token_value(token) for token in stage[1:]]
    for index, value in enumerate(values):
        if value in {"--is", "--unless", "--rollback"} and index + 1 >= len(values):
            findings.append(
                Finding(path, statement, "error", f"missing value after {value}")
            )


def _validate_stage(runtime, stage, *, path, statement, findings):
    if not stage:
        findings.append(Finding(path, statement, "error", "empty pipeline stage"))
        return

    first = token_value(stage[0])
    if first == "repeat":
        _validate_repeat(
            stage,
            path=path,
            statement=statement,
            findings=findings,
        )
        return
    if first == "check":
        _validate_check(
            stage,
            path=path,
            statement=statement,
            findings=findings,
        )
        return

    child = _explicit_recipe_path(first, path.parent)
    if child is not None:
        if not child.is_file():
            findings.append(
                Finding(
                    path,
                    statement,
                    "error",
                    f"referenced child recipe does not exist: {first}",
                )
            )
        return

    try:
        resolve_operation(runtime, stage)
    except OperationLookupError as exc:
        findings.append(
            Finding(
                path,
                statement,
                "warning",
                f"operation is not statically resolvable: {exc.query}",
            )
        )
    except (LookupError, TypeError, ValueError) as exc:
        findings.append(Finding(path, statement, "error", str(exc)))


def _validate_companion(path: Path, *, root: Path, findings):
    companion = companion_path(path)
    if companion is None:
        return
    try:
        source = companion.read_text(encoding="utf-8")
        compile(source, str(companion), "exec")
    except (OSError, SyntaxError) as exc:
        findings.append(Finding(path, 0, "error", f"invalid companion Python: {exc}"))


def validate_recipes(runtime, target=None):
    """Validate recipe syntax/composition without executing recipe side effects."""
    target_path = _target_path(target)
    recipes = _recipe_paths(target_path)
    if not recipes:
        raise RecipeValidationError(f"No .rx recipes found under {target_path}")

    root = target_path if target_path.is_dir() else target_path.parent
    findings = []
    checked = 0

    for recipe in recipes:
        checked += 1
        _validate_companion(recipe, root=root, findings=findings)
        try:
            commands, _ = load_recipe(recipe)
        except (OSError, ValueError, TypeError) as exc:
            findings.append(Finding(recipe, 0, "error", f"parse failed: {exc}"))
            continue

        statement_index = 0
        for command in commands:
            for statement_tokens in statements(command.get("tokens", ())):
                statement_index += 1
                stages = _split_pipeline(statement_tokens)
                if any(not stage for stage in stages):
                    findings.append(
                        Finding(
                            recipe,
                            statement_index,
                            "error",
                            "pipeline contains an empty stage",
                        )
                    )
                    continue
                for stage in stages:
                    _validate_stage(
                        runtime,
                        stage,
                        path=recipe,
                        statement=statement_index,
                        findings=findings,
                    )

    errors = [finding for finding in findings if finding.level == "error"]
    warnings = [finding for finding in findings if finding.level == "warning"]
    rendered = [finding.render(root) for finding in findings]

    if errors:
        detail = "\n".join(finding.render(root) for finding in errors)
        raise RecipeValidationError(
            f"Recipe validation failed with {len(errors)} error(s):\n{detail}"
        )

    return {
        "target": str(target_path),
        "recipes": checked,
        "errors": 0,
        "warnings": len(warnings),
        "findings": rendered,
    }
