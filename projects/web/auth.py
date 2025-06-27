# file: projects/web/auth.py

from gway import gw
import base64
import random
import string
import time

class Challenge:
    """
    Represents a single auth challenge, which may be required or optional.
    Supports HTTP and WebSocket (Bottle/FastAPI) flows.
    """
    def __init__(self, fn, *, required=True, name=None):
        self.fn = fn
        self.required = required
        self.name = name or fn.__name__

    def check(self, *, strict=False, context=None):
        """
        If required or strict, block on failure.
        If not required and not strict, log failure but don't block.
        Also: set 401 if blocking (required or strict), and engine is bottle.
        Passes 'context' for additional WebSocket/FastAPI state.
        """
        result, info = self.fn(context=context)
        if result:
            return True
        if not self.required and not strict:
            gw.info(f"[auth] Optional challenge '{self.name}' failed (user not blocked).")
            return True
        # Set 401 if running under bottle
        if info.get("engine") == "bottle":
            try:
                response = info["response"]
                response.status = 401
                response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
            except Exception:
                gw.debug("[auth] Could not set 401/WWW-Authenticate header.")
        # For FastAPI HTTP: set status_code on response (if possible)
        if info.get("engine") == "fastapi" and info.get("response") is not None:
            try:
                info["response"].status_code = 401
                info["response"].headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
            except Exception:
                gw.debug("[auth] Could not set 401/WWW-Authenticate for FastAPI.")
        # For WebSocket, raise error or return False, user must handle in their route
        return False

_challenges = []

def is_authorized(*, strict=False, context=None):
    if not _challenges:
        return True
    for challenge in _challenges:
        if not challenge.check(strict=strict, context=context):
            return False
    return True

def _parse_basic_auth_header(header):
    if not header or not header.startswith("Basic "):
        return None, None
    try:
        auth_b64 = header.split(" ", 1)[1]
        auth_bytes = base64.b64decode(auth_b64)
        user_pass = auth_bytes.decode("utf-8")
        username, password = user_pass.split(":", 1)
        return username, password
    except Exception as e:
        gw.debug(f"[auth] Failed to parse basic auth header: {e}")
        return None, None

def _basic_auth(allow, engine):
    """
    Returns a function that checks HTTP Basic Auth for the configured engine.
    Returns (result:bool, context:dict)
    Accepts an explicit 'context' argument for WebSocket/FastAPI use.
    """
    def challenge(context=None):
        ctx = {} if context is None else dict(context)
        try:
            # Determine engine if not fixed
            if engine == "auto":
                engine_actual = "bottle"
                # Try to detect FastAPI context
                if ctx.get("websocket", None):
                    engine_actual = "fastapi_ws"
                elif hasattr(gw.web, "app") and hasattr(gw.web.app, "is_setup"):
                    if gw.web.app.is_setup("fastapi"):
                        engine_actual = "fastapi"
                else:
                    engine_actual = "bottle"
            else:
                engine_actual = engine
            ctx["engine"] = engine_actual

            if engine_actual == "bottle":
                from bottle import request, response
                ctx["response"] = response
                auth_header = request.get_header("Authorization")
                username, password = _parse_basic_auth_header(auth_header)
            elif engine_actual == "fastapi":
                # Context should include 'request' and 'response'
                req = ctx.get("request")
                resp = ctx.get("response")
                ctx["response"] = resp
                auth_header = req.headers.get("authorization") if req else None
                username, password = _parse_basic_auth_header(auth_header)
            elif engine_actual == "fastapi_ws":
                # Context should include 'websocket'
                ws = ctx.get("websocket")
                # FastAPI WebSocket headers: use 'authorization'
                auth_header = None
                if ws:
                    # For Starlette/FastAPI, headers are lowercase keys
                    headers = getattr(ws, "headers", None)
                    if headers:
                        auth_header = headers.get("authorization")
                        # Accept fallback with capitalization
                        if not auth_header:
                            auth_header = headers.get("Authorization")
                username, password = _parse_basic_auth_header(auth_header)
            else:
                gw.error(f"[auth] Unknown engine: {engine_actual}")
                return False, ctx

            if not username:
                return False, ctx

            users = gw.cdv.load_all(allow)
            user_entry = users.get(username)
            if not user_entry:
                return False, ctx

            expiration = user_entry.get("expiration")
            if expiration:
                try:
                    if time.time() > float(expiration):
                        gw.info(f"[auth] Temp user '{username}' expired.")
                        return False, ctx
                except Exception as e:
                    gw.warn(f"[auth] Could not parse expiration for '{username}': {e}")

            stored_b64 = user_entry.get("b64")
            if not stored_b64:
                return False, ctx
            try:
                stored_pass = base64.b64decode(stored_b64).decode("utf-8")
            except Exception as e:
                gw.error(f"[auth] Failed to decode b64 password for user '{username}': {e}")
                return False, ctx
            if password != stored_pass:
                return False, ctx
            return True, ctx

        except Exception as e:
            gw.error(f"[auth] Exception: {e}")
            return False, ctx

    return challenge

def check_websocket_auth(websocket, allow="work/basic_auth.cdv"):
    """
    Explicit utility for FastAPI WebSocket routes.
    Usage: call at start of websocket handler, pass 'websocket'.
    Returns True if authorized, otherwise False (should close connection).
    """
    challenge = _basic_auth(allow, "fastapi_ws")
    return challenge(context={"websocket": websocket})[0]

def _temp_username(length=8):
    consonants = 'bcdfghjkmnpqrstvwxyz'
    digits = '23456789'
    return ''.join(random.choices(consonants + digits, k=length))

def _temp_password(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def config_basic(
    *, 
    allow='work/basic_auth.cdv', 
    engine="auto", 
    optional=False,
    temp_link=False, 
    expiration=3600,   # 1 hour default
):
    if temp_link:
        username = _temp_username()
        password = _temp_password()
        expiration = str(time.time() + expiration)
        pw_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
        gw.cdv.update(allow, username, b64=pw_b64, expiration=expiration)

        demo_path = "ocpp/csms/charger-status"
        resource_url = gw.build_url(demo_path)
        from urllib.parse import urlparse
        p = urlparse(resource_url)
        basic_url = f"{p.scheme}://{username}:{password}@{p.hostname}"
        if p.port:
            basic_url += f":{p.port}"
        basic_url += f"{p.path}"

        gw.info(f"[auth] Temp user generated: {username} exp:{expiration}")
        gw.info(f"[auth] Temp login URL: {resource_url}")

        print("\n==== GWAY TEMPORARY LOGIN LINK ====")
        print(f"    {resource_url}")
        print(f"    username: {username}")
        print(f"    password: {password}")
        print(f"    valid until: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(expiration)))}")
        print(f"\n    (HTTP Basic Auth URL for advanced users: {basic_url})")
        print("====================================\n")

    required = not optional
    challenge_fn = _basic_auth(allow, engine)
    _challenges.append(Challenge(challenge_fn, required=required, name="basic_auth"))
    typ = "REQUIRED" if required else "OPTIONAL"
    gw.info(f"[auth] Registered {typ} basic auth challenge: allow='{allow}' engine='{engine}'")
    if temp_link:
        return {
            "username": username,
            "password": password,
            "expiration": expiration,
            "url": resource_url,
            "basic_url": basic_url,
        }

def clear():
    _challenges.clear()

def is_setup():
    return bool(_challenges)

def create_user(username, password, *, allow='work/basic_auth.cdv', force=False, **fields):
    if not username or not password:
        raise ValueError("Both username and password are required")
    if not force:
        users = gw.cdv.load_all(allow)
        if username in users:
            raise ValueError(f"User '{username}' already exists in '{allow}' (set force=True to update)")
    pw_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    user_fields = {"b64": pw_b64}
    user_fields.update(fields)
    gw.cdv.update(allow, username, **user_fields)
    gw.info(f"[auth] Created/updated user '{username}' in '{allow}'")
