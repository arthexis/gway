# Repository Guidelines

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
