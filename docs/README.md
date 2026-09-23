# GWAY Documentation

This directory documents the behavior implemented on the active branch.

## Current guides

- [Projects](PROJECTS.md) — project discovery, standard Python metadata consumed by GWAY, project variables, Sous Chef attributes, and filesystem conventions.
- [Platform boundary](PLATFORM.md) — what GWAY owns versus application/domain repositories, composition boundaries, and documentation ownership.
- [Recipes](RECIPES.md) — the authoritative implemented recipe language: execution, context, companion Python files, nested recipes, check, --unless, repeat, rollback journals, reload/process handoff, execution boundaries, and transaction safety.
- [Logging](LOGGING.md) — logical sources, journal/rotating-file backends, read/tail/search semantics, platform defaults, and the ordinary GWAY operation contract used by MCP.
- [MCP](MCP.md) — generic `gway(command)` transport, canonical authorization, scopes/tokens, HTTP deployment, service supervision, and logging examples.
- [Glossary](GLOSSARY.md) — canonical definitions for GWAY terminology.

The top-level [README](../README.rst) is intentionally concise and should orient readers rather than duplicate these guides. Agent-specific implementation and validation rules live in [AGENTS.md](../AGENTS.md); that file is an implementation/maintenance guide rather than a second user manual.

When adding documentation, distinguish implemented behavior from roadmap ideas. Do not copy syntax from older branches without verifying it against the active parser and tests.
