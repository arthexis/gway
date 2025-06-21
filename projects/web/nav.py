# TODO: Consider using HTMX for the navbar (but not anywhere else)
# The idea behind this is that using htmx with arbitrary view output leads to unexpected
# results. However, the navbar is self-contained. We should try updating the links and compass 
# in a lightweight manner through htmx. 

# file: projects/web/nav.py

import os
from gway import gw
from bottle import request

def render(*, current_url=None, homes=None):
    """
    Renders the sidebar navigation.
    Always highlights and shows the current page, even if not yet in the visited cookie.
    """
    cookies_ok = gw.web.app.is_enabled('cookies') and gw.web.cookies.check_consent()
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

    # --- New: Build title count mapping for disambiguation ---
    all_links = []
    if homes:
        for home_title, home_route in homes:
            all_links.append((home_title, home_route.strip("/")))
    all_links.extend(entries)  # Add visited
    title_count = {}
    title_routes = {}
    for title, route in all_links:
        k = title.strip().lower()
        title_count[k] = title_count.get(k, 0) + 1
        title_routes.setdefault(k, []).append(route)

    def disambiguate(title, route):
        """Append route info if title is duplicated."""
        k = title.strip().lower()
        if title_count[k] == 1:
            return title
        # Use shortest unique suffix as disambiguator
        siblings = set(title_routes[k]) - {route}
        segments = route.split("/")
        for i in range(1, len(segments)+1):
            suffix = "/".join(segments[-i:])
            if all(not s.endswith(suffix) for s in siblings):
                return f"{title} ({suffix})"
        return f"{title} ({route})"  # fallback

    # --- Build HTML ---
    links = ""
    # Homes
    if homes:
        for home_title, home_route in homes:
            route = home_route.strip("/")
            is_current = ' class="current"' if route == current_route else ""
            disp_title = disambiguate(home_title, route)
            links += f'<li><a href="/{home_route}"{is_current}>{disp_title.upper()}</a></li>'
    # Visited (most recent first, not already in homes)
    if cookies_ok and entries:
        visited_rendered = set()
        for title, route in reversed(entries):
            if route in home_routes or route in visited_rendered:
                continue
            visited_rendered.add(route)
            is_current = ' class="current"' if route == current_route else ""
            disp_title = disambiguate(title, route)
            links += f'<li><a href="/{route}"{is_current}>{disp_title}</a></li>'
    elif not homes:
        links += f'<li class="current">{current_title.upper()}</li>'

    # ... (rest of function unchanged)

    # --- Search box ---
    search_box = '''
        <form action="/site/help" method="get" class="nav">
            <input type="text" name="topic" placeholder="Search this GWAY" class="help" />
        </form>
    '''

    # --- QR code for this page ---
    compass = ""
    if current_url:
        qr_url = gw.qr.generate_url(current_url)
        compass = f'''
            <div class="compass">
                <p class="compass"><h3>QR Code to Here</h3></p>
                <img src="{qr_url}" alt="QR Code" class="compass" />
            </div>
        '''

    # --- Style/theme selector ---
    style_selector = ""
    if cookies_ok:
        styles_dir = gw.resource("data/static/styles")
        all_styles = [
            f for f in sorted(os.listdir(styles_dir))
            if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
        ]
        css_cookie = gw.web.cookies.get("css")
        main_style = css_cookie if css_cookie in all_styles else (all_styles[0] if all_styles else "base.css")
        style_selector = style_selector_form(request.fullpath, styles_dir, all_styles, main_style)

    # --- Remove cookies button ---
    remove_button = '''
        <form method="post" action="/cookies/remove" style="margin-top: 1rem">
            <button type="submit">Remove our cookies</button>
        </form>
    ''' if cookies_ok else ""

    gw.debug(f"Visited cookie raw: {gw.web.cookies.get('visited')}")
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
    css_cookie = gw.web.cookies.get("css")
    main_style = css_cookie if css_cookie in all_styles else (all_styles[0] if all_styles else "base.css")
    next_url = request.forms.get("next") or request.query.get("next") or "/"

    if request.method == "POST":
        style = request.forms.get("css")
        if style and style in all_styles:
            gw.web.cookies.set("css", style)
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
    selector = style_selector_form(
        request.fullpath + ('?' + request.query_string if request.query_string else ''),
        styles_dir, all_styles, style
    )

    return f"""
        <h1>Select a Site Theme</h1>
        {selector}
        {preview_html}
        <h3>CSS Source: {style}</h3>
        <pre style="max-height:400px;overflow:auto;">{html_escape(css_code)}</pre>
    """


def style_selector_form(current_path, styles_dir, all_styles, selected_style):
    from bottle import request
    next_url = current_path + ('?' + request.query_string if request.query_string else '')
    options = []
    added = set()
    if selected_style:
        options.append(f'<option value="{selected_style}" selected>{selected_style[:-4].upper()}</option>')
        added.add(selected_style)
    for style in all_styles:
        if style not in added:
            options.append(f'<option value="{style}">{style[:-4].upper()}</option>')
    return f"""
        <form method="post" action="/nav/styles" class="style-form" style="margin-bottom: 0.5em">
            <input type="hidden" name="next" value="{html_escape(next_url)}">
            <select id="css-style" name="css" class="style-selector" style="width:100%" onchange="this.form.submit()">
                {''.join(options)}
            </select>
            <noscript><button type="submit">Set</button></noscript>
        </form>
    """
