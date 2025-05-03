import os
import logging
import time
import hashlib

from urllib.parse import quote, unquote
from functools import wraps
from gway import requires, Gateway

logger = logging.getLogger(__name__)
gway = Gateway()

_css_cache = {}


@requires("bottle", "docutils")
def setup_app(*, app=None):
    """Configure a simple application that showcases the use of GWAY to generate websites."""
    from bottle import Bottle, static_file, request, response, template

    if app is None: app = Bottle()

    def security_middleware(app):
        """Middleware to fix headers and secure cookies."""
        def wrapped_app(environ, start_response):
            def custom_start_response(status, headers, exc_info=None):
                # Remove default 'Server' header
                headers = [(k, v) for k, v in headers if k.lower() != 'server']
                # Add fixed headers
                headers += [
                    ("Cache-Control", "no-cache, no-store, must-revalidate"),
                    ("X-Content-Type-Options", "nosniff"),
                    ("Server", "GWAY")  # Optional: replace with your server name
                ]
                return start_response(status, headers, exc_info)

            return app(environ, custom_start_response)

        # Patch Bottle's response.set_cookie to enforce secure, httponly
        original_set_cookie = response.set_cookie

        @wraps(original_set_cookie)
        def secure_set_cookie(name, value, **kwargs):
            kwargs.setdefault("secure", True)
            kwargs.setdefault("httponly", True)
            kwargs.setdefault("samesite", "Lax")
            kwargs.setdefault("path", "/")
            return original_set_cookie(name, value, **kwargs)

        response.set_cookie = secure_set_cookie

        return wrapped_app


    def cookies_enabled():
        return request.get_cookie("cookies_accepted") == "yes"
    
    def update_visited(current):
        if not cookies_enabled():
            return []
        
        raw = request.get_cookie("visited", "")
        visited = [unquote(v) for v in raw.split(",") if v]

        if current not in visited:
            visited.append(current)

        # Store as comma-separated quoted values
        cookie_value = ",".join(quote(v) for v in visited)
        response.set_cookie("visited", cookie_value)

        return visited
    
    def build_navbar(visited):
        if not cookies_enabled():
            visited = []
        links = "".join(
            f'<li><a href="/?c={b}">{b.title()}</a></li>' for b in sorted(visited) if b
        )
        search_box = '''
            <form action="/" method="get" style="margin-bottom: 1em;">
                <input type="hidden" name="c" value="help" />
                <input 
                    type="text" 
                    name="path" 
                    placeholder="Search GWAY" 
                    style="width: 100%; padding: 0.5em; border-radius: 8px; border: 1px solid #ccc;" 
                />
            </form>
        '''
        return f"<aside>{search_box}<ul>{links}</ul></aside>"

    def load_css(path):
        """Load and cache CSS from the given path."""
        if path in _css_cache:
            return _css_cache[path]
        
        if not os.path.exists(path):
            return "/* CSS file not found */"
        
        with open(path, "r", encoding="utf-8") as f:
            css = f.read()
            _css_cache[path] = css
            return css

    def make_template(*, title="GWAY", navbar="", content="", css_path="data/static/default.css"):
        css = load_css(css_path)
        version = gway.version()
        return template("""<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8" />
                <title>{{!title}}</title>
                <style>{{!css}}</style>
                <link rel="icon" href="/static/favicon.ico" type="image/x-icon" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
                {{!navbar}}
                <main>{{!content}}</main>
                <hr><footer>This website was built, tested and released with GWAY v{{!version}}. 
                        GWAY is powered by <a href="https://www.python.org/">Python</a>. 
                        Hosting by <a href="https://www.gelectriic.org/">Gelectriic Solutions</a>.</footer>
            </body>
            </html>
        """, **locals())

    @app.route("/accept-cookies", method="POST")
    def accept_cookies():
        response.set_cookie("cookies_accepted", "yes")
        redirect_url = request.forms.get("next", "/")
        response.status = 303
        response.set_header("Location", redirect_url)
        return ""
    
    @app.route("/")
    def index():
        c = request.query.get("c", "readme").replace("-", "_")
        kwargs = {k: v for k, v in request.query.items() if k != "c"}

        builder = getattr(gway.website, f"build_{c}", None)

        visited = []
        if not builder:
            content = f"<p>No content found for '<code>{c}</code>'</p>"
        else:
            try:
                content = builder(**kwargs)
                visited = update_visited(c)
            except Exception as e:
                content = f"<p>Error in content builder '<code>{c}</code>': {e}</p>"

        navbar = build_navbar(visited)

        if not cookies_enabled():
            consent_box = f"""
                <div class="consent-box">
                    <form action="/accept-cookies" method="post">
                        <input type="hidden" name="next" value="/?c={c}" />
                        This app uses cookies to improve your experience. 
                        <button type="submit">Accept</button>
                    </form>
                </div>
            """
            content = consent_box + content

        return make_template(navbar=navbar, content=content)

    @app.route("/static/<filename:path>")
    def send_static(filename):
        return static_file(filename, root=gway.resource("data", "static"))
    
    @app.route("/temp/<filename:path>")
    def send_temp(filename):
        return static_file(filename, root=gway.resource("temp", "shared"))

    app = security_middleware(app)
    return app


@requires("bottle", "requests")
def setup_proxy(*, endpoint : str, app=None, websockets=False):
    """
    Create a proxy handler to the given Bottle app.
    When using this proxy, attach/create this proxy first then attach the rest of your routes.
    Otherwise, the proxy will catch all requests and block other routes.
    """
    from bottle import request, Bottle
    import requests

    # TODO: Implement websocket forwarding if websockets=True
    # This should be transparent to websocket applications, including authentication

    if app is None: app = Bottle()

    @app.route("/<path:path>", method=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    def proxy_handler(path):
        target_url = f"{endpoint.rstrip('/')}/{path}"
        headers = {key: value for key, value in request.headers.items()}
        method = request.method
        try:
            resp = requests.request(method, target_url, headers=headers, data=request.body.read(), stream=True)
            return resp.content, resp.status_code, resp.headers.items()
        except Exception as e:
            logger.error("Proxy request failed: %s", e)
            return f"Proxy error: {e}", 502


@requires("bottle")
def start_server(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=False  # this is the trigger
):
    """Start an HTTP server to host the given application, or the default website if None."""
    from bottle import run

    def run_server():
        actual_app = app or setup_app()
        if proxy:
            actual_app = setup_proxy(endpoint=proxy, app=actual_app)
        run(actual_app, host=host, port=int(port), debug=debug)

    if daemon:
        import asyncio
        return asyncio.to_thread(run_server)  # returns coroutine
    else:
        run_server()


@requires("requests")
def watch_url(url, on_change, poll_interval=30.0, logger=None):
    import threading
    import requests

    logger.info(f"Watching url: {url}")
    stop_event = threading.Event()

    def _watch():
        last_hash = None
        while not stop_event.is_set():
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                current_hash = hashlib.sha256(response.content).hexdigest()
                logger.debug(f"{current_hash=}")

                if last_hash is not None and current_hash != last_hash:
                    if logger:
                        logger.warning(f"URL content changed: {url}")
                    on_change()
                    os._exit(1)

                last_hash = current_hash
            except Exception as e:
                if logger:
                    logger.warning(f"Error watching URL {url}: {e}")
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


