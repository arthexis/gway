import os
import time
import shutil
import secrets
import hashlib
import threading
from datetime import datetime
from bottle import request  # Default gway web apps use bottle
from gway import gw


# This code used to be part of the sample web/site.py views but was extended 
# into its own project. The goal is to have a small and secure, self-contained
# electronic file box system that can allow human users, as well as automated
# nodes, to exchange digital files if they know a mutual secret.

# It can be deployed in CLI/recipes as:
# > [gway] web app setup --project box 
# To deploy it into [BASE_URL]/box/[upload/download].


_open_boxes = {}  # box_id -> expire_timestamp
_gc_lock = threading.Lock()
_gc_thread_on = False


def _cleanup_boxes():
    """Background cleanup of expired box_ids and their empty folders."""
    while True:
        with _gc_lock:
            now = time.time()
            expired = [bid for bid, exp in _open_boxes.items() if exp < now]
            for bid in expired:
                del _open_boxes[bid]
                try:
                    short, _ = bid.split(".", 1)
                    folder = gw.resource("work", "uploads", short)
                    if os.path.isdir(folder) and not os.listdir(folder):
                        shutil.rmtree(folder)
                except Exception as e:
                    print(f"[UPLOAD] Cleanup error for box {bid}: {e}")
        time.sleep(60)


def render_upload_view(*, box_id: str = None, timeout: int = 60, files: int = 4, app=None, **kwargs):
    """
    GET: Display upload interface or create a new upload box.
    POST: Handle uploaded files to a specific box_id.
    """
    global _gc_thread_on
    if not _gc_thread_on:
        threading.Thread(target=_cleanup_boxes, daemon=True).start()
        _gc_thread_on = True

    # Handle file upload (POST)
    if request.method == 'POST':
        if not box_id:
            return "<h1>Missing box_id</h1><p>You must provide a box_id in the query string.</p>"

        with _gc_lock:
            expire = _open_boxes.get(box_id)
            if not expire or expire < time.time():
                return "<h1>Upload Box Expired or Not Found</h1><p>Please regenerate a new box_id.</p>"

        try:
            short, _ = box_id.split(".", 1)
        except ValueError:
            return "<h1>Invalid box_id format</h1><p>Expected form: <code>short.long</code>.</p>"

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

        download_url = gw.web.app.build_url("download", box_id=box_id)
        return (
            "<pre>" + "\n".join(results) + "</pre>" +
            f"<p><a href='?box_id={box_id}'>Upload more files to this box</a></p>" +
            f"<p><a href='{download_url}'>Go to download page for this box</a></p>"
        )

    # Handle UI display (GET)
    if not box_id:
        # Deterministic box_id generation based on user info
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
                url = gw.build_url("upload", box_id=full_id)
                message = f"[UPLOAD] Upload box created (expires in {timeout} min): {url}"
                print(("-" * 70) + '\n' + message + '\n' + ("-" * 70))
                gw.warning(message)

        return """
            <h1>Upload Box Ready</h1>
            <p>We've prepared an upload box for you. Check the console for the access URL.</p>
            <p>To use it, go to <code>?box_id=…</code> and upload your files there.</p>
        """

    # Validate and show upload UI
    with _gc_lock:
        expire = _open_boxes.get(box_id)
        if not expire or expire < time.time():
            return "<h1>Upload Box Expired or Not Found</h1><p>Please regenerate a new box_id.</p>"

    try:
        short, _ = box_id.split(".", 1)
    except ValueError:
        return "<h1>Invalid box_id format</h1><p>Expected form: <code>short.long</code>.</p>"

    # Generate N file input fields
    file_inputs = "\n".join(
        f'<input type="file" name="file">' for _ in range(max(1, files))
    )
    download_url = gw.build_url("download", box_id=box_id)

    return f"<h1>Upload to Box: {short}</h1>" + f"""
        <form method="POST" enctype="multipart/form-data">
            {file_inputs}
            <br><p><button type="submit">Upload</button><p/>
        </form>
        <p>Files will be stored in <code>work/uploads/{short}/</code></p>
        <p><a href="{download_url}">Go to download page for this box</a></p>
    """


def render_download_view(*hashes: tuple[str], box_id: str = None, **kwargs):
    """
    GET: Show list of files in the box (with hash), allow selection/download.
    If a single hash is provided, return that file. Multiple hashes are not supported yet.
    """
    gw.warning(f"Download view: {hashes=} {box_id=} {kwargs=}")
    if not box_id:
        return "<h1>Missing box_id</h1><p>You must provide a box_id in the query string.</p>"

    try:
        short, _ = box_id.split(".", 1)
    except ValueError:
        return "<h1>Invalid box_id format</h1><p>Expected form: <code>short.long</code>.</p>"

    folder = gw.resource("work", "uploads", short)
    if not os.path.isdir(folder):
        return "<h1>Box not found</h1><p>The folder associated with this box_id does not exist.</p>"

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
            gw.error(f"Error reading file {name} in box {box_id}: {e}")
            continue

    if hashes:
        if len(hashes) > 1:
            raise NotImplementedError("Multi-hash downloads are not supported yet.")
        h = hashes[0]
        if h not in file_map:
            return f"<h1>No matching file</h1><p>Hash {h} not found in this box.</p>"

        path = file_map[h]
        name = os.path.basename(path)

        def _stream():
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk

        from bottle import response
        response.content_type = 'application/octet-stream'
        response.headers['Content-Disposition'] = f'attachment; filename="{name}"'
        return _stream()

    html = "<h1>Download Files</h1><ul>"
    for h, name, size, mtime in file_info:
        time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        link = gw.build_url("download", h, box_id=box_id)
        html += f'<li><a href="{link}">{name}</a> ({size} bytes, modified {time_str}, MD5: {h})</li>'
    html += "</ul>"
    return html
