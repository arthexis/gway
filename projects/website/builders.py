import os
from gway import Gateway, requires

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


@requires("qrcode[pil]")
def build_qr_code(*, value=None):
    """Generate a QR code for a given value and serve it from cache if available."""
    import base64
    import qrcode

    # If no value provided, show a form
    if not value:
        return '''
            <h1>QR Code Generator</h1>
            <form method="get">
                <input type="hidden" name="c" value="qr-code" />
                <input type="text" name="value" placeholder="Enter text or URL" required
                    style="width: 60%; padding: 0.5em; margin-right: 0.5em;" />
                <button type="submit" style="padding: 0.5em;">Generate QR</button>
            </form>
        '''

    # Generate filename: base64 encoding of value + ".png"
    safe_filename = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=") + ".png"
    qr_path = gway.resource("temp", "shared", "qr_codes", safe_filename)

    # Generate QR only if it doesn't already exist
    if not os.path.exists(qr_path):
        img = qrcode.make(value)
        img.save(qr_path)

    # Construct URL to serve QR image
    qr_url = f"/temp/qr_codes/{safe_filename}"

    return f"""
        <h1>QR Code for: <code>{value}</code></h1>
        <img src="{qr_url}" alt="QR Code" style="max-width: 300px;" />
        <p><a href="/?c=qr-code">Generate another</a></p>
    """
