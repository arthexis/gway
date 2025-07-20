# file: projects/web/nav.py

import os
import html
import random
from gway import gw
from bottle import request

_forced_style = None
_default_style = None
_side = "left"


def render(*, homes=None, links=None):
    """
    Renders the sidebar navigation including search, home links, visited links, and a QR compass.
    """
    cookies_ok = (
        gw.web.app.is_setup("web.cookies") and gw.web.cookies.accepted()
    )
    links_map = links or {}
    gw.verbose(f"Render nav with {homes=} {links_map=} {cookies_ok=}")

    visited = []
    if cookies_ok:
        visited_cookie = gw.web.cookies.get("visited", "")
        if visited_cookie:
            visited = visited_cookie.split("|")

    current_route = request.fullpath.strip("/")
    current_title = (
        current_route.split("/")[-1]
        .replace("-", " ")
        .replace("_", " ")
        .title()
    )

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
    if (
        cookies_ok
        and current_route not in home_routes
        and current_route not in visited_set
    ):
        entries.append((current_title, current_route))
        visited_set.add(current_route)

    # --- Build HTML links ---
    links_html = ""
    if homes:
        for home_title, home_route in homes:
            route = home_route.strip("/")
            is_current = ' class="current"' if route == current_route else ""
            proj_root = route.rsplit("/", 1)[0] if "/" in route else route
            links_html += f'<li><a href="/{home_route}"{is_current}>{home_title.upper()}</a>'
            sub = links_map.get(home_route)
            if sub and current_route.startswith(proj_root):
                links_html += '<ul class="sub-links">'
                for name in sub:
                    if isinstance(name, tuple):
                        target_proj, view_name = name
                        target_root = target_proj.replace(".", "/")
                        sub_route = f"{target_root}/{view_name}".strip("/")
                        label = (
                            view_name.replace("-", " ")
                            .replace("_", " ")
                            .title()
                        )
                    else:
                        sub_route = f"{proj_root}/{name}".strip("/")
                        label = (
                            name.replace("-", " ").replace("_", " ").title()
                        )
                    active = (
                        ' class="active"' if sub_route == current_route else ""
                    )
                    links_html += (
                        f'<li><a href="/{sub_route}"{active}>{label}</a></li>'
                    )
                links_html += "</ul>"
            links_html += "</li>"
    if cookies_ok and entries:
        visited_rendered = set()
        for title, route in reversed(entries):
            if route in home_routes or route in visited_rendered:
                continue
            visited_rendered.add(route)
            is_current = ' class="current"' if route == current_route else ""
            links_html += (
                f'<li><a href="/{route}"{is_current}>{title}</a></li>'
            )
    elif not homes:
        links_html += f'<li class="current">{current_title.upper()}</li>'

    # --- Search box ---
    search_box = """
        <form action="/web/site/help" method="get" class="nav">
            <textarea name="topic" id="help-search"
                placeholder="Search this GWAY"
                class="help" rows="1"
                autocomplete="off"
                spellcheck="false"
                style="overflow:hidden; resize:none; min-height:2.4em; max-height:10em;"
                oninput="autoExpand(this)"
            >{}</textarea>
        </form>
    """.format(
        request.query.get("topic", "")
    )

    # --- Current user info (Basic Auth) ---
    user_html = ""
    try:
        auth_header = request.get_header("Authorization")
        username, _ = gw.web.auth.parse_basic_auth_header(auth_header)
        if username:
            logout_url = gw.web.app.build_url("auth", "logout")
            user_html = (
                f'<p class="user-info">User: {html.escape(username)} '
                f'<a href="{logout_url}" class="logout">Logout</a></p>'
            )
    except Exception as e:
        gw.debug(f"Could not resolve auth user: {e}")

    # --- QR code for this page ---

    compass = ""
    toggle = ""
    render_compass_exists = False

    # Attempt to locate a view_compass function for the current route
    view_compass_func = None
    view_part = None
    try:
        obj = gw
        for part in current_route.split("/"):
            attr = part.replace("-", "_")
            if hasattr(obj, attr):
                obj = getattr(obj, attr)
                if hasattr(obj, "view_compass"):
                    view_compass_func = getattr(obj, "view_compass")
            else:
                view_part = attr
                break
        if hasattr(obj, "render_compass"):
            render_compass_exists = True
        elif view_part and hasattr(obj, f"render_{view_part}_compass"):
            render_compass_exists = True
    except Exception as e:
        gw.debug(f"Error searching for view_compass: {e}")
        view_compass_func = None

    from urllib.parse import parse_qsl, urlencode

    params = dict(parse_qsl(request.query_string))
    mode = params.get("compass") or ("local" if view_compass_func else "qr")

    if mode != "qr" and view_compass_func:
        try:
            compass = view_compass_func()
        except Exception as e:
            gw.debug(f"view_compass error: {e}")
            compass = ""
            mode = "qr"

    if mode == "qr":
        try:
            url = current_url()
            qr_url = gw.studio.qr.generate_url(url)
            compass = f'<img src="{qr_url}" alt="QR Code" class="compass" />'
        except Exception as e:
            gw.debug(f"Could not generate QR compass: {e}")

    if view_compass_func:
        params["compass"] = "local" if mode == "qr" else "qr"
        label = "Show local compass" if mode == "qr" else "Show QR to Here"
        toggle_href = request.fullpath.split("?")[0]
        qs = urlencode(params)
        if qs:
            toggle_href += "?" + qs
        toggle = f'<p style="font-size:80%" class="compass-toggle"><a href="{toggle_href}">[{label}]</a></p>'

    if compass:
        data_attr = ""
        if render_compass_exists:
            data_attr = (
                ' gw-render="compass" gw-double-click="refresh"'
            )
        compass = f'<div class="compass"{data_attr}>{compass}</div>'

    if _side == "top":
        return f"<nav class='top-bar'><ul class='top-links'>{links_html}</ul>{search_box}</nav>"
    return f"<aside>{search_box}<ul>{links_html}</ul><br>{compass}{toggle}</aside>"


def active_style():
    """
    Returns the current user's preferred style path (to .css file), checking:
    - URL ?css= param (for preview/testing)
    - 'css' cookie
    - First available style, or '/static/styles/base.css' if none found
    This should be called by render_template for every page load.
    """
    styles = list_styles()
    style_cookie = (
        gw.web.cookies.get("css")
        if gw.web.app.is_setup("web.cookies")
        else None
    )
    style_query = request.query.get("css")
    style_path = None

    if _forced_style:
        if _forced_style == "random":
            if styles:
                src, fname = random.choice(styles)
                return (
                    f"/static/styles/{fname}"
                    if src == "global"
                    else f"/static/{src}/styles/{fname}"
                )
        else:
            for src, fname in styles:
                if fname == _forced_style:
                    return (
                        f"/static/styles/{fname}"
                        if src == "global"
                        else f"/static/{src}/styles/{fname}"
                    )
            if _forced_style.startswith("/"):
                return _forced_style

    # Prefer query param (if exists and valid)
    if style_query:
        if style_query == "random" and styles:
            src, fname = random.choice(styles)
            return (
                f"/static/styles/{fname}"
                if src == "global"
                else f"/static/{src}/styles/{fname}"
            )
        for src, fname in styles:
            if fname == style_query:
                style_path = (
                    f"/static/styles/{fname}"
                    if src == "global"
                    else f"/static/{src}/styles/{fname}"
                )
                break
    # Otherwise, prefer cookie
    if not style_path and style_cookie:
        if style_cookie == "random" and styles:
            src, fname = random.choice(styles)
            return (
                f"/static/styles/{fname}"
                if src == "global"
                else f"/static/{src}/styles/{fname}"
            )
        for src, fname in styles:
            if fname == style_cookie:
                style_path = (
                    f"/static/styles/{fname}"
                    if src == "global"
                    else f"/static/{src}/styles/{fname}"
                )
                break
    # Otherwise, use configured default
    if not style_path and _default_style:
        if _default_style == "random" and styles:
            src, fname = random.choice(styles)
            return (
                f"/static/styles/{fname}"
                if src == "global"
                else f"/static/{src}/styles/{fname}"
            )
        for src, fname in styles:
            if fname == _default_style:
                style_path = (
                    f"/static/styles/{fname}"
                    if src == "global"
                    else f"/static/{src}/styles/{fname}"
                )
                break
        if not style_path and _default_style.startswith("/"):
            style_path = _default_style
    # Otherwise, first available style
    if not style_path and styles:
        src, fname = styles[0]
        style_path = (
            f"/static/styles/{fname}"
            if src == "global"
            else f"/static/{src}/styles/{fname}"
        )
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
        if path and path[0]:
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
                if f.endswith(".css") and os.path.isfile(
                    os.path.join(global_dir, f)
                ):
                    if f not in seen:
                        styles.append(("global", f))
                        seen.add(f)
        if project:
            proj_dir = gw.resource("data", "static", project, "styles")
            if os.path.isdir(proj_dir):
                for f in sorted(os.listdir(proj_dir)):
                    if f.endswith(".css") and os.path.isfile(
                        os.path.join(proj_dir, f)
                    ):
                        if f not in seen:
                            styles.append((project, f))
                            seen.add(f)
        return styles

    styles = list_styles_local(project)
    all_styles = [fname for _, fname in styles]
    style_sources = {fname: src for src, fname in styles}
    # Include the special 'random' option
    all_styles.append("random")

    cookies_enabled = gw.web.app.is_setup("web.cookies")
    cookies_accepted = gw.web.cookies.accepted() if cookies_enabled else False
    css_cookie = gw.web.cookies.get("css")

    # Handle POST
    if request.method == "POST":
        selected_style = request.forms.get("css")
        if (
            cookies_enabled
            and cookies_accepted
            and selected_style
            and selected_style in all_styles
        ):
            gw.web.cookies.set("css", selected_style)
            response.status = 303
            response.set_header("Location", request.fullpath)
            return ""

    # --- THIS IS THE MAIN LOGIC: ---
    # Priority: query param > explicit function arg > cookie > default
    style_query = request.query.get("css")
    selected_style = (
        style_query
        if style_query in all_styles
        else (
            css
            if css in all_styles
            else (
                css_cookie
                if css_cookie in all_styles
                else (all_styles[0] if all_styles else "base.css")
            )
        )
    )
    # If still not valid, fallback to default
    if selected_style not in all_styles:
        selected_style = all_styles[0] if all_styles else "base.css"

    # Determine preview link and path for raw CSS
    if selected_style == "random":
        css_link = ""
        if styles:
            src, fname = random.choice(styles)
            preview_href = (
                f"/static/styles/{fname}"
                if src == "global"
                else f"/static/{src}/styles/{fname}"
            )
            css_link = f'<link rel="stylesheet" href="{preview_href}">'
        preview_html = f"""
        {css_link}
        <div class="style-preview">
            <h2>Theme Preview: RANDOM</h2>
            <p>This option selects a random theme on each visit.</p>
        </div>
        """
        css_code = "Random theme"
    else:
        if style_sources.get(selected_style) == "global":
            preview_href = f"/static/styles/{selected_style}"
            css_path = gw.resource("data", "static", "styles", selected_style)
            css_link = f'<link rel="stylesheet" href="/static/styles/{selected_style}">'
        else:
            preview_href = f"/static/{project}/styles/{selected_style}"
            css_path = gw.resource(
                "data", "static", project, "styles", selected_style
            )
            css_link = f'<link rel="stylesheet" href="/static/{project}/styles/{selected_style}">'

        preview_html = f"""
        {css_link}
        <div class="style-preview">
            <h2>Theme Preview: {selected_style[:-4].replace('_', ' ').title()}</h2>
            <p>This is a preview of the <b>{selected_style}</b> theme.</p>
            <button>Sample button</button>
            <input type="text" placeholder="Text input" style="display:block;margin:0.5em 0;">
            <label style="display:block;margin:0.25em 0;"><input type="checkbox"> Checkbox</label>
            <label style="display:block;margin:0.25em 0;"><input type="radio" name="r"> Radio</label>
            <select style="display:block;margin:0.5em 0;">
                <option>Option A</option>
                <option>Option B</option>
            </select>
            <pre>code block</pre>
        </div>
        """
        css_code = ""
        try:
            with open(css_path, encoding="utf-8") as f:
                css_code = f.read()
        except Exception:
            css_code = "Could not load CSS file."

    styles_with_random = styles + [(None, "random")]
    selector = style_selector_form(
        all_styles=styles_with_random,
        selected_style=selected_style,
        cookies_enabled=cookies_enabled,
        cookies_accepted=cookies_accepted,
        project=project,
    )

    return f"""
        <h1>Select a Site Theme</h1>
        {selector}
        {preview_html}
        <h3>CSS Source: {selected_style}</h3>
        <pre style="max-height:400px;overflow:auto;">{html_escape(css_code)}</pre>
    """


def style_selector_form(
    all_styles, selected_style, cookies_enabled, cookies_accepted, project
):
    options = []
    for src, fname in all_styles:
        if fname == "random":
            selected = " selected" if fname == selected_style else ""
            options.append(f'<option value="random"{selected}>RANDOM</option>')
            continue
        label = fname[:-4].upper()
        label = (
            f"GLOBAL: {label}"
            if src == "global"
            else f"{src.upper()}: {label}"
        )
        selected = " selected" if fname == selected_style else ""
        options.append(f'<option value="{fname}"{selected}>{label}</option>')

    info = ""
    if cookies_enabled and not cookies_accepted:
        info = "<p><b><a href='/web/cookies/cookie-jar'>Accept cookies to save your style preference.</a></b></p>"

    # No JS redirect actually needed.
    if cookies_enabled and cookies_accepted:
        return f"""
            {info}
            <form method="post" action="/web/nav/style-switcher" class="style-form" style="margin-bottom: 0.5em">
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
        """


def list_styles(project=None):
    seen = set()
    styles = []
    global_dir = gw.resource("data", "static", "styles")
    if os.path.isdir(global_dir):
        for f in sorted(os.listdir(global_dir)):
            if f.endswith(".css") and os.path.isfile(
                os.path.join(global_dir, f)
            ):
                if f not in seen:
                    styles.append(("global", f))
                    seen.add(f)
    if project:
        proj_dir = gw.resource("data", "static", project, "styles")
        if os.path.isdir(proj_dir):
            for f in sorted(os.listdir(proj_dir)):
                if f.endswith(".css") and os.path.isfile(
                    os.path.join(proj_dir, f)
                ):
                    if f not in seen:
                        styles.append((project, f))
                        seen.add(f)
    return styles


def setup_app(*, app=None, style=None, default_style=None, default_css=None, side="left", **_):
    """Optional hook to set nav defaults when the project is added.

    ``style`` forces a theme (including ``random`` for per-request variation).
    ``default_style``/``default_css`` chooses the fallback theme when no cookie
    or query parameter is set. ``side`` accepts ``left``, ``right`` or ``top`` to
    position the navigation bar.
    """
    global _forced_style, _default_style, _side
    if default_style is None:
        default_style = default_css
    if default_style:
        _default_style = default_style
        gw.info(f"web.nav default style: {default_style}")
    if style:
        _forced_style = style
        gw.info(f"web.nav forced style: {style}")
    if side in {"left", "right", "top"}:
        _side = side
        gw.info(f"web.nav side set to {side}")
    else:
        gw.error(f"Invalid nav side: {side}")
    return app


def side() -> str:
    """Return the configured navigation side ('left', 'right' or 'top')."""
    return _side
