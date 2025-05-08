import os
import base64
from gway import requires, gw


_qr_code_cache = set()

@requires("qrcode[pil]")
def generate_url(value):
    """Return the URL for a QR code image for a given value, generating it if needed."""
    import qrcode
    safe_filename = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=") + ".png"
    if not safe_filename in _qr_code_cache:
        qr_path = gw.resource("temp", "shared", "qr_codes", safe_filename)
        if not os.path.exists(qr_path):
            img = qrcode.make(value)
            img.save(qr_path)
        _qr_code_cache.add(safe_filename)
    return f"/temp/qr_codes/{safe_filename}"

