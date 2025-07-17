# file: projects/ocpp/rfid.py
"""Authorization helpers for OCPP RFID transactions."""

import traceback
from gway import gw


# TODO: This validatior should continue to exist, but now it should manually find the 
#       customer's ID by finding the RFID in the provided payload and looking it up 
#       (reloading the file each time) from a CDV (see projects/cdb.py) stored in 
#       work/ocpp/rfids.cdv and storing two extra keys: balance (float) and allowed (default True)
#       See the params ocpp.csms.setup_app sends to this function to fix the signature.

def authorize_balance(record=None, **_):
    """Default validator: allow if record balance >= 1."""
    try:
        return float((record or {}).get("balance", "0")) >= 1
    except Exception:
        return False
    
# TODO: Create another authorizer that just checks that allowed is True and not the balance (authorize_allowed)
#       If possible create some common functions so we can add more authorizers on the same file later
    
# TODO: Create functions to manually create RFID entries, delete them, update them, enable, disable, credit and debit

# TODO: Remove the allowlist and denylist parameters from approve and everywhere else. 

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

