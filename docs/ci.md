# Project-owned CI

Gway CI is a project convention, not a GitHub-specific subsystem.

## Question

Can Gway provide a project-defined CI contract that runs identically on a developer machine and an automated runner, without embedding GitHub Actions concepts or introducing a separate CI configuration language?

## Answer

Yes. CI should be represented by an ordinary directory recipe named `ci`; Gway ships its maintained entry point as `sampler/ci/__main__.rx`, which collapses through the existing `__main__` convention so it is directly callable as `gway ci`, while projects may shadow sampler fallback with their own root `ci.rx`. Gway supplies generic execution, failure propagation, and structured-result semantics; the project recipe defines what its CI actually does.

`ci` should not become a special-purpose built-in unless implementation exposes a generic capability that recipes cannot provide.

## Plan

1. Establish `ci` as the conventional project CI entry point, with Gway's maintained recipe in `sampler/ci/__main__.rx` and verify normal root resolution makes `gway ci` work without special parser handling.
2. Ensure recipe/process failures propagate to Gway's process exit code correctly.
3. Make CI execution compatible with the ordinary `--json` result surface, adding stable overall/check results only where existing result semantics are insufficient.
4. Add Gway's own `sampler/ci/__main__.rx` with representative recipe validation and primary tests.
5. Cover successful CI, failed CI, JSON execution, and root recipe discovery.
6. Convert one existing GitHub Actions CI job to bootstrap Gway and invoke `gway ci`.
7. Confirm local and runner execution use the same command and definition.
8. Keep root `ci.rx` documented as an optional project override of sampler fallback.

Matrices, forge status/labels, artifacts, auto-merge, deployment, Watchtower reconciliation, and publication are deferred.

## Acceptance

`gway ci` and `gway ci --json` work from a Gway checkout, execute the project-defined recipe, propagate process success/failure correctly, expose stable machine-readable results, and one GitHub Actions job invokes the same entry point.

**GitHub invokes Gway's CI; Gway does not implement GitHub CI.**

## Structured results

JSON is a generic recipe-execution envelope rather than a CI-specific format. A recipe invoked with `--json` returns its final `result` and chronological `results` history. Consequently `gway ci --json` is machine-readable while ordinary non-recipe JSON commands retain their existing output shape.

## Result

Gway now owns the Python 3.10 project's CI definition through the maintained `sampler/ci/__main__.rx` recipe. The GitHub runner supplies checkout, Python, dependency installation, timeout, and diagnostic process boundaries, then delegates project validation to `python -m gway ci`.

The same sampler recipe is discoverable from a local checkout, while a project root `ci.rx` can shadow it through normal root resolution. Recipe JSON execution exposes both the final result and chronological result history, so `gway ci --json` uses the same execution contract without a GitHub-specific reporting path. Python 3.13 compatibility remains separately runner-defined and is outside this first migration chunk.
