# file: projects/web/site.py

import os
import html
import shlex
import traceback
from docutils.core import publish_parts
from pathlib import Path
import re
from gway import gw, __
from gway.console import process, chunk
import markdown as mdlib

_DEFAULT_TOME = __('[README]', 'README')

def view_reader(
    *parts,
    tome=_DEFAULT_TOME,
    ext=None,
    origin="root",
    **kwargs,
):
    """
    Render a resource file (.rst or .md) as HTML.
    If origin='root', only files in the resource root (no subfolders).
    Never serves files starting with dot or underscore.
    """
    if parts and (tome == _DEFAULT_TOME or tome == "README"):
        tome = "/".join(str(p).strip("/") for p in parts)

    gw.verbose(f"[reader] Called with tome={tome!r}, ext={ext!r}, origin={origin!r}")
    fname = _sanitize_filename(tome)
    gw.verbose(f"[reader] Sanitized filename: {fname}")

    ext = (str(ext).strip().lower() if ext else None)
    if ext and ext.startswith('.'):
        ext = ext[1:]
    gw.verbose(f"[reader] Normalized ext: {ext}")

    # Security: Never allow files starting with dot/underscore
    if _is_hidden_or_private(fname):
        gw.verbose(f"[reader] Access denied due to hidden/private filename: {fname}")
        return "<b>Access denied.</b>"

    def file_variants(base):
        if base.endswith('/'):
            base = base.rstrip('/') + '/README'
        if ext in {'rst', 'md'}:
            variants = [f"{base}.{ext}"]
        else:
            base_, ext_ = os.path.splitext(base)
            if ext_ in {'.rst', '.md'}:
                variants = [base]
            else:
                variants = [f"{base}.rst", f"{base}.md"]
        gw.verbose(f"[reader] Candidate variants for base {base}: {variants}")
        return variants

    use_root = origin == "root" and "/" not in tome
    if use_root:
        resource_dir = os.path.dirname(gw.resource('README.rst'))  # This IS the resource root
        gw.verbose(f"[reader] Resource root directory: {resource_dir}")
        for candidate in file_variants(fname):
            gw.verbose(f"[reader] Checking candidate: {candidate}")
            if _is_hidden_or_private(candidate):
                gw.verbose(f"[reader] Skipped hidden/private candidate: {candidate}")
                continue
            try:
                resource_path = gw.resource(candidate)
                gw.verbose(f"[reader] Resolved resource path: {resource_path}")
            except Exception as e:
                gw.verbose(f"[reader] gw.resource({candidate}) exception: {e}")
                continue
            # Only allow files in the resource root
            if not os.path.isfile(resource_path):
                gw.verbose(f"[reader] Not a file: {resource_path}")
                continue
            if os.path.dirname(resource_path) != resource_dir:
                gw.verbose(f"[reader] File not in resource root: {resource_path}")
                continue
            if _is_hidden_or_private(os.path.basename(resource_path)):
                gw.verbose(f"[reader] File rejected (hidden/private): {resource_path}")
                continue
            gw.verbose(f"[reader] Will open file: {resource_path}")
            try:
                with open(resource_path, encoding="utf-8") as f:
                    content = f.read()
                if candidate.lower().endswith(".rst"):
                    html = publish_parts(source=content, writer_name="html")["html_body"]
                elif candidate.lower().endswith(".md"):
                    html = mdlib.markdown(content)
                else:
                    gw.verbose(f"[reader] Unsupported file type for {candidate}")
                    html = "<b>Unsupported file type.</b>"
                gw.verbose(f"[reader] Successfully rendered {candidate}")
                return html
            except Exception as e:
                gw.verbose(f"[reader] Exception reading or rendering {resource_path}: {e}")
                continue
        exts = ' or '.join(['.rst', '.md']) if not ext else f".{ext}"
        gw.verbose(f"[reader] File not found or not allowed: {fname}{exts}; falling back to static")

    if origin == "root":
        origin = "static"

    if origin == "static":
        base_dir = Path(gw.resource('data', 'static'))
        safe_path = _sanitize_relpath(tome)
        gw.verbose(f"[reader] Static safe path: {safe_path!r}")
        if not safe_path:
            return "<b>Access denied.</b>"
        candidate_dir = Path(base_dir, safe_path)
        if candidate_dir.is_dir():
            safe_path = f"{safe_path.rstrip('/')}/README"
        for candidate in file_variants(safe_path):
            gw.verbose(f"[reader] Checking static candidate: {candidate}")
            parts = candidate.split('/')
            resource_path = gw.resource('data', 'static', *parts)
            resolved = Path(resource_path).resolve()
            if not resolved.is_file() or base_dir not in resolved.parents:
                gw.verbose(f"[reader] Invalid static path: {resolved}")
                continue
            if any(_is_hidden_or_private(p) for p in parts):
                gw.verbose(f"[reader] Hidden/private segment in {candidate}")
                continue
            try:
                with open(resolved, encoding='utf-8') as f:
                    content = f.read()
                if resolved.suffix == '.rst':
                    html = publish_parts(source=content, writer_name='html')['html_body']
                elif resolved.suffix == '.md':
                    html = mdlib.markdown(content)
                else:
                    html = '<b>Unsupported file type.</b>'
                return html
            except Exception as e:
                gw.verbose(f"[reader] Exception reading {resolved}: {e}")
                continue
        exts = ' or '.join(['.rst', '.md']) if not ext else f".{ext}"
        return f"<b>File not found or not allowed: {safe_path}{exts}</b>"

    # Fallback for other origins (not fully implemented here)
    gw.verbose(f"[view_reader] Non-root origin {origin} not implemented in this snippet.")
    return "<b>Invalid or unsupported origin.</b>"

def _sanitize_filename(fname):
    """
    Sanitize the filename: only allow dots and alphanumerics. No slashes, no backslashes, no "..".
    """
    fname = str(fname)
    fname = fname.replace('/', '').replace('\\', '').replace('..', '')
    fname = ''.join(c for c in fname if c.isalnum() or c in '._-')
    return fname

def _sanitize_relpath(path):
    """Sanitize a relative path under data/static."""
    parts = []
    segments = str(path).split('/')
    for i, segment in enumerate(segments):
        segment = segment.strip()
        if not segment:
            if i == len(segments) - 1:
                continue  # allow trailing slash
            return None
        if segment.startswith('.') or segment.startswith('_') or '..' in segment:
            return None
        clean = ''.join(c for c in segment if c.isalnum() or c in '._-')
        parts.append(clean)
    return '/'.join(parts)

def _is_hidden_or_private(fname):
    """
    Returns True if filename (or its extension) starts with a dot or underscore.
    """
    fname = os.path.basename(fname)
    if not fname:
        return True
    if fname[0] in {'.', '_'}:
        return True
    name, ext = os.path.splitext(fname)
    if ext and ext[1:2] in {'.', '_'}:
        return True
    if name.startswith('.') or name.startswith('_'):
        return True
    return False

def _looks_like_html(text: str) -> bool:
    """Heuristic check for HTML content."""
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped:
        return False
    return bool(re.search(r'<[a-zA-Z][^>]*>', stripped))

def view_help(topic="", *args, **kwargs):
    """
    Render dynamic help based on GWAY introspection and search-style links.
    If there is an exact match in the search, show it at the top (highlighted).
    """

    # gw.gelp at all times, compliment this result with other information.

    topic_in = topic or ""

    # --- Local console commands via search box ---
    if topic_in.strip().startswith(">"):
        if gw.web.server.is_local():
            cmd_str = topic_in.strip()[1:].strip()
            if not cmd_str:
                return "<i>No command provided.</i>"
            import shlex, html
            from gway.console import chunk, process
            try:
                tokens = shlex.split(cmd_str)
                commands = chunk(tokens)
                results, _ = process(commands)
                html_parts = []
                for r in results:
                    if r is None:
                        continue
                    if isinstance(r, str) and _looks_like_html(r):
                        html_parts.append(r)
                    else:
                        html_parts.append(gw.cast.to_html(r))
                if not html_parts:
                    res_dict = gw.results.get_results()
                    res_html = gw.cast.to_html(res_dict)
                    return (
                        "<div class='cli-result'>"
                        "<i>No result returned. Showing gw.results:</i><hr>"
                        + res_html + "</div>"
                    )
                return "<div class='cli-result'>" + "<hr>".join(html_parts) + "</div>"
            except SystemExit as ex:
                if gw.debug_enabled:
                    tb = traceback.format_exc()
                    log_tail = ""
                    try:
                        log_path = gw.resource("logs", "gway.log")
                        with open(log_path) as lf:
                            log_tail = "".join(lf.readlines()[-20:])
                    except Exception:
                        log_tail = "(unable to read log)"
                    return (
                        "<h2>Command Error</h2>"
                        f"<pre>{html.escape(str(ex))}</pre>"
                        f"<pre>{html.escape(tb)}</pre>"
                        f"<pre>{html.escape(log_tail)}</pre>"
                    )
                return f"<pre>{html.escape(str(ex))}</pre>"
            except Exception as ex:
                if gw.debug_enabled:
                    tb = traceback.format_exc()
                    log_tail = ""
                    try:
                        log_path = gw.resource("logs", "gway.log")
                        with open(log_path) as lf:
                            log_tail = "".join(lf.readlines()[-20:])
                    except Exception:
                        log_tail = "(unable to read log)"
                    return (
                        "<h2>Command Error</h2>"
                        f"<pre>{html.escape(str(ex))}</pre>"
                        f"<pre>{html.escape(tb)}</pre>"
                        f"<pre>{html.escape(log_tail)}</pre>"
                    )
                return f"<pre>{html.escape(str(ex))}</pre>"
        else:
            return "<b>Console commands disabled (not local).</b>"
          
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

    # --- Exact match highlighting logic ---
    # Only applies if help_info contains "Matches"
    if "Matches" in help_info:
        matches = help_info["Matches"]
        exact_key = (topic_in.replace(" ", "/").replace(".", "/").replace("-", "_")).strip("/")
        # Try to find an exact match (project, or project/function) in matches
        def canonical_str(m):
            p, f = m.get("Project", ""), m.get("Function", "")
            return (f"{p}/{f}" if f else p).replace(".", "/").replace("-", "_")
        exact = None
        exact_idx = -1
        for idx, m in enumerate(matches):
            if canonical_str(m).lower() == exact_key.lower():
                exact = m
                exact_idx = idx
                break

        sections = []
        # If found, show exact at top with highlight
        if exact is not None:
            sections.append('<div class="help-exact">' + _render_help_section(exact, use_query_links=True, highlight=True) + '</div>')
            # Add separator if there are more matches
            if len(matches) > 1:
                sections.append('<hr class="help-sep">')
            # Remove exact match from below
            rest = [m for i, m in enumerate(matches) if i != exact_idx]
        else:
            rest = matches

        for idx, match in enumerate(rest):
            section_html = _render_help_section(match, use_query_links=True)
            if idx < len(rest) - 1:
                section_html += '<hr class="help-sep">'
            sections.append(section_html)

        multi = f"<div class='help-multi'>{''.join(sections)}</div>"
        page = f"<h1>{title}</h1>{multi}"
        if "class='python'" in page:
            page += highlight_js
        return page

    # Not a multi-match result: just render normally
    body = _render_help_section(help_info, use_query_links=True)
    page = f"<h1>{title}</h1>{body}"
    if "class='python'" in page:
        page += highlight_js
    return page

def _render_help_section(info, use_query_links=False, highlight=False, *args, **kwargs):
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

        elif key == "Parameters" and isinstance(value, list):
            rows_html = []
            for p in value:
                builder = p.get("builder")
                if builder and use_query_links:
                    builder = f'<a href="?topic={builder}">{html.escape(builder)}</a>'
                elif builder:
                    builder = html.escape(builder)
                else:
                    builder = ""
                rows_html.append(
                    f"<tr><td>{html.escape(p['name'])}</td><td>{html.escape(p.get('type',''))}</td><td>{builder}</td></tr>"
                )
            value = (
                "<table class='param-table'><tr><th>Name</th><th>Type</th><th>Builder</th></tr>"
                + "".join(rows_html)
                + "</table>"
            )

        elif key in ("Docstring", "TODOs"):
            value = f"<div class='doc'>{html.escape(str(value))}</div>"

        # Only for regular text fields, run _autolink_refs
        elif use_query_links and isinstance(value, str):
            value = _autolink_refs(value)
            value = f"<p>{value}</p>"

        else:
            value = f"<p>{html.escape(str(value))}</p>"

        rows.append(f"<section><h3>{key}</h3>{value}</section>")

    # Highlight exact matches with a CSS class
    article_class = 'help-entry'
    if highlight:
        article_class += ' help-entry-exact'
    return f"<article class='{article_class}'>{header}{''.join(rows)}</article>"

def _autolink_refs(text):
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
    qr_url = gw.studio.qr.generate_url(value)
    back_link = gw.web.app_url("qr-code")
    return f"""
        <h1>QR Code for:</h1>
        <h2><code>{value}</code></h2>
        <img src="{qr_url}" alt="QR Code" class="qr" />
        <p><a href="{back_link}">Generate another</a></p>
    """


def _create_github_issue(title: str, body: str) -> str:
    """Create an issue in the GWAY repository and return the issue URL."""
    return gw.hub.create_issue(title, body)


def view_feedback(*, name=None, email=None, topic=None, message=None, create_issue=None):
    """Display feedback form and submit feedback as a GitHub issue."""
    import html
    from bottle import request

    token = gw.hub.get_token()
    mail_configured = all(
        os.environ.get(k)
        for k in ["MAIL_SENDER", "MAIL_PASSWORD", "SMTP_SERVER", "SMTP_PORT"]
    )
    if request.method != "POST" and not token and not mail_configured:
        return (
            "<h1>Feedback unavailable</h1>"
            "<p>GitHub token and mail settings not configured.</p>"
        )

    if request.method == "POST":
        name = (name or "").strip()
        email = (email or "").strip()
        topic = (topic or "").strip()
        message = (message or "").strip()
        create_issue = bool(create_issue)

        missing = [field for field, val in [
            ("Name", name),
            ("Email", email),
            ("Topic", topic),
            ("Message", message),
        ] if not val]
        if missing:
            miss = ", ".join(missing)
            back = gw.web.app.build_url("feedback")
            return f"<h1>Missing required fields: {html.escape(miss)}</h1><p><a href='{back}'>Back</a></p>"

        issue_url = ""
        fallback_to_mail = False
        if create_issue:
            body = f"**From:** {name}\n\n{message}"
            try:
                issue_url = _create_github_issue(topic, body)
            except Exception:
                fallback_to_mail = True
                gw.mail.send(
                    f"Feedback: {topic}",
                    body=f"From: {name} <{email}>\n\n{message}",
                )
        else:
            gw.mail.send(
                f"Feedback: {topic}",
                body=f"From: {name} <{email}>\n\n{message}",
            )

        msg = "<h1>Thank you for your feedback!</h1>"
        if issue_url:
            msg += f"<p>It was recorded as <a href='{issue_url}'>GitHub issue</a>.</p>"
        elif fallback_to_mail:
            msg += "<p>GitHub issue creation failed; feedback sent via email.</p>"
        return msg

    issue_option = (
        "<label class=\"checkbox-right\">"
        "Optional: Create an Issue Report for GWAY or this website."
        "<input type=\"checkbox\" name=\"create_issue\" value=\"1\" {('checked' if create_issue else '')}/>"
        "</label>"
    ) if token else "<p>(GitHub issue creation unavailable)</p>"
    return f"""
        <h1>Send Feedback</h1>
        <p>Your name and message may be publicly displayed and processed. Your email will be kept private.</p>
        <form method="post">
            <input type="text" name="name" placeholder="Your Name" required class="main" value="{html.escape(name or '')}" />
            <input type="email" name="email" placeholder="Email" required class="main" value="{html.escape(email or '')}" />
            <input type="text" name="topic" placeholder="Topic" required class="main" value="{html.escape(topic or '')}" />
            <textarea name="message" placeholder="Message" required rows="6" class="main">{html.escape(message or '')}</textarea>
            {issue_option}
            <button type="submit" class="submit btn-block">Submit</button>
        </form>
    """


def view_debug_info():
    """Return HTML with debug info about the current request and log tail."""
    from bottle import request
    import html as _html

    info = []
    info.append(f"<b>URL:</b> {_html.escape(request.url or '')}")
    info.append(f"<b>Method:</b> {_html.escape(request.method or '')}")
    info.append(f"<b>Version:</b> {_html.escape(gw.version())}")
    try:
        commit = gw.hub.commit()
        if commit:
            info.append(f"<b>Commit:</b> {_html.escape(commit)}")
    except Exception:
        pass

    log_tail = ""
    try:
        log_path = gw.resource("logs", "gway.log")
        with open(log_path, "r", encoding="utf-8") as lf:
            lines = lf.readlines()[-20:]
            log_tail = "".join(lines)
    except Exception:
        log_tail = "(log unavailable)"

    return (
        "<div class='debug-info'>" + "<br>".join(info) +
        f"<pre>{_html.escape(log_tail)}</pre></div>"
    )


def view_future_updates():
    """Show pending version and changelog information."""
    import html as _html
    import requests

    current = gw.version()
    latest = None
    try:
        resp = requests.get("https://pypi.org/pypi/gway/json", timeout=5)
        resp.raise_for_status()
        latest = resp.json()["info"]["version"]
    except Exception as e:
        gw.verbose(f"Failed to fetch PyPI version: {e}")

    if latest and latest != current:
        notice = (
            f"There is a newer version of GWAY pending: { _html.escape(latest) }"
            f" (installed { _html.escape(current) })."
        )
    else:
        latest = latest or current
        notice = f"We are at the latest version ({ _html.escape(latest) })."

    changes = ""
    try:
        from pathlib import Path

        path = Path(gw.resource("CHANGELOG.rst"))
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if "Unreleased" in lines:
            idx = lines.index("Unreleased") + 2
            body = []
            while idx < len(lines) and lines[idx].startswith("- "):
                body.append(lines[idx])
                idx += 1
            changes = "\n".join(body).strip()
    except Exception:
        pass

    if changes:
        changelog = "<pre>" + _html.escape(changes) + "</pre>"
    else:
        changelog = "<p>No pending changes.</p>"

    return (
        "<h1>Future Updates</h1>"
        f"<p>{notice}</p>"
        "<h2>Unreleased Changes</h2>" + changelog
    )


def view_project_readmes():
    """Render an HTML tree of README links discovered under ``data/static``."""
    base_dir = Path(gw.resource("data", "static"))

    def insert(tree: dict, parts: tuple[str, ...], url: str) -> None:
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
        node["_url"] = url

    tree: dict = {}
    for path in sorted(base_dir.rglob("README.rst")):
        rel = path.relative_to(base_dir).with_suffix("")
        parts = rel.parts
        if any(_is_hidden_or_private(p) for p in parts):
            continue
        if parts and parts[-1].lower() == "readme":
            parts = parts[:-1]
        tome = "/".join(parts)
        url = gw.web.app.build_url("web", "site", "reader", tome=tome)
        insert(tree, parts, url)

    def render(node: dict, root: bool = False) -> str:
        items = []
        for name, child in sorted(node.items()):
            if name == "_url":
                continue
            label = html.escape(name.replace("_", " ").title())
            url = child.get("_url")
            link = f"<a href='{url}'>{label}</a>" if url else label
            sub = render(child, False)
            items.append(f"<li>{link}{sub}</li>")
        cls = " class='readme-list'" if root else ""
        return f"<ul{cls}>" + "".join(items) + "</ul>" if items else ""

    body = render(tree, True) if tree else "<p>No READMEs found.</p>"
    return "<h1>Project READMEs</h1>" + body


def view_gateway_cookbook(*, recipe: str | None = None) -> str:
    """Display recipe files under ``recipes`` with optional file preview."""
    base_dir = Path(gw.resource("recipes"))

    if recipe:
        safe = _sanitize_relpath(recipe)
        if not safe:
            return "<b>Invalid recipe path.</b>"
        file_path = base_dir / safe
        if file_path.is_dir():
            recipe = None
        elif file_path.suffix != ".gwr" or not file_path.is_file():
            return "<b>Recipe not found.</b>"
        if recipe:
            content = file_path.read_text(encoding="utf-8")
            title = html.escape(file_path.name)
            body = html.escape(content)
            return f"<h1>{title}</h1><pre><code class='gwr'>{body}</code></pre>"

    tree: dict = {}

    def insert(node: dict, parts: tuple[str, ...]):
        head, *tail = parts
        if tail:
            node = node.setdefault(head, {})
            insert(node, tuple(tail))
        else:
            node.setdefault("_files", []).append("/".join(parts))

    for path in sorted(base_dir.rglob("*.gwr")):
        rel = path.relative_to(base_dir)
        parts = rel.parts
        if any(_is_hidden_or_private(p) for p in parts):
            continue
        insert(tree, parts)

    def render(node: dict, root: bool = False) -> str:
        items = []
        for name in sorted(k for k in node.keys() if k != "_files"):
            sub = render(node[name], False)
            items.append(f"<li>{html.escape(name)}{sub}</li>")
        for rel_path in node.get("_files", []):
            href = gw.web.app.build_url("web", "site", "gateway-cookbook", recipe=rel_path)
            label = html.escape(Path(rel_path).stem.replace("_", " ").title())
            items.append(f"<li><a href='{href}'>{label}</a></li>")
        cls = " class='cookbook-list'" if root else ""
        return f"<ul{cls}>" + "".join(items) + "</ul>" if items else ""

    body = render(tree, True) if tree else "<p>No recipes found.</p>"
    return "<h1>Gateway Cookbook</h1>" + body


def view_pending_todos():
    """Render an HTML table of TODOs grouped by project."""
    import ast
    import inspect
    import os
    from pathlib import Path

    def _extract_todos(source: str):
        todos = []
        lines = source.splitlines()
        current = []
        for line in lines:
            stripped = line.strip()
            if "# TODO" in stripped:
                if current:
                    todos.append("\n".join(current))
                current = [stripped]
            elif current and (stripped.startswith("#") or not stripped):
                current.append(stripped)
            elif current:
                todos.append("\n".join(current))
                current = []
        if current:
            todos.append("\n".join(current))
        return todos

    todos: dict[str, list[tuple[str, str]]] = {}
    extract = _extract_todos
    base = Path("projects")
    for path in base.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        dotted = path.relative_to(base).with_suffix("").as_posix().replace("/", ".")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        try:
            tree = ast.parse("".join(lines))
        except Exception:
            continue
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            start = node.lineno - 1
            end = node.end_lineno or start
            prepend = []
            i = start - 1
            while i >= 0 and not lines[i].strip():
                i -= 1
            while i >= 0 and lines[i].strip().startswith("#"):
                prepend.insert(0, lines[i])
                i -= 1
            block = "".join(prepend + lines[start:end])
            for todo in extract(block) or []:
                t = todo.strip()
                if not t.startswith("# TODO"):
                    continue
                todos.setdefault(dotted, []).append((node.name, t))

    if not todos:
        return "<h1>No TODOs found.</h1>"

    html_parts = ["<h1>Pending TODOs</h1>"]
    for proj in sorted(todos):
        html_parts.append(f"<h2>{html.escape(proj)}</h2>")
        html_parts.append(
            "<table class='todo-table'><tr><th>Function</th><th>TODO</th><th></th></tr>"
        )
        for func, todo in todos[proj]:
            link = gw.web.app.build_url("web", "site", "help", topic=f"{proj}/{func}")
            fb_url = gw.web.app.build_url(
                "feedback",
                topic=f"TODO request for {proj}.{func}",
                message=f"Please add a TODO for {proj}.{func}"
            )
            html_parts.append(
                f"<tr><td><a href='{link}'>{html.escape(func)}</a></td>"
                f"<td><pre>{html.escape(todo)}</pre></td>"
                f"<td><a class='btn-small' href='{fb_url}'>Request TODO</a></td></tr>"
            )
        html_parts.append("</table>")
    return "".join(html_parts)


def build_help_db(*, update: bool = False):
    """Compatibility wrapper for :func:`gw.help_db.build`."""
    gw.warning(
        "web.site.build_help_db is deprecated; use help-db.build instead"
    )
    return gw.help_db.build(update=update)


