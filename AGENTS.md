# Repository Guidelines

This branch is the minimal GWAY Gateway rebuild.

## Scope

Keep the repository focused on GWAY core mechanics. Do not add bundled domain
projects, framework-specific integrations, deployment tooling, or third-party
runtime dependencies unless the architecture explicitly calls for them.

The current baseline must remain importable and runnable with no runtime
dependencies.

## Testing

Install the package and pytest, then run:

```bash
python -m pip install -e .
python -m pip install pytest
python -m pytest -q
```

At minimum, preserve smoke coverage for importing `gway`, constructing
`Gateway`, and invoking the CLI help entry point.
