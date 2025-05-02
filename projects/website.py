import os
import logging
import time
import hashlib
from gway import requires, Gateway, tag

logger = logging.getLogger(__name__)

# TODO: Create a build_navbar function that can be used by setup_app to create a navbar on the right side of the page
# Build functions should produce html fragments that can be used by other build or setup functions
# The navbar should be  


@requires("bottle", "docutils")
def setup_app(*, app=None):
    """Configure a simple application that showcases the use of GWAY to generate websites."""
    from bottle import Bottle, static_file, request, template
    from docutils.core import publish_parts

    gway = Gateway()
    if app is None: app = Bottle()

    @app.route("/help/<path:re:.*>")
    def show_reference(path):
        parts = [p.replace("-", "_") for p in path.strip("/").split("/")]

        if len(parts) == 1:
            help_info = gway.help(parts[0])
            title = f"Help for {parts[0]}"
        elif len(parts) == 2:
            help_info = gway.help(parts[0], parts[1])
            title = f"Help for {parts[0]}.{parts[1]}"
        else:
            return template("""
                <!DOCTYPE html>
                <html><head><title>GWAY Help</title></head>
                <body style="font-family: sans-serif; max-width: 700px; margin: 2em auto;">
                    <h2>Invalid help subject</h2>
                </body>
                </html>
            """)

        if help_info is None:
            return template("""
                <!DOCTYPE html>
                <html><head><title>GWAY Help</title></head>
                <body style="font-family: sans-serif; max-width: 700px; margin: 2em auto;">
                    <h2>Function Not Found</h2>
                    <p>No function found for the given path.</p>
                </body>
                </html>
            """)

        return template("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{{!title}}</title>
                <style>
                    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.6; }
                    pre { background: #f5f5f5; padding: 1em; overflow-x: auto; }
                </style>
            </head>
            <body>
                <h1>{{!title}}</h1>
                <h3>Signature</h3>
                <pre>{{!help_info['Signature']}}</pre>

                <h3>Docstring</h3>
                <pre>{{!help_info['Docstring']}}</pre>

                <h3>Example CLI</h3>
                <pre>{{!help_info['Example CLI']}}</pre>

                <h3>Example Code</h3>
                <pre>{{!help_info['Example Code']}}</pre>
            </body>
            </html>
        """, **locals())

    @app.route("/")
    def index():
        gway = Gateway()
        readme_path = gway.resource("README.rst")

        with open(readme_path, encoding="utf-8") as f:
            rst_content = f.read()

        html_parts = publish_parts(source=rst_content, writer_name="html")
        body = html_parts["html_body"]
        version = gway.version()

        return template("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>GWAY v{{!version}}</title>
                <style>
                    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.6; }
                    a { color: #1e88e5; }
                    pre { background: #f5f5f5; padding: 1em; overflow-x: auto; }
                </style>
            </head>
            <body>
                <h1>Welcome to GWAY v{{!version}}</h1>
                <p><a href="https://pypi.org/project/gway/">Latest Release on PyPI</a></p>
                <p><a href="https://github.com/arthexis/gway/">View the Source Code</a></p>
                {{!body}}
            </body>
            </html>
        """, **locals())

    @app.route("/static/<filename:path>")
    def send_static(filename):
        gway = Gateway()
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

