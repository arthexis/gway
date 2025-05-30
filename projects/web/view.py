# web/view.py

# These view functions can be rendered by setup_app.
# Views receive the query params and json payload merged into kwargs.
# Don't use inline CSS ever, each user can have different css configurations. 

def readme(*args, **kwargs):
    """Render the README.rst file as HTML."""
    from gway import gw
    from docutils.core import publish_parts

    readme_path = gw.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]


def help(topic="", *args, **kwargs):
    """Render dynamic help based on GWAY introspection and search-style links."""
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


def qr_code(*args, value=None, **kwargs):
    """Generate a QR code for a given value and serve it from cache if available."""
    from gway import gw
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


def awg_finder(
    *args, meters=None, amps="40", volts="220", material="cu", 
    max_lines="3", phases="1", conduit=None, neutral="0", **kwargs
):
    """Page builder for AWG cable finder with HTML form and result."""
    from gway import gw
    if not meters:
        return '''
            <h1>AWG Cable Finder</h1>
            <p>Warning: This calculator may not be applicable to your use case.
              Consult your local electrical code before making real-life cable sizing decisions.</p>
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


def theme():
    """Allows user to choose from available stylesheets and shows current selection."""
    import os
    from gway import gw
    from bottle import request, response, redirect

    styles_dir = gw.resource("data", "static", "styles")
    available = sorted(
        f for f in os.listdir(styles_dir)
        if f.endswith(".css") and not f.startswith("default.") and
        os.path.isfile(os.path.join(styles_dir, f))
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
        <form method="post">
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


def register(**kwargs):
    """
    Register a node by accepting a POST with node_key and secret_key.
    Stores registration requests in registry.sqlite with nodes_allowed and nodes_denied tables.
    Sends email to ADMIN_EMAIL with approve/deny links.
    Handles approval/denial responses via a 'response' query param.
    """
    import os
    import secrets
    from gway import gw
    from bottle import request

    # Database file path inside data folder
    db_path = ("temp", "registry.sqlite")

    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        return "<p class='error'>Admin email not configured.</p>"
    
    # Connect to DB using gw.sql.connect
    with gw.sql.connect(*db_path, row_factory=True) as cur:
        # Ensure tables exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_key TEXT UNIQUE,
                secret_key TEXT,
                request_secret TEXT UNIQUE,
                approved INTEGER DEFAULT 0,
                denied INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nodes_allowed (
                node_key TEXT PRIMARY KEY,
                secret_key TEXT,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nodes_denied (
                node_key TEXT PRIMARY KEY,
                secret_key TEXT,
                denied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Process response param for approval/denial
        response = kwargs.get("response", "")
        if response.startswith("approve:") or response.startswith("deny:"):
            action, req_secret = response.split(":", 1)
            cur.execute("SELECT node_key, secret_key, approved, denied FROM requests WHERE request_secret = ?", (req_secret,))
            row = cur.fetchone()
            if not row:
                return "<p class='error'>Invalid or expired approval token.</p>"
            if row["approved"]:
                return "<p>Request already approved.</p>"
            if row["denied"]:
                return "<p>Request already denied.</p>"

            node_key = row["node_key"]
            secret_key = row["secret_key"]

            if action == "approve":
                # Mark approved
                cur.execute("UPDATE requests SET approved=1 WHERE request_secret=?", (req_secret,))
                # Insert into nodes_allowed (ignore if exists)
                cur.execute("""
                    INSERT OR REPLACE INTO nodes_allowed (node_key, secret_key) VALUES (?, ?)
                """, (node_key, secret_key))
                return f"<p>Node <code>{node_key}</code> approved successfully.</p>"

            elif action == "deny":
                # Mark denied
                cur.execute("UPDATE requests SET denied=1 WHERE request_secret=?", (req_secret,))
                # Insert into nodes_denied (ignore if exists)
                cur.execute("""
                    INSERT OR REPLACE INTO nodes_denied (node_key, secret_key) VALUES (?, ?)
                """, (node_key, secret_key))
                return f"<p>Node <code>{node_key}</code> denied successfully.</p>"

            else:
                return "<p class='error'>Unknown response action.</p>"

        # Otherwise, expect POST with registration info
        if request.method != "POST":
            return """
                <h1>Node Registration</h1>
                <p>Please POST JSON with <code>node_key</code> and <code>secret_key</code>.</p>
            """

        node_key = kwargs.get("node_key")
        secret_key = kwargs.get("secret_key")
        if not node_key or not secret_key:
            return "<p class='error'>Missing required fields: node_key and secret_key.</p>"

        # Check if node_key already registered or pending
        cur.execute("SELECT approved, denied FROM requests WHERE node_key = ?", (node_key,))
        existing = cur.fetchone()
        if existing:
            if existing["approved"]:
                return f"<p>Node <code>{node_key}</code> is already approved.</p>"
            if existing["denied"]:
                return f"<p>Node <code>{node_key}</code> has been denied previously.</p>"
            return f"<p>Node <code>{node_key}</code> registration is pending approval.</p>"

        # Generate a unique request secret for approval links
        request_secret = secrets.token_urlsafe(32)

        # Insert registration request
        cur.execute("""
            INSERT INTO requests (node_key, secret_key, request_secret) VALUES (?, ?, ?)
        """, (node_key, secret_key, request_secret))

        # Send email to admin with approve/deny links
        base_url = gw.web.app_url("register-node")

        approve_link = f"{base_url}?response=approve:{request_secret}"
        deny_link = f"{base_url}?response=deny:{request_secret}"

        email_subject = f"Node Registration Request: {node_key}"
        email_body = f"""
A new node registration request has been received:

Node Key: {node_key}

To approve the node, click here:
{approve_link}

To deny the node, click here:
{deny_link}
"""
        # Send email
        try:
            gw.mail.send(
                to=admin_email,
                subject=email_subject,
                body=email_body
            )
        except Exception as e:
            return f"<p class='error'>Failed to send notification email: {e}</p>"

        return f"<p>Registration request for node <code>{node_key}</code> received. An administrator will review it shortly.</p>"
