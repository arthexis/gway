# file: projects/web/auth.py

from gway import gw
import base64

class Challenge:
    """
    Represents a single auth challenge, which may be required or optional.
    """
    def __init__(self, fn, *, required=True, name=None):
        self.fn = fn
        self.required = required
        self.name = name or fn.__name__

    def check(self, strict=False):
        """
        Evaluate the challenge.
        - If required or strict, a failure blocks authorization.
        - If optional and not strict, only logs result.
        """
        result = self.fn(strict=strict)
        if self.required or strict:
            return result
        # Optional: always return True for is_authorized (unless strict), but log
        if not result:
            gw.info(f"[auth] Optional challenge '{self.name}' failed (user not blocked).")
        return True

# All registered challenges (as Challenge instances)
_challenges = []

def is_authorized(*, strict=False):
    """
    Runs all configured auth challenges in order.
    Returns True only if all required (or all, if strict=True) challenges succeed.
    - If strict=True: ALL challenges (required/optional) must succeed.
    - If strict=False: only required challenges must succeed; optional failures logged.
    """
    if not _challenges:
        return True  # No challenge configured: allow all
    for challenge in _challenges:
        if not challenge.check(strict=strict):
            return False
    return True

def _parse_basic_auth_header(header):
    """
    Parse HTTP Basic Auth header and return (username, password) tuple or (None, None).
    """
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

def _basic_auth_challenge(allow, engine):
    """
    Returns a function that checks HTTP Basic Auth for the configured engine.
    The function accepts strict as a kwarg, controlling whether to block/401 on failure.
    """
    def challenge(*, strict=False):
        try:
            if engine == "auto":
                # Detect active web framework
                engine_actual = "bottle"
                if hasattr(gw.web, "app") and hasattr(gw.web.app, "is_enabled"):
                    if gw.web.app.is_enabled("fastapi"):
                        engine_actual = "fastapi"
                else:
                    engine_actual = "bottle"
            else:
                engine_actual = engine

            # -- Bottle mode --
            if engine_actual == "bottle":
                from bottle import request, response
                auth_header = request.get_header("Authorization")
                username, password = _parse_basic_auth_header(auth_header)
                if not username:
                    if strict:
                        response.status = 401
                        response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
                    return False

                users = gw.cdv.load_all(allow)
                user_entry = users.get(username)
                if not user_entry:
                    if strict:
                        response.status = 401
                        response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
                    return False
                stored_b64 = user_entry.get("b64")
                if not stored_b64:
                    if strict:
                        response.status = 401
                        response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
                    return False
                try:
                    stored_pass = base64.b64decode(stored_b64).decode("utf-8")
                except Exception as e:
                    gw.error(f"[auth] Failed to decode b64 password for user '{username}': {e}")
                    if strict:
                        response.status = 401
                        response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
                    return False
                if password != stored_pass:
                    if strict:
                        response.status = 401
                        response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
                    return False
                return True

            # -- FastAPI mode (placeholder, to be implemented) --
            elif engine_actual == "fastapi":
                gw.warn("[auth] FastAPI basic auth is not yet implemented")
                return True

            else:
                gw.error(f"[auth] Unknown engine: {engine_actual}")
                return False
        except Exception as e:
            gw.error(f"[auth] Exception: {e}")
            return False

    return challenge

def config_basic(*, allow='work/basic_auth.cdv', engine="auto", optional=False):
    """
    Register a basic authentication challenge using username/password pairs from a CDV.
    Username is the key, password is the value under 'b64' (base64-encoded).
    - If optional=True, failure does not block unless strict=True.
    """
    required = not optional
    challenge_fn = _basic_auth_challenge(allow, engine)
    _challenges.append(Challenge(challenge_fn, required=required, name="basic_auth"))
    typ = "REQUIRED" if required else "OPTIONAL"
    gw.info(f"[auth] Registered {typ} basic auth challenge: allow='{allow}' engine='{engine}'")

def clear():
    """
    Clear all registered auth challenges (for testing or reset).
    """
    _challenges.clear()

def is_enabled():
    """
    Returns True if any auth challenge is registered.
    """
    return bool(_challenges)

def create_user(username, password, *, allow='work/basic_auth.cdv', overwrite=False, **fields):
    """
    Create (or update if overwrite=True) a user in the CDV file for basic auth.
    Stores password as b64 field (base64 encoded).
    You can pass extra fields as kwargs.
    """
    if not username or not password:
        raise ValueError("Both username and password are required")
    # Check existence if not overwriting
    if not overwrite:
        users = gw.cdv.load_all(allow)
        if username in users:
            raise ValueError(f"User '{username}' already exists in '{allow}' (set overwrite=True to update)")
    pw_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    user_fields = {"b64": pw_b64}
    user_fields.update(fields)
    gw.cdv.update(allow, username, **user_fields)
    gw.info(f"[auth] Created/updated user '{username}' in '{allow}'")
