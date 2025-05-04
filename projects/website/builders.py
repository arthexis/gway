from gway import Gateway

gway = Gateway()


def build_readme():
    """Render the README.rst file as HTML."""
    from docutils.core import publish_parts

    readme_path = gway.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def build_help(path=""):
    """Render dynamic help based on GWAY introspection."""
    # Handle None input and normalize separators
    if not path:
        return "<h2>No help topic provided</h2><p>Please enter a valid topic or function name.</p>"

    # Allow whitespace and punctuation as separators (convert to slash first)
    path = path.replace(" ", "/").replace(".", "/").replace("-", "_")
    parts = [p for p in path.strip("/").split("/") if p]

    if len(parts) == 1:
        help_info = gway.help(parts[0])
        title = f"Help for {parts[0]}"
    elif len(parts) == 2:
        help_info = gway.help(parts[0], parts[1])
        title = f"Help for {parts[0]}.{parts[1]}"
    else:
        return "<h2>Invalid help subject</h2><p>Use format: <code>project function</code></p>"

    if help_info is None:
        return "<h2>Function Not Found</h2><p>No help found for the given input.</p>"

    rows = "".join(f"<h3>{k}</h3><pre>{v}</pre>" for k, v in help_info.items())
    return f"<h1>{title}</h1>{rows}"


def build_qr_code(*, value=None):
    """Generate a QR code for a given value and serve it from cache if available."""
    if not value:
        return '''
            <h1>QR Code Generator</h1>
            <form method="get">
                <input type="hidden" name="c" value="qr-code" />
                <input type="text" name="value" placeholder="Enter text or URL" required class="large" />
                <button type="submit" style="padding: 0.5em;">Generate QR</button>
            </form>
        '''
    
    qr_url = gway.project.generate_qr_code_url(value)
    return f"""
        <h1>QR Code for: <code>{value}</code></h1>
        <img src="{qr_url}" alt="QR Code" style="max-width: 300px;" />
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
                <button type="submit" style="padding: 0.5em;">Find Cable</button>
            </form>
        '''

    try:
        result = gway.awg.find_cable(
            meters=meters, amps=amps, volts=volts,
            material=material, max_lines=max_lines, 
            phases=phases, conduit=conduit, neutral=neutral
        )
    except Exception as e:
        return f"<p style='color:red;'>Error: {e}</p><p><a href='/?c=awg-finder'>Try again</a></p>"

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
