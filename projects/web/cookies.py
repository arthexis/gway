# file: projects/web/cookies.py

import re
import html
from bottle import request, response
from gway import gw

# --- Core Cookie Utilities ---

def set(name, value, path="/", expires=None, secure=None, httponly=True, samesite="Lax", **kwargs):
    """Set a cookie on the response. Only includes expires if set, to avoid Bottle crash."""
    if not check_consent() and name != "cookies_accepted":
        return
    if secure is None:
        secure = (getattr(request, "urlparts", None) and request.urlparts.scheme == "https")
    params = dict(
        path=path,
        secure=secure,
        httponly=httponly,
        samesite=samesite,
        **kwargs
    )
    if expires is not None:
        params['expires'] = expires
    response.set_cookie(name, value, **params)

def get(name: str, default=None):
    """Get a cookie value from the request. Returns None if blank or unset."""
    val = request.get_cookie(name, default)
    return None if (val is None or val == "") else val

def remove(name: str, path="/"):
    """
    Remove a cookie by blanking and setting expiry to epoch (deleted).
    """
    if not check_consent():
        return
    expires = "Thu, 01 Jan 1970 00:00:00 GMT"
    response.set_cookie(name, value="", path=path, expires=expires, secure=False)
    response.set_cookie(name, value="", path=path, expires=expires, secure=True)

def clear_all(path="/"):
    """
    Remove all cookies in the request, blanking and expiring each.
    """
    if not check_consent():
        return
    for cookie in list(request.cookies):
        remove(cookie, path=path)

def check_consent() -> bool:
    """
    Returns True if the user has accepted cookies (not blank, not None).
    """
    cookie_value = get("cookies_accepted")
    return cookie_value == "yes"

def list_all() -> dict:
    """
    Returns a dict of all cookies from the request, omitting blanked cookies.
    """
    if not check_consent():
        return {}
    return {k: v for k, v in request.cookies.items() if v not in (None, "")}

def append(name: str, label: str, value: str, sep: str = "|") -> list:
    """
    Append a (label=value) entry to the specified cookie, ensuring no duplicates (label-based).
    Useful for visited history, shopping cart items, etc.
    """
    if not check_consent():
        return []
    raw = get(name, "")
    items = raw.split(sep) if raw else []
    label_norm = label.lower()
    # Remove existing with same label
    items = [v for v in items if not (v.split("=", 1)[0].lower() == label_norm)]
    items.append(f"{label}={value}")
    cookie_value = sep.join(items)
    set(name, cookie_value)
    return items

# --- Views ---

def view_accept(*, next="/cookies/cookie-jar"):
    set("cookies_accepted", "yes")
    response.status = 303
    response.set_header("Location", next)
    return ""

def view_remove(*, next="/cookies/cookie-jar", confirm = False):
    # Only proceed if the confirmation checkbox was passed in the form
    if not confirm:
        response.status = 303
        response.set_header("Location", next)
        return ""
    if not check_consent():
        response.status = 303
        response.set_header("Location", next)
        return ""
    clear_all()
    response.status = 303
    response.set_header("Location", next)
    return ""

def view_cookie_jar(*, eat=None):
    cookies_ok = check_consent()
    # Handle eating a cookie (removal via ?eat=)
    if cookies_ok and eat:
        eat_key = str(eat)
        eat_key_norm = eat_key.strip().lower()
        if eat_key_norm not in ("cookies_accepted", "cookies_eaten") and eat_key in request.cookies:
            remove(eat_key)
            try:
                eaten_count = int(get("cookies_eaten") or "0")
            except Exception:
                eaten_count = 0
            set("cookies_eaten", str(eaten_count + 1))
            response.status = 303
            response.set_header("Location", "/cookies/cookie-jar")
            return ""

    def describe_cookie(key, value):
        key = html.escape(key or "")
        value = html.escape(value or "")
        protected = key in ("cookies_accepted", "cookies_eaten")
        x_link = ""
        if not protected:
            x_link = (
                f" <a href='/cookies/cookie-jar?eat={key}' "
                "style='color:#a00;text-decoration:none;font-weight:bold;font-size:1.1em;margin-left:0.5em;' "
                "title='Remove this cookie' onclick=\"return confirm('Remove cookie: {0}?');\">[X]</a>".format(key)
            )
        if not value:
            return f"<li><b>{key}</b>: (empty)</li>"
        if key == "visited":
            items = value.split("|")
            links = "".join(
                f"<li><a href='/{html.escape(route)}'>{html.escape(title)}</a></li>"
                for title_route in items if "=" in title_route
                for title, route in [title_route.split('=', 1)]
            )
            return f"<li><b>{key}</b>:{x_link}<ul>{links}</ul></li>"
        elif key == "css":
            return f"<li><b>{key}</b>: {value} (your selected style){x_link}</li>"
        elif key == "cookies_eaten":
            return f"<li><b>{key}</b>: {value} 🍪 (You have eaten <b>{value}</b> cookies)</li>"
        return f"<li><b>{key}</b>: {value}{x_link}</li>"

    if not cookies_ok:
        return """
        <h1>You are currently not holding any cookies from this website</h1>
        <p>Until you press the "Accept our cookies" button below, your actions
        on this site will not be recorded, but your interaction may also be limited.</p>
        <p>This restriction exists because some functionality (like navigation history,
        styling preferences, or shopping carts) depends on cookies.</p>
        <form method="POST" action="/cookies/accept" style="margin-top: 2em;">
            <button type="submit" style="font-size:1.2em; padding:0.5em 2em;">Accept our cookies</button>
        </form>
        """
    else:
        stored = []
        for key in sorted(request.cookies):
            val = get(key, "")
            stored.append(describe_cookie(key, val))

        cookies_html = "<ul>" + "".join(stored) + "</ul>" if stored else "<p>No stored cookies found.</p>"

        removal_form = """
            <form method="POST" action="/cookies/remove" style="margin-top:2em;">
                <div style="display: flex; align-items: center; margin-bottom: 1em; gap: 0.5em;">
                    <input type="checkbox" id="confirm" name="confirm" value="1" required
                        style="width:1.2em; height:1.2em; vertical-align:middle; margin:0;" />
                    <label for="confirm" style="margin:0; cursor:pointer; font-size:1em; line-height:1.2;">
                        I understand my cookie data cannot be recovered once deleted.
                    </label>
                </div>
                <button type="submit" style="color:white;background:#a00;padding:0.4em 2em;font-size:1em;border-radius:0.4em;border:none;">
                    Delete all my cookie data
                </button>
            </form>
        """

        return f"""
        <h1>Cookies are enabled for this site</h1>
        <p>Below is a list of the cookie-based information we are currently storing about you:</p>
        {cookies_html}
        <p>We never sell your data. We never share your data beyond the service providers used to host and deliver 
        this website, including database, CDN, and web infrastructure providers necessary to fulfill your requests.</p>
        <p>You can remove all stored cookie information at any time by using the form below.</p>
        {removal_form}
        <hr>
        <p>On the other hand, you can make your cookies available in other browsers and devices by configuring an identity.</p>
        <p><button><a href="/cookies/my-identity">Learn more about identities.</a></button></p>
        """

# --- Identities System ---

def _normalize_identity(identity: str) -> str:
    """
    Normalize identity string using slug rules: lowercase, alphanumeric and dashes, no spaces.
    """
    identity = identity.strip().lower()
    identity = re.sub(r"[\s_]+", "-", identity)
    identity = re.sub(r"[^a-z0-9\-]", "", identity)
    identity = re.sub(r"\-+", "-", identity)
    identity = identity.strip("-")
    return identity

def _identities_path():
    """Returns the path to the identities.cdv file in work/."""
    return gw.resource("work", "identities.cdv")

def _read_identities():
    """Reads identities.cdv as dict of identity -> cookies_dict. Returns {} if not present."""
    path = _identities_path()
    try:
        return gw.cdv.load_all(path)
    except Exception:
        return {}

def _write_identities(identity_map):
    """Writes the given identity_map back to identities.cdv using gw.cdv.save_all."""
    path = _identities_path()
    gw.cdv.save_all(path, identity_map)

def _get_current_cookies():
    """Return a dict of all current cookies (excluding blank/None)."""
    return {k: v for k, v in request.cookies.items() if v not in (None, "")}

def _restore_cookies(cookie_dict):
    """Set all cookies in the cookie_dict, skipping cookies_accepted to avoid accidental opt-in."""
    for k, v in cookie_dict.items():
        if k == "cookies_accepted":
            continue
        set(k, v)
        

def view_my_identity(*, claim=None, set_identity=None):
    """
    View and manage identity linking for cookies.
    - GET: Shows current identity and allows claim or update.
    - POST (claim/set_identity): Claim an identity and save/load cookies to/from identities.cdv.
    
    If user claims an existing identity AND already has an identity cookie, 
    ALL existing cookies (except cookies_accepted) are wiped before restoring the claimed identity.
    No wipe is performed when creating a new identity.
    """
    cookies_ok = check_consent()
    identity = get("identity", "")

    # Handle claiming or setting identity via POST
    if claim or set_identity:
        ident = (claim or set_identity or "").strip()
        norm = _normalize_identity(ident)
        if not norm:
            msg = "<b>Identity string is invalid.</b> Please use only letters, numbers, and dashes."
        else:
            identity_map = _read_identities()
            existing = identity_map.get(norm)
            if not existing:
                # New identity: Save all current cookies (except identity and cookies_accepted) to record
                current = _get_current_cookies()
                filtered = {k: v for k, v in current.items() if k not in ("identity", "cookies_accepted")}
                identity_map[norm] = filtered
                _write_identities(identity_map)
                set("identity", norm)
                msg = (
                    f"<b>Identity <code>{html.escape(norm)}</code> claimed and stored!</b> "
                    "Your cookie data has been saved under this identity. "
                    "You may now restore it from any device or browser by claiming this identity again."
                )
            else:
                # If user already has an identity, wipe all their cookies (except cookies_accepted) before restoring
                if identity:
                    for k in list(request.cookies):
                        if k not in ("cookies_accepted",):
                            remove(k)
                # Restore cookies from identity
                _restore_cookies(existing)
                set("identity", norm)
                # Merge new cookies into record (overwriting with current, but not blanking any missing)
                merged = existing.copy()
                for k, v in _get_current_cookies().items():
                    if k not in ("identity", "cookies_accepted"):
                        merged[k] = v
                identity_map[norm] = merged
                _write_identities(identity_map)
                msg = (
                    f"<b>Identity <code>{html.escape(norm)}</code> loaded!</b> "
                    "All cookies for this identity have been restored and merged with your current data. "
                    "Future changes to your cookies will update this identity."
                )
        # After processing, reload view with message
        return view_my_identity() + f"<div style='margin:1em 0; color:#080;'>{msg}</div>"

    # GET: Show info, form, and current identity
    identity_note = (
        f"<div style='margin:1em 0; color:#005;'><b>Current identity:</b> <code>{html.escape(identity)}</code></div>"
        if identity else
        "<div style='margin:1em 0; color:#888;'>You have not claimed an identity yet.</div>"
    )
    claim_form = """
    <form method="POST" style="margin-top:1em;">
        <label for="identity" style="font-size:1em;">
            Enter an identity string to claim (letters, numbers, dashes):</label>
        <input type="text" id="identity" name="set_identity" required pattern="[a-zA-Z0-9\\-]+"
               style="margin-left:0.5em; font-size:1.1em; width:12em; border-radius:0.3em; border:1px solid #aaa;"/>
        <button type="submit" style="margin-left:1em; font-size:1em;">Claim / Load</button>
    </form>
    """
    return f"""
    <h1>Cookie Identities</h1>
    <p>
        Identities allow you to copy your cookie data (such as preferences, navigation history, shopping cart, etc)
        from one device or browser to another, without needing to register an account.
        Claiming an identity will save a copy of your current cookie data under the identity string you provide.<br>
        <b>Warning:</b> Anyone who knows this identity string can restore your cookie data, so choose carefully.
    </p>
    {identity_note}
    {claim_form}
    <p style='margin-top:2em; color:#555; font-size:0.98em;'>
        To transfer cookies:<br>
        1. On your main device, claim an identity (e.g. "my-handle-123").<br>
        2. On another device/browser, visit this page and claim the same identity to restore your data.<br>
        3. Any changes you make while holding an identity will update the stored copy.
    </p>
    """


def update_identity_on_cookie_change():
    """
    Called when any cookie is set or removed, to update the identity record (if any) in identities.cdv.
    """
    identity = get("identity")
    if identity:
        norm = _normalize_identity(identity)
        if not norm:
            return
        identity_map = _read_identities()
        current = {k: v for k, v in _get_current_cookies().items() if k not in ("identity", "cookies_accepted")}
        identity_map[norm] = current
        _write_identities(identity_map)

# --- Patch set() and remove() to trigger update_identity_on_cookie_change ---

_orig_set = set
def set(name, value, *args, **kwargs):
    _orig_set(name, value, *args, **kwargs)
    update_identity_on_cookie_change()

_orig_remove = remove
def remove(name, *args, **kwargs):
    _orig_remove(name, *args, **kwargs)
    update_identity_on_cookie_change()
