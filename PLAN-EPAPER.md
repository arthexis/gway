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

The gway-epaper milestone should validate that a hardware-facing Python project can be installed and dispatched through GWAY without adding ePaper-specific code to GWAY core. The project should expose a deliberate Python command namespace through `gway.toml`, keep display/backend dependencies inside its own managed environment, and document the intended appliance commands.

As with gway-wireguard, GWAY should own command discovery, generated help, aliases, type conversion, JSON rendering, and dispatch. `gway-epaper` should expose ordinary typed Python functions and keep hardware/domain logic in its own package rather than maintaining a second GWAY-facing parser.

Expected acceptance should include at least:

```text
gway install epaper
gway epaper --help
```

plus one hardware-independent diagnostic/status command that can run on a development machine and the relevant display command validation on the target Raspberry Pi/ePaper hardware.
