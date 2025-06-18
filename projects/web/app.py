# projects/web/app.py

from urllib.parse import urlencode
import bottle
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw

_version = None
_homes = []  # (title, route)
_enabled = set()
UPLOAD_MB = 100


def setup(*,
    app=None,
    project="web.site",
    path=None,
    home: str = None,
    prefix: str = "view",
    static="static",
    work="work",
    engine="bottle",
):
    global _version, _homes
    if engine != "bottle":
        raise NotImplementedError("Only Bottle is supported at the moment.")

    _version = _version or gw.version()
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
        nonlocal home, prefix
        segments = [s for s in view.strip("/").split("/") if s]
        view_name = segments[0].replace("-", "_") if segments else home
        args = segments[1:] if segments else []
        kwargs = dict(request.query)
        if request.method in ("POST", "PUT"):
            try:
                kwargs.update(request.json or dict(request.forms))
            except Exception as e:
                return redirect_error(e, note="Error loading JSON payload", broken_view_name=view_name)

        target_func_name = f"{prefix}_{view_name}" if prefix else view_name
        view_func = None
        for source in sources:
            view_func = getattr(source, target_func_name, None)
            if callable(view_func):
                if 'url_stack' not in gw.context:
                    gw.context['url_stack'] = []
                gw.context['url_stack'].append((project, path))
                break

        if not callable(view_func):
            return redirect_error(
                note=f"View not found: {target_func_name} in {projects}",
                broken_view_name=view_name,
                default=default_home()
            )

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

        except Exception as e:
            return redirect_error(e, note="Error during view execution", broken_view_name=view_func.__name__, default=default_home())

        return render_template(
            title="GWAY - " + view_func.__name__.replace("_", " ").title(),
            full_url=request.fullpath,
            content=content,
            static=static,
            css_file="base.css"
        )

    @app.route("/", method=["GET", "POST"])
    def index():
        response.status = 302
        response.set_header("Location", default_home())
        return ""

    @app.error(404)
    def handle_404(error):
        return redirect_error(
            error,
            note=f"404 Not Found: {request.url}",
            default=default_home()
        )

    if gw.verbose:
        gw.debug(f"Registered homes: {_homes}")
        debug_routes(app)

    return oapp if oapp else app


def build_url(*args, **kwargs):
    path = "/".join(str(a).strip("/") for a in args if a)
    if 'url_stack' in gw.context and (url_stack := gw.context['url_stack']):
        _, prefix = url_stack[-1]
        url = f"/{prefix}/{path}"
    else:
        url = f"/{path}"
    if kwargs:
        url += "?" + urlencode(kwargs)
    return url

def render_template(*, title="GWAY", full_url="", content="", static="static", css_file=None):
    global _version
    version = _version = _version or gw.version()
    css_links = f'<link rel="stylesheet" href="/{static}/styles/base.css">\n'
    if css_file and css_file != "base.css":
        css_links += f'<link rel="stylesheet" href="/{static}/styles/{css_file}">\n'
    favicon = f'<link rel="icon" href="/{static}/favicon.ico" type="image/x-icon" />'
    credits = f'''
        <p>GWAY is written in <a href="https://www.python.org/">Python 3.13</a>.
        Hosting by <a href="https://www.gelectriic.com/">Gelectriic Solutions</a>, 
        <a href="https://pypi.org">PyPI</a> 
        and <a href="https://github.com/arthexis/gway">Github</a>.</p>
    '''
    if is_enabled('navbar'):
        navbar = gw.web.navbar.render(
            current_url=full_url,
            homes=_homes
        )
    else:
        navbar = ""
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
            <div class="page-wrap">
                <div class="layout">
                    {{!navbar}}<main>{{!content}}</main>
                </div>
                <footer><p>This website was <strong>built</strong>, <strong>tested</strong> 
                    and <strong>released</strong> with <a href="https://arthexis.com">GWAY</a> 
                    <a href="https://pypi.org/project/gway/{{!version}}/">v{{!version}}</a>.</p>
                    {{!credits}}
                </footer>
            </div>

        </body>
        </html>
    """, **locals())


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

def redirect_error(error=None, note="", default=None, broken_view_name=None):
    """
    Unified error redirect: in debug mode, show a debug page; otherwise redirect.
    The default redirect is the primary home as resolved by default_home().
    """
    from bottle import request, response
    import traceback
    import html

    debug_enabled = bool(getattr(gw, "debug", False))
    visited = gw.web.cookies.get("visited", "")
    visited_items = visited.split("|") if visited else []

    # --- Remove broken link from visited on any 404/view-not-found ---
    pruned = False
    if broken_view_name and gw.web.cookies.check_consent():
        norm_broken = (broken_view_name or "").replace("-", " ").replace("_", " ").title().lower()
        new_items = []
        for v in visited_items:
            title = v.split("=", 1)[0].strip().lower()
            if title == norm_broken:
                pruned = True
                continue
            new_items.append(v)
        if pruned:
            gw.web.cookies.set("visited", "|".join(new_items))
            visited_items = new_items  # reflect the change for UI

    # --- DEBUG MODE: show error info as page ---
    if debug_enabled:
        tb_str = ""
        if error:
            tb_str = "".join(traceback.format_exception(type(error), error, getattr(error, "__traceback__", None)))
        debug_content = f"""
        <html>
        <head>
            <title>GWAY Debug: Error</title>
            <style>
                body {{ font-family: monospace, sans-serif; background: #23272e; color: #e6e6e6; }}
                .traceback {{ background: #16181c; color: #ff8888; padding: 1em; border-radius: 5px; margin: 1em 0; white-space: pre; }}
                .kv {{ color: #6ee7b7; }}
                .section {{ margin-bottom: 2em; }}
                h1 {{ color: #ffa14a; }}
                a {{ color: #69f; }}
                .copy-btn {{ margin: 1em 0; background:#333;color:#fff;padding:0.4em 0.8em;border-radius:4px;cursor:pointer;border:1px solid #aaa; }}
            </style>
        </head>
        <body>
            <h1>GWAY Debug Error</h1>
            <div id="debug-content">
                <div class="section"><b>Note:</b> {html.escape(str(note) or "")}</div>
                <div class="section"><b>Error:</b> {html.escape(str(error) or "")}</div>
                <div class="section"><b>Path:</b> {html.escape(request.path or "")}<br>
                                     <b>Method:</b> {html.escape(request.method or "")}<br>
                                     <b>Full URL:</b> {html.escape(request.url or "")}</div>
                <div class="section"><b>Query:</b> {html.escape(str(dict(request.query)) or "")}</div>
                <div class="section"><b>Form:</b> {html.escape(str(getattr(request, "forms", "")) or "")}</div>
                <div class="section"><b>Headers:</b> {html.escape(str(dict(request.headers)) or "")}</div>
                <div class="section"><b>Cookies:</b> {html.escape(str(dict(request.cookies)) or "")}</div>
                <div class="section"><b>Traceback:</b>
                    <div class="traceback">{html.escape(tb_str or '(no traceback)')}</div>
                </div>
            </div>
            <div><a href="{html.escape(default or default_home())}">&#8592; Back to home</a></div>
        </body>
        </html>
        """
        response.status = 500
        response.content_type = "text/html"
        return debug_content

    # --- NON-DEBUG: just redirect ---
    response.status = 302
    response.set_header("Location", default or default_home())
    return ""
