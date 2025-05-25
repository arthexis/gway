
def readme(*args, **kwargs):
    """Render the README.rst file as HTML."""
    from gway import gw
    from docutils.core import publish_parts

    readme_path = gw.resource("README.rst")
    with open(readme_path, encoding="utf-8") as f:
        rst_content = f.read()

    html_parts = publish_parts(source=rst_content, writer_name="html")
    return html_parts["html_body"]
