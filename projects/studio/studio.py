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
    html = ["<h1>Studio Bench</h1>"]
    html.append(
        "<style>"
        ".studio-cards{display:flex;flex-wrap:wrap;gap:1em;margin:1em 0;}"
        ".studio-card{display:block;padding:1em;border:1px solid var(--muted,#ccc);"
        "border-radius:8px;background:var(--card-bg,#f9f9f9);width:16em;"
        "text-decoration:none;color:inherit;}"
        ".studio-card h2{margin-top:0;font-size:1.2em;}"
        ".studio-card p{margin:.4em 0;}"
        "</style>"
    )
    html.append("<div class='studio-cards'>")
    for label, url, info in links:
        html.append(
            f"<a class='studio-card' href='{url}'><h2>{label}</h2><p>{info}</p></a>"
        )
    html.append("</div>")
    return "\n".join(html)
