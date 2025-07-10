# file: projects/web/cookies.py

import re
import html
from bottle import request, response
from gway import gw

# --- Core Cookie Utilities ---

def set(name, value, path="/", expires=None, secure=None, httponly=True, samesite="Lax", **kwargs):
    """Set a cookie on the response. Only includes expires if set."""
    if not accepted() and name != "cookies_accepted":
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
    if not accepted():
        return
    expires = "Thu, 01 Jan 1970 00:00:00 GMT"
    response.set_cookie(name, value="", path=path, expires=expires, secure=False)
    response.set_cookie(name, value="", path=path, expires=expires, secure=True)

def clear_all(path="/"):
    """
    Remove all cookies in the request, blanking and expiring each.
    """
    if not accepted():
        return
    for cookie in list(request.cookies):
        remove(cookie, path=path)

def accepted() -> bool:
    """
    Returns True if the user has accepted cookies (not blank, not None).
    """
    cookie_value = get("cookies_accepted")
    return cookie_value == "yes"

def list_all() -> dict:
    """
    Returns a dict of all cookies from the request, omitting blanked cookies.
    """
    if not accepted():
        return {}
    return {k: v for k, v in request.cookies.items() if v not in (None, "")}

def append(name: str, label: str, value: str, sep: str = "|") -> list:
    """
    Append a (label=value) entry to the specified cookie, ensuring no duplicates (label-based).
    Useful for visited history, shopping cart items, etc.
    """
    if not accepted():
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
    if not accepted():
        response.status = 303
        response.set_header("Location", next)
        return ""
    clear_all()
    response.status = 303
    response.set_header("Location", next)
    return ""

def view_cookie_jar(*, eat=None):
    cookies_ok = accepted()
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
        """

