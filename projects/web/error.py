# file: projects/web/error.py

from gway import gw

def view_debug_error(
    *,
    title="GWAY Debug Error",
    message="An error occurred.",
    err=None,
    status=500,
    default=None
):
    """
    Render a debug error view with detailed traceback and request info.
    """
    from bottle import request, response
    import traceback
    import html

    tb_str = ""
    if err:
        tb_str = "".join(traceback.format_exception(type(err), err, getattr(err, "__traceback__", None)))

    debug_content = f"""
    <html>
    <head>
        <title>{html.escape(title)}</title>
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
        <h1>{html.escape(title)}</h1>
        <div id="debug-content">
            <div class="section"><b>Message:</b> {html.escape(str(message) or "")}</div>
            <div class="section"><b>Error:</b> {html.escape(str(err) or "")}</div>
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
        <div><a href="{html.escape(default or gw.web.app.default_home())}">&#8592; Back to home</a></div>
    </body>
    </html>
    """
    response.status = status
    response.content_type = "text/html"
    return debug_content

def redirect(message="", *, err=None, default=None, view_name=None):
    """
    GWAY error/redirect handler.
    Deprecated: 'view_name'. Now uses gw.web.app.current_endpoint.
    """
    from bottle import request, response

    debug_enabled = bool(getattr(gw, "debug", False))
    visited = gw.web.cookies.get("visited", "")
    visited_items = visited.split("|") if visited else []

    # --- DEPRECATED: view_name, use gw.web.app.current_endpoint instead ---
    if view_name is not None:
        import warnings
        warnings.warn(
            "redirect(): 'view_name' is deprecated. Use gw.web.app.current_endpoint instead.",
            DeprecationWarning
        )
    curr_view = getattr(gw.web.app, "current_endpoint", None)
    view_key = curr_view() if callable(curr_view) else curr_view
    if not view_key and view_name:
        view_key = view_name

    pruned = False
    if view_key and gw.web.cookies.check_consent():
        norm_broken = (view_key or "").replace("-", " ").replace("_", " ").title().lower()
        new_items = []
        for v in visited_items:
            title = v.split("=", 1)[0].strip().lower()
            if title == norm_broken:
                pruned = True
                continue
            new_items.append(v)
        if pruned:
            gw.web.cookies.set("visited", "|".join(new_items))
            visited_items = new_items

    if debug_enabled:
        return view_debug_error(
            title="GWAY Debug Error",
            message=message,
            err=err,
            status=500,
            default=default
        )

    response.status = 302
    response.set_header("Location", default or gw.web.app.default_home())
    return ""

def unauthorized(message="Unauthorized: You do not have access to this resource.", *, err=None, default=None):
    """
    If in debug mode: show detailed error.
    If not in debug: return a 401 Unauthorized and a WWW-Authenticate header to trigger the browser auth dialog.
    """
    from bottle import response

    debug_enabled = bool(getattr(gw, "debug", False))
    if debug_enabled:
        return view_debug_error(
            title="401 Unauthorized",
            message=message,
            err=err,
            status=401,
            default=default
        )

    # 401 with auth header = browser will prompt for password
    response.status = 401
    response.headers['WWW-Authenticate'] = 'Basic realm="GWAY"'
    response.content_type = "text/plain"
    return message
