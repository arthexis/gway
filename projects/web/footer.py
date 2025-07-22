# file: projects/web/footer.py
"""Utilities for managing page footer links."""

from gway import gw
import sys

_footer_links: dict[str, list[object]] = {}


def clear():
    """Reset all stored footer links."""
    _footer_links.clear()


def parse_links(links) -> list[object]:
    """Return a list of link tokens from a string or iterable."""
    if not links:
        return []
    if isinstance(links, str):
        tokens = links.replace(',', ' ').split()
    else:
        try:
            tokens = list(links)
        except Exception:
            tokens = []
    result: list[object] = []
    for t in tokens:
        token = str(t).strip()
        if not token:
            continue
        if ':' in token:
            proj, view = token.split(':', 1)
            result.append((proj.strip(), view.strip()))
        else:
            result.append(token)
    return result


def add_footer_links(route: str, links=None, project: str | None = None):
    """Register footer links for ``route``."""
    parsed = parse_links(links)
    if not parsed:
        return
    if project:
        parsed = [
            (project, item) if not isinstance(item, tuple) else item
            for item in parsed
        ]
    existing = _footer_links.get(route, [])
    _footer_links[route] = existing + parsed
    gw.debug(f"Added footer links for {route}: {_footer_links[route]}")


def render_footer_links(homes=None) -> str:
    """Return HTML for footer links associated with ``homes`` routes."""
    webapp_mod = sys.modules[gw.web.app.setup_app.__module__]
    if homes is None:
        homes = getattr(webapp_mod, "_homes", [])
    items = []
    for _, route in homes:
        sub = _footer_links.get(route)
        if not sub:
            continue
        proj_root = route.rsplit('/', 1)[0] if '/' in route else route
        for name in sub:
            if isinstance(name, tuple):
                proj, view = name
                href = f"{proj.replace('.', '/')}/{view}".strip('/')
                func_title = getattr(webapp_mod, "_func_title", lambda p, v: None)
                label = func_title(proj, view) or (
                    view.replace('-', ' ').replace('_', ' ').title()
                )
            else:
                href = f"{proj_root}/{name}".strip('/')
                proj = proj_root.replace('/', '.')
                func_title = getattr(webapp_mod, "_func_title", lambda p, v: None)
                label = func_title(proj, name) or (
                    name.replace('-', ' ').replace('_', ' ').title()
                )
            items.append(f'<a href="/{href}">{label}</a>')
    return '<p class="footer-links">' + ' | '.join(items) + '</p>' if items else ""
