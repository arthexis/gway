# file: projects/web/app.py

# TODO: It was reported that /favicon.ico is missing or returning an error. 
#       Screenshot attached.

import os
from urllib.parse import urlencode
import bottle
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw

_ver = None
_homes = []  # (title, route)
_enabled = set()
UPLOAD_MB = 100

def setup(*,
    app=None,
    project="web.site",
    path=None,
    home: str = None,
    views: str = "view",
    apis: str = "api",
    static="static",
    work="work",
    engine="bottle",
):
    # file: projects/web/app.py
    global _ver, _homes
    if engine != "bottle":
        raise NotImplementedError("Only Bottle is supported at the moment.")

    _ver = _ver or gw.version()
    bottle.BaseRequest.MEMFILE_MAX = UPLOAD_MB * 1024 * 1024

    projects = gw.to_list(project, flat=True)
    sources = []
    for proj_name in projects:
        try:
            sources.append(gw[proj_name])
        except Exception:
            gw.abort(f"Project {proj_name} not found in Gateway during app setup.")

    if path is None:
        path = projects[0].replace('.', '/')
        if path.startswith('web/'):
            path = path.removeprefix('web/')

    for enabled_proj in projects:
        if enabled_proj.startswith('web.'):
            enabled_proj = enabled_proj[4:]
        _enabled.add(enabled_proj)

    is_new_app = not (app := gw.unwrap_one(app, Bottle) if (oapp := app) else None)
    if is_new_app:
        gw.info("No Bottle app found; creating a new Bottle app.")
        app = Bottle()
        _homes.clear()

    if home:
        add_home(home, path)

    # Serve work files (unchanged)
    if work:
        @app.route(f"/{work}/<filename:path>")
        def send_work(filename):
            filename = filename.replace('-', '_')
            return static_file(filename, root=gw.resource("work", "shared"))

    if static:
        # --- Global static (styles and scripts) ---
        @app.route(f"/{static}/styles/<filename:path>")
        def send_global_style(filename):
            return static_file(filename, root=gw.resource("data", "web", "static", "styles"))

        @app.route(f"/{static}/scripts/<filename:path>")
        def send_global_script(filename):
            return static_file(filename, root=gw.resource("data", "web", "static", "scripts"))

        # --- Project static (styles and scripts) ---
        @app.route(f"/{static}/<project>/styles/<filename:path>")
        def send_project_style(project, filename):
            # Security check
            if ".." in project or "/" in project or "\\" in project:
                return HTTPResponse(status=400, body="Bad project name.")
            static_root = gw.resource("data", project, "static", "styles")
            return static_file(filename, root=static_root)

        @app.route(f"/{static}/<project>/scripts/<filename:path>")
        def send_project_script(project, filename):
            if ".." in project or "/" in project or "\\" in project:
                return HTTPResponse(status=400, body="Bad project name.")
            static_root = gw.resource("data", project, "static", "scripts")
            return static_file(filename, root=static_root)

        # --- Project generic static ---
        @app.route(f"/{static}/<project>/<filename:path>")
        def send_project_static(project, filename):
            if ".." in project or "/" in project or "\\" in project:
                return HTTPResponse(status=400, body="Bad project name.")
            static_root = gw.resource("data", project, "static")
            return static_file(filename, root=static_root)
        
    @app.route(f"/{path}/<view:path>", method=["GET", "POST"])
    def view_dispatch(view):
        nonlocal home, views, apis
        segments = [s for s in view.strip("/").split("/") if s]
        view_name = segments[0].replace("-", "_") if segments else home
        args = segments[1:] if segments else []
        kwargs = dict(request.query)
        if request.method == "POST":
            try:
                kwargs.update(request.json or dict(request.forms))
            except Exception as e:
                return gw.web.error.redirect(e, note="Error loading JSON payload", view_name=view_name)

        method = request.method.upper()

        # Main view function
        view_func = None
        target_func_name = f"{views}_{view_name}" if views else view_name
        found_mode = "view"

        # Try view mode first (classic)
        for source in sources:
            func = getattr(source, target_func_name, None)
            if callable(func):
                view_func = func
                found_mode = "view"
                if 'url_stack' not in gw.context:
                    gw.context['url_stack'] = []
                gw.context['url_stack'].append((project, path))
                break

        # If not found, try API mode (api_<method>_<view>, then api_<view>)
        if not callable(view_func) and apis:
            api_func_specific = f"{apis}_{method.lower()}_{view_name}"
            api_func_generic = f"{apis}_{view_name}"
            specific_func = None
            generic_func = None
            for source in sources:
                f_specific = getattr(source, api_func_specific, None)
                f_generic = getattr(source, api_func_generic, None)
                if callable(f_specific) and not specific_func:
                    specific_func = f_specific
                if callable(f_generic) and not generic_func:
                    generic_func = f_generic
            # Prefer specific over generic
            if specific_func:
                view_func = specific_func
                found_mode = "api"
            elif generic_func:
                view_func = generic_func
                found_mode = "api"

        if not callable(view_func):
            return gw.web.error.redirect(
                note=f"View/API not found: {target_func_name} or {apis}_*_{view_name} in {projects}",
                view_name=view_name,
                default=default_home()
            )

        try:
            content = view_func(*args, **kwargs)
            # API mode: return JSON unless HTTPResponse
            if found_mode == "api":
                if isinstance(content, HTTPResponse):
                    return content
                response.content_type = "application/json"
                return gw.to_json(content)
            # VIEW mode: regular template handling
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
            return gw.web.error.redirect(e, note="Broken view", view_name=view_func.__name__, default=default_home())

        # --- CSS selection ---
        css_query = request.query.get('css')
        css_cookie = gw.web.cookies.get("css")
        css = css_query or css_cookie or 'base.css'
        project_name = projects[0].split('.')[-1]  # eg 'site'
        css_files = collect_css_files(
            static=static, 
            project=project_name,
            view_name=view_name,
            css=css,
        )
        js_files = collect_js_files(
            static=static, 
            project=project_name,
            view_name=view_name,
        )
        return render_template(
            title="GWAY - " + view_func.__name__.replace("_", " ").title(),
            content=content,
            static=static,
            css_files=css_files,
            js_files=js_files,  # <-- add this line
        )


    @app.route("/", method=["GET", "POST"])
    def index():
        response.status = 302
        response.set_header("Location", default_home())
        return ""

    @app.error(404)
    def handle_404(error):
        return gw.web.error.redirect(
            error,
            note=f"404 Not Found: {request.url}",
            default=default_home()
        )
    
    @app.route("/favicon.ico")
    def favicon():
        # Extract project from route or default to first project
        project_name = projects[0].split('.')[-1]  # e.g., 'site'
        # Try project-specific favicon first
        project_favicon = gw.resource("data", project_name, "static", "favicon.ico")
        if os.path.isfile(project_favicon):
            return static_file("favicon.ico", root=os.path.dirname(project_favicon))
        # Fallback: serve global favicon
        global_favicon = gw.resource("data", "web", "static", "favicon.ico")
        if os.path.isfile(global_favicon):
            return static_file("favicon.ico", root=os.path.dirname(global_favicon))
        # Not found: 404
        return HTTPResponse(status=404, body="favicon.ico not found")

    if gw.verbose:
        gw.debug(f"Registered homes: {_homes}")
        debug_routes(app)

    return oapp if oapp else app


def build_url(*args, **kwargs):
    path = "/".join(str(a).strip("/") for a in args if a)
    if 'url_stack' in gw.context and (url_stack := gw.context['url_stack']):
        _, views = url_stack[-1]
        url = f"/{views}/{path}"
    else:
        url = f"/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url


def render_template(*, title="GWAY", content="", static="static", css_files=None, js_files=None):
    global _ver
    version = _ver = _ver or gw.version()
    css_links = ""
    if not css_files:
        css_files = [("global", "base.css")]
    for src, fname in css_files:
        if src == "global":
            href = f"/{static}/styles/{fname}"
        else:
            href = f"/{static}/{src}/styles/{fname}"
        css_links += f'<link rel="stylesheet" href="{href}">\n'

    js_links = ""
    if js_files:
        for src, fname in js_files:
            if src == "global":
                src_path = f"/{static}/scripts/{fname}"
            else:
                src_path = f"/{static}/{src}/scripts/{fname}"
            js_links += f'<script src="{src_path}"></script>\n'

    favicon = f'<link rel="icon" href="/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is written in <a href="https://www.python.org/">Python 3.13</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> and <a href="https://github.com/arthexis/gway">Github</a>.</p>
    '''

    nav = ""
    if 'gw' in globals() and hasattr(gw, 'web') and hasattr(gw.web, 'nav') and is_enabled('nav'):
        nav = gw.web.nav.render(
            current_url=gw.web.nav.get_current_url(),
            homes=_homes
        )

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


# Note that the logic for collecting JS and CSS is not the same, for example:
# All web/static/scripts/*.js files found are installed by default in all site pages.
# However only web/static/styles/base.css is fixed, and other *.css files are user options.

def collect_js_files(*, static, project, view_name):
    """
    Collect JS files for the current view:
    - Always include all .js files in global static/scripts/
    - Always include project base.js if exists
    - Always include project <view_name>.js if exists (try both dashed and underscored)
    """
    files = []
    # --- Add all global scripts ---
    global_scripts_path = gw.resource("data", "web", "static", "scripts")
    if os.path.isdir(global_scripts_path):
        for fname in sorted(os.listdir(global_scripts_path)):
            if fname.endswith(".js"):
                files.append(("global", fname))
    # --- Project base.js ---
    proj_base = gw.resource("data", project, "static", "scripts", "base.js")
    if os.path.isfile(proj_base):
        files.append((project, "base.js"))
    # --- Project view-specific JS ---
    vnames = set()
    vnames.add(f"{view_name}.js")
    vnames.add(f"{view_name.replace('-', '_')}.js")
    vnames.add(f"{view_name.replace('_', '-')}.js")
    for candidate in vnames:
        proj_view = gw.resource("data", project, "static", "scripts", candidate)
        if os.path.isfile(proj_view):
            files.append((project, candidate))
    return files

def collect_css_files(*, static, project, view_name, css=None):
    """
    Collect CSS files for the current view:
    - Always include global base.css
    - Always include global selected css (if not base)
    - Always include project base.css (if exists)
    - Always include project <view_name>.css (if exists; view_name may have dashes/underscores)
    """
    files = [("global", "base.css")]
    if css and css != "base.css":
        files.append(("global", css))

    # Always add project base.css if it exists
    proj_base = gw.resource("data", project, "static", "styles", "base.css")
    if os.path.isfile(proj_base):
        files.append((project, "base.css"))

    # Always add project view-specific css if it exists (try both dashed and underscored)
    vnames = set()
    vnames.add(f"{view_name}.css")
    vnames.add(f"{view_name.replace('-', '_')}.css")
    vnames.add(f"{view_name.replace('_', '-')}.css")  # just in case

    for candidate in vnames:
        proj_view = gw.resource("data", project, "static", "styles", candidate)
        if os.path.isfile(proj_view):
            files.append((project, candidate))

    return files
