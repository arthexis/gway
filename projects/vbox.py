# projects/vbox.py

import os
import time
import shutil
import secrets
import hashlib
import threading
from datetime import datetime
from bottle import request, HTTPResponse
from gway import gw


"""
This virtual box (vbox) system allows users with admin access to upload and download 
files to/from a secure folder in the remote server. 

In CLI/Recipes you may use:
> [gway] web app setup --project vbox --home upload

To deploy it and sey the home to [BASE_URL]/vbox/upload.
"""

_open_boxes = {}  # vbid -> expire_timestamp
_gc_lock = threading.Lock()
_gc_thread_on = False

VBOX_PATH = "work", "vbox"


def purge(*, all=False):
    """Manually purge expired vbox entries and remove their folders.

    Args:
        all (bool): If True, delete all folders, even non-empty ones and those not in _open_boxes.
    """
    base_dir = gw.resource(*VBOX_PATH)
    with _gc_lock:
        now = time.time()
        expired = [bid for bid, exp in _open_boxes.items() if exp < now]
        known_prefixes = set()

        # Clean up known/active expired boxes
        for bid in expired:
            del _open_boxes[bid]
            try:
                short, _ = bid.split(".", 1)
                known_prefixes.add(short)
                folder = os.path.join(base_dir, short)
                if os.path.isdir(folder) and (all or not os.listdir(folder)):
                    shutil.rmtree(folder)
            except Exception as e:
                gw.error(f"[PURGE] Error cleaning known box {bid}: {e}")

        # Clean up orphan folders
        for name in os.listdir(base_dir):
            if name in known_prefixes:
                continue
            path = os.path.join(base_dir, name)
            if not os.path.isdir(path):
                continue
            if all:
                try:
                    shutil.rmtree(path)
                except Exception as e:
                    gw.error(f"[PURGE] Error removing orphan box {name}: {e}")
            else:
                try:
                    if not os.listdir(path):
                        shutil.rmtree(path)
                except Exception as e:
                    gw.error(f"[PURGE] Error removing orphan empty box {name}: {e}")


def periodic_purge(*, seconds=120):
    """Background thread to periodically purge expired upload boxes."""
    while True:
        purge()
        time.sleep(seconds)


def render_box_error(title: str, message: str, *, back_link: bool = True, target: str="upload") -> str:
    """Helper for error display with optional link back to upload main page."""
    html = f"<h1>{title}</h1><p>{message}</p>"
    if back_link:
        url = gw.web.app.build_url(target)
        html += f'<p class="error"><a href="{url}?">Back to {target} page</a></p>'
    return html


def render_upload_view(*, vbid: str = None, timeout: int = 60, files: int = 4, email: str = None, **kwargs):
    """
    GET: Display upload interface or create a new upload box.
    POST: Handle uploaded files to a specific vbid.
    """
    global _gc_thread_on
    if not _gc_thread_on:
        threading.Thread(target=periodic_purge, daemon=True).start()
        _gc_thread_on = True

    admin_email = os.environ.get("ADMIN_EMAIL")
    gw.info(f"[VBOX] Entry: vbid={vbid!r}, timeout={timeout}, files={files}, email={email!r}, method={request.method}")

    # Handle file upload (POST) with a vbid (the classic file upload case)
    if request.method == 'POST' and vbid:
        gw.info(f"[VBOX] POST file upload for vbid={vbid}")
        with _gc_lock:
            expire = _open_boxes.get(vbid)
            if not expire or expire < time.time():
                gw.warning(f"[VBOX] vbox expired for vbid={vbid}")
                return render_box_error("Upload Box Expired", "Please regenerate a new vbid.")

        try:
            short, _ = vbid.split(".", 1)
        except ValueError:
            gw.error(f"[VBOX] Invalid vbid format: {vbid}")
            return render_box_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

        upload_dir = gw.resource(*VBOX_PATH, short)
        os.makedirs(upload_dir, exist_ok=True)

        uploaded_files = request.files.getlist("file")
        results = []
        for f in uploaded_files:
            save_path = os.path.join(upload_dir, f.filename)
            try:
                f.save(save_path)
                results.append(f"Uploaded {f.filename}")
                gw.info(f"[VBOX] Uploaded {f.filename} to {short}")
            except Exception as e:
                results.append(f"Error uploading {f.filename}: {e}")
                gw.error(f"[VBOX] Issue uploading {f.filename} to {short}")
                gw.exception(e)

        download_short_url = gw.web.app.build_url("download", vbid=short)
        download_long_url = gw.web.app.build_url("download", vbid=vbid)
        gw.info(f"[VBOX] Returning upload result UI for vbid={vbid}")
        return (
            "<pre>" + "\n".join(results) + "</pre>" +
            f"<p><a href='?vbid={vbid}'>UPLOAD MORE files to this box</a></p>" +
            f"<p><a href='{download_short_url}'>Go to PUBLIC READ-ONLY download page for this box</a></p>" +
            f"<p><a href='{download_long_url}'>Go to HIDDEN WRITE download page for this box</a></p>"
        )

    # If no vbid: always create/check the vbox and show the email form
    if not vbid:
        gw.info(f"[VBOX] No vbid present, always creating/checking box.")
        remote_addr = request.remote_addr or ''
        user_agent = request.headers.get('User-Agent') or ''
        identity = remote_addr + user_agent
        hash_digest = hashlib.sha256(identity.encode()).hexdigest()
        short = hash_digest[:12]
        full_id = f"{short}.{hash_digest[:40]}"

        with _gc_lock:
            now = time.time()
            expires = _open_boxes.get(full_id)
            if not expires or expires < now:
                _open_boxes[full_id] = now + timeout * 60
                os.makedirs(gw.resource(*VBOX_PATH, short), exist_ok=True)
                url = gw.build_url("upload", vbid=full_id)
                message = f"[UPLOAD] Upload box created (expires in {timeout} min): {url}"
                print(("-" * 70) + '\n' + message + '\n' + ("-" * 70))
                gw.warning(message)
                gw.info(f"[VBOX] Created new box: {full_id}")
            else:
                url = gw.build_url("upload", vbid=full_id)
                gw.info(f"[VBOX] Existing box reused: {full_id}")

        # --- Email notification if email is present (from POST or GET) ---
        # Accept both POST form value and GET param for email
        submitted_email = None
        if request.method == "POST":
            submitted_email = request.forms.get("email", "").strip()
            gw.info(f"[VBOX] POST email form: submitted_email={submitted_email!r}")
        elif request.method == "GET":
            submitted_email = email or ""
            gw.info(f"[VBOX] GET param email: submitted_email={submitted_email!r}")

        admin_notif = ""
        sent_copy_msg = "<p>A copy of the access URL was sent to the admin.</p>"
        if submitted_email:
            if admin_email and submitted_email.lower() == admin_email.strip().lower():
                subject = "[VBOX] Upload Box Link"
                body = (
                    f"A new upload box was created.\n\n"
                    f"Access URL: {url}\n\n"
                    f"This box will expire in {timeout} minutes."
                )
                try:
                    gw.mail.send(subject, body=body, to=admin_email)
                    gw.info(f"[VBOX] Sent upload URL email to admin.")
                except Exception as e:
                    gw.error(f"[VBOX] Error sending VBOX notification email: {e}")
                admin_notif = sent_copy_msg
            else:
                admin_notif = sent_copy_msg
                gw.info(f"[VBOX] Pretend email sent: {submitted_email!r} != {admin_email!r}")

        # Show the ready box UI + the optional email form
        email_form_html = (
            "<form method='POST'>"
            "<input type='email' name='email' required placeholder='Your email address'>"
            "<button type='submit'>Request Link</button>"
            "</form>"
        )
        form_message = (
            "<p>If you are a site member, you may request a URL to be sent to your email by entering it here.</p>"
        )

        return (
            "<h1>Upload Box Ready</h1>"
            "<p>We've prepared an upload box for you. Check the console for the access URL.</p>"
            "<p>To use it, go to <code>?vbid=…</code> and upload your files there.</p>"
            f"{admin_notif}"
            f"{form_message if not submitted_email else ''}{email_form_html if not submitted_email else ''}"
        )

    # Validate and show upload UI for an existing vbid
    gw.info(f"[VBOX] Render upload UI for vbid={vbid!r}")
    with _gc_lock:
        expire = _open_boxes.get(vbid)
        if not expire or expire < time.time():
            gw.warning(f"[VBOX] vbox expired for vbid={vbid}")
            return render_box_error("Upload Box Expired or Not Found", "Please regenerate a new vbid.")

    try:
        short, _ = vbid.split(".", 1)
    except ValueError:
        gw.error(f"[VBOX] Invalid vbid format: {vbid}")
        return render_box_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

    # Generate N file input fields
    file_inputs = "\n".join(
        f'<input type="file" name="file">' for _ in range(max(1, files))
    )

    download_url = gw.build_url("download", vbid=vbid)
    gw.info(f"[VBOX] Displaying upload form for {short}")

    return f"<h1>Upload to Box: {short}</h1>" + f"""
        <form method="POST" enctype="multipart/form-data">
            {file_inputs}
            <br><p><button type="submit">Upload</button><p/>
        </form>
        <p>Files will be stored in <code>work/{VBOX_PATH}/{short}/</code></p>
        <p><a href="{download_url}">Go to download page for this box</a></p>
    """


# TODO: Create a new function "open_remote" which allows us to create a vbox
#       on a remote system. It takes a param with the server url and optional alt path
#       This programatically accesses /<path>/upload to trigger the generation and
#       provides an email to the endpoint. Then search the given email with gw.mail.search 
#       to retrieve the secret URL and store it using gw.cdv.store to save it to a CDV file at
#       gw.resource(*VBOX_PATH, 'remotes.cdv') using the b64 of the server_url as the key
#       and storing the vbox=vbid in the cdv. The function should check in this file to see if
#       we already have a vbox set with that remote. 

def open_remote(server_url: str='[SERVER_URL]', *, path:str='vbox', email:str='[ADMIN_EMAIL]'):
    pass


def stream_file_response(path: str, filename: str) -> HTTPResponse:
    """Return a proper file download response that bypasses HTML templating."""
    headers = {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename="{filename}"',
    }
    with open(path, 'rb') as f:
        body = f.read()
    return HTTPResponse(body=body, status=200, headers=headers)


def render_download_view(*hashes: tuple[str], vbid: str = None, **kwargs):
    """
    GET: Show list of files in the box (with hash), allow selection/download.
    If a single hash is provided, return that file. Multiple hashes are not supported yet.

    - Allows access via full vbid (short.long) or short-only (just the folder name).
    - If full vbid is used, shows link to upload more files.
    """
    gw.warning(f"Download view: {hashes=} {vbid=} {kwargs=}")
    if not vbid:
        return render_box_error("Missing vbid", "You must provide a vbid in the query string.")

    # Accept full or short vbid
    if "." in vbid:
        short, _ = vbid.split(".", 1)
    else:
        short = vbid  # Accept short-only vbid for downloads

    folder = gw.resource(*VBOX_PATH, short)
    if not os.path.isdir(folder):
        return render_box_error("Box not found", "The folder associated with this vbid does not exist.")

    file_map = {}  # hash -> full_path
    file_info = []  # tuples for UI: (hash, name, size, mtime)

    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
                md5 = hashlib.md5(data).hexdigest()
                file_map[md5] = path
                size = len(data)
                mtime = os.path.getmtime(path)
                file_info.append((md5, name, size, mtime))
        except Exception as e:
            gw.error(f"Error reading file {name} in box {vbid}: {e}")
            continue

    # If a specific file is requested by hash
    if hashes:
        if len(hashes) > 1:
            raise NotImplementedError("Multi-hash downloads are not supported (yet).")
        h = hashes[0]
        if h not in file_map:
            return f"<h1>No matching file</h1><p>Hash {h} not found in this box.</p>"

        path = file_map[h]
        name = os.path.basename(path)
        return stream_file_response(path, name)

    # Render file listing
    html = "<h1>Download Files</h1><ul>"
    for h, name, size, mtime in file_info:
        time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        link = gw.build_url("download", h, vbid=vbid)
        html += f'<li><a href="{link}">{name}</a> ({size} bytes, modified {time_str}, MD5: {h})</li>'
    html += "</ul>"

    # Only include upload link if full vbid was used
    if "." in vbid:
        upload_url = gw.build_url("upload", vbid=vbid)
        html += f"<p><a href='{upload_url}'>Add more files to this box</a></p>"

    return html
