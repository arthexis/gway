import os
from gway import gw, requires


# Don't use inline CSS ever, each user can have different css configurations. 

def view_gway(*args, **kwargs):
    """Render the README.rst file as HTML."""
    from docutils.core import publish_parts

    readme_path = gw.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def view_help(topic="", *args, **kwargs):
    """Render dynamic help based on GWAY introspection and search-style links."""
    topic = topic.replace(" ", "/").replace(".", "/").replace("-", "_") if topic else ""
    parts = [p for p in topic.strip("/").split("/") if p]

    if len(parts) == 0:
        help_info = gw.help()
        title = "Available Projects"
        content = "<ul>"
        for project in help_info["Available Projects"]:
            content += f'<li><a href="/help?topic={project}">{project}</a></li>'
        content += "</ul>"
        return f"<h1>{title}</h1>{content}"

    elif len(parts) == 1:
        project = parts[0]
        help_info = gw.help(project)
        title = f"Help Topics for <code>{project}</code>"

    elif len(parts) == 2:
        project, function = parts
        help_info = gw.help(project, function)
        title = f"Help for <code>{project}.{function}</code>"

    else:
        return "<h2>Invalid help subject</h2><p>Use format: <code>project function</code></p>"

    if help_info is None:
        return "<h2>Not Found</h2><p>No help found for the given input.</p>"

    if "Matches" in help_info:
        sections = [help_section(match, use_query_links=True) for match in help_info["Matches"]]
        return f"<h1>{title}</h1>{''.join(sections)}"

    return f"<h1>{title}</h1>{help_section(help_info, use_query_links=True)}"


def help_section(info, use_query_links=False, *args, **kwargs):
    """Render a help section with clean formatting and route-based query links."""
    rows = []
    for key, value in info.items():
        if use_query_links:
            if key == "Project":
                value = f'<a href="/help?topic={value}">{value}</a>'
            elif key == "Function":
                proj = info.get("Project", "")
                value = f'<a href="/help?topic={proj}/{value}">{value}</a>'

        if key in ("Signature", "Example CLI", "Example Code", "Full Code"):
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
            <form method="post" action="/qr-code">
                <input type="text" name="value" placeholder="Enter text or URL" required class="main" />
                <button type="submit" class="submit">Generate QR</button>
            </form>
        '''
    qr_url = gw.qr_code.generate_url(value)
    return f"""
        <h1>QR Code for:</h1>
        <h2><code>{value}</code></h2>
        <img src="{qr_url}" alt="QR Code" class="qr" />
        <p><a href="/qr-code">Generate another</a></p>
    """


def view_awg_finder(
    *args, meters=None, amps="40", volts="220", material="cu", 
    max_lines="3", phases="1", conduit=None, neutral="0", **kwargs
):
    """Page builder for AWG cable finder with HTML form and result."""
    
    if not meters:
        return '''
            <h1>AWG Cable Finder</h1>
            <p>Warning: This calculator may not be applicable to your use case.
              Consult your local electrical code before making real-life cable sizing decisions.</p>
            <form method="get" action="/awg-finder">
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

@requires("bottle")
def view_css_selector():
    """Allows user to choose from available stylesheets and shows current selection."""
    from bottle import request, response, redirect

    styles_dir = gw.resource("data", "static", "styles")
    available = sorted(
        f for f in os.listdir(styles_dir)
        if f.endswith(".css") and os.path.isfile(os.path.join(styles_dir, f))
    )

    # Handle form submission
    if request.method == "POST":
        selected = request.forms.get("css")
        if selected in available:
            response.set_cookie("css", selected, path="/")
            return redirect("/")  # Redirect to GET view
        else:
            return f"<p class='error'>Invalid selection: {selected}</p>"

    current = request.get_cookie("css") or "default.css"

    form = f"""
        <h1>Select CSS Theme</h1>
        <p>Current theme: <strong>{current}</strong></p>
        <form method="post" action="/css-selector">
            <select name="css">
                {{options}}
            </select>
            <button type="submit">Set Theme</button>
        </form>
    """

    options = "\n".join(
        f'<option value="{css}"{" selected" if css == current else ""}>{css}</option>'
        for css in available
    )
    return form.format(options=options)
