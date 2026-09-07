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
- Do not add bundled `projects/`, recipes, a second sigil implementation, shared mutable result/context state, Arthexis-specific imports, or legacy helper collections.
- Add new behavior in the implementation chunk described by `PLAN.md`; avoid pulling later-chunk complexity forward.

## Package Layout

Use a `src/` layout. Core responsibilities should stay separated as the implementation grows: project metadata, registry/config, repository management, adapters, dispatch, CLI value resolution, and execution.

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

Tests should verify behavior that exists, not merely assert that removed legacy behavior stays absent. A narrow import-safety test is acceptable where it protects the generation boundary itself.
