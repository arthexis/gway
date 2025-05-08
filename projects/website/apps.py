import os
from functools import wraps
from gway import requires, gw

_css_cache = {}


@requires("bottle", "docutils")
def setup_app(*, app=None):
    """Configure a simple application that showcases the use of GWAY to generate websites."""
    from bottle import Bottle, static_file, request, response, template, HTTPResponse

    version = gw.version()
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
                    ("Server", f"GWAY v{version}")  # Optional: replace with your server name
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
       
        cookie_value = "|".join(visited)   # Use a safe separator (not comma) and avoid quotes
        response.set_cookie(cookie_name, cookie_value)

        return visited

    def render_navbar(visited, current_url=None):

        # TODO: Take the size of the viewport into consideration. If the screen is too
        # narrow, make the navbar appear below the main content instead.

        if not cookies_enabled():
            visited = ["readme"]
        links = "".join(
            f'<li><a href="/{b}">{b.title()}</a></li>' for b in sorted(visited) if b
        )
        search_box = '''
            <form action="/help" method="get" class="navbar">
                <input type="text" name="topic" placeholder="Search GWAY" class="help" />
            </form>
        '''
        qr_html = ""
        if current_url:
            qr_url = gw.qr_code.generate_url(current_url)
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

    def render_template(*, 
            title="GWAY", navbar="", content="", css="default.css", 
            inline_css=False,
        ):
        nonlocal version
        css_path = gw.resource("data", "static", "styles", css)

        if css != "default.css" and not os.path.exists(css_path):
            css = "default.css"
            css_path = gw.resource("data", "static", "styles", css)

        if inline_css:
            css_content = load_css(css_path)
            css_html = f"<style>{css_content}</style>"
        else:
            css_url = f"/static/styles/{css}"
            css_html = f'<link rel="stylesheet" href="{css_url}" />'

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
                <br/><hr><footer><p>This website was built, tested and released with GWAY v{{!version}}.</p>
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
        response.status = 302
        response.set_header("Location", "/readme")
        return ""

    @app.route("/static/<filename:path>")
    def send_static(filename):
        return static_file(filename, root=gw.resource("data", "static"))
    
    @app.route("/temp/<filename:path>")
    def send_temp(filename):
        return static_file(filename, root=gw.resource("temp", "shared"))
        
    @app.route("/<view:path>", method=["GET", "POST"])
    def view_dispatch(view):
        segments = view.strip("/").split("/")
        view_name = segments[0].replace("-", "_")
        args = segments[1:]

        import website.views as views
        view_func = getattr(views, f"view_{view_name}", None)
        kwargs = dict(request.query)

        try:
            gw.info(f"Dispatching to function {view_func.__name__}")
            content = view_func(*args, **kwargs)
            visited = update_visited(view_name)
        except HTTPResponse as res:
            return res
        except Exception as e:
            gw.exception(e)
            # Redirect to /readme on any error
            response.status = 302
            response.set_header("Location", "/readme")
            return ""

        current_url = request.fullpath
        if request.query_string:
            current_url += "?" + request.query_string

        navbar = render_navbar(visited, current_url=current_url)
        if not cookies_enabled():
            consent_box = f"""
                <div class="consent-box">
                    <form action="/accept-cookies" method="post">
                        <input type="hidden" name="next" value="/{view}" />
                        This app uses cookies to improve your experience. 
                        <button type="submit"> Accept </button>
                    </form>
                </div>
            """
            content = consent_box + content

        css = request.get_cookie("css", "default.css")
        return render_template(navbar=navbar, content=content, css=css)

    app = security_middleware(app)
    return app

