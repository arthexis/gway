# Structured CI results

The maintained `gway ci` entry point returns a canonical structured result while
preserving ordinary human-readable test output. This result is intended to be the
local source of truth consumed later by GitHub CI checks and Drive-related status
operations.

## State vocabulary

The canonical CI state vocabulary is provider-independent:

- `pending`
- `passed`
- `failed`
- `cancelled`
- `skipped`
- `neutral`
- `unknown`

Local maintained CI currently emits `passed`, `failed`, or `neutral`; the wider
vocabulary allows provider adapters to normalize GitHub and other CI systems later.

## Result shape

A normal maintained run has this shape:

```json
{
  "state": "failed",
  "phase": "tests",
  "suite": "integration",
  "started_at": "2026-09-30T22:00:00+00:00",
  "completed_at": "2026-09-30T22:00:47+00:00",
  "duration": 47.2,
  "validation": {
    "state": "passed",
    "target": "...",
    "recipes": 120,
    "errors": 0,
    "warnings": 0,
    "findings": []
  },
  "tests": {
    "state": "failed",
    "tests": 819,
    "passed": 814,
    "failed": 2,
    "errors": 0,
    "skipped": 3,
    "duration": 46.5,
    "failures": [
      {
        "id": "tests/foo/test_bar.py::test_something",
        "category": "assertion",
        "summary": "expected 3, got 4"
      }
    ],
    "returncode": 1,
    "command": ["..."]
  }
}
```

Full traceback/log output is deliberately not part of this compact contract. Later
`observe` operations can expose that diagnostic evidence.

## Failure envelope

An ordinary CI failure is a valid result, not a Gway implementation error. Gway
therefore emits the complete structured result (and any requested `-o/--output`
sidecar) and then exits non-zero. The process exit status is execution metadata and
is not injected into the public result mapping.

Unexpected implementation exceptions are not converted into ordinary CI failures.

## Structural source

Pytest continues writing its normal terminal output. The maintained CI capability
asks pytest for a temporary JUnit XML report and derives counts, durations and
failure identities from that machine-readable report. It does not scrape pytest's
human-oriented terminal rendering.

Recipe validation is performed before tests. A recipe-validation failure returns a
structured `phase: validation` result and does not start the test suite.
