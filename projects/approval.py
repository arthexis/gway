# projects/approval.py

import os
import secrets
from datetime import datetime
from gway import gw

# CDV path for storing approval requests
approvals_path = ("work", "approvals.cdv")


def generate_key():
    """Generate a unique approval key."""
    return secrets.token_urlsafe(16)


def request(category, data: dict, role=None, send_email=True):
    """
    Store an approval request and optionally send an approval email.

    Params:
    - category: str, e.g., 'register', 'invite', etc.
    - data: dict, arbitrary metadata for the approval
    - role: optional str, used to infer email target if sending
    - send_email: bool, defaults to True

    Returns:
    - approval_key (str)
    """
    approval_key = generate_key()

    record = {
        "type": category,
        "data": data,
        "status": "pending",
        "created":  datetime.now().isoformat(),
    }

    gw.cdv.store(*approvals_path, approval_key, **record)

    if send_email and role:
        _send_approval_email(approval_key, category, data, role)

    return approval_key


def _send_approval_email(approval_key, category, data, role):
    """
    Internal: Send a basic approval/deny email for a role-based approval.
    You can customize per `category` later if needed.
    """
    email_key = f"{role.upper()}_EMAIL"
    to_email = os.environ.get(email_key) or os.environ.get("ADMIN_EMAIL")

    if not to_email:
        raise RuntimeError(f"Missing email for approval role: {role}")

    base_url = os.environ.get("BASE_URL", "").rstrip("/")
    endpoint = gw.web.app_url("register")  # can use a shared endpoint
    approve_link = f"{base_url}{endpoint}?response=approve:{approval_key}"
    deny_link = f"{base_url}{endpoint}?response=deny:{approval_key}"

    subject = f"{category.capitalize()} Approval Requested"

    body = f"""An approval request was submitted:

Type: {category}
Key: {approval_key}
Data: {data}

Approve:
{approve_link}

Deny:
{deny_link}
"""

    gw.mail.send(to=to_email, subject=subject, body=body)


def resolve(response: str):
    """
    Resolve a response string of the form 'approve:key' or 'deny:key'.
    Returns (status: 'approved' | 'denied' | 'error', details: str or dict).
    """
    if ":" not in response:
        return "error", "Invalid response format."

    action, key = response.split(":", 1)
    record = gw.cdv.find(*approvals_path, key, status="status=")

    if not record:
        return "error", "Invalid or expired approval key."

    if record.get("status") != "pending":
        return "error", f"Request already {record.get('status')}."

    if action == "approve":
        record["status"] = "approved"
    elif action == "deny":
        record["status"] = "denied"
    else:
        return "error", "Unknown approval action."

    record["resolved"] = datetime.now().isoformat()
    gw.cdv.store(*approvals_path, key, **record)

    return record["status"], record["data"]
