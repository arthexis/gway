import os
import logging
import time
import hashlib
from gway import requires, Gateway

logger = logging.getLogger(__name__)


@requires("bottle", "docutils")
def setup_app(*, app=None):
    """Configure a simple application that showcases the use of GWAY to generate websites."""
    from bottle import Bottle, static_file, request, response, template

    gway = Gateway()
    if app is None: app = Bottle()

    def cookies_enabled():
        return request.get_cookie("cookies_accepted") == "yes"

    def update_visited(current):
        if not cookies_enabled():
            return []
        visited = request.get_cookie("visited", "").split(",")
        if current not in visited:
            visited.append(current)
        visited = list(sorted(set(visited), key=lambda x: (x != "readme", x.lower())))
        response.set_cookie("visited", ",".join(visited))
        return visited

    def build_navbar(visited):
        if not cookies_enabled():
            visited = []
        links = "".join(
            f'<li><a href="/?c={b}">{b.title()}</a></li>' for b in sorted(visited) if b
        )
        search_box = '''
            <form action="/help/" method="get" style="margin-bottom: 1em;">
                <input 
                    type="text" 
                    name="q" 
                    placeholder="Search GWAY" 
                    style="width: 100%; padding: 0.5em; border-radius: 8px; border: 1px solid #ccc;" 
                />
            </form>
        '''
        return f"<aside>{search_box}<ul>{links}</ul></aside>"

    def make_template(*, title="GWAY", navbar="", content=""):
        return template("""<!DOCTYPE html>
            <html>
            <head>
                <title>{{!title}}</title>
                <style>
                    body { font-family: sans-serif; max-width: 900px; margin: 40px auto; line-height: 1.6; }
                    aside { float: left; width: 220px; margin-right: 2em; }
                    main { overflow: hidden; }
                    pre { background: #f5f5f5; padding: 1em; overflow-x: auto; }
                    li a { text-decoration: none; color: #1e88e5; }
                    .consent-box {
                        background: #fff3cd;
                        border: 1px solid #ffeeba;
                        padding: 1em;
                        margin-bottom: 1.5em;
                        border-radius: 8px;
                    }
                    .consent-box form { display: inline; }
                </style>
            </head>
            <body>
                {{!navbar}}
                <main>{{!content}}</main>
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

    @app.route("/help/<path:re:.*>")
    def show_help(path):
        parts = [p.replace("-", "_") for p in path.strip("/").split("/")]

        if len(parts) == 1:
            help_info = gway.help(parts[0])
            title = f"Help for {parts[0]}"
        elif len(parts) == 2:
            help_info = gway.help(parts[0], parts[1])
            title = f"Help for {parts[0]}.{parts[1]}"
        else:
            return make_template(
                title="Invalid Help",
                content="<h2>Invalid help subject</h2>"
            )

        if help_info is None:
            return make_template(
                title="Help Not Found",
                content="<h2>Function Not Found</h2><p>No function found for the given path.</p>"
            )

        # Display help_info dynamically
        rows = ""
        for key, val in help_info.items():
            rows += f"<h3>{key}</h3><pre>{val}</pre>"

        content = f"<h1>{title}</h1>{rows}"
        return make_template(title=title, content=content)

    @app.route("/")
    def index():
        c = request.query.get("c", "readme")
        kwargs = {k: v for k, v in request.query.items() if k != "c"}

        builder = getattr(gway.website, f"build_{c}", None)
        if not builder:
            content = f"<p>No content found for '{c}'</p>"
        else:
            try:
                content = builder(**kwargs)
            except Exception as e:
                content = f"<p>Error in content builder: {e}</p>"

        visited = update_visited(c)
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


def build_readme():
    """Render the README.rst file as HTML."""
    from docutils.core import publish_parts

    gway = Gateway()
    readme_path = gway.resource("README.rst")

    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]
