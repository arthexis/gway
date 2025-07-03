# file: projects/web/web.py

from gway import gw

def build_url(*args, **kwargs):
    """Build a fully-qualified context-aware URL given a path sequence and query params."""
    try:
        url = gw.web.app.build_url(*args, **kwargs)
        return base_url() + url
    except AttributeError:
        return base_url() + '/'.join(args) 

def build_ws_url(*args, **kwargs):
    """Build a fully-qualified context-aware WS URL given a path sequence and query params."""
    try:
        url = gw.web.app.build_url(*args, **kwargs)
        return base_ws_url() + url
    except AttributeError:
        return base_ws_url() + '/'.join(args) 

def base_host():
    # Replace '0.0.0.0' with '127.0.0.1' by convention
    val = gw.resolve('[BASE_HOST]', '[SITE_HOST]', '[LOCALHOST]', '127.0.0.1')
    if val == "0.0.0.0":
        val = "127.0.0.1"
    return val

def base_port():
    return gw.resolve('[BASE_PORT]', '[SITE_PORT]', '[HTTP_PORT]', '8888')

def build_protocol(protocol: str, url: str) -> str:
    """
    Strip any protocol from url and attach the desired one, ensuring //host:port.
    Always replaces 0.0.0.0 with 127.0.0.1.
    """
    from urllib.parse import urlparse

    s = url.strip()
    s = s.replace("0.0.0.0", "127.0.0.1")
    # Handle bare port (e.g. "8888")
    if s.isdigit():
        s = f"127.0.0.1:{s}"
    # Remove existing protocol if present
    parsed = urlparse(s if "://" in s else f"//{s}", scheme="")
    # Compose netloc (host:port)
    host = parsed.hostname or ""
    if host == "0.0.0.0":
        host = "127.0.0.1"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{host}{port}" if host else s.lstrip("/")
    # Always attach '//' after protocol for clarity
    return f"{protocol}://{netloc}"

def _get_protocol(host_url, prefer_ssl: bool, kind: str = "http") -> str:
    """
    Select protocol ("http"/"https" or "ws"/"wss") based on host.
    Forces plain protocol if host is localhost or 127.0.0.1.
    kind: "http" or "ws"
    """
    from urllib.parse import urlparse
    s = host_url.strip()
    s = s.replace("0.0.0.0", "127.0.0.1")
    parsed = urlparse(s if "://" in s else f"//{s}", scheme="")
    host = parsed.hostname or ""
    if host in {"127.0.0.1", "localhost"}:
        return "http" if kind == "http" else "ws"
    # Default SSL policy
    return "https" if (kind == "http" and prefer_ssl) else ("wss" if kind == "ws" and prefer_ssl else kind)

def base_url(*, ssl_default=True):
    """
    Returns the canonical HTTP(S) base URL, e.g. 'https://host:port'
    Forces http if host is localhost/127.0.0.1.
    """
    host_url = gw.resolve('[BASE_URL]', '[SITE_URL]', '[LOCAL_URL]', '')
    if not host_url:
        host = base_host()
        port = base_port()
        host_url = f"{host}:{port}"
    use_https = gw.cast.to_bool(gw.resolve('[USE_HTTPS]', '[ENABLE_SSL]', '[USE_SSL]', ssl_default))
    protocol = _get_protocol(host_url, use_https, kind="http")
    return build_protocol(protocol, host_url)

def base_ws_url(*, ssl_default=False):
    """
    Returns the canonical WS(S) base URL, e.g. 'ws://host:port'
    Forces ws if host is localhost/127.0.0.1.
    If the host_url already has a port, replace it with the ws_port.
    """
    from urllib.parse import urlparse

    host_url = gw.resolve('[BASE_URL]', '[SITE_URL]', '')
    ws_port = int(gw.resolve('[WEBSOCKET_PORT]', '9000'))
    if not host_url:
        host = base_host()
        port = base_port()
        host_url = f"{host}:{port}"

    # Parse out host and port
    s = host_url.strip().replace("0.0.0.0", "127.0.0.1")
    # urlparse needs protocol to parse port correctly
    parsed = urlparse(s if "://" in s else f"//{s}", scheme="")

    host = parsed.hostname or ""
    # Use ws_port, replacing any existing port
    netloc = f"{host}:{ws_port}" if host else f"127.0.0.1:{ws_port}"

    use_wss = gw.cast.to_bool(gw.resolve('[USE_WSS]', '[ENABLE_SSL]', '[USE_SSL]', ssl_default))
    protocol = _get_protocol(netloc, use_wss, kind="ws")
    return f"{protocol}://{netloc}"
