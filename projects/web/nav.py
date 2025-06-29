# file: projects/web/nav.py

import os
from gway import gw
from bottle import request

def render(*, homes=None):
    """
    Renders the sidebar navigation including search, home links, visited links, and a QR compass.
    """
    cookies_ok = gw.web.app.is_setup('web.cookies') and gw.web.cookies.check_consent()
    gw.debug(f"Render nav with {homes=} {cookies_ok=}")

    visited = []
    if cookies_ok:
        visited_cookie = gw.web.cookies.get("visited", "")
        if visited_cookie:
            visited = visited_cookie.split("|")

    current_route = request.fullpath.strip("/")
    current_title = (current_route.split("/")[-1] or "readme").replace('-', ' ').replace('_', ' ').title()

    visited_set = set()
    entries = []
    for entry in visited:
        if "=" not in entry:
            continue
        title, route = entry.split("=", 1)
        canon_route = route.strip("/")
        if canon_route not in visited_set:
            entries.append((title, canon_route))
            visited_set.add(canon_route)

    home_routes = set()
    if homes:
        for home_title, home_route in homes:
            home_routes.add(home_route.strip("/"))
    if cookies_ok and current_route not in home_routes and current_route not in visited_set:
        entries.append((current_title, current_route))
        visited_set.add(current_route)

    # --- Build HTML links ---
    links = ""
    if homes:
        for home_title, home_route in homes:
            route = home_route.strip("/")
            is_current = ' class="current"' if route == current_route else ""
            links += f'<li><a href="/{home_route}"{is_current}>{home_title.upper()}</a></li>'
    if cookies_ok and entries:
        visited_rendered = set()
        for title, route in reversed(entries):
            if route in home_routes or route in visited_rendered:
                continue
            visited_rendered.add(route)
            is_current = ' class="current"' if route == current_route else ""
            links += f'<li><a href="/{route}"{is_current}>{title}</a></li>'
    elif not homes:
        links += f'<li class="current">{current_title.upper()}</li>'

    # --- Search box ---
    search_box = '''
        <form action="/site/help" method="get" class="nav">
            <textarea name="topic" id="help-search"
                placeholder="Search this GWAY"
                class="help" rows="1"
                autocomplete="off"
                spellcheck="false"
                style="overflow:hidden; resize:none; min-height:2.4em; max-height:10em;"
                oninput="autoExpand(this)"
            >{}</textarea>
        </form>
    '''.format(request.query.get("topic", ""))

    # --- QR code for this page ---
    compass = ""
    try:
        url = current_url()
        qr_url = gw.qr.generate_url(url)
        compass = f'''
            <div class="compass">
                <img src="{qr_url}" alt="QR Code" class="compass" />
            </div>
        '''
    except Exception as e:
        gw.debug(f"Could not generate QR compass: {e}")

    gw.debug(f"Visited cookie raw: {gw.web.cookies.get('visited')}")
    return f"<aside>{search_box}<ul>{links}</ul><br>{compass}</aside>"

def active_style():
    """
    Returns the current user's preferred style path (to .css file), checking:
    - URL ?css= param (for preview/testing)
    - 'css' cookie
    - First available style, or '/static/styles/base.css' if none found
    This should be called by render_template for every page load.
    """
    styles = list_styles()
    style_cookie = gw.web.cookies.get("css") if gw.web.app.is_setup('web.cookies') else None
    style_query = request.query.get("css")
    style_path = None

    # Prefer query param (if exists and valid)
    if style_query:
        for src, fname in styles:
            if fname == style_query:
                style_path = f"/static/styles/{fname}" if src == "global" else f"/static/{src}/styles/{fname}"
                break
    # Otherwise, prefer cookie
    if not style_path and style_cookie:
        for src, fname in styles:
            if fname == style_cookie:
                style_path = f"/static/styles/{fname}" if src == "global" else f"/static/{src}/styles/{fname}"
                break
    # Otherwise, first available style
    if not style_path and styles:
        src, fname = styles[0]
        style_path = f"/static/styles/{fname}" if src == "global" else f"/static/{src}/styles/{fname}"
    # Fallback to base
    return style_path or "/static/styles/base.css"

def current_url():
    """Returns the current full URL path (with querystring)."""
    url = request.fullpath
    if request.query_string:
        url += "?" + request.query_string
    return url

def html_escape(text):
    import html
    return html.escape(text or "")

# --- Style view endpoints ---

def view_style_switcher(*, css=None, project=None):
    """
    Shows available styles (global + project), lets user choose, preview, and see raw CSS.
    If cookies are accepted, sets the style via cookie when changed in dropdown.
    If cookies are not accepted, only uses the css param for preview.
    """
    import os
    from bottle import request, response

    # Determine the project from context or fallback if not provided
    if not project:
        path = request.fullpath.strip("/").split("/")
        if path and path[0] in ("conway", "awg", "site", "etron"):
            project = path[0]
        else:
            project = "site"

    def list_styles_local(project):
        seen = set()
        styles = []
        # Global styles
        global_dir = gw.resource("data", "static", "styles")
        if os.path.isdir(global_dir):
            for f in sorted(os.listdir(global_dir)):
                if f.endswith(".css") and os.path.isfile(os.path.join(global_dir, f)):
                    if f not in seen:
                        styles.append(("global", f))
                        seen.add(f)
        if project:
            proj_dir = gw.resource("data", "static", project, "styles")
            if os.path.isdir(proj_dir):
                for f in sorted(os.listdir(proj_dir)):
                    if f.endswith(".css") and os.path.isfile(os.path.join(proj_dir, f)):
                        if f not in seen:
                            styles.append((project, f))
                            seen.add(f)
        return styles

    styles = list_styles_local(project)
    all_styles = [fname for _, fname in styles]
    style_sources = {fname: src for src, fname in styles}

    cookies_enabled = gw.web.app.is_setup('web.cookies')
    cookies_accepted = gw.web.cookies.check_consent() if cookies_enabled else False
    css_cookie = gw.web.cookies.get("css")

    # Handle POST
    if request.method == "POST":
        selected_style = request.forms.get("css")
        if cookies_enabled and cookies_accepted and selected_style and selected_style in all_styles:
            gw.web.cookies.set("css", selected_style)
            response.status = 303
            response.set_header("Location", request.fullpath)
            return ""

    # --- THIS IS THE MAIN LOGIC: ---
    # Priority: query param > explicit function arg > cookie > default
    style_query = request.query.get("css")
    selected_style = (
        style_query if style_query in all_styles else
        (css if css in all_styles else
         (css_cookie if css_cookie in all_styles else
          (all_styles[0] if all_styles else "base.css")))
    )
    # If still not valid, fallback to default
    if selected_style not in all_styles:
        selected_style = all_styles[0] if all_styles else "base.css"

    # Determine preview link and path for raw CSS
    if style_sources.get(selected_style) == "global":
        preview_href = f"/static/styles/{selected_style}"
        css_path = gw.resource("data", "static", "styles", selected_style)
        css_link = f'<link rel="stylesheet" href="/static/styles/{selected_style}">'
    else:
        preview_href = f"/static/{project}/styles/{selected_style}"
        css_path = gw.resource("data", "static", project, "styles", selected_style)
        css_link = f'<link rel="stylesheet" href="/static/{project}/styles/{selected_style}">'

    preview_html = f"""
        {css_link}
        <div class="style-preview">
            <h2>Theme Preview: {selected_style[:-4].replace('_', ' ').title()}</h2>
            <p>This is a preview of the <b>{selected_style}</b> theme.</p>
            <button>Sample button</button>
            <pre>code block</pre>
        </div>
    """
    css_code = ""
    try:
        with open(css_path, encoding="utf-8") as f:
            css_code = f.read()
    except Exception:
        css_code = "Could not load CSS file."

    selector = style_selector_form(
        all_styles=styles,
        selected_style=selected_style,
        cookies_enabled=cookies_enabled,
        cookies_accepted=cookies_accepted,
        project=project
    )

    return f"""
        <h1>Select a Site Theme</h1>
        {selector}
        {preview_html}
        <h3>CSS Source: {selected_style}</h3>
        <pre style="max-height:400px;overflow:auto;">{html_escape(css_code)}</pre>
    """


def style_selector_form(all_styles, selected_style, cookies_enabled, cookies_accepted, project):
    options = []
    for src, fname in all_styles:
        label = fname[:-4].upper()
        label = f"GLOBAL: {label}" if src == "global" else f"{src.upper()}: {label}"
        selected = " selected" if fname == selected_style else ""
        options.append(f'<option value="{fname}"{selected}>{label}</option>')

    info = ""
    if cookies_enabled and not cookies_accepted:
        info = "<p><b><a href='/cookies/cookie-jar'>Accept cookies to save your style preference.</a></b></p>"

    # No JS redirect actually needed.
    if cookies_enabled and cookies_accepted:
        return f"""
            {info}
            <form method="post" action="/nav/style-switcher" class="style-form" style="margin-bottom: 0.5em">
                <select id="css-style" name="css" class="style-selector" style="width:100%" onchange="this.form.submit()">
                    {''.join(options)}
                </select>
                <noscript><button type="submit">Set</button></noscript>
            </form>
        """
    else:
        # Preview-only (no saving)
        return f"""
            {info}
            <select id="css-style" name="css" class="style-selector" style="width:100%" onchange="styleSelectChanged(this)">
                {''.join(options)}
            </select>
            <script>
                function styleSelectChanged(sel) {{
                    var val = sel.value;
                    var url = new URL(window.location.href);
                    url.searchParams.set('css', val);
                    window.location.href = url.toString();
                }}
            </script>
        """

def list_styles(project=None):
    seen = set()
    styles = []
    global_dir = gw.resource("data", "static", "styles")
    if os.path.isdir(global_dir):
        for f in sorted(os.listdir(global_dir)):
            if f.endswith(".css") and os.path.isfile(os.path.join(global_dir, f)):
                if f not in seen:
                    styles.append(("global", f))
                    seen.add(f)
    if project:
        proj_dir = gw.resource("data", "static", project, "styles")
        if os.path.isdir(proj_dir):
            for f in sorted(os.listdir(proj_dir)):
                if f.endswith(".css") and os.path.isfile(os.path.join(proj_dir, f)):
                    if f not in seen:
                        styles.append((project, f))
                        seen.add(f)
    return styles
