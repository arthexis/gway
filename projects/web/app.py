# projects/web/app.py

import os
from functools import wraps
from urllib.parse import urlencode
from bottle import Bottle, static_file, request, response, template, HTTPResponse
from gway import gw

# TODO: Whenever a broken view is visited, before redirecting to the home view,
# If the current broken view is on the cookies for the navbar, purge it.

# TODO: A special prefix "*" or ... (elipsis) can be used to denote "all functions without prefix"
# When passed to param prefix. This would allow invoking _all_ functions in a project without
# checking the prefix at all (watch out for the underscore in the middle of {prefix}_{view_name})

def setup(*,
    app=None,
    project="web.site",
    path=None,
    static="static",
    work="work",
    home: str = "readme",
    prefix: str = "view",
):    
    """
    Configure one or more Bottle apps to work with GWAY.
    Accepts either `app=` keyword, `*apps` positional, or both.
    If multiple Bottle apps are passed, a tuple is returned.
    This version allows `project` to be either a string or an iterable of project names.
    """
    # Normalize `project` into a list of project names
    if isinstance(project, str):
        projects = [project]
    else:
        try:
            projects = list(project)
        except TypeError:
            # Fallback: treat as single string if not iterable
            projects = [str(project)]

    # Determine default `path` if not provided
    if path is None:
        first_proj = projects[0]
        path = "gway" if first_proj == "web.site" else first_proj.replace(".", "/")

    version = gw.version()
    _is_new_app = not (app := gw.unwrap(app, Bottle) if (oapp := app) else None)
    gw.info(f"Unwrapped {app=} from {oapp=} ({_is_new_app=})")

    if _is_new_app:
        gw.info("No Bottle app found; creating a new Bottle app.")
        app = Bottle()

        # Define URL-building helpers
        gw.web.static_url = lambda *args, **kwargs: build_url(static, *args, **kwargs)
        gw.web.work_url = lambda *args, **kwargs: build_url(work, *args, **kwargs)
        gw.web.app_url = lambda *args, **kwargs: build_url(path, *args, **kwargs)
        gw.web.redirect_error = redirect_error

        def security_middleware(app):
            def wrapped_app(environ, start_response):
                def custom_start_response(status, headers, exc_info=None):
                    headers = [(k, v) for k, v in headers if k.lower() != "server"]
                    headers += [
                        ("Cache-Control", "no-cache"),
                        ("X-Content-Type-Options", "nosniff"),
                        ("Server", f"GWAY v{version}"),
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

    def cookies_enabled():
        return request.get_cookie("cookies_accepted") == "yes"

    def update_visited(current, cookie_name="visited"):
        if not cookies_enabled():
            return []
        raw = request.get_cookie(cookie_name, "")
        visited = raw.split("|") if raw else []

        title = current.replace("-", " ").replace("_", " ").title()
        visited = [v for v in visited if not v.startswith(f"{title}=")]
        route = request.fullpath.lstrip("/")
        visited.append(f"{title}={route}")

        cookie_value = "|".join(visited)
        response.set_cookie(cookie_name, cookie_value)
        return visited

    def render_navbar(visited, current_url=None):
        if not cookies_enabled() or len(visited) < 1:
            visited = ["Readme=readme"]

        links = ""
        seen = set()
        for entry in reversed(visited):
            if "=" not in entry:
                continue
            title, route = entry.split("=", 1)
            if title in seen:
                continue
            seen.add(title)
            links += f'<li><a href="/{route}">{title}</a></li>'

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

        styles_dir = gw.resource("data", "static", "styles")
        available_styles = sorted(
            f for f in os.listdir(styles_dir)
            if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
        )

        current_style = request.get_cookie("css") or "default.css"
        options = "\n".join(
            f'<option value="{s}"{" selected" if s == current_style else ""}>{s[:-4]}</option>'
            for s in available_styles
        )
        style_selector = f'''
            <form method="get" class="style-form">
                <label for="css-style">Style:</label>
                <select id="css-style" name="css" class="style-selector" onchange="this.form.submit()">
                    {options}
                </select>
                <noscript><button type="submit">Set</button></noscript>
            </form>
        '''

        return f"<aside>{search_box}<ul>{links}</ul><br>{qr_html}<br>{style_selector}</aside>"

    def render_template(*, title="GWAY", navbar="", content="", css_files=None):
        nonlocal version
        css_files = css_files or ["default.css"]
        css_links = "\n".join(
            f'<link rel="stylesheet" href="/{static}/styles/{css}">' for css in css_files
        )
        favicon = f'<link rel="icon" href="/{static}/favicon.ico" type="image/x-icon" />'
        credits = f'''
            <p>GWAY is powered by <a href="https://www.python.org/">Python 3.13</a>.
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

    if static:
        @app.route(f"/{static}/<filename:path>")
        def send_static(filename):
            return static_file(filename, root=gw.resource("data", "static"))

    if work:
        @app.route(f"/{work}/<filename:path>")
        def send_work(filename):
            filename = filename.replace('-', '_')
            return static_file(filename, root=gw.resource("work", "shared"))

    @app.route(f"/{path}/<view:path>", method=["GET", "POST"])
    def view_dispatch(view):
        segments = [s for s in view.strip("/").split("/") if s]
        if not segments:
            segments = [home]
        view_name = segments[0].replace("-", "_")
        args = segments[1:]
        kwargs = dict(request.query)
        if request.method == "POST":
            try:
                if request.json:
                    kwargs.update(request.json)
                elif request.forms:
                    kwargs.update(request.forms.decode())
            except Exception as e:
                return redirect_error(e, note="Error loading JSON payload")

        # Attempt to dispatch the view across all specified projects
        sources = []
        for proj_name in projects:
            try:
                sources.append(gw[proj_name])
            except Exception as e:
                # Skip projects that fail to load, but you could also log/warn here
                continue

        for source in sources:
            view_func = getattr(source, f"{prefix}_{view_name}", None)
            if callable(view_func):
                break
        else:
            return redirect_error(
                note=f"View '{prefix}_{view_name}' not found in any project: {projects}"
            )

        try:
            gw.info(f"Dispatch to view {view_func.__name__} (args={args}, kwargs={kwargs})")
            content = view_func(*args, **kwargs)
            if content and not isinstance(content, str):
                content = gw.to_html(content)
            visited = update_visited(view_name)
        except HTTPResponse as resp:
            return resp
        except Exception as e:
            return redirect_error(e, note="Error during view execution")

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

        style_param = request.query.get("css") or request.query.get("style")
        if style_param:
            if not style_param.endswith(".css"):
                style_param += ".css"
            response.set_cookie("css", style_param, path="/")
            css_files = ["default.css", style_param]
        else:
            css_cookie = request.get_cookie("css", "")
            css_files = ["default.css"] + [c.strip() for c in css_cookie.split(",") if c.strip()]

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
    
    @app.error(404)
    def handle_404(error):
        fallback = "/gway/readme"
        try:
            return redirect_error(
                error,
                note=f"404 Not Found: {request.url}",
                default=f"/{path}/{home}" if path and home else fallback
            )
        except Exception as e:
            return redirect_error(e, note="Failed during 404 fallback", default=fallback)

    if _is_new_app:
        app = security_middleware(app)
        return app if not oapp else (oapp, app)
    
    return oapp


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
