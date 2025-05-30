from functools import wraps
from urllib.parse import urlencode
from collections.abc import Iterable
from gway import gw

# TODO: After the changes to how projects and modules work in gway, it has been 
# decided that web.app.setup will no longer accept modules to load views from and 
# instead use the project option only. Sub-projects of that project will be 
# allowed for serving. So, if project="ocpp", both ocpp/csms.py and ocpp/evcs.py projects will
# be exposed, as /ocpp/csms and /ocpp/evcs endpoints respectively. 

# TODO: web/views.py has been renamed to web/view.py Make sure this is consistent in the code

def setup(
        *,
        app=None,
        project="web.view",
        path="gway",
        static="static",
        temp="temp",
        home: str = "readme",
    ):
    """
    Configure a simple application that showcases the use of GWAY to generate web apps.
    This version uses Bottle but can ingest other frameworks safely.
    """
    from bottle import Bottle, static_file, request, response, template, HTTPResponse

    # TODO: Add a "home" parameter that will be used to determine the default view
    # used as the landing and redirect after errors. This is needed because
    # the default readme view may not exist in other projects. If home is None
    # default to the readme as now. home should be relative to project or default web.view

    # TODO: If readme is not found, try index, home, start or first before giving up.

    # TODO: Ensure all references to module are removed and use projects not.
    # Remember we can access functions directly with gw['project.path.func_name']

    version = gw.version()

    if app is not None:
        if isinstance(app, Iterable) and not isinstance(app, Bottle):
            bottles = [a for a in app if isinstance(a, Bottle)]
            if len(bottles) == 1:
                app = bottles[0]
            elif len(bottles) == 0:
                gw.warn("No Bottle app found in iterable; creating new Bottle app.")
                app = Bottle()
            else:
                raise TypeError("Iterable must contain at most one Bottle app.")
        elif not isinstance(app, Bottle):
            raise TypeError("Provided app must be a Bottle instance or an iterable containing one.")
    else:
        app = Bottle()

    _first_setup = not hasattr(app, "_gway_paths")
    if _first_setup:
        # The app produced by setup_app can be passed to setup_again with a new path
        # In such cases, we avoid performing some setup steps
        app._gway_paths = {path: project}
        gw.web.static_url = lambda *args, **kwargs: build_url(static, *args, **kwargs)
        gw.web.temp_url   = lambda *args, **kwargs: build_url(temp, *args, **kwargs)
        gw.web.app_url    = lambda *args, **kwargs: build_url(path, *args, **kwargs)
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

    else:
        app._gway_paths[path] = (project, module)

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
            qr_url = gw.qr.generate_url(current_url)
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

    if _first_setup:

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
            # 1. Normalize segments & apply `home` fallback
            segments = [s for s in view.strip("/").split("/") if s]
            if not segments:
                segments = [home]
            view_name = segments[0].replace("-", "_")
            args = segments[1:]
            kwargs = dict(request.query)

            # Merge POST payload
            if request.method == "POST":
                try:
                    if request.json:
                        kwargs.update(request.json)
                    elif request.forms:
                        kwargs.update(request.forms.decode())
                except Exception as e:
                    return redirect_error(e, note="Error loading JSON payload")

            # 2. Resolve the GWAY project namespace via bracket notation
            try:
                source = gw[project]
            except Exception as e:
                return redirect_error(e, note=f"Project '{project}' not found via gw['{project}']")

            # 3. Locate the view function
            view_func = getattr(source, view_name, None)
            if not callable(view_func):
                view_func = getattr(source, f"view_{view_name}", None)
            if not callable(view_func) and hasattr(source, view_name):
                sub = getattr(source, view_name)
                view_func = getattr(sub, view_name, None)

            if not callable(view_func):
                return redirect_error(note=f"View '{view_name}' not found in project '{project}'")

            # 4. Invoke & render
            try:
                gw.info(f"Dispatching to view {view_func.__name__} (args={args}, kwargs={kwargs})")
                content = view_func(*args, **kwargs)
                visited = update_visited(view_name)
            except HTTPResponse as resp:
                return resp
            except Exception as e:
                return redirect_error(e, note="Error during view execution")

            # 5. Navbar, consent, CSS, template—unchanged
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

            css_cookie = request.get_cookie("css", "")
            css_files = ["default.css"] + [c.strip() for c in css_cookie.split(",") if c.strip()]

            return render_template(
                title="GWAY - " + view_name.replace("_", " ").title(),
                navbar=navbar,
                content=content,
                css_files=css_files
            )
        
    if _first_setup:
                
        @app.route("/", method=["GET", "POST"])
        def index():
            response.status = 302
            response.set_header("Location", f"/{path}/readme")
            return ""

        app = security_middleware(app)

    return app

...

def build_url(prefix, *args, **kwargs):
    path = "/".join(str(a).strip("/") for a in args if a)
    url = f"/{prefix}/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url


def redirect_error(error=None, note="", default="/gway/readme"):
    from bottle import request, response
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
    response.set_header("Location", default)
    return ""

