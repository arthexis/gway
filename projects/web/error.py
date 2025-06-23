from gway import gw

def redirect(error=None, *, note="", default=None, view_name=None):
    from bottle import request, response
    import traceback
    import html

    debug_enabled = bool(getattr(gw, "debug", False))
    visited = gw.web.cookies.get("visited", "")
    visited_items = visited.split("|") if visited else []

    pruned = False
    if view_name and gw.web.cookies.check_consent():
        norm_broken = (view_name or "").replace("-", " ").replace("_", " ").title().lower()
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
            <div><a href="{html.escape(default or gw.web.app.default_home())}">&#8592; Back to home</a></div>
        </body>
        </html>
        """
        response.status = 500
        response.content_type = "text/html"
        return debug_content

    response.status = 302
    response.set_header("Location", default or gw.web.app.default_home())
    return ""

