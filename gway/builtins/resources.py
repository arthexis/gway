
__all__ = [
    "normalize_ext",
    "resource",
]


def normalize_ext(e: str) -> str:
    return e if e.startswith(".") else f".{e}"


def resource(*parts, touch: bool = False, check: bool = False, text: bool = False, dir: bool = False):
    """Locate or create a resource path."""
    import os
    import pathlib
    from gway import gw

    rel_path = pathlib.Path(*parts)
    tried = []

    pkg_root = pathlib.Path(__file__).resolve().parents[1]
    candidates = [
        pathlib.Path.cwd(),
        pathlib.Path(os.environ.get("GWAY_ROOT")) if os.environ.get("GWAY_ROOT") else None,
        pathlib.Path.home(),
        pkg_root,
    ]

    path = None
    for base in filter(None, candidates):
        candidate = base / rel_path
        if candidate.exists() or touch or dir:
            path = candidate
            break
        tried.append(str(candidate))

    if path is None:
        path = pathlib.Path.cwd() / rel_path

    if not (touch or dir) and check and not path.exists():
        gw.abort(f"Required resource {path} missing. Tried: {tried}")

    path.parent.mkdir(parents=True, exist_ok=True)

    if dir:
        path.mkdir(parents=True, exist_ok=True)
    elif touch and not path.exists():
        path.touch()

    if text:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:  # pragma: no cover - file IO
            gw.abort(f"Failed to read {path}: {e}")
    return path.resolve()


def resource_list(*parts, ext: str | None = None, prefix: str | None = None, suffix: str | None = None):
    """List files inside a resourced directory."""
    from gway import gw
    base_dir = resource(*parts)
    if not base_dir.exists() or not base_dir.is_dir():
        gw.abort(f"Resource directory {base_dir} does not exist or is not a directory")

    matches = []
    for item in base_dir.iterdir():
        if not item.is_file():
            continue
        name = item.name
        if ext and not name.endswith(ext):
            continue
        if prefix and not name.startswith(prefix):
            continue
        if suffix and not name.endswith(suffix):
            continue
        matches.append(item)

    matches.sort(key=lambda p: p.stat().st_ctime)
    return matches
