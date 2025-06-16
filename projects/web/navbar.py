# projects/web/navbar.py

import os
from gway import gw
from bottle import request

def render(*, current_url=None, homes=None):
    """
    Renders the sidebar navigation.
    - Homes are shown in the order defined.
    - Visited links shown most recent first, only if their route is NOT a home route.
    - The current page is always highlighted.
    - Fetches `visited` list from cookies on every call.
    """
    cookies_ok = gw.web.cookie.check_consent()
    gw.debug(f"Render navbar with {homes=} {cookies_ok=}")

    # Get current visited links directly from the cookie (never from args)
    visited = []
    if cookies_ok:
        visited_cookie = gw.web.cookie.get("visited", "")
        if visited_cookie:
            visited = visited_cookie.split("|")

    links = ""
    current_route = request.fullpath.strip("/")
    home_routes = set()
    if homes:
        for home_title, home_route in homes:
            home_routes.add(home_route.strip("/"))

    # --- Homes: always shown, always in declared order ---
    if homes:
        for home_title, home_route in homes:
            route = home_route.strip("/")
            is_current = ' class="current"' if route == current_route else ""
            links += f'<li><a href="/{home_route}"{is_current}>{home_title.upper()}</a></li>'

    # --- Visited links only if cookies are accepted ---
    if cookies_ok and visited:
        visited_routes = set()
        for entry in reversed(visited):  # Most recent first
            if "=" not in entry:
                continue
            title, route = entry.split("=", 1)
            canon_route = route.strip("/")
            # Only show visited links not already in homes, and avoid visited duplicates
            if canon_route in home_routes or canon_route in visited_routes:
                continue
            visited_routes.add(canon_route)
            is_current = ' class="current"' if canon_route == current_route else ""
            links += f'<li><a href="/{route}"{is_current}>{title}</a></li>'
    elif not homes:
        # No homes defined: show only current page as label
        current_title = (request.fullpath.strip("/").split("/") or ["readme"])
        title = current_title[-1].replace('-', ' ').replace('_', ' ').title()
        links += f'<li class="current">{title.upper()}</li>'

    # --- Search box ---
    search_box = '''
        <form action="/gway/help" method="get" class="navbar">
            <input type="text" name="topic" placeholder="Search this GWAY" class="help" />
        </form>
    '''

    # --- QR code for this page ---
    compass = ""
    if current_url:
        qr_url = gw.qr.generate_url(current_url)
        compass = f'''
            <div class="compass">
                <p class="compass">QR Code for this page:</p>
                <img src="{qr_url}" alt="QR Code" class="compass" />
            </div>
        '''

    # --- Style/theme selector ---
    style_selector = ""
    if cookies_ok:
        styles_dir = gw.resource("data", "static", "styles")
        all_styles = [
            f for f in sorted(os.listdir(styles_dir))
            if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
        ]
        css_cookie = gw.web.cookie.get("css")
        main_style = css_cookie if css_cookie in all_styles else (all_styles[0] if all_styles else "base.css")
        added = set()
        options = []
        if main_style:
            options.append(f'<option value="{main_style}" selected>{main_style[:-4].upper()}</option>')
            added.add(main_style)
        for style in all_styles:
            if style not in added:
                options.append(f'<option value="{style}">{style[:-4].upper()}</option>')
        style_selector = f"""
            <form method="post" action="/nav/styles" class="style-form" style="margin-bottom: 0.5em">
                <input type="hidden" name="next" value="{html_escape(request.fullpath + ('?' + request.query_string if request.query_string else ''))}">
                <select id="css-style" name="css" class="style-selector" style="width:100%" onchange="this.form.submit()">
                    {''.join(options)}
                </select>
                <noscript><button type="submit">Set</button></noscript>
            </form>
        """

    # --- Remove cookies button ---
    remove_button = ""
    if cookies_ok:
        remove_button = '''
            <form method="post" action="/cookie/remove" style="margin-top: 1rem">
                <button type="submit">Remove our cookies</button>
            </form>
        '''

    visited = gw.web.cookie.get("visited")
    gw.debug(f"Visited cookie raw: {visited}")
    return f"<aside>{search_box}<ul>{links}</ul><br>{compass}<br>{style_selector}<br>{remove_button}</aside>"

def html_escape(text):
    import html
    return html.escape(text or "")

# --- Style view endpoints ---

def view_styles(**kwargs):
    """
    GET: Shows available styles, lets user choose, displays a preview and raw CSS.
    POST: Sets style cookie and redirects back to the chosen page.
    """
    from bottle import request, response, redirect, template

    styles_dir = gw.resource("data", "static", "styles")
    all_styles = [
        f for f in sorted(os.listdir(styles_dir))
        if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
    ]
    css_cookie = gw.web.cookie.get("css")
    main_style = css_cookie if css_cookie in all_styles else (all_styles[0] if all_styles else "base.css")
    next_url = request.forms.get("next") or request.query.get("next") or "/"

    if request.method == "POST":
        style = request.forms.get("css")
        if style and style in all_styles:
            gw.web.cookie.set("css", style)
        response.status = 303
        response.set_header("Location", next_url)
        return ""

    # GET: Show all styles, preview, and code block
    style = request.query.get("css") or main_style
    preview_html = f"""
        <link rel="stylesheet" href="/static/styles/{style}" />
        <div class="style-preview">
            <h2>Theme Preview: {style[:-4].title()}</h2>
            <p>This is a preview of the <b>{style}</b> theme.</p>
            <button>Sample button</button>
            <pre>code block</pre>
        </div>
    """
    css_path = os.path.join(styles_dir, style)
    css_code = ""
    try:
        with open(css_path, encoding="utf-8") as f:
            css_code = f.read()
    except Exception:
        css_code = "Could not load CSS file."

    options = [
        f'<option value="{s}"{" selected" if s==style else ""}>{s[:-4].title()}</option>'
        for s in all_styles
    ]
    selector = f"""
        <form method="post" action="/nav/styles">
            <input type="hidden" name="next" value="{html_escape(next_url)}">
            <select name="css" onchange="this.form.submit()">
                {''.join(options)}
            </select>
            <noscript><button type="submit">Set</button></noscript>
        </form>
    """

    return f"""
        <h1>Select a Site Theme</h1>
        {selector}
        {preview_html}
        <h3>CSS Source: {style}</h3>
        <pre style="max-height:400px;overflow:auto;">{html_escape(css_code)}</pre>
    """
