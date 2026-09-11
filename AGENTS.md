# Repository Guidelines

## Project Summary

GWAY 1.x is a lightweight GitHub-backed project manager and universal command dispatcher. It installs trusted projects into managed local environments and exposes their commands through `gway <project> <command>`.

The pre-1.0 implementation is preserved in `arthexis/gway-legacy`. Do not reintroduce legacy architecture into this repository unless the current architecture or an explicitly approved issue requires it. See `docs/PLAN.md` for the current architecture and roadmap.

## Design Rules

- Keep GWAY small and framework-neutral.
- Keep domain/application dependencies in managed projects, not in GWAY core.
- `sigils` is the one deliberate GWAY runtime dependency and provides the CLI value-expression language; do not duplicate its parser or resolver in GWAY.
- Project and command resolution must remain deterministic. Apply Sigil/solve semantics only where the current command grammar defines them.
- Projects own their command surfaces; GWAY discovers them through adapters.
- Framework differences belong behind adapter interfaces.
- Prefer Python standard-library dependencies in core when practical.
- Preserve `gway <project> <command>` as the canonical qualified command shape even when shorthand is added.
- For genuine local OS permission failures (`PermissionError`, `EACCES`, `EPERM`) at the common CLI boundary, preserve the failure and print a concise `sudo gway ...` hint using the user's original argument vector. Apply this consistently to core lifecycle commands and managed project commands; never rerun automatically as root and do not infer permission failures from message text alone.
- Do not add bundled `projects/`, recipes, a second sigil implementation, shared mutable global result/context state, Arthexis-specific imports, or legacy helper collections.
- Track active implementation sequencing in GitHub issues. Do not create permanent numbered-chunk planning documents for completed work.

## Package Layout

Use a `src/` layout. Core responsibilities should stay separated as the implementation grows: project metadata, registry/config, repository management, adapters, dispatch, CLI value resolution, chaining, services/lifecycle, and execution.

Keep checkout-critical files such as `README.md`, `AGENTS.md`, `CHANGELOG.md`, and the license at the repository root. Put detailed architecture, language, API, requirements, and operational documentation under `docs/`.

## Python Style

`pyproject.toml` is the canonical Ruff configuration for this repository. Do not duplicate or override Ruff rule selection in workflows, scripts, or agent instructions.

Current expectations are:

- Python target: 3.11.
- Maximum line length: 100.
- Ruff configuration comes from `pyproject.toml`.
- Prefer modern Python syntax covered by the configured Ruff rules.
- New or edited Python must pass both Ruff lint and Ruff format before the change is considered complete.

Use the repository configuration explicitly when checking code:

```bash
python -m ruff check --config pyproject.toml src tests
python -m ruff format --check --config pyproject.toml src tests
```

When fixing style locally, prefer Ruff itself rather than manually approximating its output:

```bash
python -m ruff check --fix --config pyproject.toml src tests
python -m ruff format --config pyproject.toml src tests
```

## Testing

Install in editable mode and run pytest:

```bash
python -m pip install -e '.[dev]'
pytest
```

At minimum, changes to CLI/bootstrap behavior must keep both of these working:

```bash
python -m gway --help
gway --help
```

Tests should verify supported behavior rather than merely asserting that removed legacy behavior stays absent. A narrow import-safety test is acceptable where it protects a real compatibility boundary.
