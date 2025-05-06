import os
from gway import Gateway, requires

gway = Gateway()

# Considerations for ALL builder functions:
# Don't use inline CSS ever, each user can have different css configurations. 
# Instead use simple common sense names for classes and add them to .css files.
# The class name should not indicate aesthetics, but the function of the element.

def build_readme():
    """Render the README.rst file as HTML."""
    from docutils.core import publish_parts

    readme_path = gway.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def build_help(q=""):
    """Render dynamic help based on GWAY introspection and search-style links."""
    q = q.replace(" ", "/").replace(".", "/").replace("-", "_") if q else ""
    parts = [p for p in q.strip("/").split("/") if p]

    if len(parts) == 0:
        help_info = gway.help()
        title = "Available Projects"
        content = "<ul>"
        for project in help_info["Available Projects"]:
            content += f'<li><a href="?c=help&q={project}">{project}</a></li>'
        content += "</ul>"
        return f"<h1>{title}</h1>{content}"

    elif len(parts) == 1:
        project = parts[0]
        help_info = gway.help(project)
        title = f"Help Topics for <code>{project}</code>"

    elif len(parts) == 2:
        project, function = parts
        help_info = gway.help(project, function)
        title = f"Help for <code>{project}.{function}</code>"

    else:
        return "<h2>Invalid help subject</h2><p>Use format: <code>project function</code></p>"

    if help_info is None:
        return "<h2>Not Found</h2><p>No help found for the given input.</p>"

    if "Matches" in help_info:
        sections = [render_help_section(match, use_query_links=True) for match in help_info["Matches"]]
        return f"<h1>{title}</h1>{''.join(sections)}"

    return f"<h1>{title}</h1>{render_help_section(help_info, use_query_links=True)}"


def render_help_section(info, use_query_links=False):
    """Render a help section with clean formatting and query-style links."""
    rows = []
    for key, value in info.items():
        if use_query_links:
            if key == "Project":
                value = f'<a href="?c=help&q={value}">{value}</a>'
            elif key == "Function":
                proj = info.get("Project", "")
                value = f'<a href="?c=help&q={proj}/{value}">{value}</a>'

        if key in ("Signature", "Example CLI", "Example Code", "Full Code"):
            value = f"<pre><code>{value}</code></pre>"
        elif key in ("Docstring", "TODOs"):
            value = f"<div class='doc'>{value}</div>"
        else:
            value = f"<p>{value}</p>"

        rows.append(f"<section><h3>{key}</h3>{value}</section>")

    return f"<article class='help-entry'>{''.join(rows)}</article>"


def build_qr_code(*, value=None):
    """Generate a QR code for a given value and serve it from cache if available."""
    if not value:
        return '''
            <h1>QR Code Generator</h1>
            <form method="get">
                <input type="hidden" name="c" value="qr-code" />
                <input type="text" name="value" placeholder="Enter text or URL" required class="main" />
                <button type="submit" class="submit">Generate QR</button>
            </form>
        '''
    
    qr_url = gway.project.generate_qr_code_url(value)
    return f"""
        <h1>QR Code for:</h1>
        <h2><code>{value}</code></h2>
        <img src="{qr_url}" alt="QR Code" class="qr" />
        <p><a href="/?c=qr-code">Generate another</a></p>
    """


def build_awg_finder(
    *, meters=None, amps="40", volts="220", material="cu", 
    max_lines="3", phases="1", conduit=None, neutral="0"
):
    """Page builder for AWG cable finder with HTML form and result."""
    
    if not meters:
        return '''
            <h1>AWG Cable Finder</h1>
            <p>Warning: This calculator may not be applicable to your use case.
              Consult your local electrical code before making real-life cable sizing decisions.</p>
            <form method="get">
                <input type="hidden" name="c" value="awg-finder" />
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
        result = gway.awg.find_cable(
            meters=meters, amps=amps, volts=volts,
            material=material, max_lines=max_lines, 
            phases=phases, conduit=conduit, neutral=neutral
        )
    except Exception as e:
        return f"<p class='error'>Error: {e}</p><p><a href='/?c=awg-finder'>Try again</a></p>"

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
        <p><a href="/?c=awg-finder">Calculate again</a></p>
    """

@requires("bottle")
def build_css_selector():
    """Allows user to choose from available stylesheets and shows current selection."""
    from bottle import request, response, redirect

    styles_dir = gway.resource("data", "static", "styles")
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
        <form method="post" action="/?c=css-selector">
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
