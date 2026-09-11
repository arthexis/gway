# Repository Guidelines

## Project Summary

GWAY 1.x is a lightweight GitHub-backed project manager and universal command dispatcher. It installs trusted projects into managed local environments and exposes their commands through `gway <project> <command>`.

The pre-1.0 implementation is preserved in `arthexis/gway-legacy`. Do not reintroduce legacy architecture into this repository unless `PLAN.md` explicitly schedules it.

## Design Rules

- Keep GWAY small and framework-neutral.
- Keep domain/application dependencies in managed projects, not in GWAY core.
- `sigils` is the one deliberate GWAY runtime dependency and provides the CLI value-expression language; do not duplicate its parser or resolver in GWAY.
- Project names and command paths remain literal. Resolve Sigils only in command argument values before adapter parsing.
- Projects own their command surfaces; GWAY discovers them through adapters.
- Framework differences belong behind adapter interfaces.
- The first supported adapters are Python and Django only.
- Prefer Python standard-library dependencies in core when practical.
- Preserve `gway <project> <command>` as the user-facing command shape.
- For genuine local OS permission failures (`PermissionError`, `EACCES`, `EPERM`) at the common CLI boundary, preserve the failure and print a concise `sudo gway ...` hint using the user's original argument vector. Apply this consistently to core lifecycle commands and managed project commands; never rerun automatically as root and do not infer permission failures from message text alone.
- Do not add bundled `projects/`, recipes, a second sigil implementation, shared mutable result/context state, Arthexis-specific imports, or legacy helper collections.
- Add new behavior in the implementation chunk described by `PLAN.md`; avoid pulling later-chunk complexity forward.

## Package Layout

Use a `src/` layout. Core responsibilities should stay separated as the implementation grows: project metadata, registry/config, repository management, adapters, dispatch, CLI value resolution, and execution.

## Python Style

`pyproject.toml` is the canonical Ruff configuration for this repository. Do not duplicate or override Ruff rule selection in workflows, scripts, or agent instructions.

Current expectations are:

- Python target: 3.11.
- Maximum line length: 100.
- Ruff lint families: `E`, `F`, `I`, `UP`, and `B`.
- Imports must satisfy Ruff's `I` rules rather than being hand-sorted ad hoc.
- Prefer modern Python syntax covered by Ruff's `UP` rules.
- Avoid bug-prone patterns covered by Ruff's `B` rules.
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

Quality checks run before package, compatibility, and clean-install checks. If Ruff fails, the more expensive checks should remain skipped until style is corrected.

At minimum, changes to CLI/bootstrap behavior must keep both of these working:

```bash
python -m gway --help
gway --help
```

Tests should verify behavior that exists, not merely assert that removed legacy behavior stays absent. A narrow import-safety test is acceptable where it protects the generation boundary itself.
