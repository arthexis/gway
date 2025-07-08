# Repository Guidelines

## Project Summary
**GWAY** is a CLI and function-dispatch framework. Any Python function inside
`projects/` can be invoked from the command line or via ``from gway import gw``.
Dispatcher helpers expose special functions as web routes:
- ``view_*`` → ``/project/view`` (HTML output, optionally method specific ``view_get_*``/``view_post_*``).
- ``api_*`` → ``/api/project/view`` (JSON output).
- ``render_*`` → ``/render/project/view/hash`` (HTML/JSON fragments).
Call ``gw.web.app.make()`` to register views and ``gw.web.server.serve_app()`` to launch the server.
Existing utilities (``gw.awg``, ``gw.ocpp``, ``gw.vbox`` etc.) are loaded lazily and should be reused via
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
