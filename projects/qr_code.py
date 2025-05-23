import os
import uuid
import base64

from io import BytesIO
from gway import requires, gw


_qr_code_cache = set()


@requires("qrcode[pil]")
def generate_img(value, *, path=None):
    """Generate a QR code image from the given value and save it to the specified path.
    If path is not provided, we use a random uuid to name it, unrelated to the value.
    """
    import qrcode
    img = qrcode.make(value)
    if path is None:
        path = gw.resource("temp", "qr_codes", str(uuid.uuid4()) + ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return {"image": img, "path": path}


generate_image = generate_img


def generate_url(value):
    """Return the local URL to a QR code with the given value. 
    This will only work when the website is up and running to serve /temp.
    This generates a new QR code image if needed, or uses a cache if possible.
    """
    safe_filename = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=") + ".png"
    if safe_filename not in _qr_code_cache:
        qr_path = gw.resource("temp", "shared", "qr_codes", safe_filename)
        if not os.path.exists(qr_path):
            generate_image(value, path=qr_path)
        _qr_code_cache.add(safe_filename)
    return f"/temp/qr_codes/{safe_filename}"


def generate_b64data(value):
    """Generate a QR code image from the given value and return it as a base64-encoded PNG string."""
    import qrcode
    img = qrcode.make(value)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@requires(cv2="opencv-python", numpy="numpy")
def scan_image(source):
    """
    Scan the given image (file‑path or PIL.Image) for QR codes and return
    a list of decoded string values. Returns [] if nothing’s found.
    """
    import cv2
    import numpy as np

    # 1) Load image into an OpenCV BGR array
    if isinstance(source, str):
        img_bgr = cv2.imread(source)
        if img_bgr is None:
            raise FileNotFoundError(f"Could not open image file: {source}")
    else:
        # assume PIL.Image
        pil_img = source
        # convert to RGB array, then to BGR
        rgb = np.array(pil_img)
        img_bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    # 2) Detect & decode (multi‑code capable)
    detector = cv2.QRCodeDetector()
    # OpenCV ≥4.7 supports detectAndDecodeMulti:
    try:
        ok, decoded_texts, points, _ = detector.detectAndDecodeMulti(img_bgr)
        if ok:
            return [text for text in decoded_texts if text]
    except AttributeError:
        # fallback for older OpenCV: single‑code only
        data, points, _ = detector.detectAndDecode(img_bgr)
        return [data] if data else []

    return []


scan_img = scan_image
