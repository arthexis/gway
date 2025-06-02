# projects/web/view.py

# These view functions can be rendered by setup_app.
# Views receive the query params and json payload merged into kwargs.
# Don't use inline CSS ever, each user can have their own style sheets.

import os
from docutils.core import publish_parts
from bottle import request, response, redirect
from gway import gw


def view_readme(*args, **kwargs):
    """Render the README.rst file as HTML."""

    readme_path = gw.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def view_help(topic="", *args, **kwargs):
    """Render dynamic help based on GWAY introspection and search-style links."""

    # 

    from gway import gw
    topic = topic.replace(" ", "/").replace(".", "/").replace("-", "_") if topic else ""
    parts = [p for p in topic.strip("/").split("/") if p]

    if len(parts) == 0:
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

    elif len(parts) == 2:
        project, function = parts
        help_info = gw.help(project, function)
        title = f"Help for <code>{project}.{function}</code>"

    else:
        return "<h2>Invalid help subject</h2><p>Use format: <code>project function</code></p>"

    if help_info is None:
        return "<h2>Not Found</h2><p>No help found for the given input.</p>"

    if "Matches" in help_info:
        sections = [_help_section(match, use_query_links=True) for match in help_info["Matches"]]
        return f"<h1>{title}</h1>{''.join(sections)}"

    return f"<h1>{title}</h1>{_help_section(help_info, use_query_links=True)}"


def _help_section(info, use_query_links=False, *args, **kwargs):
    """Render a help section with clean formatting and route-based query links."""
    rows = []
    for key, value in info.items():
        if use_query_links:
            if key == "Project":
                value = f'<a href="?topic={value}">{value}</a>'
            elif key == "Function":
                proj = info.get("Project", "")
                value = f'<a href="?topic={proj}/{value}">{value}</a>'

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

def view_register(**kwargs):
    """
    Register a node using .cdv-based storage with approval handled by gw.approval.

    Accepts:
    - node_key: str
    - secret_key: str
    - start: optional ISO date string, defaults to now
    - end: optional ISO date string
    - credits: optional int
    - role: optional str, defaults to 'ADMIN'
    - message: optional str, included in approval email
    - response: optional 'approve:<key>' or 'deny:<key>'
    """
    import os
    from datetime import datetime
    from gway import gw

    registry_path = ("work", "registry.cdv")
    now_iso = datetime.now().isoformat()

    # 1) If this request has a response parameter, resolve it via gw.approval.resolve()
    response = kwargs.get("response")
    if response:
        status, details = gw.approval.resolve(response)

        if status == "error":
            return f"<p class='error'>{details}</p>"

        # details is the original payload dict we passed to request()
        payload = details
        node_key   = payload.get("node_key")
        secret_key = payload.get("secret_key")
        start      = payload.get("start")
        end        = payload.get("end")
        credits    = payload.get("credits")
        role       = payload.get("role")

        if status == "approved":
            # Store into registry.cdv under node_key
            record = {
                "secret_key": secret_key,
                "start":      start,
            }
            if end:
                record["end"] = end
            if credits:
                record["credits"] = str(credits)
            record["role"] = role

            gw.cdv.store(*registry_path, node_key, **record)
            return f"<p>Node <code>{node_key}</code> approved.</p>"

        elif status == "denied":
            # Mark denied in registry.cdv (optional)
            record = {
                "secret_key": secret_key,
                "denied":     now_iso,
                "start":      start,
            }
            if end:
                record["end"] = end
            if credits:
                record["credits"] = str(credits)
            record["role"] = role

            gw.cdv.store(*registry_path, node_key, **record)
            return f"<p>Node <code>{node_key}</code> denied.</p>"

    # 2) If no kwargs provided at all, render the HTML form
    if not kwargs:
        return """
        <h1>Register Node</h1>
        <p>This form is intended for existing customers and local development.</p>
        <form method='post'>
            <label>Node Key: <input name='node_key' required></label><br>
            <label>Secret Key: <input name='secret_key' required></label><br>
            <label>Start (optional): <input name='start' placeholder='YYYY-MM-DD'></label><br>
            <label>End (optional): <input name='end' placeholder='YYYY-MM-DD'></label><br>
            <label>Credits (optional): <input name='credits' type='number'></label><br>
            <label>Role (optional): <input name='role' placeholder='ADMIN'></label><br>
            <label>Message (optional): <br>
                <textarea name='message' rows='4' cols='40' placeholder='Add any message to the admin'></textarea>
            </label><br>
            <button type='submit'>Submit</button>
        </form>
        """

    # 3) Otherwise, process a new registration submission
    node_key   = kwargs.get("node_key")
    secret_key = kwargs.get("secret_key")
    start      = kwargs.get("start") or now_iso
    end        = kwargs.get("end")
    credits    = kwargs.get("credits")
    role       = (kwargs.get("role") or "ADMIN").upper()
    message    = kwargs.get("message", "").strip()

    if not node_key or not secret_key:
        return "<p class='error'>Missing node_key or secret_key.</p>"

    # 3a) Check if this node_key already exists in registry.cdv
    existing = gw.cdv.find(*registry_path, node_key)
    if existing:
        if "start" in existing and "end" in existing and not existing.get("denied"):
            return f"<p>Node <code>{node_key}</code> already registered.</p>"
        if existing.get("denied"):
            return f"<p>Node <code>{node_key}</code> has been denied.</p>"
        return f"<p>Node <code>{node_key}</code> registration is pending approval.</p>"

    # 3b) Build the payload for approval
    payload = {
        "node_key":   node_key,
        "secret_key": secret_key,
        "start":      start,
        "end":        end,
        "credits":    credits,
        "role":       role,
    }
    if message:
        payload["message"] = message

    # 3c) Request approval via gw.approval.request()
    try:
        gw.approval.request(
            category="register",
            data=payload,
            role=role,
            send_email=True
        )
    except Exception as e:
        return f"<p class='error'>Failed to queue approval request: {e}</p>"

    return f"<p>Registration for <code>{node_key}</code> submitted. An admin will review soon.</p>"
