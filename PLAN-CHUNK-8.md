# Chunk 8 execution plan

Chunk 8 converts `arthexis/gway-epaper` to the GWAY 1.x project model and validates the Python adapter against another hardware-facing Raspberry Pi project.

## Phase 1 - Core permission UX

Implement the cross-cutting permission requirement first because `gway install epaper` can encounter protected paths during real deployment.

- handle genuine `PermissionError`, `EACCES`, and `EPERM` at the common CLI error boundary;
- preserve the failure and exit status;
- print a platform-appropriate `sudo gway ...` hint built from the original argv;
- never retry automatically as root;
- cover both a core lifecycle command path and a managed project command path.

## Phase 2 - Inspect gway-epaper

- identify the current package layout and operator-facing operations;
- separate public GWAY-facing functions from private display/backend helpers;
- identify one diagnostic/status command that can run without ePaper hardware;
- identify the real display command that should be validated on the target Raspberry Pi.

## Phase 3 - Manifest and Python namespace

- add or validate `gway.toml`;
- use project name `epaper`;
- select the generic Python adapter;
- expose a deliberate importable command module/package;
- keep hardware dependencies in the `gway-epaper` environment rather than GWAY core.

## Phase 4 - Command surface

- expose ordinary typed Python functions for supported operator commands;
- rely on GWAY for discovery, help, aliases, type conversion, JSON rendering, and dispatch;
- keep low-level bootstrap, device drivers, and implementation helpers private;
- avoid introducing a second GWAY-facing parser inside the project.

## Phase 5 - Development-machine validation

Required acceptance:

```text
gway install epaper
gway epaper --help
gway epaper <diagnostic-or-status-command>
```

The diagnostic/status command must work without connected ePaper hardware.

Also validate the permission UX using real exception types: failures remain non-zero and show the correct `sudo gway ...` hint without executing the command again.

## Phase 6 - Raspberry Pi hardware validation

On the target Raspberry Pi/ePaper installation:

```text
gway install epaper
gway epaper --help
gway epaper <display-command> ...
```

Confirm the relevant display operation reaches the existing backend successfully through the managed project environment.

## Deferred follow-up

Do not block Chunk 8 on optional root command exports such as `gway ocpp` for an Arthexis command. That generic manifest/dispatcher feature is recorded in `REQUIREMENTS.md` and should be implemented later with deterministic namespace collision handling.
