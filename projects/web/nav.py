# file: projects/web/nav.py

import os
from gway import gw
from bottle import request

# TODO: Currently, when cookies have not been accepted, the style switch selection box becomes disabled.
#       However, as per the message to the user, they should still be able to switch, they just won't be
#       saved, meaning we reload using the css param to have the css show only here. 
#       The selection should still work in both modes, using the proper mechanism for each case.


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

    # --- Build HTML ---
    links = ""
    # Homes
    if homes:
        for home_title, home_route in homes:
            route = home_route.strip("/")
            is_current = ' class="current"' if route == current_route else ""
            links += f'<li><a href="/{home_route}"{is_current}>{home_title.upper()}</a></li>'
    # Visited (most recent first, not already in homes)
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
        <form action="/site/help" method="get" class="nav" style="margin-bottom:1.5em;">
            <textarea name="topic" id="help-search"
                placeholder="Search this GWAY"
                class="help"
                rows="1"
                autocomplete="off"
                spellcheck="false"
                style="overflow:hidden; resize:none; min-height:2.4em; max-height:10em;"
                oninput="autoExpand(this)"
            >{}</textarea>
        </form>
        <script>
        function autoExpand(el) {{
            el.style.height = '2.4em'; // base height for 1 line
            if (el.value.trim() !== "") {{
                el.style.height = "auto";
                el.style.height = (el.scrollHeight) + "px";
            }}
        }}
        window.addEventListener("DOMContentLoaded", function(){{
            var el = document.getElementById('help-search');
            if (el && el.value.trim() !== "") autoExpand(el);
        }});
        </script>
    '''.format(request.query.get("topic", ""))

    # --- QR code for this page ---
    compass = ""
    if current_url:
        qr_url = gw.qr.generate_url(current_url)
        compass = f'''
            <div class="compass">
                <img src="{qr_url}" alt="QR Code" class="compass" />
            </div>
        '''

    gw.debug(f"Visited cookie raw: {gw.web.cookies.get('visited')}")
    return f"<aside>{search_box}<ul>{links}</ul><br>{compass}</aside>"

def html_escape(text):
    import html
    return html.escape(text or "")


# --- Style view endpoints ---

def view_style_switcher(*, css=None):
    """
    GET/POST: Shows available styles, lets user choose, displays a preview and raw CSS.
    If cookies are accepted, sets the style via cookie when changed in dropdown (no redirect).
    If cookies are not accepted, only uses the css param for preview.
    """
    import os
    from bottle import request, response

    styles_dir = gw.resource("data", "static", "styles")
    all_styles = [
        f for f in sorted(os.listdir(styles_dir))
        if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
    ]

    # --- Consent logic ---
    cookies_enabled = gw.web.app.is_enabled('cookies')
    cookies_accepted = gw.web.cookies.check_consent() if cookies_enabled else False

    css_cookie = gw.web.cookies.get("css")
    selected_style = None

    if request.method == "POST":
        selected_style = request.forms.get("css")
        if cookies_enabled and cookies_accepted and selected_style and selected_style in all_styles:
            gw.web.cookies.set("css", selected_style)
            # REDIRECT after setting
            response.status = 303
            response.set_header("Location", request.fullpath)
            return ""

    # Pick style: POST > URL param > cookie > default
    style = (
        selected_style or
        css or
        request.query.get("css") or
        (css_cookie if (css_cookie in all_styles) else None) or
        (all_styles[0] if all_styles else "base.css")
    )
    if style not in all_styles:
        style = all_styles[0] if all_styles else "base.css"

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

    selector = style_selector_form(
        all_styles=all_styles,
        selected_style=style,
        cookies_enabled=cookies_enabled,
        cookies_accepted=cookies_accepted
    )

    return f"""
        <h1>Select a Site Theme</h1>
        {selector}
        {preview_html}
        <h3>CSS Source: {style}</h3>
        <pre style="max-height:400px;overflow:auto;">{html_escape(css_code)}</pre>
    """

def style_selector_form(all_styles, selected_style, cookies_enabled, cookies_accepted):
    """
    Renders the style selector dropdown.
    - If cookies are accepted, submit as a form (POST).
    - If not, switch theme using URL ?css=...
    """
    options = []
    added = set()
    if selected_style:
        options.append(f'<option value="{selected_style}" selected>{selected_style[:-4].upper()}</option>')
        added.add(selected_style)
    for style in all_styles:
        if style not in added:
            options.append(f'<option value="{style}">{style[:-4].upper()}</option>')

    # Info
    info = ""
    if cookies_enabled and not cookies_accepted:
        info = "<p><b><a href='/cookies/cookie-jar'>Accept cookies to save your style preference.</a></b></p>"

    # JS for non-cookie: redirect on select
    # We use window.location to append/update the ?css=... param
    js_redirect = """
    <script>
    function styleSelectChanged(sel) {
        var css = sel.value;
        var url = window.location.pathname + window.location.search.replace(/([?&])css=[^&]*(&|$)/, '$1').replace(/^\\?|&$/g, '');
        url += (url.indexOf('?') === -1 ? '?' : '&') + 'css=' + encodeURIComponent(css);
        window.location = url;
    }
    </script>
    """

    if cookies_enabled and cookies_accepted:
        # Form submit as POST
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
        # No submit, only JS redirect
        return f"""
            {info}
            {js_redirect}
            <select id="css-style" name="css" class="style-selector" style="width:100%" onchange="styleSelectChanged(this)">
                {''.join(options)}
            </select>
        """


def get_style():
    """
    Returns the current user's preferred style filename, checking for:
    - URL ?css=... parameter (for quick-testing themes)
    - CSS cookie (for accepted preference)
    - Otherwise, defaults to the first style or 'base.css'.
    Discovers all available styles automatically.
    """
    import os
    from bottle import request
    styles_dir = gw.resource("data", "static", "styles")
    all_styles = [
        f for f in sorted(os.listdir(styles_dir))
        if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
    ]
    style = request.query.get('css')
    if style and style in all_styles:
        return style
    css_cookie = gw.web.cookies.get("css")
    if css_cookie and css_cookie in all_styles:
        return css_cookie
    return all_styles[0] if all_styles else "base.css"


def get_current_url():
    """
    Returns the current URL path including query parameters.
    Useful for QR codes and redirects that need full context.
    """
    from bottle import request
    url = request.fullpath
    if request.query_string:
        url += "?" + request.query_string
    return url
