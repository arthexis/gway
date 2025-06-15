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


# This code used to be part of the sample web/site.py views but was extended 
# into its own project. The goal is to have a small and secure, self-contained
# virtual box system that can allow human users, as well as automated
# nodes, to exchange digital files if they know a mutual secret.

# It can be deployed in CLI/recipes as:
# > [gway] web app setup --project vbox --home upload
# To deploy it into [BASE_URL]/vbox/[upload/download].


_open_boxes = {}  # vbid -> expire_timestamp
_gc_lock = threading.Lock()
_gc_thread_on = False


def purge(*, all=False):
    """Manually purge expired vbox entries and remove their folders.

    Args:
        all (bool): If True, delete all folders, even non-empty ones and those not in _open_boxes.
    """
    base_dir = gw.resource("work", "uploads")
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


# TODO: Add a function "init_local" that creates a vbox without requiring the web UI
3 # and returns a dict with the vbox (vbid) and vbox_url (the full url)



def render_upload_view(*, vbid: str = None, timeout: int = 60, files: int = 4, email: str=None, **kwargs):
    """
    GET: Display upload interface or create a new upload box.
    POST: Handle uploaded files to a specific vbid.
    """
    global _gc_thread_on
    if not _gc_thread_on:
        threading.Thread(target=periodic_purge, daemon=True).start()
        _gc_thread_on = True

    # TODO: When email is provided and it matches os.environ('ADMIN_EMAIL') use gw.mail.send
    #       to send the URL via email to that address in a format that can be read back. 
    #       Response should show that a copy of the URL was sent to the admin without showing the email.

    # Handle file upload (POST)
    if request.method == 'POST':
        if not vbid:
            return render_box_error("Missing vbid", "You must provide a vbid in the query string.")

        with _gc_lock:
            expire = _open_boxes.get(vbid)
            if not expire or expire < time.time():
                return render_box_error("Upload Box Expired", "Please regenerate a new vbid.")

        try:
            short, _ = vbid.split(".", 1)
        except ValueError:
            return render_box_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

        upload_dir = gw.resource("work", "uploads", short)
        os.makedirs(upload_dir, exist_ok=True)

        uploaded_files = request.files.getlist("file")
        results = []
        for f in uploaded_files:
            save_path = os.path.join(upload_dir, f.filename)
            try:
                f.save(save_path)
                results.append(f"Uploaded {f.filename}")
                gw.info(f"Uploaded {f.filename} to {short}")
            except Exception as e:
                results.append(f"Error uploading {f.filename}: {e}")
                gw.error(f"Issue uploading {f.filename} to {short}")
                gw.exception(e)

        download_short_url = gw.web.app.build_url("download", vbid=short)
        download_long_url = gw.web.app.build_url("download", vbid=vbid)
        return (
            "<pre>" + "\n".join(results) + "</pre>" +
            f"<p><a href='?vbid={vbid}'>Upload more files to this box</a></p>" +
            f"<p><a href='{download_short_url}'>Go to PUBLIC READ-ONLY download page for this box</a></p>" +
            f"<p><a href='{download_long_url}'>Go to HIDDEN WRITE-ENABLED download page for this box</a></p>"
        )

    # Handle UI display (GET)
    if not vbid:

        # TODO: Tests indicate visiting the page multiple times in a rows generate multiple
        # vboxes, so our deterministic process may not be working as intended. 
        # We should also add a test to make sure it really is deterministic.

        # Deterministic vbid generation based on user info
        short = secrets.token_urlsafe(8)
        identity = (request.remote_addr or '') + (request.headers.get('User-Agent') or '') + short
        hash_digest = hashlib.sha256(identity.encode()).hexdigest()
        full_id = f"{short}.{hash_digest[:40]}"

        with _gc_lock:
            now = time.time()
            expires = _open_boxes.get(full_id)
            if not expires or expires < now:
                _open_boxes[full_id] = now + timeout * 60
                os.makedirs(gw.resource("work", "uploads", short), exist_ok=True)
                url = gw.build_url("upload", vbid=full_id)
                message = f"[UPLOAD] Upload box created (expires in {timeout} min): {url}"
                print(("-" * 70) + '\n' + message + '\n' + ("-" * 70))
                gw.warning(message)

        return """
            <h1>Upload Box Ready</h1>
            <p>We've prepared an upload box for you. Check the console for the access URL.</p>
            <p>To use it, go to <code>?vbid=…</code> and upload your files there.</p>
        """

    # Validate and show upload UI
    with _gc_lock:
        expire = _open_boxes.get(vbid)
        if not expire or expire < time.time():
            return render_box_error("Upload Box Expired or Not Found", "Please regenerate a new vbid.")

    try:
        short, _ = vbid.split(".", 1)
    except ValueError:
        return render_box_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

    # Generate N file input fields
    file_inputs = "\n".join(
        f'<input type="file" name="file">' for _ in range(max(1, files))
    )

    download_url = gw.build_url("download", vbid=vbid)

    return f"<h1>Upload to Box: {short}</h1>" + f"""
        <form method="POST" enctype="multipart/form-data">
            {file_inputs}
            <br><p><button type="submit">Upload</button><p/>
        </form>
        <p>Files will be stored in <code>work/uploads/{short}/</code></p>
        <p><a href="{download_url}">Go to download page for this box</a></p>
    """


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

    folder = gw.resource("work", "uploads", short)
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
