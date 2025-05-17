import os
import uuid
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

        if not cookies_enabled():
            visited = ["gway"]
        links = "".join(
            f'<li><a href="/{b.replace("_", "-")}">{b.replace("_", " ").replace("-", " ").title()}</a></li>'
            for b in sorted(visited) if b
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

    def render_template(*, title="GWAY", navbar="", content="", css_files=None):
        nonlocal version
        css_files = css_files or ["default.css"]

        css_links = "\n".join(
            f'<link rel="stylesheet" href="/static/styles/{css}">'
            for css in css_files
        )

        return template("""<!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8" />
                <title>{{!title}}</title>
                {{!css_links}}
                <link rel="icon" href="/static/favicon.ico" type="image/x-icon" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            </head>
            <body>
                {{!navbar}}
                <main>{{!content}}</main>
                <br/><footer><p>This website was built, tested and released with GWAY v{{!version}}.</p>
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
        response.set_header("Location", "/gway")
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
            gw.info(f"Dispatching to function {view_func}")
            content = view_func(*args, **kwargs)
            visited = update_visited(view_name)
        except HTTPResponse as res:
            return res
        except Exception as e:
            gw.exception(e)  # Redirect to /gway on any error after logging
            response.status = 302
            response.set_header("Location", "/gway")
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

        css_cookie = request.get_cookie("css", "")  # e.g. "dark-mode.css"
        css_files = ["default.css"] + [f.strip() for f in css_cookie.split(",") if f.strip()]
        return render_template(navbar=navbar, content=content, css_files=css_files)
    
    app = security_middleware(app)
    return app


# TODO: Merge setup_forms_app into setup_app, including giving it the forms_dir
# results_dir and route_prefix. 


@requires("markdown", "bottle")
def setup_forms_app(*,
    app=None,
    forms_dir="data/forms",
    results_dir="temp/result",
    route_prefix="/form"
):
    import markdown
    from bottle import Bottle, static_file, request, redirect
    from gway import process_commands, load_batch

    """
    Sets up a Bottle app that serves .gws forms at /form/<form-name> and POSTs results.

    Args:
        app: An optional Bottle app to attach routes to.
        forms_dir: Directory (relative to resource root) where .gws files are stored.
        results_dir: Directory (relative to resource root) for storing result HTML.
        route_prefix: URL prefix for form and result routes.

    Returns:
        Configured Bottle app.
    """
    if app is None:
        app = Bottle()

        @app.route("/")
        def index_redirect():
            redirect(route_prefix + "s")  # e.g., "/forms"

    form_path = lambda name: gw.resource(forms_dir, f"{name}.gws")
    result_path = lambda name: gw.resource(results_dir, f"{name}.html")
    result_url = lambda name: f"{route_prefix}/results/{name}.html"

    os.makedirs(gw.resource(results_dir), exist_ok=True)

    @app.route(f"{route_prefix}/results/<filename>")
    def show_result(filename):
        return static_file(filename, root=gw.resource(results_dir))

    @app.route(f"{route_prefix}/<form_name>", method="GET")
    def show_form(form_name):
        script_file = form_path(form_name)
        if not os.path.isfile(script_file):
            return f"<p>Form '{form_name}' not found.</p>"

        commands, comments = load_batch(script_file)

        # Extract instructions from comments
        instructions = "\n".join(c[1:].strip() for c in comments)
        html_instructions = markdown.markdown(instructions)

        # Extract fields from commands
        fields = set()

        def collect_fields(chunk):
            for tok in chunk[1:]:
                if tok.startswith("{") and tok.endswith("}"):
                    fields.add(tok[1:-1])
            return False

        process_commands(commands, callback=collect_fields)

        form_fields = "\n".join(
            f'<label>{field}: <input name="{field}" required></label><br>'
            for field in sorted(fields)
        )

        return f"""
        <html><body>
        <h2>Form: {form_name}</h2>
        <div>{html_instructions}</div><br>
        <form method="POST">
            {form_fields}
            <br><button type="submit">Submit</button>
        </form>
        </body></html>
        """

    @app.route(f"{route_prefix}/<form_name>", method="POST")
    def submit_form(form_name):
        script_file = form_path(form_name)
        if not os.path.isfile(script_file):
            return f"<p>Form '{form_name}' not found.</p>"

        commands, _ = load_batch(script_file)
        form_data = dict(request.forms)
        txn_id = str(uuid.uuid4())

        # Run commands using form data
        results, _ = process_commands(
            commands,
            callback=lambda chunk: True,
            **form_data
        )

        result_html = f"""
        <html><body>
        <p><a href="{route_prefix}/{form_name}">&larr; Back to form</a></p>
        <h2>Results</h2>
        <pre>{results}</pre>
        </body></html>
        """

        with open(result_path(txn_id), "w") as f:
            f.write(result_html)

        redirect(result_url(txn_id))

    @app.route(route_prefix, method="GET")
    @app.route(route_prefix + "s", method="GET")
    def list_forms():
        forms_root = gw.resource(forms_dir)
        form_files = [
            f for f in os.listdir(forms_root)
            if f.endswith(".gws") and os.path.isfile(os.path.join(forms_root, f))
        ]

        entries = []
        for filename in sorted(form_files):
            name = filename[:-4]  # remove .gws
            path = os.path.join(forms_root, filename)
            with open(path, encoding="utf-8") as f:
                hint = ""
                for line in f:
                    line = line.strip()
                    if line.startswith("#") and len(line) > 1:
                        hint = line[1:].strip()
                        break
            entries.append((name, hint))

        links_html = "\n".join(
            f"<p><a href='{route_prefix}/{name}'>{name}</a><br><small>{hint}</small></p>"
            for name, hint in entries
        )

        return f"""
        <html><body>
        <h2>Available Forms</h2>
        {links_html}
        </body></html>
        """

    return app

