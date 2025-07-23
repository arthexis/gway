from gway import gw


def view_studio_bench(*, _title="Studio Bench", **_):
    """Landing page listing available Studio web views."""
    links = [
        (
            "Animate GIF",
            gw.web.build_url("studio.screen", "animate-gif"),
            "Convert image frames into a GIF",
        ),
    ]
    html = [
        '<link rel="stylesheet" href="/static/web/cards.css">',
        "<h1>Studio Bench</h1>",
        "<div class='gw-cards'>",
    ]
    for label, url, info in links:
        html.append(
            "<div class='gw-card'>"
            f"<a href='{url}' class='main-link'><h2>{label}</h2><p>{info}</p></a>"
            "</div>"
        )
    html.append("</div>")
    return "\n".join(html)


view_studio_bench._title = "Studio Bench"
