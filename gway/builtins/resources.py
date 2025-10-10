
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

    def _safe_home() -> pathlib.Path | None:
        """Return a usable home directory path or ``None``."""
        env_candidates = [
            os.environ.get("GWAY_HOME"),
            os.environ.get("HOME"),
            os.environ.get("USERPROFILE"),
        ]
        for value in env_candidates:
            if value:
                return pathlib.Path(value).expanduser()

        homedrive = os.environ.get("HOMEDRIVE")
        homepath = os.environ.get("HOMEPATH")
        if homedrive and homepath:
            return pathlib.Path(homedrive) / homepath.lstrip("\\/")

        try:
            return pathlib.Path.home()
        except RuntimeError:
            return None

    search_roots = [pathlib.Path.cwd()]
    env_root = os.environ.get("GWAY_ROOT")
    if env_root:
        search_roots.append(pathlib.Path(env_root))

    home_dir = _safe_home()
    if home_dir is not None:
        search_roots.append(home_dir)

    pkg_root = pathlib.Path(__file__).resolve().parents[1]
    search_roots.append(pkg_root)

    path = None
    for root in search_roots:
        candidate = root / rel_path
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
