# Manual Sigil Context Validation

Use this guide to validate the adapter-provided lazy Sigil context bridge before enabling ORM-backed providers in a real managed project.

## 1. Install the branch

From a checkout of this branch:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
gway --version
```

Expected version:

```text
1.0.1
```

Confirm the protected namespace API is installed through GWAY's runtime dependency:

```bash
python -c 'from sigils import SafeNamespace, NamespaceProvider; print("sigils-ok")'
```

Expected:

```text
sigils-ok
```

## 2. Register the bundled Django fixture

```bash
gway register tests/fixtures/django_project
gway list
```

`django-fixture` should be listed.

The fixture declares this provider in `gway.toml`:

```toml
[adapter]
type = "django"
manage = "manage.py"
settings = "gway_django_fixture.settings"
sigils = "gway_django_fixture.sigils:context"
```

The provider is called only for lazy command argument resolution and only after Django has initialized.

## 3. Positive provider resolution

Run:

```bash
gway django-fixture echo '[THING.name]'
```

Expected:

```text
demo
```

Verify that GWAY passes project and command metadata into the provider:

```bash
gway django-fixture echo '[THING.project]'
gway django-fixture echo '[THING.command]'
```

Expected:

```text
django-fixture
echo
```

## 4. Protected namespace negative test

Run:

```bash
gway django-fixture echo '[THING.name.upper]'
```

Expected output is the unresolved token itself:

```text
[THING.name.upper]
```

This proves a value reached through `SafeNamespace` cannot escape into built-in tools or arbitrary attribute traversal.

## 5. Eager/lazy separation

Run from any known directory:

```bash
gway django-fixture echo '%[cwd]'
gway django-fixture echo '[THING.name]'
```

The first command should print the working directory captured by GWAY's eager context. The second should print `demo` from the Django provider. ORM/provider roots are intentionally lazy-only; do not rely on `%[THING.*]` for project data.

## 6. Reserved namespace protection

Project providers must not return any of these top-level keys:

```text
cwd
home
gway
project
command
```

GWAY rejects a provider attempting to replace them instead of silently shadowing core context.

## 7. Real-project canary criteria

Before enabling an Arthexis model root, keep the first provider intentionally small. Recommended first canary:

```text
NODE.hostname
NODE.role
NODE.address
```

For the real Arthexis test, verify all of the following through a harmless management command:

```text
[NODE.hostname]       -> expected seeded value
[NODE.__class__]      -> unresolved
[NODE.save]           -> unresolved
[NODE.delete]         -> unresolved
[NODE.hostname.upper] -> unresolved unless explicitly projected by Arthexis
```

Do not add a second model/root until the first one passes positive, negative, Secret/redaction, and full-dispatch tests.
