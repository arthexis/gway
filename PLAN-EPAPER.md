# gway-epaper roadmap extension

`arthexis/gway-epaper` is an explicit post-Django/Arthexis milestone in the GWAY redesign. Treat it as the next implementation chunk after the Arthexis end-to-end conversion, before lifecycle and appliance work.

Ordering:

```text
Chunk 6 - Django adapter MVP
  -> Chunk 7 - Convert Arthexis
  -> Chunk 8 - Convert gway-epaper
  -> update/remove lifecycle
  -> appliance/system installation
  -> remaining operational project conversions
```

Chunk 8 starts with one small core CLI prerequisite discovered during the Arthexis/ePaper install path: when a command fails because the local OS denies access, GWAY should preserve the failure and add an actionable sudo hint. This behavior belongs at the common CLI error boundary so it applies consistently to `install`, future `update`/`remove`, and managed project commands rather than being implemented separately by each operation or adapter.

Permission handling requirements:

- recognize genuine `PermissionError` and `OSError` permission failures such as `EACCES`/`EPERM` rather than matching error-message text;
- print the original failure plus a concise hint containing the user's original command, for example `sudo gway install epaper`;
- preserve the non-zero failure status;
- never automatically retry or rerun a command as root;
- apply the same behavior to core lifecycle commands and managed project command execution where the failure reaches GWAY's CLI boundary;
- keep the implementation platform-aware so systems without `sudo` are not given a misleading command.

The gway-epaper milestone should then validate that a hardware-facing Python project can be installed and dispatched through GWAY without adding ePaper-specific code to GWAY core. The project should expose a deliberate Python command namespace through `gway.toml`, keep display/backend dependencies inside its own managed environment, and document the intended appliance commands.

As with gway-wireguard, GWAY should own command discovery, generated help, aliases, type conversion, JSON rendering, and dispatch. `gway-epaper` should expose ordinary typed Python functions and keep hardware/domain logic in its own package rather than maintaining a second GWAY-facing parser.

Expected acceptance should include at least:

```text
gway install epaper
gway epaper --help
```

plus one hardware-independent diagnostic/status command that can run on a development machine and the relevant display command validation on the target Raspberry Pi/ePaper hardware.

Chunk 8 acceptance should also verify the common permission UX with at least one core command path and one managed project command path: a real OS permission exception must produce a non-zero result and a correct `sudo gway ...` hint without re-executing the command.
