# file: projects/web/chat/whats.py
"""Minimal WhatsApp Cloud API helpers."""

import os
import requests
from gway import gw


def send_message(to: str, body: str, *, token: str | None = None, phone_id: str | None = None, preview_url: bool = False):
    """Send a text message using the WhatsApp Cloud API.

    Parameters
    ----------
    to : str
        Destination phone number in international format ("+123...").
    body : str
        Text body to send.
    token : str, optional
        Access token. Defaults to ``WHATS_TOKEN`` environment variable.
    phone_id : str, optional
        Business phone number ID. Defaults to ``WHATS_PHONE_ID`` environment variable.
    preview_url : bool, optional
        Enable link preview in message body.

    Returns
    -------
    dict
        Parsed JSON response or ``{"error": ...}`` on failure.
    """
    token = token or os.environ.get("WHATS_TOKEN")
    phone_id = phone_id or os.environ.get("WHATS_PHONE_ID")
    if not token or not phone_id:
        gw.error("WhatsApp credentials missing.")
        return {"error": "Missing WhatsApp token or phone id."}

    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": gw.resolve(body), "preview_url": bool(preview_url)},
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        return resp.json()
    except Exception as e:
        gw.error(f"WhatsApp send error: {e}")
        return {"error": str(e)}


def api_post_send(*, to=None, body=None, preview_url=False, token=None, phone_id=None, **kwargs):
    """POST /chat/whats/send - Send a WhatsApp message."""
    if not (to and body):
        return {"error": "'to' and 'body' are required"}
    return send_message(str(to), str(body), token=token, phone_id=phone_id, preview_url=preview_url)
