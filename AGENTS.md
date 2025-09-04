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
