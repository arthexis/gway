from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.request import urlopen


def _load_bytes(value: str, content: bool) -> bytes:
    """Return bytes from ``value``.

    If ``content`` is False, ``value`` is treated as plain text.
    Otherwise ``value`` is interpreted as a filename or URL and its
    contents are loaded as bytes.
    """
    if content:
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https"):
            with urlopen(value) as resp:
                return resp.read()
        return Path(value).read_bytes()
    return value.encode()


def _load_text(value: str, content: bool) -> str:
    """Return text from ``value``.

    When ``content`` is True the value is read from a file or URL.
    """
    if content:
        parsed = urlparse(value)
        if parsed.scheme in ("http", "https"):
            with urlopen(value) as resp:
                return resp.read().decode()
        return Path(value).read_text()
    return value


def _default_out(ext: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"b64_{ts}{ext}")


def encode(value: str, content: bool = False, out: Optional[str] = None) -> str:
    """Base64 encode ``value`` or the contents of a file/URL.

    Args:
        value: Text to encode or path/URL when ``content`` is True.
        content: Treat ``value`` as filename or URL.
        out: Optional output file to store the encoded text.
    Returns:
        The Base64 encoded string or the output filename if ``out`` is provided.
    """
    data = _load_bytes(value, content)
    encoded = base64.b64encode(data).decode()
    if out:
        outfile = Path(out)
        outfile.write_text(encoded)
        return str(outfile)
    return encoded


def decode(value: str, content: bool = False, out: Optional[str] = None) -> str:
    """Decode Base64 ``value`` or a file/URL containing Base64 text.

    Args:
        value: Base64 string or path/URL when ``content`` is True.
        content: Interpret ``value`` as filename or URL.
        out: Optional output filename for binary data.
    Returns:
        Decoded text if it is UTF-8 printable, otherwise the path to the
        output file where binary data was written.
    """
    source = _load_text(value, content)
    decoded = base64.b64decode(source)
    try:
        text = decoded.decode()
        if all(ch.isprintable() or ch in "\r\n\t" for ch in text):
            if out:
                outfile = Path(out)
                outfile.write_text(text)
                return str(outfile)
            return text
    except UnicodeDecodeError:
        pass

    outfile = Path(out) if out else _default_out(".bin")
    outfile.write_bytes(decoded)
    return str(outfile)
