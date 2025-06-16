# projects/web/cookie.py

import html
from bottle import request, response
from gway import gw

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

def view_accept(next="/cookie/jar"):
    # Only this is allowed to set cookies if not already enabled!
    set("cookies_accepted", "yes")
    response.status = 303
    response.set_header("Location", next)
    return ""

def view_remove(next="/cookie/jar"):
    if not check_consent():
        response.status = 303
        response.set_header("Location", next)
        return ""
    clear_all()
    response.status = 303
    response.set_header("Location", next)
    return ""

def view_jar():
    cookies_ok = check_consent()

    def describe_cookie(key, value):
        key = html.escape(key or "")
        value = html.escape(value or "")
        if not value:
            return f"<li><b>{key}</b>: (empty)</li>"

        if key == "visited":
            items = value.split("|")
            links = "".join(
                f"<li><a href='/{html.escape(route)}'>{html.escape(title)}</a></li>"
                for title_route in items if "=" in title_route
                for title, route in [title_route.split("=", 1)]
            )
            return f"<li><b>{key}</b>:<ul>{links}</ul></li>"

        elif key == "css":
            return f"<li><b>{key}</b>: {value} (your selected style)</li>"

        return f"<li><b>{key}</b>: {value}</li>"

    if not cookies_ok:
        return """
        <h1>All our cookies have been removed</h1>
        <p>Until you press the "Accept our cookies" button above again, your actions
        on this site will not be recorded, but your interaction may also be limited.</p>
        <p>This restriction exists because some functionality (like navigation history,
        styling preferences, or shopping carts) depends on cookies.</p>
        <p><a href="javascript:history.back()">← Go back</a></p>
        """
    else:
        stored = []
        for key in sorted(request.cookies):
            val = get(key, "")
            stored.append(describe_cookie(key, val))

        cookies_html = "<ul>" + "".join(stored) + "</ul>" if stored else "<p>No stored cookies found.</p>"

        return f"""
        <h1>Cookies are enabled for this site</h1>
        <p>Below is a list of the cookie-based information we are currently storing about you:</p>
        {cookies_html}
        <p>We do not sell or share your cookie data beyond the service providers used to host and
        deliver this website. These include database, CDN, and web infrastructure providers necessary
        to fulfill your requests.</p>
        <p>You can remove all stored cookie information at any time by pressing the 
        "Remove our cookies" button in the navbar.</p>
        <p><a href="javascript:history.back()">← Go back</a></p>
        """
