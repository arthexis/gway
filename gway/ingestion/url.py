"""HTTP(S) URL materialization for ingestion."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urldefrag, urlsplit
from urllib.request import Request, urlopen

from gway.cache import digest


@dataclass(frozen=True)
class RemoteArtifact:
    """Materialized remote source and its cache provenance."""

    url: str
    path: Path
    content_hash: str
    cache_hit: bool
    final_url: str | None = None


def is_url(source):
    """Return whether source is an HTTP(S) URL."""
    if not isinstance(source, str) or not source:
        return False
    parsed = urlsplit(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _canonical_url(source):
    if not is_url(source):
        raise ValueError(f"Unsupported ingestion URL: {source!r}")
    clean, _ = urldefrag(source)
    return clean


def _filename(url):
    name = Path(unquote(urlsplit(url).path)).name
    return name or "resource"


def materialize(gateway, source, *, refresh=False):
    """Fetch/cache one URL and return its materialized artifact."""
    url = _canonical_url(source)
    entry = gateway.cache.entry("url", url)
    metadata_path = entry / "metadata.json"
    metadata = gateway.cache.read_json(metadata_path)

    if not refresh and isinstance(metadata, dict):
        relative = metadata.get("artifact")
        content_hash = metadata.get("content_hash")
        if isinstance(relative, str) and isinstance(content_hash, str):
            cached = entry / relative
            if cached.is_file():
                return RemoteArtifact(
                    url=url,
                    path=cached,
                    content_hash=content_hash,
                    cache_hit=True,
                    final_url=metadata.get("final_url"),
                )

    request = Request(url, headers={"User-Agent": "gway-url-ingestion/1"})
    with urlopen(request) as response:
        payload = response.read()
        final_url = getattr(response, "geturl", lambda: url)() or url

    content_hash = digest(payload)
    filename = _filename(final_url)
    relative = Path(content_hash) / filename
    artifact = entry / relative

    if not artifact.is_file():
        gateway.cache.write(artifact, payload)

    gateway.cache.write_json(
        metadata_path,
        {
            "url": url,
            "final_url": final_url,
            "content_hash": content_hash,
            "artifact": relative.as_posix(),
        },
    )

    return RemoteArtifact(
        url=url,
        path=artifact,
        content_hash=content_hash,
        cache_hit=False,
        final_url=final_url,
    )


def ingest_url(gateway, source, *, trust=False, refresh=False, **kwargs):
    """Materialize a remote source and delegate trusted code to path ingestion."""
    artifact = materialize(gateway, source, refresh=refresh)

    if not trust:
        raise PermissionError(
            "Remote ingestion requires trust=True before cached content is executed; "
            f"materialized at {artifact.path}"
        )

    from .router import ingest_path

    return ingest_path(gateway, artifact.path, **kwargs)
