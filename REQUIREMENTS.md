# GWAY Requirements

This file records cross-cutting product requirements that apply across implementation chunks.

## Permission failure guidance

When GWAY receives a genuine local OS permission failure at its common CLI boundary, it must preserve the failure and provide an actionable privilege-escalation hint where appropriate.

Requirements:

- recognize `PermissionError` and permission-related `OSError` values such as `EACCES` and `EPERM` structurally rather than matching message text;
- preserve the original non-zero failure status;
- on platforms where `sudo` is an appropriate available mechanism, print a concise hint using the user's original command vector, e.g. `sudo gway install epaper`;
- never automatically re-execute a failed command as root;
- apply consistently to GWAY lifecycle commands and managed project commands that reach the common CLI error boundary.

## Optional root command export

At lower priority, managed projects should be able to opt in through `gway.toml` to exporting project commands into GWAY's root command namespace. This must be adapter-neutral so Django projects such as Arthexis can expose an operator command as `gway ocpp` while retaining the qualified form `gway arthexis ocpp`.

Resolution requirements:

1. GWAY core commands take precedence;
2. installed project names and aliases take precedence;
3. opted-in exported project commands are considered after those namespaces;
4. collisions between exported commands from multiple projects must fail with a clear ambiguity error rather than choosing implicitly;
5. the manifest declares the export behavior; GWAY core must not contain application-specific command names.

This feature is not a Chunk 8 blocker and is intended for later CLI/dispatcher polish after lifecycle and appliance behavior are stable.
