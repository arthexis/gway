# file: projects/web/app.py

import os
from urllib.parse import urlencode
import bottle
import json
import datetime
import time
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw


_ver = None
_homes = []   # (title, route)
_links: dict[str, list[str]] = {}
_enabled = set()
_registered_routes: set[tuple[str, str]] = set()
_fresh_mtime = None
_fresh_dt = None
UPLOAD_MB = 100

def _refresh_fresh_date():
    """Return cached datetime of VERSION modification, updating cache if needed."""
    global _fresh_mtime, _fresh_dt
    try:
        path = gw.resource("VERSION")
        mtime = os.path.getmtime(path)
    except Exception:
        return None
    if _fresh_mtime != mtime:
        _fresh_mtime = mtime
        _fresh_dt = datetime.datetime.fromtimestamp(mtime)
    return _fresh_dt


def _format_fresh(dt: datetime.datetime | None) -> str:
    """Return human friendly string for datetime `dt`."""
    if not dt:
        return "unknown"
    now = datetime.datetime.now(dt.tzinfo)
    delta = now - dt
    if delta < datetime.timedelta(minutes=1):
        return "seconds ago"
    if delta < datetime.timedelta(hours=1):
        minutes = int(delta.total_seconds() // 60)
        return "a minute ago" if minutes == 1 else f"{minutes} minutes ago"
    if delta < datetime.timedelta(days=1):
        hours = int(delta.total_seconds() // 3600)
        return "an hour ago" if hours == 1 else f"{hours} hours ago"
    if delta < datetime.timedelta(days=7):
        days = delta.days
        return "a day ago" if days == 1 else f"{days} days ago"
    if dt.year == now.year:
        return dt.strftime("%B %d").replace(" 0", " ")
    return dt.strftime("%B %d, %Y").replace(" 0", " ")

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

def make_app(*,
    app=None,
    project="web.site",
    path=None,
    home: str = None,
    links=None,
    views: str = "view",
    apis: str = "api",
    renders: str = "render",
    static="static",
    shared="shared",
    css="global",           # Default CSS (without .css extension)
    js="global",            # Default JS  (without .js extension)
    auth_required=False,    # Default: Don't enforce --optional security
    engine="bottle",
):
    """
    Make Bottle web application with symmetrical static/shared public folders.
    Only one project can be made per call. CSS/JS params are used as the only static includes.
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
            
    oapp = app
    match app:
        case Bottle() as b:
            app = b
            is_new_app = False
        case list() | tuple() as seq:
            app = next((x for x in seq if isinstance(x, Bottle)), None)
            is_new_app = app is None
        case None:
            is_new_app = True
        case _ if isinstance(app, Bottle):
            is_new_app = False
        case _ if hasattr(app, "__iter__") and not isinstance(app, (str, bytes, bytearray)):
            app = next((x for x in app if isinstance(x, Bottle)), None)
            is_new_app = app is None
        case _:
            is_new_app = app is None or not isinstance(app, Bottle)

    if is_new_app:
        gw.info("No Bottle app found; creating a new Bottle app.")
        app = Bottle()
        _homes.clear()
        _links.clear()
        _registered_routes.clear()
        if home:
            add_home(home, path)
            add_links(f"{path}/{home}", links)

        def index():
            response.status = 302
            response.set_header("Location", default_home())
            return ""
        add_route(app, "/", ["GET", "POST"], index)

        @app.error(404)
        def handle_404(error):
            return gw.web.error.redirect(f"404 Not Found: {request.url}", err=error)
    
    elif home:
        add_home(home, path)
        add_links(f"{path}/{home}", links)

    if getattr(gw, "timed_enabled", False):
        @app.hook('before_request')
        def _gw_start_timer():
            request.environ['gw.start'] = time.perf_counter()

        @app.hook('after_request')
        def _gw_stop_timer():
            start = request.environ.pop('gw.start', None)
            if start is not None:
                gw.log(f"[web] {request.method} {request.path} took {time.perf_counter() - start:.3f}s")

    # Serve shared files (flat mount)
    if shared:
        def send_shared(filepath):
            file_path = gw.resource("work", "shared", filepath)
            if os.path.isfile(file_path):
                return static_file(os.path.basename(file_path), root=os.path.dirname(file_path))
            return HTTPResponse(status=404, body="shared file not found")
        add_route(app, f"/{path}/{shared}/<filepath:path>", "GET", send_shared)
        add_route(app, f"/{shared}/<filepath:path>", "GET", send_shared)

    # Serve static files (flat mount)
    if static:
        def send_static(filepath):
            file_path = gw.resource("data", "static", filepath)
            if os.path.isfile(file_path):
                return static_file(os.path.basename(file_path), root=os.path.dirname(file_path))
            return HTTPResponse(status=404, body="static file not found")
        add_route(app, f"/{path}/{static}/<filepath:path>", "GET", send_static)
        add_route(app, f"/{static}/<filepath:path>", "GET", send_static)
        
    def _maybe_auth(message: str):
        if is_make('web.auth') and not gw.web.auth.is_authorized(strict=auth_required):
            return gw.web.error.unauthorized(message)
        return None

    if views:
        def view_dispatch(view):
            nonlocal home, views
            if (unauth := _maybe_auth("Unauthorized: You are not permitted to view this page.")):
                return unauth
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
            method = request.method.lower()  # 'get' or 'post'
            method_func_name = f"{views}_{method}_{view_name}"
            generic_func_name = f"{views}_{view_name}"

            # Prefer view_get_x/view_post_x before view_x
            view_func = getattr(source, method_func_name, None)
            if not callable(view_func):
                view_func = getattr(source, generic_func_name, None)
            if not callable(view_func):
                return gw.web.error.redirect(f"View not found: {method_func_name} or {generic_func_name} in {project}")

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
        add_route(app, f"/{path}/<view:path>", ["GET", "POST"], view_dispatch)

    # API dispatcher (only if apis is not None)
    if apis:
        def api_dispatch(view):
            nonlocal home, apis
            if (unauth := _maybe_auth("Unauthorized: API access denied.")):
                return unauth
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
                return json.dumps(gw.cast.to_dict(result))
            except HTTPResponse as res:
                return res
            except Exception as e:
                return gw.web.error.redirect("Broken API", err=e)
        add_route(app, f"/api/{path}/<view:path>", ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"], api_dispatch)
            
    if renders:
        def render_dispatch(view, hash):
            nonlocal renders
            if (unauth := _maybe_auth("Unauthorized: Render access denied.")):
                return unauth
            kwargs = dict(request.query)
            gw.context['current_endpoint'] = path

            # Normalize dashes to underscores for Python function names
            func_view = view.replace("-", "_")
            func_hash = hash.replace("-", "_")
            func_name = f"{renders}_{func_hash}"

            # Optionally: Allow render_<view>_<hash> if you want to dispatch more granularly
            #func_name = f"{renders}_{func_view}_{func_hash}"

            render_func = getattr(source, func_name, None)
            if not callable(render_func):
                # Fallback: allow view as prefix, e.g. render_charger_status_charger_list
                alt_func_name = f"{renders}_{func_view}_{func_hash}"
                render_func = getattr(source, alt_func_name, None)
                if not callable(render_func):
                    return gw.web.error.redirect(
                        f"Render function not found: {func_name} or {alt_func_name} in {project}")

            if request.method == "POST":
                try:
                    params = request.json or dict(request.forms) or request.body.read()
                    if params:
                        kwargs.update(gw.cast.to_dict(params))
                except Exception as e:
                    return gw.web.error.redirect("Error loading POST parameters", err=e)

            try:
                result = render_func(**kwargs)
                # Dict: pass through as JSON
                if isinstance(result, dict):
                    response.content_type = "application/json"
                    return json.dumps(result)
                # List: treat as a list of HTML fragments (return as JSON)
                if isinstance(result, list):
                    html_list = [x if isinstance(x, str) else gw.to_html(x) for x in result]
                    response.content_type = "application/json"
                    return json.dumps(html_list)
                # String/bytes: send as plain text (fragment)
                if isinstance(result, (str, bytes)):
                    response.content_type = "text/html"
                    return result
                # Else: fallback to JSON
                response.content_type = "application/json"
                return json.dumps(gw.cast.to_dict(result))
            except HTTPResponse as res:
                return res
            except Exception as e:
                return gw.web.error.redirect("Broken render function", err=e)

        add_route(app, f"/render/{path}/<view>/<hash>", ["GET", "POST"], render_dispatch)

    def favicon():
        proj_parts = project.split('.')
        candidate = gw.resource("data", "static", *proj_parts, "favicon.ico")
        if os.path.isfile(candidate):
            return static_file("favicon.ico", root=os.path.dirname(candidate))
        global_favicon = gw.resource("data", "static", "favicon.ico")
        if os.path.isfile(global_favicon):
            return static_file("favicon.ico", root=os.path.dirname(global_favicon))
        return HTTPResponse(status=404, body="favicon.ico not found")
    add_route(app, "/favicon.ico", "GET", favicon)

    if gw.verbose:
        gw.info(f"Registered homes: {_homes}")
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
    fresh = _format_fresh(_refresh_fresh_date())
    build = ""
    if getattr(gw, "debug_enabled", False):
        try:
            build = f" Build: {gw.release.commit()}"
        except Exception:
            build = ""

    css_files = gw.cast.to_list(css_files)
    theme_css = None
    if is_make('web.nav'):
        try:
            theme_css = gw.web.nav.active_style()
        except Exception:
            theme_css = None
    # <<< Patch: APPEND, don't prepend! >>>
    if theme_css and theme_css not in css_files:
        css_files.append(theme_css)

    css_links = ""
    if css_files:
        for href in css_files:
            css_links += f'<link rel="stylesheet" href="{href}">\n'

    js_files = gw.cast.to_list(js_files)
    js_links = ""
    if js_files:
        for src in js_files:
            js_links += f'<script src="{src}"></script>\n'

    favicon = f'<link rel="icon" href="/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is written in <a href="https://www.python.org/">Python 3.10</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> and <a href="https://github.com/arthexis/gway">Github</a>.</p>
    '''
    nav = gw.web.nav.render(homes=_homes, links=_links) if is_make('web.nav') else ""

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
                    <a href="https://pypi.org/project/gway/{{!version}}/">v{{!version}}</a>,
                    fresh since {{!fresh}}{{!build}}.</p>
                    {{!credits}}
                </footer>
            </div>
            {{!js_links}}
        </body>
        </html>
    """, **locals())
    return html

def default_home():
    for _, route in _homes:
        if route:
            return "/" + route.lstrip("/")
    return "/site/reader"

def debug_routes(app):
    for route in app.routes:
        gw.debug(f"{route.method:6} {route.rule:30} -> {route.callback.__name__}")

def _route_exists(app, rule: str, methods) -> bool:
    methods = gw.cast.to_list(methods)
    for route in app.routes:
        if route.rule == rule and route.method in methods:
            return True
    return False

def add_route(app, rule: str, method, callback):
    """Register route unless already handled."""
    methods = gw.cast.to_list(method or "GET")
    for m in methods:
        key = (m.upper(), rule)
        if key in _registered_routes or _route_exists(app, rule, m):
            gw.debug(f"Skipping duplicate route: {m} {rule}")
            continue
        _registered_routes.add(key)
        app.route(rule, method=m)(callback)

def is_make(project_name):
    global _enabled
    return project_name in _enabled

def add_home(home, path):
    global _homes
    title = home.replace('-', ' ').replace('_', ' ').title()
    route = f"{path}/{home}"
    if (title, route) not in _homes:
        _homes.append((title, route))
        gw.debug(f"Added home: ({title}, {route})")

def add_links(route: str, links=None):
    global _links
    parsed = parse_links(links)
    if parsed:
        _links[route] = parsed
        gw.debug(f"Added links for {route}: {parsed}")

def parse_links(links) -> list[str]:
    if not links:
        return []
    if isinstance(links, str):
        tokens = links.replace(',', ' ').split()
    else:
        try:
            tokens = list(links)
        except Exception:
            tokens = []
    return [t.strip() for t in tokens if t]
