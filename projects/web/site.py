# projects/web/site.py

# These view functions can be rendered by setup_app as the default website.
# Views receive the query params and json payload merged into kwargs.
# Don't use inline CSS ever, each user can have their own style sheets.

import html
from docutils.core import publish_parts
from bottle import request, response
from gway import gw


def view_readme(*args, **kwargs):
    """Render the README.rst file as HTML."""

    readme_path = gw.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def view_restyle(css=None, next=None):
    """
    Sets the css cookie to the requested value and redirects to 'next'.
    Accepts both GET (query params) and POST (form params).
    If missing params, show info/debug.
    """
    css_val = css or request.forms.get('css') or request.query.get('css')
    next_val = next or request.forms.get('next') or request.query.get('next')

    if not css_val or not next_val:
        response.status = 400
        return (
            "<h1>Style Switcher</h1>"
            "<p>This endpoint is for switching styles. Use the style selector in the navbar.</p>"
            f"<p>css: <b>{html.escape(str(css_val) if css_val else '')}</b> | next: <b>{html.escape(str(next_val) if next_val else '')}</b></p>"
        )

    if gw.web.cookie.check_consent():
        gw.web.cookie.set("css", css_val)

    response.status = 303
    response.set_header("Location", next_val)
    return ""


# TODO: Improve help display:
# 1. Put project and function in the same vertical axis to save height.
# 2. Turn references into links to help topics.
# 3. Add colorization to python code.
# 4. Separate signature into a table of positionals and keyword only params.
# 5. CLI example should be as exhaustive as possible (use all --options?).
# 6. When getting help for multiple items, wrap them in a div for styling
#    Suggest CSS we can add to base.css to decorate each help item.

def view_help(topic="", *args, **kwargs):
    """Render dynamic help based on GWAY introspection and search-style links."""
    topic = topic.replace(" ", "/").replace(".", "/").replace("-", "_") if topic else ""
    parts = [p for p in topic.strip("/").split("/") if p]

    if not parts:
        help_info = gw.help()
        title = "Available Projects"
        content = "<ul>"
        for project in help_info["Available Projects"]:
            content += f'<li><a href="?topic={project}">{project}</a></li>'
        content += "</ul>"
        return f"<h1>{title}</h1>{content}"

    elif len(parts) == 1:
        project = parts[0]
        help_info = gw.help(project)
        title = f"Help Topics for <code>{project}</code>"

    else:
        *project_path, maybe_function = parts
        obj = gw
        for segment in project_path:
            obj = getattr(obj, segment, None)
            if obj is None:
                return f"<h2>Not Found</h2><p>Project path invalid at <code>{segment}</code>.</p>"

        project_str = ".".join(project_path)

        if hasattr(obj, maybe_function):
            function = maybe_function
            help_info = gw.help(project_str, function, full=True)
            full_name = f"{project_str}.{function}"
            title = f"Help for <code>{full_name}</code>"
        else:
            # It's a project, not a function
            help_info = gw.help(project_str)
            full_name = f"{project_str}.{maybe_function}"
            title = f"Help Topics for <code>{full_name}</code>"

    if help_info is None:
        return "<h2>Not Found</h2><p>No help found for the given input.</p>"

    if "Matches" in help_info:
        sections = [_render_help_section(match, use_query_links=True) for match in help_info["Matches"]]
        return f"<h1>{title}</h1>{''.join(sections)}"

    return f"<h1>{title}</h1>{_render_help_section(help_info, use_query_links=True)}"


def _render_help_section(info, use_query_links=False, *args, **kwargs):
    """Render a help section with clean formatting and route-based query links."""
    import html
    rows = []
    for key, value in info.items():
        if use_query_links:
            if key == "Project":
                value = f'<a href="?topic={value}">{value}</a>'
            elif key == "Function":
                proj = info.get("Project", "")
                value = f'<a href="?topic={proj}/{value}">{value}</a>'

        if key == "Full Code":
            escaped = html.escape(value)
            value = f"<pre><code>{escaped}</code></pre>"
        elif key in ("Signature", "Example CLI", "Example Code"):
            value = f"<pre><code>{value}</code></pre>"
        elif key in ("Docstring", "TODOs"):
            value = f"<div class='doc'>{value}</div>"
        else:
            value = f"<p>{value}</p>"

        rows.append(f"<section><h3>{key}</h3>{value}</section>")

    return f"<article class='help-entry'>{''.join(rows)}</article>"


def view_qr_code(*args, value=None, **kwargs):
    """Generate a QR code for a given value and serve it from cache if available."""
    if not value:
        return '''
            <h1>QR Code Generator</h1>
            <form method="post">
                <input type="text" name="value" placeholder="Enter text or URL" required class="main" />
                <button type="submit" class="submit">Generate QR</button>
            </form>
        '''
    qr_url = gw.qr.generate_url(value)
    back_link = gw.web.app_url("qr-code")
    return f"""
        <h1>QR Code for:</h1>
        <h2><code>{value}</code></h2>
        <img src="{qr_url}" alt="QR Code" class="qr" />
        <p><a href="{back_link}">Generate another</a></p>
    """


def view_awg_finder(
    *args, meters=None, amps="40", volts="220", material="cu", 
    max_lines="3", phases="1", conduit=None, neutral="0", **kwargs
):
    """Page builder for AWG cable finder with HTML form and result."""
    if not meters:
        return '''
            <h1>AWG Cable Finder</h1>
            <p>Warning: This calculator may not be applicable to your use case. It may be completely wrong.
              Consult a LOCAL certified electrician before making real-life cable sizing decisions.</p>
            <form method="post">
                <label>Meters: <input type="number" name="meters" required min="1" /></label><br/>
                <label>Amps: <input type="number" name="amps" value="40" /></label><br/>
                <label>Volts: <input type="number" name="volts" value="220" /></label><br/>
                <label>Material: 
                    <select name="material">
                        <option value="cu">Copper (cu)</option>
                        <option value="al">Aluminum (al)</option>
                        <option value="?">Don't know</option>
                    </select>
                </label><br/>
                <label>Max Lines: <input type="number" name="max_lines" value="3" /></label><br/>
                <label>Phases: 
                    <select name="phases">
                        <option value="1">Single Phase (1)</option>
                        <option value="3">Three Phase (3)</option>
                    </select>
                </label><br/>
                <label>Neutral (0 or 1): <input type="number" name="neutral" value="0" /></label><br/>
                <label>Conduit (emt/true/blank): <input name="conduit" /></label><br/><br/>
                <button type="submit" class="submit">Find Cable</button>
            </form>
        '''
    try:
        result = gw.awg.find_cable(
            meters=meters, amps=amps, volts=volts,
            material=material, max_lines=max_lines, 
            phases=phases, conduit=conduit, neutral=neutral
        )
    except Exception as e:
        return f"<p class='error'>Error: {e}</p><p><a href='/awg-finder'>Try again</a></p>"

    return f"""
        <h1>Recommended Cable</h1>
        <ul>
            <li><strong>AWG Size:</strong> {result['awg']}</li>
            <li><strong>Lines:</strong> {result['lines']}</li>
            <li><strong>Total Cables:</strong> {result['cables']}</li>
            <li><strong>Total Length (m):</strong> {result['cable_m']}</li>
            <li><strong>Voltage Drop:</strong> {result['vdrop']:.2f} V ({result['vdperc']:.2f}%)</li>
            <li><strong>Voltage at End:</strong> {result['vend']:.2f} V</li>
            {f"<li><strong>Conduit:</strong> {result['conduit']} ({result['pipe_in']})</li>" if 'conduit' in result else ""}
        </ul>
        <p><a href="/awg-finder">Calculate again</a></p>
    """




...