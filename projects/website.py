import logging
from gway import requires, Gateway

logger = logging.getLogger(__name__)


@requires("bottle", "docutils")
def start_server(
    host="[WEBSITE_HOST|localhost]",
    port="[WEBSITE_PORT|8800]",
    debug=False,
):
    from bottle import Bottle, static_file, run, template
    app = Bottle()

    @app.route("/")
    def index():
        from docutils.core import publish_parts

        gway = Gateway()
        readme_path = gway.resource("README.rst")

        with open(readme_path, encoding="utf-8") as f:
            rst_content = f.read()

        html_parts = publish_parts(source=rst_content, writer_name="html")
        body = html_parts["html_body"]

        return template("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>GWAY - Dynamic CLI Framework</title>
                <style>
                    body { font-family: sans-serif; max-width: 800px; margin: 40px auto; line-height: 1.6; }
                    a { color: #1e88e5; }
                    pre { background: #f5f5f5; padding: 1em; overflow-x: auto; }
                </style>
            </head>
            <body>
                <h1>Welcome to GWAY</h1>
                <p><a href="https://pypi.org/project/gway/">View on PyPI</a></p>
                {{!body}}
            </body>
            </html>
        """, body=body)

    # Static file handler if needed
    @app.route("/static/<filename:path>")
    def send_static(filename):
        gway = Gateway()
        return static_file(filename, root=gway.resource("data", "static"))

    run(app, host=host, port=port, debug=debug)
