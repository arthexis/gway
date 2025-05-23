import importlib
from functools import wraps
from urllib.parse import urlencode
from gway import gw


def _build_url(prefix, *args, **kwargs):
    path = "/".join(str(a).strip("/") for a in args if a)
    url = f"/{prefix}/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url


def setup_app(*, 
              app=None, project=None, module=None, 
              path="gway", static="static", temp="temp", title="GWAY"
            ):
    """Configure a simple application that showcases the use of GWAY to generate web apps."""
    from bottle import Bottle, static_file, request, response, template, HTTPResponse

    version = gw.version()
    if app is None: app = Bottle()

    def redirect_error(error=None, note=""):
        gw.error("Redirecting due to error." + (" " + note if note else ""))
        
        # Log request metadata
        gw.error(f"Method: {request.method}")
        gw.error(f"Path: {request.path}")
        gw.error(f"Full URL: {request.url}")
        gw.error(f"Query: {dict(request.query)}")
        
        try:
            if request.json:
                gw.error(f"JSON body: {request.json}")
            elif request.forms:
                gw.error(f"Form data: {request.forms.decode()}")
        except Exception as e:
            gw.exception(e)

        # Log headers and cookies for more context
        gw.error(f"Headers: {dict(request.headers)}")
        gw.error(f"Cookies: {request.cookies}")

        if error:
            gw.exception(error)

        # Redirect to default view
        response.status = 302
        response.set_header("Location", f"/{path}/readme")
        return ""

    gw.web.static_url = lambda *args, **kwargs: _build_url(static, *args, **kwargs)
    gw.web.temp_url   = lambda *args, **kwargs: _build_url(temp, *args, **kwargs)
    gw.web.app_url    = lambda *args, **kwargs: _build_url(path, *args, **kwargs)
    gw.web.redirect_error = redirect_error

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
        # This may report an error for cookies not being secure in development which we can ignore
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

        if not cookies_enabled() or len(visited) < 2:
            visited = ["readme", "theme"]
        links = "".join(
            f'<li><a href="/{path}/{b.replace("_", "-")}">{b.replace("_", " ").replace("-", " ").title()}</a></li>'
            for b in sorted(visited) if b
        )
        search_box = f'''
            <form action="/{path}/help" method="get" class="navbar">
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

    def render_template(*, title="GWAY", navbar="", content="", css_files=None):
        nonlocal version
        css_files = css_files or ["default.css"]

        css_links = "\n".join(
            f'<link rel="stylesheet" href="/{static}/styles/{css}">'
            for css in css_files
        )
        favicon = f'<link rel="icon" href="/{static}/favicon.ico" type="image/x-icon" />'
        credits = f'''
            <p>GWAY is powered by <a href="https://www.python.org/">Python</a>.
            Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>.</p>
        '''

        return template("""<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8" />
                <title>{{!title}}</title>
                {{!css_links}}
                {{!favicon}}
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
                {{!navbar}}
                <main>{{!content}}</main>
                <br/><footer><p>This website was built, tested and released with GWAY v{{!version}}.</p>
                {{!credits}}
                </footer>
            </body>
            </html>
        """, **locals())

    @app.route("/accept-cookies", method="POST")
    def accept_cookies():
        response.set_cookie("cookies_accepted", "yes")
        redirect_url = request.forms.get("next", "/readme")
        response.status = 303
        if not redirect_url.startswith("/"):
            redirect_url = f"/{redirect_url}"
        response.set_header("Location", f"/{path}{redirect_url}")
        return ""

    @app.route(f"/{static}/<filename:path>")
    def send_static(filename):
        return static_file(filename, root=gw.resource("data", "static"))
    
    @app.route(f"/{temp}/<filename:path>")
    def send_temp(filename):
        return static_file(filename, root=gw.resource("temp", "shared"))
        
    @app.route(f"/{path}/<view:path>", method=["GET", "POST"])
    def view_dispatch(view):
        # TODO: When a POST is received with a payload, assign the top-level
        # items as kwargs (combined with request.query if needed)

        # Normalize incoming path
        segments   = view.strip("/").split("/")
        view_name  = segments[0].replace("-", "_")
        args       = segments[1:]
        kwargs     = dict(request.query)

        # If POST, update with form or JSON body data
        if request.method == "POST":
            try:
                if request.json:
                    kwargs.update(request.json)
                elif request.forms:
                    kwargs.update(request.forms.decode())  # decode() makes it a dict
            except Exception as e:
                return redirect_error(e, note="Error loading JSON payload")

        # Dynamically import the module or project package
        try:
            if module:
                source = importlib.import_module(module)
            elif project:
                source = getattr(gw, project)
            else:
                source = importlib.import_module("web.views")
        except (ImportError, AttributeError) as e:
            return redirect_error(e, note="Error loading views")

        # Try to resolve the callable:
        # 1) First, a function named exactly `view_name`
        # 2) Then, a function named `view_<view_name>`
        view_func = getattr(source, view_name, None)
        if not callable(view_func):
            view_func = getattr(source, f"view_{view_name}", None)
        if not callable(view_func):
            return redirect_error(note="View not found or not callable")

        # Execute the view
        try:
            gw.info(f"Dispatching to view {view_func.__name__} (args={args}, kwargs={kwargs})")
            content = view_func(*args, **kwargs)
            visited = update_visited(view_name)
        except HTTPResponse as resp:
            return resp
        except Exception as e:
            return redirect_error(e, note="View not found or not callable")

        # Build navbar & consent
        full_url = request.fullpath
        if request.query_string:
            full_url += "?" + request.query_string
        navbar = render_navbar(visited, current_url=full_url)

        if not cookies_enabled():
            consent_box = f"""
                <div class="consent-box">
                <form action="/accept-cookies" method="post">
                    <input type="hidden" name="next" value="/{view}" />
                    This site uses cookies to improve your experience.
                    <button type="submit">Accept</button>
                </form>
                </div>
            """
            content = consent_box + content

        # CSS preferences
        css_cookie = request.get_cookie("css", "")
        css_files  = ["default.css"] + [c.strip() for c in css_cookie.split(",") if c.strip()]

        # Render the final page
        return render_template(
            title="GWAY - " + view_name.replace("_", " ").title(),
            navbar=navbar,
            content=content,
            css_files=css_files
        )
            
    @app.route("/", method=["GET", "POST"])
    def index():
        response.status = 302
        response.set_header("Location", f"/{path}/readme")
        return ""

    app = security_middleware(app)
    return app
