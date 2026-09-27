"""Static validation for GWAY recipe source trees."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..dispatch import OperationLookupError, resolve_operation
from ..ingestion.router import has_path_syntax
from ..tokens import is_literal, is_unquoted, statements, token_value
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
    if not has_path_syntax(source):
        return None

    target = Path(source).expanduser()
    if not target.is_absolute():
        target = parent / target

    candidates = [target]
    if target.suffix == "":
        candidates.append(target.with_suffix(".rx"))
    if target.is_dir():
        candidates.extend(
            (
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
    checks = 0
    rollback = False
    unless = False
    index = 1

    while index < len(stage):
        option_token = stage[index]
        option = token_value(option_token)
        literal_option = is_literal(option_token)

        if not option.startswith("--"):
            findings.append(
                Finding(
                    path,
                    statement,
                    "error",
                    f"unexpected check argument {option!r}",
                )
            )
            return

        if not literal_option and option in {"--true", "--false"}:
            checks += 1
            index += 1
            continue

        if not literal_option and option == "--is":
            if index + 1 >= len(stage):
                findings.append(
                    Finding(path, statement, "error", "missing value after --is")
                )
                return
            checks += 1
            index += 2
            continue

        if not literal_option and option == "--unless":
            if unless:
                findings.append(
                    Finding(
                        path,
                        statement,
                        "error",
                        "check accepts only one --unless condition",
                    )
                )
                return
            if index + 1 >= len(stage):
                findings.append(
                    Finding(
                        path,
                        statement,
                        "error",
                        "missing boolean condition after --unless",
                    )
                )
                return
            unless = True
            index += 2
            continue

        if not literal_option and option == "--rollback":
            if rollback:
                findings.append(
                    Finding(
                        path,
                        statement,
                        "error",
                        "check accepts only one --rollback journal",
                    )
                )
                return
            if index + 1 >= len(stage):
                findings.append(
                    Finding(
                        path,
                        statement,
                        "error",
                        "missing journal name after --rollback",
                    )
                )
                return
            next_token = stage[index + 1]
            next_value = token_value(next_token)
            if not is_literal(next_token) and next_value.startswith("--"):
                findings.append(
                    Finding(
                        path,
                        statement,
                        "error",
                        "missing journal name after --rollback",
                    )
                )
                return
            rollback = True
            index += 2
            continue

        inverted = not literal_option and option.startswith("--no-")
        name = option[5:] if inverted else option[2:]
        if not name:
            findings.append(
                Finding(path, statement, "error", f"invalid check argument {option!r}")
            )
            return

        if index + 1 < len(stage):
            next_token = stage[index + 1]
            next_value = token_value(next_token)
            if is_literal(next_token) or (
                not next_value.startswith("--") and next_value != "-"
            ):
                index += 1

        checks += 1
        index += 1

    if not checks:
        findings.append(
            Finding(
                path,
                statement,
                "error",
                "check requires at least one assertion",
            )
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
