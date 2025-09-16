# Repository Guidelines

## Project Summary
**GWAY** is a CLI and function-dispatch framework. Any Python function inside
`projects/` can be invoked from the command line or via ``from gway import gw``.
Existing utilities (``gw.awg`` etc.) are loaded lazily and should be reused via
``gw.<project>.<sub>.<function>``.

### Glossary
* **Gateway (`gw`)** – main object providing access to all projects and saved results.
* **Sigil** – placeholder syntax like ``[VAR|default]`` resolved from context or environment.
* **Recipe (.gwr)** – automation script run with ``gway -r file``.
* **CDV** – colon-delimited value storage used by ``gw.cdv`` utilities.

### Recommendations
* Reuse built-in helpers by importing ``gw`` and calling ``gw.<project>.<function>``.
* Results from previous calls are stored in ``gw.results`` and may be referenced with sigils for chaining.
* Check ``README.rst`` for full documentation of available projects and commands.
* Don't add to the main ``README.rst`` unless instructed otherwise. Enrich the
  static ``README`` files of individual projects instead.

### Agent Advice
1. When designing new prototypes, stick with the short, verb-led names used across existing projects (``clock.now``, ``clock.plus``, ``clock.timestamp``) so Gateway can recover a ``subject`` from ``verb_subject`` names when chaining results (see ``projects/clock.py`` and ``gway/gateway.py``).
2. Prefer plain functions over classes and return CLI-friendly payloads such as status strings or dictionaries that can be unpacked into result keys, following patterns like ``env.save`` returning the updated environment mapping and ``mail.send`` reporting delivery status text (see ``projects/env.py`` and ``projects/mail.py``).
3. Keep CLI parameters optional by placing them after ``*``; anything before ``*`` becomes required even if it has a default. Functions like ``clock.now`` and ``help_db.build`` show the keyword-only style to emulate (see ``projects/clock.py`` and ``projects/help_db.py``).
4. Treat every public function (those not starting with ``_``) as CLI-ready: accept primitive arguments directly while still supporting richer objects when passed, as the mail helpers do with simple subject/body strings plus optional async behavior (see ``projects/mail.py``).
5. Design outputs so multiple commands can chain together. Gateway stores each result under its detected ``subject`` and merges dictionaries into the shared context, so returning named fields makes recipe injection effortless (see ``gway/gateway.py``).
6. Always reach helpers through the shared ``gw`` instance (``from gway import gw``) instead of importing project modules manually; the ``gw`` singleton exposes utilities like ``gw.resource`` and ``gw.mail`` for reuse (see ``projects/help_db.py`` and ``gway/gateway.py``).

## Testing
- Install requirements and the package in editable mode before running tests:
  ```bash
  pip install -r requirements.txt
  pip install -e .
  ```
- Run the test suite using the built-in runner:
  ```bash
  gway test --coverage
  ```
  (omit `--coverage` if not needed)

These instructions apply to CODEX and CI environments.
## Renaming functions
When changing a function name, update all related assets to keep the project consistent:
- Python modules inside `projects/`
- project documentation under `data/static`
- static assets such as CSS or templates
- recipe files in `recipes/`
- tests and helper tooling
- help database entries
