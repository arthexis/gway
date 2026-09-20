"""Durable preservation of customized managed installations."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .model import Installation, validate_name


@dataclass(frozen=True)
class Stash:
    """One durable snapshot of a customized managed project."""

    name: str
    path: Path
    tree: Path
    created_at: str
    recorded_fingerprint: str | None
    actual_fingerprint: str

    def __post_init__(self):
        validate_name(self.name)
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "tree", Path(self.tree))


def preserve(existing, managed_path, actual_fingerprint, stashes_root):
    """Atomically preserve one customized managed tree and its provenance."""
    if not isinstance(existing, Installation):
        raise TypeError("stash preservation requires an Installation record")

    managed_path = Path(managed_path)
    stashes_root = Path(stashes_root)
    project_root = stashes_root / existing.name
    project_root.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(timezone.utc).isoformat()
    stash_id = f"{created_at.replace(':', '-')}-{uuid.uuid4().hex[:12]}"
    destination = project_root / stash_id
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{stash_id}.stage-",
            dir=project_root,
        )
    )
    tree = temporary / "tree"

    try:
        shutil.copytree(
            managed_path,
            tree,
            symlinks=True,
        )
        metadata = {
            "name": existing.name,
            "created_at": created_at,
            "source": existing.source,
            "scope": existing.scope,
            "requested_ref": existing.requested_ref,
            "resolved_revision": existing.resolved_revision,
            "recorded_fingerprint": existing.fingerprint,
            "actual_fingerprint": actual_fingerprint,
            "install_path": str(existing.install_path),
            "tree": "tree",
        }
        metadata_path = temporary / "metadata.json"
        metadata_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise

    return Stash(
        name=existing.name,
        path=destination,
        tree=destination / "tree",
        created_at=created_at,
        recorded_fingerprint=existing.fingerprint,
        actual_fingerprint=actual_fingerprint,
    )
