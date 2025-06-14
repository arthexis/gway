# projects/web/app.py

# Web components located here are minimal to build any website, if you remove anything
# you start to get compatibility issues. So, I decided to put them all in one bagel.

import os
from functools import wraps
from urllib.parse import urlencode
import bottle
from datetime import datetime
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw

_version = None
_env_home = None
_global_homes = []  # (title, route) 

UPLOAD_MB_LIMIT = 100
 

def setup(*,
    app=None,
    project="web.site",
    path=None,
    home: str = None,
    prefix: str = "view",
    navbar: bool = True,
    static="static",
    work="work",
    engine=Bottle
):
    """
    Configure one or more Bottle-based apps. Use "web server start-app" to launch.

    This app will give web user access to any functions in the given project that
    follow any of these naming conventions, encapsulating them in a simple UI.

        1. {prefix}_{view_name}
        2. render_{view_name}_{prefix}
        3. build_{view_name}_{prefix}
        4. {view_name}_to_html

    You can use gw.web.app.build_url in your views to generate contextual URLs.

    Parameters:
        - app: App or app collection to attach to. None to create a new app.
        - project: GWAY project to get functions from (views, middleware, etc.)
        - home: If multiple apps are stacked the first declared home wins.
        - path: Optional mounting path segment(s), defaults to the project name.
        - prefix: Prefix used to identify public views. Defaults to 'view'.
        - navbar: Display a default navbar unless False.
        - work: URL path for access to /work/shared files.
        - static URL path for access to shared /data/static files.
    """
    global _version, _env_home, _global_homes
    if not engine is Bottle:
        raise NotImplementedError("Only Bottle is supported at the moment.")
    _version = _version or gw.version()
    _env_home = os.environ.get('HOME', 'gway/readme')
    bottle.BaseRequest.MEMFILE_MAX = UPLOAD_MB_LIMIT * 1024 * 1024

    projects = gw.to_list(project, flat=True)
    if path is None:
        path = "gway" if projects[0] == "web.site" else projects[0].replace('.', '/')
        project_path = projects[0].replace('.', '/') if path != "gway" else "gway"
    else:
        project_path = path

    is_new_app = not (app := gw.unwrap_one(app, Bottle) if (oapp := app) else None)
    gw.debug(f"Unwrapped {app=} from {oapp=} ({is_new_app=})")

    if home:
        title = home.replace('-', ' ').replace('_', ' ').title()
        route = f"{project_path}/{home}"
        if (title, route) not in _global_homes:
            _global_homes.append((title, route))

    if is_new_app:
        gw.info("No Bottle app found; creating a new Bottle app.")
        app = Bottle()
        _global_homes.clear()

        @app.route("/accept-cookies", method="POST")
        def accept_cookies():
            response.set_cookie("cookies_accepted", "yes", path="/", samesite="Lax", httponly=True)
            response.status = 303
            response.set_header("Location", "/gway/cookies")
            return ""
        
        @app.route("/remove-cookies", method="POST")
        def remove_cookies():
            expires = datetime.utcfromtimestamp(0).strftime('%a, %d %b %Y %H:%M:%S GMT')
            for cookie in request.cookies:
                response.set_cookie(
                    cookie, value="deleted", path="/", expires=expires,
                    secure=False, httponly=True, samesite="Lax"
                )
                response.set_cookie(
                    cookie, value="deleted", path="/", expires=expires,
                    secure=True, httponly=True, samesite="Lax"
                )

            response.status = 303            
            response.set_header("Location", "/gway/cookies")
            return ""

    if static:
        @app.route(f"/{static}/<filename:path>")
        def send_static(filename):
            return static_file(filename, root=gw.resource("data", "static"))

    if work:
        @app.route(f"/{work}/<filename:path>")
        def send_work(filename):
            filename = filename.replace('-', '_')
            return static_file(filename, root=gw.resource("work", "shared"))

    @app.route(f"/{path}/<view:path>", method=["GET", "POST", "PUT"])
    def view_dispatch(view):
        nonlocal navbar, home
        segments = [s for s in view.strip("/").split("/") if s]
        
        # Use fallback sequence if no view specified and home is None
        if not segments:
            fallback_names = (
                [home] if home else
                ["index", "readme", "status", "local", "main", "start", 
                 "first", "setup", "begin", "wizard", "home", "upload"]
            )
        else:
            fallback_names = [segments[0].replace("-", "_")]

        args = segments[1:] if segments else []
        kwargs = dict(request.query)

        if request.method in ("POST", "PUT"):
            try:
                if request.json:
                    kwargs.update(request.json)
                elif request.forms:
                    kwargs.update(dict(request.forms))
            except Exception as e:
                return redirect_error(e, note="Error loading JSON payload", 
                                      broken_view_name=fallback_names[0])

        sources = []
        for proj_name in projects:
            try:
                sources.append(gw[proj_name])
            except Exception:
                continue

        view_func = None
        for view_name in fallback_names:
            for source in sources:
                candidates = [
                    f"{prefix}_{view_name}",
                    f"render_{view_name}_{prefix}",
                    f"build_{view_name}_{prefix}",
                    f"{view_name}_to_html",
                ]
                for name in candidates:
                    view_func = getattr(source, name, None)
                    if callable(view_func):
                        if 'url_stack' not in gw.context:
                            gw.context['url_stack'] = []
                        (url_stack := gw.context['url_stack']).append((project, path))
                        break
                if view_func:
                    break
            if view_func:
                break
        else:
            return redirect_error(
                note=f"View not found using any naming convention for names {fallback_names} in: {projects}",
                broken_view_name=fallback_names[0],
                default=f"/{path or project.replace('.', '/')}/{home}" if home else "/gway/readme"
            )

        try:
            gw.debug(f"Dispatch to {view_func.__name__} (args={args}, kwargs={kwargs})")
            content = view_func(*args, **kwargs)

            if isinstance(content, HTTPResponse):
                return content
            elif isinstance(content, bytes):
                response.content_type = "application/octet-stream"
                response.body = content
                return response
            elif content is None:
                return ""
            elif not isinstance(content, str):
                content = gw.to_html(content)

            visited = update_visited_cookie(view_name)
        except HTTPResponse as resp:
            return resp
        except Exception as e:
            return redirect_error(e, note="Error during view execution", broken_view_name=view_func.__name__)

        full_url = request.fullpath
        if request.query_string:
            full_url += "?" + request.query_string
        if navbar is True:
            navbar = render_navbar(visited, path, current_url=full_url)
        if not cookies_enabled():
            consent_box = f"""
                <div class="consent-box">
                <form action="/accept-cookies" method="post">
                    <input type="hidden" name="next" value="/{view}" />
                    This application uses cookies to improve your experience.
                    <button type="submit">Accept our cookies</button>
                </form>
                </div>
            """
            content = consent_box + content

        style_param = request.query.get("css") or request.query.get("style")
        if style_param:
            if not style_param.endswith(".css"):
                style_param += ".css"
            response.set_cookie("css", style_param, path="/")
            css_files = ["base.css", style_param]
        else:
            css_cookie = request.get_cookie("css", "")
            css_files = ["base.css"] + [c.strip() for c in css_cookie.split(",") if c.strip()]

        try:
            return render_template(
                title="GWAY - " + view_func.__name__.replace("_", " ").title(),
                navbar=navbar,
                content=content,
                static=static,
                css_files=css_files
            )
        finally:
            url_stack.pop()

    @app.route("/", method=["GET", "POST"])
    def index():
        response.status = 302
        response.set_header("Location", get_default_home())
        return ""

    @app.error(404)
    def handle_404(error):
        try:
            return redirect_error(
                error,
                note=f"404 Not Found: {request.url}",
                default=response.set_header("Location", get_default_home())
            )
        except Exception as e:
            return redirect_error(e, note="Failed during 404 fallback", default="/gway/readme")

    if is_new_app:
        app = cookie_middleware(app)

    gw.debug(f"Registered homes: {_global_homes}")
    return oapp if oapp else app


def build_url(*args, **kwargs):
    """
    Dynamically construct an URL to the local application based on caller context.
    """
    path = "/".join(str(a).strip("/") for a in args if a)
    if 'url_stack' in gw.context and (url_stack := gw.context['url_stack']):
        _, prefix = url_stack[-1]
        url = f"/{prefix}/{path}"
    else:
        url = f"/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url


def render_navbar(visited, path, current_url=None):
    global _global_homes

    gw.debug(f"render_navbar -> {_global_homes=}")
    cookies_ok = cookies_enabled()
    links = ""
    seen = set()

    if cookies_ok and visited:
        sorted_visited = sorted(visited, key=lambda x: x.split("=")[0].lower())
        for entry in sorted_visited:
            if "=" not in entry:
                continue
            title, route = entry.split("=", 1)
            if title in seen:
                continue
            seen.add(title)
            links += f'<li><a href="/{route}">{title}</a></li>'
    else:
        # Show current view if available
        current_title = (request.fullpath.strip("/").split("/") or ["readme"])
        title = current_title[-1].replace('-', ' ').replace('_', ' ').title()
        links += f'<li><strong>{title.upper()}</strong></li>'
        # Add global homes
        for home_title, home_route in sorted(_global_homes):
            if home_title.lower() == title.lower():
                continue
            links += f'<li><a href="/{home_route}">{home_title.upper()}</a></li>'

    search_box = f'''
        <form action="/gway/help" method="get" class="navbar">
            <input type="text" name="topic" placeholder="Search GWAY" class="help" />
        </form>
    '''

    compass = ""
    if current_url:
        qr_url = gw.qr.generate_url(current_url)
        compass = f'''
            <div class="compass">
                <p class="compass">QR Code for this page:</p>
                <img src="{qr_url}" alt="QR Code" class="compass" />
            </div>
        '''

    style_selector = ""
    if cookies_ok:
        styles_dir = gw.resource("data", "static", "styles")
        available_styles = sorted(
            f for f in os.listdir(styles_dir)
            if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
        )

        current_style = request.get_cookie("css") or "base.css"
        options = "\n".join(
            f'<option value="{s}"{" selected" if s == current_style else ""}>{s[:-4]}</option>'
            for s in available_styles
        )
        style_selector = f'''
            <form method="get" class="style-form">
                <select id="css-style" name="css" class="style-selector" onchange="this.form.submit()"
                    style="width: 100%">
                    {options}
                </select>
                <noscript><button type="submit">Set</button></noscript>
            </form>
        '''

    remove_button = ""
    if cookies_ok:
        remove_button = '''
            <form method="post" action="/remove-cookies" style="margin-top: 1rem">
                <button type="submit">Remove our cookies</button>
            </form>
        '''

    return f"<aside>{search_box}<ul>{links}</ul><br>{compass}<br>{style_selector}<br>{remove_button}</aside>"

...


def render_template(*, title="GWAY", navbar="", content="", static="static", css_files=None):
    global _version
    version = _version = _version or gw.version()
    css_files = css_files or ["base.css"]
    css_links = "\n".join(
        f'<link rel="stylesheet" href="/{static}/styles/{css}">' for css in css_files
    )
    favicon = f'<link rel="icon" href="/{static}/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is powered by <a href="https://www.python.org/">Python 3.13</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> 
        and <a href="https://github.com/arthexis/gway">Github</a>.</p>
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
            <div class="layout">
            {{!navbar}}
            <main>{{!content}}</main>
            </div>
            <br/><footer><p>This website was built, tested and released with 
                    <a href="https://arthexis.com/gway/readme">GWAY</a> 
                    <a href="https://pypi.org/project/gway/{{!version}}/">v{{!version}}</a>.</p>
            {{!credits}}
            </footer>
        </body>
        </html>
    """, **locals())


def redirect_error(error=None, note="", default="/gway/readme", broken_view_name=None):
    from bottle import request, response
    gw.error("Redirecting due to error." + (" " + note if note else ""))

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

    gw.error(f"Headers: {dict(request.headers)}")
    gw.error(f"Cookies: {request.cookies}")

    if error:
        gw.exception(error)

    response.status = 302
    response.set_header("Location", default)
    return ""

...

# Handling of cookies


def cookies_enabled():
    cookie_value = request.get_cookie("cookies_accepted")
    gw.debug(f"@ cookies_enabled {cookie_value!r}")
    return cookie_value == "yes"


def update_visited_cookie(current, cookie_name="visited"):
    if not cookies_enabled():
        return []

    raw = request.get_cookie(cookie_name, "")
    visited = raw.split("|") if raw else []

    title = current.replace("-", " ").replace("_", " ").title()
    route = request.fullpath.lstrip("/")

    # Exact-title case-insensitive match only
    visited = [v for v in visited if v.split("=")[0].lower() != title.lower()]
    visited.append(f"{title}={route}")

    cookie_value = "|".join(visited)
    response.set_cookie(cookie_name, cookie_value, path="/")

    return visited


def cookie_middleware(app):
    global _version
    _version = _version or gw.version()
    def wrapped_app(environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            headers = [(k, v) for k, v in headers if k.lower() != "server"]
            headers += [
                ("Cache-Control", "no-cache"),
                ("X-Content-Type-Options", "nosniff"),
                ("Server", f"GWAY v{_version}"),
            ]
            return start_response(status, headers, exc_info)

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
        return app(environ, custom_start_response)

    return wrapped_app


def get_default_home():
    """Return the first defined home route from _global_homes, or fallback to /gway/readme."""
    for title, route in _global_homes:
        if route:  # not None or empty
            return "/" + route.lstrip("/")
    return "/gway/readme"
