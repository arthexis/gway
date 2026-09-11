# GWAY Architecture and Roadmap

## Purpose

GWAY is a lightweight project manager, command dispatcher, and composition layer for the Arthexis/GWAY ecosystem. It turns managed projects into discoverable command namespaces while keeping project dependencies and domain logic outside GWAY core.

The pre-1.0 implementation is preserved in `arthexis/gway-legacy`; this repository should not recreate its bundled-project architecture.

## Current architecture

GWAY separates these responsibilities:

- **Registry and repository management** resolve, install, register, upgrade, and remove projects.
- **Project metadata** records checkout, environment, repository, revision, aliases, and manifest configuration.
- **Adapters** expose framework-specific command surfaces through a common command model. Python and Django are the primary supported adapters.
- **Dispatcher and runner** resolve commands and execute them in the correct managed environment.
- **Sigils** provide the command-value language and protected eager/lazy context resolution.
- **Chaining** composes command stages while preserving native values and invocation-local context.
- **Services and lifecycle** let managed projects describe install/upgrade hooks and service topology without moving application-specific behavior into GWAY core.
- **CLI and Python API** are front ends over the same managed command model.

## Command model

The canonical qualified command shape remains:

```text
gway <project> <command> [arguments]
```

Core lifecycle and management commands remain top-level, for example:

```text
gway list
gway search
gway install wireguard
gway upgrade wireguard
gway remove wireguard
gway info wireguard
gway path wireguard
```

Projects own their command surfaces. GWAY discovers and describes those commands rather than hard-coding domain operations centrally.

## Project manifests

Managed repositories expose `gway.toml`. A manifest identifies the project, adapter, command entrypoint, and any lifecycle/service metadata GWAY needs to manage the project. It should not duplicate the project's full command list.

Python projects expose ordinary typed functions through the Python adapter. Django projects expose management commands through the Django adapter. Framework-specific behavior stays behind adapter interfaces.

## Composition language

Sigils and chaining are first-class parts of current GWAY rather than deferred redesign milestones. Project and command routing remains deterministic; values may be resolved through Sigils, solve/template stages, transfer selectors, and chain context.

See [CHAINING.md](CHAINING.md) for the chaining grammar and transfer rules.

## Design invariants

1. Keep GWAY small and framework-neutral.
2. Keep domain dependencies in managed projects.
3. Projects own their command surfaces.
4. Adapters isolate framework differences.
5. Managed projects execute in their own environments.
6. CLI and Python API share the same registry/dispatcher/runner semantics.
7. Sigils remains the dedicated value-expression dependency; do not duplicate its parser in GWAY.
8. Core command resolution must remain deterministic as new shorthand or export syntax is introduced.
9. Lifecycle and service facilities must remain generic rather than embedding Arthexis or hardware-specific policy.
10. New syntax should compose with chaining and preserve literal escape paths.

## Active roadmap

Current work is tracked primarily in GitHub issues rather than numbered implementation chunks. The major active directions are:

- complete and harden command chaining, solve-stage grammar, transfer routing, and related shorthand;
- improve global execution controls such as silent/no-op behavior and explainability/debug tracing;
- continue generic managed-install, upgrade, lifecycle, and service support used by Arthexis and other GWAY projects;
- support both system and user service scopes where projects declare them;
- improve flexible service command syntax without making command resolution ambiguous;
- retain optional deterministic root command export as a future dispatcher capability;
- validate generic facilities through real managed projects such as Arthexis, WireGuard, RFID, LCD, sound, web, and agent integrations without adding their domain logic to GWAY core.

Completed historical chunk plans should not remain in the repository as active roadmap documents. Git history and merged issues/PRs provide the implementation record.
