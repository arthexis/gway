# file: projects/web/app.py
"""Web application dispatcher for GWAY.

`setup_app` registers a project and exposes any ``view_*`` functions under
``/project`` for HTML responses, ``api_*`` under ``/api/project`` for JSON, and
``render_*`` under ``/render/project/<view>/<hash>`` for fragment updates.

Functions can be specialized by HTTP method (``view_get_*``/``view_post_*``) and
multiple view names may be combined with ``+`` in the path to build a mashup.
``render_*`` functions may return HTML or JSON and are ideal for dynamic
refreshes via ``render.js``.
CSS and JavaScript from enabled projects are bundled via
``web.static.collect``. ``setup_app`` defaults to ``mode='collect'`` so pages
load ``/shared/global.css`` and ``/shared/global.js`` automatically. Add
``<view>.css`` or ``<view>.js`` (without the ``view_`` prefix) to
``data/static/<project>`` for view-specific assets and avoid manual ``<link>`` or
``<script>`` tags unless ``mode='manual'`` is requested.
"""

import os
from urllib.parse import urlencode
import bottle
import json
import datetime
import time
import html
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw


_ver = None
_homes = []   # (title, route)
_links: dict[str, list[object]] = {}
_footer_links: dict[str, list[object]] = {}
_enabled = set()
_registered_routes: set[tuple[str, str]] = set()
_fresh_mtime = None
_fresh_dt = None
_build_mtime = None
_build_dt = None
_static_route = "static"
_shared_route = "shared"
_default_include_mode = "collect"
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


def _refresh_build_date():
    """Return cached datetime of BUILD modification, updating cache if needed."""
    global _build_mtime, _build_dt
    try:
        path = gw.resource("BUILD")
        mtime = os.path.getmtime(path)
    except Exception:
        return None
    if _build_mtime != mtime:
        _build_mtime = mtime
        _build_dt = datetime.datetime.fromtimestamp(mtime)
    return _build_dt


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

# TODO: Ensure we can just setup "ocpp" and it will properly know to include all sub-projects.
#       Ie, a package implicitly includes its sub-projects as delegates.

def setup_app(project,
    *,
    app=None,
    path=None,
    home: str = None,
    links=None,
    footer=None,
    views: str = "view",
    apis: str = "api",
    renders: str = "render",
    static="static",
    shared="shared",
    css="global",           # Default CSS (without .css extension)
    js="global",            # Default JS  (without .js extension)
    mode="collect",        # collect | manual | embedded
    auth="disabled",       # Accept "optional"/"disabled" words to disable
    engine="bottle",
    delegates=None,
    **setup_kwargs,
):
    """
    Setup Bottle web application with symmetrical static/shared public folders.
    ``project`` may be a single name or sequence of fallback names. The first
    project found is loaded and used. ``mode`` controls how CSS/JS files are
    included: ``collect`` (default) uses bundled files, ``manual`` links each
    file individually, and ``embedded`` inlines the contents into the page.
    ``footer`` accepts a list of links similar to ``links`` but rendered in the
    page footer instead of the navigation sidebar. Sub-projects of the loaded
    project are always scanned for missing handlers. Use ``delegates`` to
    specify additional fallback projects.
    """
    global _ver, _homes, _enabled, _static_route, _shared_route

    auth_required = str(auth).strip().lower() not in {
        "none", "false", "disabled", "optional"
    }

    if engine != "bottle":
        raise NotImplementedError("Only Bottle is supported at the moment.")

    _ver = _ver or gw.version()
    bottle.BaseRequest.MEMFILE_MAX = UPLOAD_MB * 1024 * 1024
    if static:
        _static_route = static
    if shared:
        _shared_route = shared
    include_mode = str(mode or _default_include_mode).strip().lower()

    project_names = gw.cast.to_list(project)
    if not project_names:
        gw.abort("Project must be a non-empty string or list of names.")

    source = gw.find_project(*project_names)
    if not source:
        gw.abort(
            "Project {} not found in Gateway during app setup.".format(
                ", ".join(project_names)
            )
        )

    delegate_modules = []

    # Always include sub-projects as delegate modules
    try:
        from gway.structs import Project
    except Exception:
        Project = type(source)
    for attr in getattr(source, "__dict__", {}).values():
        if isinstance(attr, Project) and attr not in delegate_modules:
            delegate_modules.append(attr)

    # Extra delegates can be specified explicitly
    for name in gw.cast.to_list(delegates):
        mod = None
        if isinstance(name, str):
            try:
                mod = gw.find_project(name)
            except Exception:
                mod = None
        elif name:
            mod = name
        if mod and mod not in delegate_modules:
            delegate_modules.append(mod)

    modules = [source] + delegate_modules

    def _find_func(name):
        for mod in modules:
            func = getattr(mod, name, None)
            if callable(func):
                return func
        return None

    # Normalize project name to the one actually loaded
    project = getattr(source, "_name", project_names[0])

    # Track project for later global static collection
    _enabled.add(project)

    if home is None and not (_homes and links):
        setup_home_func = getattr(source, "setup_home", None)
        if callable(setup_home_func):
            try:
                home = setup_home_func()
            except Exception as exc:
                gw.warn(f"{project}.setup_home failed: {exc}")

    if links is None:
        setup_links_func = getattr(source, "setup_links", None)
        if callable(setup_links_func):
            try:
                links = setup_links_func()
            except Exception as exc:
                gw.warn(f"{project}.setup_links failed: {exc}")

    # Default path is the dotted project name
    if path is None:
        path = project.replace('.', '/')
            
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
        _footer_links.clear()
        _registered_routes.clear()
        _enabled.clear()
        _enabled.add(project)
        if home:
            add_home(home, path, project)
            add_links(f"{path}/{home}", links, project)
            add_footer_links(f"{path}/{home}", footer, project)

        def index():
            response.status = 302
            response.set_header("Location", default_home())
            return ""
        add_route(app, "/", ["GET", "POST"], index)

        @app.error(404)
        def handle_404(error):
            return gw.web.error.redirect(f"404 Not Found: {request.url}", err=error)
    
    elif home:
        add_home(home, path, project)
        add_links(f"{path}/{home}", links, project)
        add_footer_links(f"{path}/{home}", footer, project)
    elif links and _homes:
        add_links(_homes[-1][1], links, project)
    elif footer and _homes:
        add_footer_links(_homes[-1][1], footer, project)

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
        if is_setup('web.auth') and not gw.web.auth.is_authorized(strict=auth_required):
            return gw.web.error.unauthorized(message)
        return None

    if views:
        def _looks_like_document(text: str) -> bool:
            if not isinstance(text, str):
                return False
            check = text.lstrip().lower()
            return check.startswith("<!doctype") or check.startswith("<html")

        def view_dispatch(view):
            nonlocal home, views
            request.environ['gw.include_mode'] = include_mode
            if (
                unauth := _maybe_auth(
                    "Unauthorized: You are not permitted to view this page."
                )
            ):
                return unauth
            # Set current endpoint in GWAY context (for helpers/build_url etc)
            gw.context["current_endpoint"] = path

            segments = [s for s in view.strip("/").split("/") if s]
            raw_names = segments[0] if segments else home
            view_names = [n.replace("-", "_") for n in raw_names.replace("+", " ").split()]
            args = segments[1:] if segments else []
            kwargs = dict(request.query)
            if request.method == "POST":
                try:
                    kwargs.update(request.json or dict(request.forms))
                except Exception as e:
                    return gw.web.error.redirect("Error loading JSON payload", err=e)

            method = request.method.lower()  # 'get' or 'post'
            contents = []
            titles = []

            for view_name in view_names:
                method_func_name = f"{views}_{method}_{view_name}"
                generic_func_name = f"{views}_{view_name}"

                # Prefer view_get_x/view_post_x before view_x
                view_func = _find_func(method_func_name)
                if not callable(view_func):
                    view_func = _find_func(generic_func_name)
                if not callable(view_func):
                    return gw.web.error.redirect(
                        f"View not found: {method_func_name} or {generic_func_name} in {project}"
                    )
                _record_includes(view_func)

                try:
                    content = view_func(*args, **kwargs)
                    if isinstance(content, HTTPResponse):
                        return content
                    elif isinstance(content, bytes):
                        response.content_type = "application/octet-stream"
                        response.body = content
                        return response
                    elif content is None:
                        content = ""
                    elif not isinstance(content, str):
                        content = gw.cast.to_html(content)
                except HTTPResponse as res:
                    return res
                except Exception as e:
                    return gw.web.error.redirect("Broken view", err=e)

                if _looks_like_document(content):
                    if contents:
                        gw.warning(
                            f"Mashup aborted: {view_name} returned full document, previous output discarded"
                        )
                    return content

                contents.append(content)
                titles.append(view_func.__name__.replace("_", " ").title())

            final_content = "".join(contents)
            media_origin = "/shared" if shared else ("static" if static else "")
            if include_mode == "collect":
                css_files = (f"{media_origin}/{css}.css",) if css else None
                js_files = (f"{media_origin}/{js}.js",) if js else None
            else:
                css_files = None
                js_files = None
            return render_template(
                title="GWAY - " + " + ".join(titles),
                content=final_content,
                css_files=css_files,
                js_files=js_files,
                mode=include_mode,
            )

        def index_dispatch():
            return view_dispatch("index")

        add_route(app, f"/{path}", ["GET", "POST"], index_dispatch)
        add_route(app, f"/{path}/", ["GET", "POST"], index_dispatch)
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

            api_func = _find_func(specific_af)
            if not callable(api_func):
                api_func = _find_func(generic_af)
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

            render_func = _find_func(func_name)
            if not callable(render_func):
                # Fallback: allow view as prefix, e.g. render_charger_status_charger_list
                alt_func_name = f"{renders}_{func_view}_{func_hash}"
                render_func = _find_func(alt_func_name)
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
                    html_list = [x if isinstance(x, str) else gw.cast.to_html(x) for x in result]
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

        if views:
            def render_view_dispatch(view):
                nonlocal views, home
                if (unauth := _maybe_auth("Unauthorized: Render view access denied.")):
                    return unauth
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
                method_func_name = f"{views}_{method}_{view_name}"
                generic_func_name = f"{views}_{view_name}"

                view_func = _find_func(method_func_name)
                if not callable(view_func):
                    view_func = _find_func(generic_func_name)
                if not callable(view_func):
                    return gw.web.error.redirect(
                        f"View not found: {method_func_name} or {generic_func_name} in {project}")
                _record_includes(view_func)

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
                        content = gw.cast.to_html(content)
                    response.content_type = "text/html"
                    return content
                except HTTPResponse as res:
                    return res
                except Exception as e:
                    return gw.web.error.redirect("Broken view", err=e)

            add_route(app, f"/render/{path}/<view:path>", ["GET", "POST"], render_view_dispatch)

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

    # --- Call project-level setup_app if defined ---
    project_setup = getattr(source, "setup_app", None)
    if callable(project_setup) and project_setup is not setup_app:
        gw.verbose(f"Delegating to {project}.setup_app")
        try:
            maybe_app = project_setup(app=app, **setup_kwargs)
            if maybe_app is not None:
                app = maybe_app
        except Exception as exc:
            gw.warn(f"{project}.setup_app failed: {exc}")
    elif setup_kwargs:
        gw.error(
            f"Extra setup arguments ignored for {project}: {', '.join(setup_kwargs.keys())}"
        )

    return oapp if oapp else app

# Use current_endpoint to get the current project route
def build_url(*args, **kwargs):
    path_parts = [str(a).strip("/") for a in args if a]
    if path_parts and (
        len(path_parts) > 1 or "." in path_parts[0] or "/" in path_parts[0]
    ):
        first = path_parts.pop(0).replace(".", "/")
        path = "/".join([first] + path_parts)
        url = f"/{path}" if path else "/"
    else:
        path = "/".join(path_parts)
        endpoint = current_endpoint()
        url = f"/{endpoint}/{path}" if endpoint and path else (
            f"/{endpoint}" if endpoint else f"/{path}"
        )
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url

def render_template(*, title="GWAY", content="", css_files=None, js_files=None, mode=None):
    global _ver
    version = _ver = _ver or gw.version()
    if getattr(gw, "debug_enabled", False):
        dt = _refresh_build_date()
    else:
        dt = _refresh_fresh_date()
    fresh = _format_fresh(dt)
    build = ""
    if getattr(gw, "debug_enabled", False):
        try:
            build = f" Build: {gw.hub.commit()}"
        except Exception:
            build = ""

    mode = str(mode or getattr(request, 'environ', {}).get('gw.include_mode') or _default_include_mode).lower()
    extra_css = request.environ.get("gw.include_css", [])
    extra_js = request.environ.get("gw.include_js", [])

    css_files = [c for c in gw.cast.to_list(css_files) if c] if mode == "collect" else []
    js_files = [j for j in gw.cast.to_list(js_files) if j] if mode == "collect" else []
    theme_css = None
    if is_setup('web.nav'):
        try:
            theme_css = gw.web.nav.active_style()
        except Exception:
            theme_css = None

    css_links = ""
    js_links = ""

    if mode == "collect":
        if theme_css and theme_css not in css_files:
            css_files.append(theme_css)
        for href in css_files:
            css_links += f'<link rel="stylesheet" href="{href}">\n'
        for src in js_files:
            js_links += f'<script src="{src}"></script>\n'
    elif mode == "manual":
        css_refs = [f"/{_static_route}/" + str(p).lstrip("/") for p in extra_css]
        if theme_css:
            css_refs.append(theme_css)
        for href in css_refs:
            css_links += f'<link rel="stylesheet" href="{href}">\n'
        for src in [f"/{_static_route}/" + str(p).lstrip("/") for p in extra_js]:
            js_links += f'<script src="{src}"></script>\n'
    else:  # embedded
        css_paths = [gw.resource("data", "static", p) for p in extra_css]
        if theme_css:
            parts = theme_css.lstrip("/").split("/")
            if parts and parts[0] == _static_route:
                css_paths.append(gw.resource("data", "static", *parts[1:]))
            elif parts and parts[0] == _shared_route:
                css_paths.append(gw.resource("work", "shared", *parts[1:]))
        for path in css_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    css_links += f"<style>\n{f.read()}\n</style>\n"
            except Exception:
                gw.debug(f"Missing CSS to embed: {path}")
        js_paths = [gw.resource("data", "static", p) for p in extra_js]
        for path in js_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    js_links += f"<script>\n{f.read()}\n</script>\n"
            except Exception:
                gw.debug(f"Missing JS to embed: {path}")

    favicon = f'<link rel="icon" href="/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is written in <a href="https://www.python.org/">Python 3.10</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> and <a href="https://github.com/arthexis/gway">Github</a>.</p>
    '''
    nav = gw.web.nav.render(homes=_homes, links=_links) if is_setup('web.nav') else ""
    nav_side = gw.web.nav.side() if is_setup('web.nav') else "left"

    debug_html = ""
    if getattr(gw, "debug_enabled", False):
        debug_html = """
            <div id='gw-debug-overlay' style='display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);color:#fff;overflow:auto;z-index:10000;padding:1em;'>
                <div style='text-align:right;'><a href='#' id='gw-debug-close' style='color:#fff;text-decoration:none;'>[x] Close</a></div>
                <div id='gw-debug-content'>Loading...</div>
            </div>
            <div id='gw-debug-btn' style='position:fixed;bottom:1em;right:1em;background:#333;color:#fff;border-radius:50%;padding:0.4em 0.6em;cursor:pointer;z-index:10001;font-weight:bold;'>&#9881;?</div>
            <script>
            (function(){
                var btn=document.getElementById('gw-debug-btn');
                var overlay=document.getElementById('gw-debug-overlay');
                var close=document.getElementById('gw-debug-close');
                function show(){
                    overlay.style.display='block';
                    fetch('/render/web/site/debug_info').then(r=>r.text()).then(t=>{document.getElementById('gw-debug-content').innerHTML=t;});
                }
                btn.addEventListener('click',function(e){e.preventDefault();show();});
                close.addEventListener('click',function(e){e.preventDefault();overlay.style.display='none';});
            })();
            </script>
        """

    message_html = gw.web.message.render() if is_setup('web.message') else ""
    footer_links_html = render_footer_links()

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
                <div class="layout{{' nav-right' if nav_side == 'right' else (' nav-top' if nav_side == 'top' else '')}}">
                    % if nav_side == 'right':
                    <main>{{!message_html}}{{!content}}</main>{{!nav}}
                    % elif nav_side == 'top':
                    {{!nav}}<main>{{!message_html}}{{!content}}</main>
                    % else:
                    {{!nav}}<main>{{!message_html}}{{!content}}</main>
                    % end
                </div>
                <footer>{{!footer_links_html}}<p>This website was <strong>built</strong>, <strong>tested</strong>
                    and <strong>released</strong> with <a href="https://arthexis.com">GWAY</a>
                    <a href="https://pypi.org/project/gway/{{!version}}/">v{{!version}}</a>,
                    fresh since {{!fresh}}{{!build}}.</p>
            {{!credits}}
                </footer>
            </div>
            {{!debug_html}}
            {{!js_links}}
        </body>
        </html>
    """, **locals())
    return html

def default_home():
    for _, route in _homes:
        if route:
            return "/" + route.lstrip("/")
    return "/web/site/reader"

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

def _record_includes(func):
    """Record CSS/JS includes for the current request if present."""
    css = getattr(func, "_include_css", [])
    js = getattr(func, "_include_js", [])
    if css:
        request.environ.setdefault("gw.include_css", set()).update(css)
    if js:
        request.environ.setdefault("gw.include_js", set()).update(js)

def is_setup(project_name):
    global _enabled
    return project_name in _enabled

def add_home(home, path, project=None):
    global _homes
    if home.lower() == "index" and project:
        title_src = project
    else:
        title_src = home
    title = title_src.replace('.', ' ').replace('-', ' ').replace('_', ' ').title()
    route = f"{path}/{home}"
    if (title, route) not in _homes:
        _homes.append((title, route))
        gw.debug(f"Added home: ({title}, {route})")

def add_links(route: str, links=None, project: str | None = None):
    global _links
    parsed = parse_links(links)
    if parsed:
        if project:
            parsed = [
                (project, item) if not isinstance(item, tuple) else item
                for item in parsed
            ]
        existing = _links.get(route, [])
        _links[route] = existing + parsed
        gw.debug(f"Added links for {route}: {_links[route]}")

def add_footer_links(route: str, links=None, project: str | None = None):
    global _footer_links
    parsed = parse_links(links)
    if parsed:
        if project:
            parsed = [
                (project, item) if not isinstance(item, tuple) else item
                for item in parsed
            ]
        existing = _footer_links.get(route, [])
        _footer_links[route] = existing + parsed
        gw.debug(f"Added footer links for {route}: {_footer_links[route]}")

def parse_links(links) -> list[object]:
    if not links:
        return []
    if isinstance(links, str):
        tokens = links.replace(',', ' ').split()
    else:
        try:
            tokens = list(links)
        except Exception:
            tokens = []
    result: list[object] = []
    for t in tokens:
        token = str(t).strip()
        if not token:
            continue
        if ':' in token:
            proj, view = token.split(':', 1)
            result.append((proj.strip(), view.strip()))
        else:
            result.append(token)
    return result

def render_footer_links() -> str:
    items = []
    for _, route in _homes:
        sub = _footer_links.get(route)
        if not sub:
            continue
        proj_root = route.rsplit('/', 1)[0] if '/' in route else route
        for name in sub:
            if isinstance(name, tuple):
                proj, view = name
                href = f"{proj.replace('.', '/')}/{view}".strip('/')
                label = view.replace('-', ' ').replace('_', ' ').title()
            else:
                href = f"{proj_root}/{name}".strip('/')
                label = name.replace('-', ' ').replace('_', ' ').title()
            items.append(f'<a href="/{href}">{label}</a>')
    cookbook = gw.web.app.build_url("web", "site", "gateway-cookbook")
    items.append(f'<a href="{cookbook}">Gateway Cookbook</a>')
    return '<p class="footer-links">' + ' | '.join(items) + '</p>' if items else ""
