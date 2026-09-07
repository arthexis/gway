# Changelog

## 1.0.0 — 2026-09-07

- Rebuilt GWAY around a GitHub-backed managed-project registry and universal command dispatcher.
- Added typed Python and Django adapter support while keeping managed projects isolated from the GWAY runtime.
- Added the first-class Python API through `gway`, `gw`, and `Gway`.
- Added system/appliance installation under `/opt/gway` with legacy command preservation.
- Adopted `gway-sigils` as GWAY's single runtime dependency.
- Added eager `%[...]` and lazy `[...]` Sigil interpolation for managed-command argument values while keeping project and command routing literal.
- Added project-, command-, path-, and GWAY-aware Sigil context values.
- Added the built-in `gway install sigils` runtime alias without creating a second managed project.
- Validated first-class Sigils end-to-end through the real `gway-wireguard` managed project.
- Adopted the shared `ci-base@v1` Python 3.11–3.14 quality, package, and compatibility baseline.
