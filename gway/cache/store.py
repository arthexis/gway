"""Generic namespaced cache storage for GWAY."""

import hashlib
import json
from pathlib import Path
import tempfile

from .paths import default_root


def digest(value):
    """Return a stable SHA-256 key for text or bytes."""
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("cache digest requires text or bytes")
    return hashlib.sha256(bytes(value)).hexdigest()


class Cache:
    """Namespaced cache rooted outside project source trees by default."""

    def __init__(self, root=None):
        self.root = (
            default_root() if root is None else Path(root).expanduser()
        ).resolve()

    def namespace(self, name):
        """Return/create one safe cache namespace."""
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise ValueError("cache namespace must be one safe path component")
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def entry(self, namespace, key):
        """Return/create a stable entry directory for a namespace/key pair."""
        path = self.namespace(namespace) / digest(key)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write(self, path, data):
        """Atomically write bytes to a path inside this cache."""
        path = Path(path)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("cache writes must stay inside the cache root") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            stream.write(bytes(data))
            temporary = Path(stream.name)
        temporary.replace(path)
        return path

    def write_json(self, path, value):
        """Atomically write JSON metadata inside this cache."""
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self.write(path, payload)

    def read_json(self, path, default=None):
        """Read JSON metadata when present."""
        path = Path(path)
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
