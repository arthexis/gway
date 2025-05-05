import os
import logging

from urllib.parse import quote, unquote
from functools import wraps
from gway import requires, Gateway

logger = logging.getLogger(__name__)
gway = Gateway()


_css_cache = {}

# TODO: Fix this reported error -> The 'server' header should only contain the server name
# Server: nginx/1.18.0 (ubuntu)

# TODO: Resource should use cache busting but URL does not match configured patterns.
# https://arthexis.com/temp/qr_codes/Lz9jPWhlbHA.png
# We should implement some kind of general cache busting solution for all hosted resources

# TODO: Create an access log (consider storing in database if not too slow)

@requires("bottle", "docutils")
def setup_app(*, app=None):
    """Configure a simple application that showcases the use of GWAY to generate websites."""
    from bottle import Bottle, static_file, request, response, template, HTTPResponse

    if app is None: app = Bottle()

    def security_middleware(app):
        """Middleware to fix headers and secure cookies."""
        def wrapped_app(environ, start_response):
            def custom_start_response(status, headers, exc_info=None):
                # Remove default 'Server' header
                headers = [(k, v) for k, v in headers if k.lower() != 'server']
                # Add fixed headers
                headers += [
                    ("Cache-Control", "no-cache"),
                    ("X-Content-Type-Options", "nosniff"),
                    ("Server", "GWAY")  # Optional: replace with your server name
                ]
                return start_response(status, headers, exc_info)

            return app(environ, custom_start_response)

        # Patch Bottle's response.set_cookie to enforce secure, httponly
        original_set_cookie = response.set_cookie

        @wraps(original_set_cookie)
        def secure_set_cookie(name, value, **kwargs):
            is_secure = request.urlparts.scheme == "https"
            kwargs.setdefault("secure", is_secure)
            kwargs.setdefault("httponly", True)
            kwargs.setdefault("samesite", "Lax")
            kwargs.setdefault("path", "/")
            return original_set_cookie(name, value, **kwargs)

        response.set_cookie = secure_set_cookie
        return wrapped_app

    def cookies_enabled():
        return request.get_cookie("cookies_accepted") == "yes"
        
    def update_visited(current, cookie_name="visited"):
        if not cookies_enabled():
            return []

        raw = request.get_cookie(cookie_name, "")
        visited = raw.split("|") if raw else []

        if current not in visited:
            visited.append(current)

        # Use a safe separator (not comma) and avoid quotes
        cookie_value = "|".join(visited)
        response.set_cookie(cookie_name, cookie_value)

        return visited

    def build_navbar(visited, current_url=None):
        if not cookies_enabled():
            visited = ["readme"]
        links = "".join(
            f'<li><a href="/?c={b}">{b.title()}</a></li>' for b in sorted(visited) if b
        )
        search_box = '''
            <form action="/" method="get" class="navbar">
                <input type="hidden" name="c" value="help" />
                <input type="text" name="path" placeholder="Search GWAY" class="help" />
            </form>
        '''
        qr_html = ""
        if current_url:
            qr_url = gway.project.generate_qr_code_url(current_url)
            qr_html = f'''
                <div class="qr">
                    <p class="qr">QR Code for this page:</p>
                    <img src="{qr_url}" alt="QR Code" class="navbar-qr" />
                </div>
            '''

        return f"<aside>{search_box}<ul>{links}</ul><br>{qr_html}</aside>"

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

    def make_template(*, 
            title="GWAY", navbar="", content="", css="default.css", 
            inline_css=False,
        ):
        css_path = gway.resource("data", "static", "styles", css)

        if css != "default.css" and not os.path.exists(css_path):
            css = "default.css"
            css_path = gway.resource("data", "static", "styles", css)

        if inline_css:
            css_content = load_css(css_path)
            css_html = f"<style>{css_content}</style>"
        else:
            css_url = f"/static/styles/{css}"
            css_html = f'<link rel="stylesheet" href="{css_url}" />'

        version = gway.version()
        return template("""<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8" />
                <title>{{!title}}</title>
                {{!css_html}}
                <link rel="icon" href="/static/favicon.ico" type="image/x-icon" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
                {{!navbar}}
                <main>{{!content}}</main>
                <br><hr><footer><p>This website was built, tested and released with GWAY v{{!version}}.</p>
                        <p>GWAY is powered by <a href="https://www.python.org/">Python</a>.
                        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>.</p></footer>
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
        
    @app.route("/", method=["GET", "POST"])
    def index():
        c = request.query.get("c")
        kwargs = {k: v for k, v in request.query.items() if k != "c"}
        builder = getattr(gway.website, f"build_{c}", None)

        visited = []
        if not builder:
            target = "/?c=readme"
            response.status = 302
            response.set_header("Location", target)
            return ""
        else:
            try:
                content = builder(**kwargs)
                visited = update_visited(c)
            except HTTPResponse as res:
                return res  
            except Exception as e:
                logger.exception(e)
                content = f"<p>Content not found.</p>"            

        current_url = request.fullpath
        if request.query_string:
            current_url += "?" + request.query_string

        navbar = build_navbar(visited, current_url=current_url)
        if not cookies_enabled():
            consent_box = f"""
                <div class="consent-box">
                    <form action="/accept-cookies" method="post">
                        <input type="hidden" name="next" value="/?c={c}" />
                        This app uses cookies to improve your experience. 
                        <button type="submit"> Accept </button>
                    </form>
                </div>
            """
            content = consent_box + content

        css = request.get_cookie("css", "default.css")
        return make_template(navbar=navbar, content=content, css=css)


    @app.route("/static/<filename:path>")
    def send_static(filename):
        return static_file(filename, root=gway.resource("data", "static"))
    
    @app.route("/temp/<filename:path>")
    def send_temp(filename):
        return static_file(filename, root=gway.resource("temp", "shared"))

    app = security_middleware(app)
    return app

