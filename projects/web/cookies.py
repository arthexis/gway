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
        <p>On the other hand, you can make your cookies available in other browsers and devices by configuring a mask.</p>
        <p><a href="/cookies/my-mask">Learn more about masks.</a></p>
        """

# --- Mask System ---

def _normalize_mask(mask: str) -> str:
    """
    Normalize mask string using slug rules: lowercase, alphanumeric and dashes, no spaces.
    """
    mask = mask.strip().lower()
    mask = re.sub(r"[\s_]+", "-", mask)
    mask = re.sub(r"[^a-z0-9\-]", "", mask)
    mask = re.sub(r"\-+", "-", mask)
    mask = mask.strip("-")
    return mask

def _masks_path():
    """Returns the path to the masks.cdv file in work/."""
    return gw.resource("work", "masks.cdv")

def _read_masks():
    """Reads masks.cdv as dict of mask -> cookies_dict. Returns {} if not present."""
    path = _masks_path()
    try:
        return gw.cdv.load_all(path)
    except Exception:
        return {}

def _write_masks(mask_map):
    """Writes the given mask_map back to masks.cdv using gw.cdv.save_all."""
    path = _masks_path()
    gw.cdv.save_all(path, mask_map)

def _get_current_cookies():
    """Return a dict of all current cookies (excluding blank/None)."""
    return {k: v for k, v in request.cookies.items() if v not in (None, "")}

def _restore_cookies(cookie_dict):
    """Set all cookies in the cookie_dict, skipping cookies_accepted to avoid accidental opt-in."""
    for k, v in cookie_dict.items():
        if k == "cookies_accepted":
            continue
        set(k, v)
        

def view_my_mask(*, claim=None, set_mask=None):
    """
    View and manage mask linking for cookies.
    - GET: Shows current mask and allows claim or update.
    - POST (claim/set_mask): Claim a mask and save/load cookies to/from masks.cdv.
    
    If user claims an existing mask AND already has a mask cookie, 
    ALL existing cookies (except cookies_accepted) are wiped before restoring the claimed mask.
    No wipe is performed when creating a new mask.
    """
    cookies_ok = check_consent()
    mask = get("mask", "")

    # Handle claiming or setting mask via POST
    if claim or set_mask:
        ident = (claim or set_mask or "").strip()
        norm = _normalize_mask(ident)
        if not norm:
            msg = "<b>mask string is invalid.</b> Please use only letters, numbers, and dashes."
        else:
            mask_map = _read_masks()
            existing = mask_map.get(norm)
            if not existing:
                # New mask: Save all current cookies (except mask and cookies_accepted) to record
                current = _get_current_cookies()
                filtered = {k: v for k, v in current.items() if k not in ("mask", "cookies_accepted")}
                mask_map[norm] = filtered
                _write_masks(mask_map)
                set("mask", norm)
                msg = (
                    f"<b>mask <code>{html.escape(norm)}</code> claimed and stored!</b> "
                    "Your cookie data has been saved under this mask. "
                    "You may now restore it from any device or browser by claiming this mask again."
                )
            else:
                # If user already has a mask, wipe all their cookies (except cookies_accepted) before restoring
                if mask:
                    for k in list(request.cookies):
                        if k not in ("cookies_accepted",):
                            remove(k)
                # Restore cookies from mask
                _restore_cookies(existing)
                set("mask", norm)
                # Merge new cookies into record (overwriting with current, but not blanking any missing)
                merged = existing.copy()
                for k, v in _get_current_cookies().items():
                    if k not in ("mask", "cookies_accepted"):
                        merged[k] = v
                mask_map[norm] = merged
                _write_masks(mask_map)
                msg = (
                    f"<b>mask <code>{html.escape(norm)}</code> loaded!</b> "
                    "All cookies for this mask have been restored and merged with your current data. "
                    "Future changes to your cookies will update this mask."
                )
        # After processing, reload view with message
        return view_my_mask() + f"<div style='margin:1em 0; color:#080;'>{msg}</div>"

    # GET: Show info, form, and current mask
    mask_note = (
        f"<div style='margin:1em 0; color:#005;'><b>Current mask:</b> <code>{html.escape(mask)}</code></div>"
        if mask else
        "<div style='margin:1em 0; color:#888;'>You have not claimed a mask yet.</div>"
    )
    claim_form = """
    <form method="POST" style="margin-top:1em;">
        <label for="mask" style="font-size:1em;">
            Enter a mask string to claim (letters, numbers, dashes):</label>
        <input type="text" id="mask" name="set_mask" required pattern="[a-zA-Z0-9\\-]+"
               style="margin-left:0.5em; font-size:1.1em; width:12em; border-radius:0.3em; border:1px solid #aaa;"/>
        <button type="submit" style="margin-left:1em; font-size:1em;">Claim / Load</button>
    </form>
    """
    return f"""
    <h1>Cookie Masks</h1>
    <p>
        <strong>Masks</strong> allow you to copy your cookie data (such as preferences, navigation history, cart, etc)
        from one device or browser to another, without needing to register an account.
        Claiming a mask will save a copy of your current cookie data under the mask string you provide.<br>
        <b>Warning:</b> Anyone who knows this mask string can restore your cookie data, so choose carefully.
    </p>
    {mask_note}
    {claim_form}
    <p style='margin-top:2em; color:#555; font-size:0.98em;'>
        To transfer your Cookies as a Mask:<br>
        1. On your main device, claim mask (e.g. "my-handle-123").<br>
        2. On another device/browser, visit this page and claim the same mask to restore your data.<br>
        3. Any changes you make while holding a mask will update the stored copy.
    </p>
    """


def update_mask_on_cookie_change():
    """
    Called when any cookie is set or removed, to update the mask record (if any) in masks.cdv.
    """
    mask = get("mask")
    if mask:
        norm = _normalize_mask(mask)
        if not norm:
            return
        mask_map = _read_masks()
        current = {k: v for k, v in _get_current_cookies().items() if k not in ("mask", "cookies_accepted")}
        mask_map[norm] = current
        _write_masks(mask_map)

# --- Patch set() and remove() to trigger update_mask_on_cookie_change ---

_orig_set = set
def set(name, value, *args, **kwargs):
    _orig_set(name, value, *args, **kwargs)
    update_mask_on_cookie_change()

_orig_remove = remove
def remove(name, *args, **kwargs):
    _orig_remove(name, *args, **kwargs)
    update_mask_on_cookie_change()
