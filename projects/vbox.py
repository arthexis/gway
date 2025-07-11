# projects/vbox.py

import os
import re
import shutil
import hashlib
import base64
import time 
import threading
import requests
from datetime import datetime
from bottle import request, HTTPResponse
from gway import gw


"""
This virtual box (vbox) system allows users with admin access to upload and download 
files to/from a secure folder in the remote server. 

In CLI/Recipes you may use:
> [gway] web app setup-app vbox --home upload

To deploy it and sey the home to [BASE_URL]/vbox/upload.
"""

_open_boxes = {}  # vbid -> expire_timestamp
_gc_lock = threading.Lock()
_gc_thread_on = False

VBOX_PATH = "work", "vbox"


def _sanitize_filename(name: str) -> str:
    """Return a safe filename by stripping path separators and unsafe chars."""
    name = str(name)
    name = name.replace("/", "").replace("\\", "").replace("..", "")
    return "".join(c for c in name if c.isalnum() or c in "._-")


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


def render_error(title: str, message: str, *, back_link: bool = True, target: str="uploads") -> str:
    """Helper for error display with optional link back to upload main page."""
    html = f"<h1>{title}</h1><p>{message}</p>"
    if back_link:
        url = gw.web.app.build_url(target)
        html += f'<p class="error"><a href="{url}?">Back to {target} page</a></p>'
    return html


def view_uploads(*, vbid: str = None, timeout: int = 60, files: int = 4, email: str = None, **kwargs):
    """
    GET: Display upload interface or create a new upload box.
    POST: Handle uploaded files to a specific vbid.
    """
    global _gc_thread_on
    if not _gc_thread_on:
        threading.Thread(target=periodic_purge, daemon=True).start()
        _gc_thread_on = True

    admin_email = os.environ.get("ADMIN_EMAIL")
    gw.info(f"Entry: vbid={vbid!r}, timeout={timeout}, files={files}, email={email!r}, method={request.method}")

    # Handle file upload (POST) with a vbid (the classic file upload case)
    if request.method == 'POST' and vbid:
        gw.info(f"POST file upload for vbid={vbid}")
        with _gc_lock:
            expire = _open_boxes.get(vbid)
            if not expire or expire < time.time():
                gw.warning(f"vbox expired for vbid={vbid}")
                return render_error("Upload Box Expired", "Please regenerate a new vbid.")

        try:
            short, _ = vbid.split(".", 1)
        except ValueError:
            gw.error(f"Invalid vbid format: {vbid}")
            return render_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

        upload_dir = gw.resource(*VBOX_PATH, short)
        os.makedirs(upload_dir, exist_ok=True)

        uploaded_files = request.files.getlist("file")
        results = []
        for f in uploaded_files:
            safe_name = _sanitize_filename(f.filename)
            save_path = os.path.join(upload_dir, safe_name)
            try:
                f.save(save_path)
                results.append(f"Uploaded {safe_name}")
                gw.info(f"Uploaded {safe_name} to {short}")
            except Exception as e:
                results.append(f"Error uploading {safe_name}: {e}")
                gw.error(f"Issue uploading {safe_name} to {short}")
                gw.exception(e)

        download_short_url = gw.web.app.build_url("download", vbid=short)
        download_long_url = gw.web.app.build_url("download", vbid=vbid)
        gw.info(f"Returning upload result UI for vbid={vbid}")
        return (
            "<pre>" + "\n".join(results) + "</pre>" +
            f"<p><a href='?vbid={vbid}'>UPLOAD MORE files to this box</a></p>" +
            f"<p><a href='{download_short_url}'>Go to PUBLIC READ-ONLY download page for this box</a></p>" +
            f"<p><a href='{download_long_url}'>Go to HIDDEN WRITE download page for this box</a></p>"
        )

    if not vbid:
        gw.info(f"No vbid present, always creating/checking box.")
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
                url = gw.web.build_url("uploads", vbid=full_id)
                message = f"[UPLOAD] Upload box created (expires in {timeout} min): {url}"
                print(("-" * 70) + '\n' + message + '\n' + ("-" * 70))
                gw.warning(message)
                gw.info(f"Created new box: {full_id}")
            else:
                url = gw.web.build_url("upload", vbid=full_id)
                gw.info(f"Existing box reused: {full_id}")

        admin_notif = ""
        sent_copy_msg = "<p>A copy of the access URL was sent to the admin.</p>"
        if email:
            if admin_email and email.lower() == admin_email.strip().lower():
                subject = "Upload Box Link"
                body = (
                    f"A new upload box was created.\n\n"
                    f"Access URL: {url}\n\n"
                    f"This box will expire in {timeout} minutes."
                )
                try:
                    gw.mail.send(subject, body=body, to=admin_email)
                    gw.info(f"Sent upload URL email to admin.")
                except Exception as e:
                    gw.error(f"Error sending VBOX notification email: {e}")
                admin_notif = sent_copy_msg
            else:
                admin_notif = sent_copy_msg
                gw.info(f"Pretend email sent: {email!r} != {admin_email!r}")

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

        local_console_info = ""
        if gw.web.server.is_local():
            local_console_info = (
                "<p>We've prepared an upload box for you. Check the console for the access URL.</p>"
                "<p>To use it, go to <code>?vbid=…</code> and upload your files there.</p>"
            )

        return (
            "<h1>Upload to Virtual Box</h1>"
            f"{local_console_info}"
            f"{admin_notif}"
            f"{form_message if not email else ''}{email_form_html if not email else ''}"
        )

    # Validate and show upload UI for an existing vbid
    gw.info(f"Render upload UI for vbid={vbid!r}")
    with _gc_lock:
        expire = _open_boxes.get(vbid)
        if not expire or expire < time.time():
            gw.warning(f"vbox expired for vbid={vbid}")
            return render_error("Upload Box Expired or Not Found", "Please regenerate a new vbid.")

    try:
        short, _ = vbid.split(".", 1)
    except ValueError:
        gw.error(f"Invalid vbid format: {vbid}")
        return render_error("Invalid vbid format", "Expected form: <code>short.long</code>.")

    # Generate N file input fields
    file_inputs = "\n".join(
        f'<input type="file" name="file">' for _ in range(max(1, files))
    )

    download_url = gw.web.build_url("download", vbid=vbid)
    gw.info(f"Displaying upload form for {short}")

    return f"<h1>Upload to Box: {short}</h1>" + f"""
        <form method="POST" enctype="multipart/form-data">
            {file_inputs}
            <br><p><button type="submit">Upload</button><p/>
        </form>
        <p>Files will be stored in <code>{'/'.join(VBOX_PATH)}/{short}/</code></p>
        <p><a href="{download_url}">Go to download page for this box</a></p>
    """


def open_remote(server_url: str = '[SERVER_URL]', *, path: str = 'vbox', email: str = '[ADMIN_EMAIL]'):
    """
    Create a vbox on a remote system, retrieve the upload link from email, and store it locally.
    - server_url: Base URL of the remote server (e.g., 'https://example.com')
    - path:       Path on remote server where vbox upload is handled (default 'vbox')
    - email:      Email address to receive the upload link (should be accessible by local mail.read)
    
    Returns: dict of stored record fields, or None if unsuccessful.
    """
    from gway import gw

    # Step 1: Compose the remote CDV record key (base64 of server_url)
    b64key = base64.urlsafe_b64encode(server_url.encode()).decode().rstrip("=")
    cdv_path = gw.resource(*VBOX_PATH, 'remotes.cdv')

    # Step 2: Check if already present in CDV
    records = gw.cdv.load_all(cdv_path)
    if b64key in records and records[b64key].get("vbox"):
        gw.info(f"[open_remote] Found existing vbox for {server_url}: {records[b64key]}")
        return records[b64key]

    # Step 3: Trigger remote vbox creation (POST to /<path>/upload)
    remote_upload_url = server_url.rstrip("/") + f"/{path}/upload"
    gw.info(f"[open_remote] Posting to remote: {remote_upload_url} with email={email!r}")

    try:
        resp = requests.post(remote_upload_url, data={"email": email}, timeout=10)
        gw.info(f"[open_remote] Remote POST status: {resp.status_code}")
    except Exception as e:
        gw.error(f"[open_remote] Remote request failed: {e}")
        return None

    # Step 4: Wait for email and search for the upload link
    subject_fragment = "Upload Box Link"
    access_url_pattern = r"Access URL: (https?://\S+)"
    found_url = None
    found_vbid = None
    max_wait = 20
    poll_interval = 2

    for attempt in range(max_wait // poll_interval):
        try:
            result = gw.mail.read(subject_fragment)
            if result:
                body, _ = result
                match = re.search(access_url_pattern, body)
                if match:
                    found_url = match.group(1)
                    gw.info(f"[open_remote] Found access URL in email: {found_url}")
                    # Extract vbid parameter from URL
                    vbid_match = re.search(r"vbid=([a-zA-Z0-9._-]+)", found_url)
                    if vbid_match:
                        found_vbid = vbid_match.group(1)
                        gw.info(f"[open_remote] Parsed vbid: {found_vbid}")
                        break
        except Exception as e:
            gw.error(f"[open_remote] Error during mail.read: {e}")
        time.sleep(poll_interval)

    if not (found_url and found_vbid):
        gw.error(f"[open_remote] Could not retrieve upload link from email for {server_url}")
        return None

    # Step 5: Store in CDV for future reference
    gw.cdv.update(
        cdv_path,
        b64key,
        vbox=found_vbid,
        url=found_url,
        server=server_url,
        email=email,
        last_updated=str(int(time.time()))
    )
    gw.info(f"[open_remote] Stored remote vbox: server={server_url} vbid={found_vbid}")

    # Step 6: Return stored record (for chaining)
    return gw.cdv.load_all(cdv_path).get(b64key)


def poll_remote(server_url: str = '[SERVER_URL]', *, target='work/vbox/remote', interval=3600):
    """
    Poll the remote vbox for files and download new/updated ones to the local target directory.
    - server_url: Remote GWAY instance base URL
    - target: Local directory to save downloaded files
    - interval: Seconds between polls (runs forever unless interval=None)
    
    Skips files already downloaded by using the modified_since parameter.
    """
    import time
    from urllib.parse import urlparse, parse_qs
    from datetime import datetime
    from gway import gw

    # Step 1: Get the remote vbox info from CDV
    b64key = base64.urlsafe_b64encode(server_url.encode()).decode().rstrip("=")
    cdv_path = gw.resource(*VBOX_PATH, 'remotes.cdv')
    records = gw.cdv.load_all(cdv_path)
    remote = records.get(b64key)
    if not (remote and remote.get("vbox")):
        gw.error(f"[poll_remote] No vbox registered for {server_url}")
        return

    vbid = remote["vbox"]
    vbox_url = remote.get("url")
    # Extract vbid if not present
    if not vbox_url:
        vbox_url = server_url.rstrip("/") + "/vbox/downloads"
    if not vbid:
        # Try to extract vbid from url param
        parts = urlparse(vbox_url)
        qs = parse_qs(parts.query)
        vbid = qs.get("vbid", [None])[0]
        if not vbid:
            gw.error("[poll_remote] Unable to determine vbid for remote poll")
            return

    os.makedirs(target, exist_ok=True)
    # Track modification times of downloaded files: name → mtime (as float)
    local_mtimes = {}

    def download_listing():
        # Get file listing from remote (no hashes, just HTML, parse with regex)
        listing_url = f"{server_url.rstrip('/')}/vbox/downloads?vbid={vbid}"
        try:
            resp = requests.get(listing_url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            gw.error(f"[poll_remote] Error fetching remote listing: {e}")
            return []
        # Parse <li><a href=...>name</a> (..., modified <time>, ...)
        file_entries = []
        for m in re.finditer(
            r'<li><a href="[^"]+">([^<]+)</a> \((\d+) bytes, modified ([^,]+), MD5: ([a-fA-F0-9]+)\)',
            resp.text
        ):
            name, size, time_str, md5 = m.groups()
            try:
                mtime = datetime.strptime(time_str.strip(), '%Y-%m-%d %H:%M:%S').timestamp()
            except Exception:
                mtime = 0
            file_entries.append({
                "name": name,
                "size": int(size),
                "mtime": mtime,
                "md5": md5
            })
        return file_entries

    def download_file(md5, name, mtime):
        # Download if missing or outdated
        safe_name = _sanitize_filename(name)
        local_path = os.path.join(target, safe_name)
        # Only download if missing or mtime newer
        if os.path.exists(local_path):
            prev = os.path.getmtime(local_path)
            if prev >= mtime:
                return False
        # Fetch using hash as param, with vbid
        file_url = f"{server_url.rstrip('/')}/vbox/downloads/{md5}?vbid={vbid}&modified_since={int(mtime)}"
        try:
            resp = requests.get(file_url, timeout=30)
            if resp.status_code == 304:
                gw.info(f"[poll_remote] Skipped {safe_name}: not modified")
                return False
            resp.raise_for_status()
            with open(local_path, "wb") as f:
                f.write(resp.content)
            os.utime(local_path, (mtime, mtime))  # Set mtime to match remote
            gw.info(f"[poll_remote] Downloaded {safe_name} ({md5})")
            return True
        except Exception as e:
            gw.error(f"[poll_remote] Error downloading {safe_name}: {e}")
            return False

    # Main polling loop
    while True:
        file_entries = download_listing()
        count = 0
        for entry in file_entries:
            name = entry["name"]
            md5 = entry["md5"]
            mtime = entry["mtime"]
            if download_file(md5, name, mtime):
                count += 1
        gw.info(f"[poll_remote] Sync complete. Downloaded {count} new/updated files from {server_url} to {target}")
        if not interval:
            break
        time.sleep(interval)


def stream_file_response(path: str, filename: str) -> HTTPResponse:
    """Return a proper file download response that bypasses HTML templating."""
    headers = {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename="{filename}"',
    }
    with open(path, 'rb') as f:
        body = f.read()
    return HTTPResponse(body=body, status=200, headers=headers)


def view_downloads(*hashes: tuple[str], vbid: str = None, modified_since=None, **kwargs):
    """
    GET: Show list of files in the box (with hash), allow selection/downloads.
    If a single hash is provided, return that file. Multiple hashes are not supported yet.

    - Allows access via full vbid (short.long) or short-only (just the folder name).
    - If full vbid is used, shows link to upload more files.
    - If modified_since is passed (as iso or epoch seconds), only send file if newer, else 304.
    """

    # try the next and so forth. Give up when every hash fails to match. First matches is chosen first.

    gw.warning(f"Download view: {hashes=} {vbid=} {kwargs=}")
    if not vbid:
        return render_error("Missing vbid", "You must provide a vbid in the query string.")

    # Accept full or short vbid
    if "." in vbid:
        short, _ = vbid.split(".", 1)
    else:
        short = vbid  # Accept short-only vbid for downloads

    folder = gw.resource(*VBOX_PATH, short)
    if not os.path.isdir(folder):
        return render_error("Box not found", "The folder associated with this vbid does not exist.")

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
        file_mtime = os.path.getmtime(path)
        # Implement modified_since logic
        if modified_since:
            try:
                # Accept both isoformat and epoch seconds
                try:
                    since = float(modified_since)
                except ValueError:
                    since = datetime.fromisoformat(modified_since).timestamp()
                if file_mtime <= since:
                    return HTTPResponse(status=304)
            except Exception as e:
                gw.error(f"modified_since parse error: {modified_since} ({e})")

        return stream_file_response(path, name)

    # Render file listing
    html = "<h1>Download Files</h1><ul>"
    for h, name, size, mtime in file_info:
        time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        link = gw.web.build_url("downloads", h, vbid=vbid)
        html += f'<li><a href="{link}">{name}</a> ({size} bytes, modified {time_str}, MD5: {h})</li>'
    html += "</ul>"

    # Only include upload link if full vbid was used
    if "." in vbid:
        upload_url = gw.web.build_url("upload", vbid=vbid)
        html += f"<p><a href='{upload_url}'>UPLOAD MORE files to this box</a></p>"

    return html