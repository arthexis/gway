# file: projects/ocpp/rfid.py
"""Authorization helpers for OCPP RFID transactions."""

import traceback
from gway import gw


def authorize_balance(record=None, **_):
    """Default validator: allow if record balance >= 1."""
    try:
        return float((record or {}).get("balance", "0")) >= 1
    except Exception:
        return False


def approve(*, payload=None, charger_id=None, allowlist=None, denylist=None, validator=authorize_balance, **_):
    """Return True if the given RFID payload is approved.

    Parameters
    ----------
    payload : dict
        Incoming message payload from the charger.
    charger_id : str, optional
        Identifier of the charger.
    allowlist : str, optional
        Path to a CDV table with allowed RFID records.
    denylist : str, optional
        Path to a CDV table with denied RFID records.
    validator : callable, optional
        Function receiving ``record``, ``payload`` and ``charger_id`` to perform
        custom checks. Defaults to :func:`authorize_balance`.
    """
    rfid = payload.get("idTag") if isinstance(payload, dict) else None
    if not rfid:
        return False
    if denylist and gw.cdv.validate(denylist, rfid):
        gw.info(f"[OCPP] RFID {rfid!r} is present in denylist. Authorization denied.")
        return False

    record = None
    if allowlist:
        table = gw.cdv.load_all(allowlist)
        record = table.get(rfid)
        if record is None:
            return False

    if validator:
        try:
            return bool(validator(record=record, payload=payload, charger_id=charger_id))
        except Exception as e:
            gw.error(f"[OCPP] approval validator failed: {e}")
            gw.debug(traceback.format_exc())
            return False
    return True

