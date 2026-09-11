# GWAY Requirements

This file records cross-cutting product requirements that are not better expressed by a focused issue or feature document.

## Permission failure guidance

When GWAY receives a genuine local OS permission failure at its common CLI boundary, it must preserve the failure and provide an actionable privilege-escalation hint where appropriate.

- Recognize `PermissionError` and permission-related `OSError` values such as `EACCES` and `EPERM` structurally rather than matching message text.
- Preserve the original non-zero failure status.
- Where `sudo` is appropriate and available, print a concise hint using the user's original command vector.
- Never automatically re-execute a failed command as root.
- Apply the behavior consistently to core lifecycle commands and managed project commands that reach the common CLI error boundary.

## CLI output

GWAY owns final result rendering across core lifecycle commands and managed project commands.

- Human-readable output is the default.
- Mappings render one field per line, with nested mappings and sequences indented consistently.
- Sequences render one item per line, with nested values indented consistently.
- Scalar values render plainly without Python container syntax.
- Interactive terminal output may use lightweight ANSI color; non-interactive output remains uncolored and `NO_COLOR` disables color explicitly.
- Machine-readable JSON is emitted only when the global `--json` flag is present.
- `--json` is reserved by GWAY and is not forwarded to adapters.
- JSON output must remain valid, uncolored JSON suitable for piping.

## Interactive prompting

GWAY can opt in to prompting for missing required managed-command option values with the global `-i` / `--interactive` flag.

- Prompting is disabled by default and never changes normal non-interactive parser behavior.
- Only missing required option values are prompted for; required positional arguments retain adapter/parser behavior.
- Prompts and validation messages go to stderr so result stdout remains clean.
- `-i`, `--interactive`, and `--json` are reserved by GWAY and are not forwarded to managed adapters.
- Adapter metadata should preserve declared option spellings so prompted values can be replayed using a valid option.

## Optional root command export

Managed projects may eventually opt in through `gway.toml` to exporting selected project commands into GWAY's root command namespace while retaining the project-qualified form.

Resolution must remain deterministic:

1. GWAY core commands take precedence.
2. Installed project names and aliases take precedence.
3. Opted-in exported project commands are considered after those namespaces.
4. Collisions between exported commands from multiple projects fail with a clear ambiguity error.
5. The manifest declares export behavior; GWAY core must not contain application-specific command names.

This remains a pending dispatcher feature. Its implementation should be tracked by the current issue/roadmap rather than by historical implementation-chunk numbering.
