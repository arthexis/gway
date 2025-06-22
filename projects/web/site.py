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
            help_info = gw.help(project_str)
            full_name = f"{project_str}.{maybe_function}"
            title = f"Help Topics for <code>{full_name}</code>"

    if help_info is None:
        return "<h2>Not Found</h2><p>No help found for the given input.</p>"

    highlight_js = '''
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script>
      window.addEventListener('DOMContentLoaded',function(){
        if(window.hljs){
          document.querySelectorAll('pre code.python').forEach(el => { hljs.highlightElement(el); });
        }
      });
    </script>
    '''

    if "Matches" in help_info:
        # Improvement 3: Clear separation using <hr> and class
        sections = []
        for idx, match in enumerate(help_info["Matches"]):
            section_html = _render_help_section(match, use_query_links=True)
            if idx < len(help_info["Matches"]) - 1:
                # Add a separator between but not after last
                section_html += '<hr class="help-sep">'
            sections.append(section_html)
        # Only inject highlight.js if there is code block
        multi = f"<div class='help-multi'>{''.join(sections)}</div>"
        if "Full Code" in str(help_info):
            multi += highlight_js
        return f"<h1>{title}</h1>{multi}"

    body = _render_help_section(help_info, use_query_links=True)
    # Only inject highlight.js if there is a code block in the output
    if "Full Code" in str(help_info):
        body += highlight_js
    return f"<h1>{title}</h1>{body}"

def _render_help_section(info, use_query_links=False, *args, **kwargs):
    import html

    proj = info.get("Project")
    func = info.get("Function")
    header = ""
    if proj and func:
        if use_query_links:
            proj_link = f'<a href="?topic={proj}">{proj}</a>'
            func_link = f'<a href="?topic={proj}/{func}">{func}</a>'
        else:
            proj_link = html.escape(proj)
            func_link = html.escape(func)
        header = f"""
        <div class="projfunc-row">
            <span class="project">{proj_link}</span>
            <span class="dot">·</span>
            <span class="function">{func_link}</span>
        </div>
        """

    rows = []
    skip_keys = {"Project", "Function"}
    for key, value in info.items():
        if key in skip_keys:
            continue

        # 1. Only autolink References (and plain text fields).
        # 2. Don't autolink Sample CLI, Signature, Full Code, etc.

        if use_query_links and key == "References" and isinstance(value, (list, tuple)):
            refs = [
                f'<a href="?topic={ref}">{html.escape(str(ref))}</a>' for ref in value
            ]
            value = ', '.join(refs)
            value = f"<div class='refs'>{value}</div>"

        # Improvement 4: Copy to clipboard button for Full Code
        elif key == "Full Code":
            code_id = f"code_{abs(hash(value))}"
            value = (
                f"<div class='full-code-block'>"
                f"<button class='copy-btn' onclick=\"copyToClipboard('{code_id}')\">Copy to clipboard</button>"
                f"<pre><code id='{code_id}' class='python'>{html.escape(str(value))}</code></pre>"
                f"</div>"
                "<script>"
                "function copyToClipboard(codeId) {"
                "  var text = document.getElementById(codeId).innerText;"
                "  navigator.clipboard.writeText(text).then(()=>{"
                "    alert('Copied!');"
                "  });"
                "}"
                "</script>"
            )

        # Code fields: no autolinking, just escape & highlight
        elif key in ("Signature", "Example CLI", "Example Code", "Sample CLI"):
            value = f"<pre><code class='python'>{html.escape(str(value))}</code></pre>"

        elif key in ("Docstring", "TODOs"):
            value = f"<div class='doc'>{html.escape(str(value))}</div>"

        # Only for regular text fields, run _autolink_refs
        elif use_query_links and isinstance(value, str):
            value = _autolink_refs(value)
            value = f"<p>{value}</p>"

        else:
            value = f"<p>{html.escape(str(value))}</p>"

        rows.append(f"<section><h3>{key}</h3>{value}</section>")

    return f"<article class='help-entry'>{header}{''.join(rows)}</article>"


def _autolink_refs(text):
    # Link "project" or "project.function" references to their help topics
    import re
    return re.sub(r'\b([a-zA-Z0-9_]+)(?:\.([a-zA-Z0-9_]+))?\b', 
        lambda m: (
            f'<a href="?topic={m.group(1)}">{m.group(1)}</a>' if not m.group(2) 
            else f'<a href="?topic={m.group(1)}/{m.group(2)}">{m.group(1)}.{m.group(2)}</a>'
        ), text)


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

