"""Automatic sitemap.xml generation for GWAY websites."""

from gway import gw
import datetime
import html
import sys

__all__ = ["generate", "view_sitemap_xml"]


def _collect_routes():
    """Return a sorted set of route paths from the current web app."""
    webapp = sys.modules[gw.web.app.setup_app.__module__]
    homes = getattr(webapp, "_homes", [])
    links_map = getattr(webapp, "_links", {})
    routes = set()

    for _, route in homes:
        base = route.strip("/")
        routes.add(base)
        sub = links_map.get(route, [])
        proj_root = base.rsplit("/", 1)[0] if "/" in base else base
        for name in sub:
            if isinstance(name, tuple):
                proj, view = name
                target = f"{proj.replace('.', '/')}/{view}".strip("/")
            else:
                target = f"{proj_root}/{name}".strip("/")
            routes.add(target)
    return sorted(routes)


def generate(base_url: str | None = None) -> str:
    """Return sitemap XML for the configured routes."""
    base = (base_url or gw.web.base_url()).rstrip("/")
    today = datetime.date.today().isoformat()
    entries = []
    for path in _collect_routes():
        loc = html.escape(f"{base}/{path}")
        entries.append(f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod></url>")
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n"
        + "\n".join(entries)
        + "\n</urlset>"
    )
    return xml


def view_sitemap_xml():
    """Bottle view that serves ``sitemap.xml``."""
    from bottle import response

    response.content_type = "application/xml"
    return generate()
