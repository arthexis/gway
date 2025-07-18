# file: projects/ocpp/rfid.py
"""Authorization helpers for OCPP RFID transactions."""

import traceback
from gway import gw

RFID_TABLE = "work/ocpp/rfids.cdv"


def _record_from_payload(payload, table_path=RFID_TABLE):
    """Return the CDV record for ``payload['idTag']`` if present."""
    rfid = payload.get("idTag") if isinstance(payload, dict) else None
    if not rfid:
        return None
    try:
        table = gw.cdv.load_all(table_path)
    except Exception:
        return None
    return table.get(rfid)


# TODO: This validatior should continue to exist, but now it should manually find the
#       customer's ID by finding the RFID in the provided payload and looking it up
#       (reloading the file each time) from a CDV (see projects/cdb.py) stored in
#       work/ocpp/rfids.cdv and storing two extra keys: balance (float) and allowed (default True)
#       See the params ocpp.csms.setup_app sends to this function to fix the signature.

def authorize_balance(*, record=None, payload=None, charger_id=None, action=None, table=RFID_TABLE, **_):
    """Default validator: allow if record balance >= 1 and allowed."""
    if record is None:
        record = _record_from_payload(payload or {}, table)
    if not record:
        return False
    try:
        allowed = str(record.get("allowed", "true")).lower() not in {"false", "0", "no", "off", ""}
        bal_ok = float(record.get("balance", "0")) >= 1
        return allowed and bal_ok
    except Exception:
        return False
    
# TODO: Create another authorizer that just checks that allowed is True and not the balance (authorize_allowed)
#       If possible create some common functions so we can add more authorizers on the same file later

def authorize_allowed(*, payload=None, charger_id=None, action=None, table=RFID_TABLE, **_):
    """Authorize only if ``allowed`` flag is truthy for the RFID."""
    record = _record_from_payload(payload or {}, table)
    if not record:
        return False
    return str(record.get("allowed", "true")).lower() not in {"false", "0", "no", "off", ""}
    
# TODO: Create functions to manually create RFID entries, delete them, update them, enable, disable, credit and debit

def create_entry(rfid, *, balance=0.0, allowed=True, table=RFID_TABLE, **fields):
    """Create or replace an RFID record."""
    fields.setdefault("balance", str(balance))
    fields.setdefault("allowed", "True" if allowed else "False")
    gw.cdv.update(table, rfid, **fields)


def update_entry(rfid, *, table=RFID_TABLE, **fields):
    """Update fields for an RFID record."""
    gw.cdv.update(table, rfid, **fields)


def delete_entry(rfid, *, table=RFID_TABLE):
    """Remove an RFID record from the table."""
    return gw.cdv.delete(table, rfid)


def enable(rfid, *, table=RFID_TABLE):
    """Mark an RFID as allowed."""
    gw.cdv.update(table, rfid, allowed="True")


def disable(rfid, *, table=RFID_TABLE):
    """Mark an RFID as not allowed."""
    gw.cdv.update(table, rfid, allowed="False")


def credit(rfid, amount=1, *, table=RFID_TABLE):
    """Add ``amount`` to the RFID balance."""
    return gw.cdv.credit(table, rfid, amount=amount, field="balance")


def debit(rfid, amount=1, *, table=RFID_TABLE):
    """Subtract ``amount`` from the RFID balance."""
    return gw.cdv.debit(table, rfid, amount=amount, field="balance")

# TODO: Remove the allowlist and denylist parameters from approve and everywhere else.

def approve(*, payload=None, charger_id=None, validator=authorize_balance, table=RFID_TABLE, **_):
    """Return True if the given RFID payload is approved.

    Parameters
    ----------
    payload : dict
        Incoming message payload from the charger.
    charger_id : str, optional
        Identifier of the charger.
    validator : callable, optional
        Function receiving ``payload``, ``charger_id`` and the loaded ``record``
        to perform custom checks. Defaults to :func:`authorize_balance`.
    """
    rfid = payload.get("idTag") if isinstance(payload, dict) else None
    if not rfid:
        return False

    record = _record_from_payload(payload, table)
    if not record:
        return False

    if validator:
        try:
            return bool(
                validator(
                    payload=payload,
                    charger_id=charger_id,
                    action=None,
                    table=table,
                    record=record,
                )
            )
        except Exception as e:
            gw.error(f"[OCPP] approval validator failed: {e}")
            gw.debug(traceback.format_exc())
            return False
    return True

