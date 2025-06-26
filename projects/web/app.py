# file: projects/web/app.py

import os
from urllib.parse import urlencode
import bottle
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw

_ver = None
_homes = []   # (title, route)
_enabled = set()
UPLOAD_MB = 100

def enabled_projects():
    """Return a set of all enabled web projects (for static.collect, etc)."""
    global _enabled
    return set(_enabled)

def current_endpoint():
    """
    Return the canonical endpoint path for the current request (the project route prefix).
    Falls back to gw.context['current_endpoint'], or None.
    """
    return gw.context.get('current_endpoint')

def setup(*,
    app=None,
    project="web.site",
    path=None,
    home: str = None,
    views: str = "view", 
    apis: str = "api",
    static="static",
    shared="shared",
    css="global",       # Default CSS (without .css extension)
    js="global",        # Default JS  (without .js extension)
    engine="bottle",
):
    """
    Setup Bottle web application with symmetrical static/shared public folders.
    Only one project per app. CSS/JS params are used as the only static includes.
    """
    global _ver, _homes, _enabled

    if engine != "bottle":
        raise NotImplementedError("Only Bottle is supported at the moment.")

    _ver = _ver or gw.version()
    bottle.BaseRequest.MEMFILE_MAX = UPLOAD_MB * 1024 * 1024

    if not isinstance(project, str) or not project:
        gw.abort("Project must be a non-empty string.")

    # Track project for later global static collection
    _enabled.add(project)

    # Always use the given project, never a list
    try:
        source = gw[project]
    except Exception:
        gw.abort(f"Project {project} not found in Gateway during app setup.")

    # Default path is the dotted project name, minus any leading web/
    if path is None:
        path = project.replace('.', '/')
        if path.startswith('web/'):
            path = path.removeprefix('web/')
            
    is_new_app = not (app := gw.unwrap_one(app, Bottle) if (oapp := app) else None)
    if is_new_app:
        gw.info("No Bottle app found; creating a new Bottle app.")
        app = Bottle()
        _homes.clear()
        add_home(home, path)

        @app.route("/", method=["GET", "POST"])
        def index():
            response.status = 302
            response.set_header("Location", default_home())
            return ""

        @app.error(404)
        def handle_404(error):
            return gw.web.error.redirect(f"404 Not Found: {request.url}", err=error)
    
    elif home:
        add_home(home, path)

    # Serve shared files (flat mount)
    if shared:
        @app.route(f"/{path}/{shared}/<filepath:path>")
        @app.route(f"/{shared}/<filepath:path>")
        def send_shared(filepath):
            file_path = gw.resource("work", "shared", filepath)
            if os.path.isfile(file_path):
                return static_file(os.path.basename(file_path), root=os.path.dirname(file_path))
            return HTTPResponse(status=404, body="shared file not found")

    # Serve static files (flat mount)
    if static:
        @app.route(f"/{path}/{static}/<filepath:path>")
        @app.route(f"/{static}/<filepath:path>")
        def send_static(filepath):
            file_path = gw.resource("data", "static", filepath)
            if os.path.isfile(file_path):
                return static_file(os.path.basename(file_path), root=os.path.dirname(file_path))
            return HTTPResponse(status=404, body="static file not found")

    # Main view dispatcher (only if views is not None)
    if views:
        @app.route(f"/{path}/<view:path>", method=["GET", "POST"])
        def view_dispatch(view):
            nonlocal home, views
            # Set current endpoint in GWAY context (for helpers/build_url etc)
            gw.context['current_endpoint'] = path
            segments = [s for s in view.strip("/").split("/") if s]
            view_name = segments[0].replace("-", "_") if segments else home
            args = segments[1:] if segments else []
            kwargs = dict(request.query)
            if request.method == "POST":
                try:
                    kwargs.update(request.json or dict(request.forms))
                except Exception as e:
                    return gw.web.error.redirect("Error loading JSON payload", error=e)

            target_func_name = f"{views}_{view_name}" if views else view_name

            view_func = getattr(source, target_func_name, None)
            if not callable(view_func):
                return gw.web.error.redirect(f"View not found: {target_func_name} in {project}")

            try:
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
            except HTTPResponse as res:
                return res
            except Exception as e:
                return gw.web.error.redirect("Broken view", err=e)

            media_origin = "/shared" if shared else ("static" if static else "")
            return render_template(
                title="GWAY - " + view_func.__name__.replace("_", " ").title(),
                content=content,
                css_files=(f"{media_origin}/{css}.css",),
                js_files=(f"{media_origin}/{js}.js",),
            )

    # API dispatcher (only if apis is not None)
    if apis:
        @app.route(f"/api/{path}/<view:path>", method=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
        def api_dispatch(view):
            nonlocal home, apis
            # Set current endpoint in GWAY context (for helpers/build_url etc)
            gw.context['current_endpoint'] = path
            segments = [s for s in view.strip("/").split("/") if s]
            view_name = segments[0].replace("-", "_") if segments else home
            args = segments[1:] if segments else []
            kwargs = dict(request.query)
            if request.method == "POST":
                try:
                    kwargs.update(request.json or dict(request.forms))
                except Exception as e:
                    return gw.web.error.redirect("Error loading JSON payload", err=e)

            method = request.method.lower()
            specific_af = f"{apis}_{method}_{view_name}"
            generic_af = f"{apis}_{view_name}"

            api_func = getattr(source, specific_af, None)
            if not callable(api_func):
                api_func = getattr(source, generic_af, None)
            if not callable(api_func):
                return gw.web.error.redirect(f"API not found: {specific_af} or {generic_af} in {project}")

            try:
                result = api_func(*args, **kwargs)
                if isinstance(result, HTTPResponse):
                    return result
                response.content_type = "application/json"
                return gw.to_json(result)
            except HTTPResponse as res:
                return res
            except Exception as e:
                return gw.web.error.redirect("Broken API", err=e)
    
    @app.route("/favicon.ico")
    def favicon():
        proj_parts = project.split('.')
        candidate = gw.resource("data", "static", *proj_parts, "favicon.ico")
        if os.path.isfile(candidate):
            return static_file("favicon.ico", root=os.path.dirname(candidate))
        global_favicon = gw.resource("data", "static", "favicon.ico")
        if os.path.isfile(global_favicon):
            return static_file("favicon.ico", root=os.path.dirname(global_favicon))
        return HTTPResponse(status=404, body="favicon.ico not found")

    if gw.verbose:
        gw.debug(f"Registered homes: {_homes}")
        debug_routes(app)

    return oapp if oapp else app

# Use current_endpoint to get the current project route
def build_url(*args, **kwargs):
    path = "/".join(str(a).strip("/") for a in args if a)
    endpoint = current_endpoint()
    if endpoint:
        url = f"/{endpoint}/{path}" if path else f"/{endpoint}"
    else:
        url = f"/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url

def render_template(*, title="GWAY", content="", css_files=None, js_files=None):
    global _ver
    version = _ver = _ver or gw.version()

    # --- MAIN: THEME CSS HANDLING ---
    theme_css = None
    if is_enabled('web.nav'):
        try:
            theme_css = gw.web.nav.get_style()
        except Exception:
            theme_css = "/static/styles/base.css"
    css_files = gw.to_list(css_files)
    if theme_css and theme_css not in css_files:
        idx = 1 if css_files and 'global.css' in css_files[0] else 0
        css_files.insert(idx, theme_css)
    css_links = ""
    if css_files:
        for href in css_files:
            css_links += f'<link rel="stylesheet" href="{href}">\n'

    js_files = gw.to_list(js_files)
    js_links = ""
    if js_files:
        for src in js_files:
            js_links += f'<script src="{src}"></script>\n'

    favicon = f'<link rel="icon" href="/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is written in <a href="https://www.python.org/">Python 3.11</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> and <a href="https://github.com/arthexis/gway">Github</a>.</p>
    '''

    nav = ""
    if is_enabled('web.nav'):
        nav = gw.web.nav.render(homes=_homes)

    html = template("""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8" />
            <title>{{!title}}</title>
            {{!css_links}}
            {{!favicon}}
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        </head>
        <body>
            <div class="page-wrap">
                <div class="layout">
                    {{!nav}}<main>{{!content}}</main>
                </div>
                <footer><p>This website was <strong>built</strong>, <strong>tested</strong> 
                    and <strong>released</strong> with <a href="https://arthexis.com">GWAY</a> 
                    <a href="https://pypi.org/project/gway/{{!version}}/">v{{!version}}</a>.</p>
                    {{!credits}}
                </footer>
            </div>
            {{!js_links}}
        </body>
        </html>
    """, **locals())
    return html

def default_home():
    for title, route in _homes:
        if route:
            return "/" + route.lstrip("/")
    return "/site/readme"

def debug_routes(app):
    for route in app.routes:
        gw.debug(f"{route.method:6} {route.rule:30} -> {route.callback.__name__}")

def is_enabled(project_name):
    global _enabled
    return project_name in _enabled

def add_home(home, path):
    global _homes
    title = home.replace('-', ' ').replace('_', ' ').title()
    route = f"{path}/{home}"
    if (title, route) not in _homes:
        _homes.append((title, route))
        gw.debug(f"Added home: ({title}, {route})")
    