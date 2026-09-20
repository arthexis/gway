from pathlib import Path


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def test_python_modules_and_packages_use_single_word_names():
    root = Path(__file__).resolve().parents[2] / "gway"
    violations = []

    for path in root.rglob("*"):
        if path.name == "__pycache__":
            continue

        if path.is_dir():
            name = path.name
            if "_" in name and not _is_dunder(name):
                violations.append(str(path.relative_to(root.parent)))
            continue

        if path.suffix != ".py":
            continue

        stem = path.stem
        if "_" in stem and not _is_dunder(stem):
            violations.append(str(path.relative_to(root.parent)))

    assert not violations, (
        "GWAY module/package names must be single words; "
        f"found: {', '.join(sorted(violations))}"
    )
