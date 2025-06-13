# projects/web/server.py

# This project supports starting apps using a local server, but also handles
# the administration of external web servers in one single package.

from numpy import iterable
from gway import gw


def start_app(*,
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    debug=False,
    proxy=None,
    app=None,
    daemon=True,
    threaded=True,
    is_worker=False,
    workers=None,
):
    """Start an HTTP (WSGI) or ASGI server to host the given application.

    - If `app` is a FastAPI instance, runs with Uvicorn.
    - If `app` is a WSGI app (Bottle, Paste URLMap, or generic WSGI callables), uses Paste+ws4py or Bottle.
    - If `app` is a zero-arg factory, it will be invoked (supporting sync or async factories).
    - If `app` is a list of apps, each will be run in its own thread (each on an incremented port).
    """
    import inspect
    import asyncio

    def run_server():
        nonlocal app
        all_apps = app if iterable(app) else (app, )

        # B. Dispatch multiple apps in threads if we aren't already in a worker
        if not is_worker and len(all_apps) > 1:
            from threading import Thread
            from collections import Counter
            threads = []
            app_types = []
            gw.info(f"Starting {len(all_apps)} apps in parallel threads.")
            for i, sub_app in enumerate(all_apps):
                try:
                    from fastapi import FastAPI
                    app_type = "FastAPI" if isinstance(sub_app, FastAPI) else type(sub_app).__name__
                except ImportError:
                    app_type = type(sub_app).__name__
                port_i = int(port) + i
                gw.info(f"  App {i+1}: type={app_type}, port={port_i}")
                app_types.append(app_type)

                t = Thread(
                    target=gw.web.server.start_app,
                    kwargs=dict(
                        host=host,
                        port=port_i,
                        debug=debug,
                        proxy=proxy,
                        app=sub_app,
                        daemon=daemon,
                        threaded=threaded,
                        is_worker=True,
                    ),
                    daemon=daemon,
                )
                t.start()
                threads.append(t)

            type_summary = Counter(app_types)
            summary_str = ", ".join(f"{count}×{t}" for t, count in type_summary.items())
            gw.info(f"All {len(all_apps)} apps started. Types: {summary_str}")

            if not daemon:
                for t in threads:
                    t.join()
            return

        # 1. If no apps passed, fallback to default app
        if not all_apps:
            # TODO: Only show this warning if the default app is being built twice which may indicate
            #       and error in the configuration or recipe. Building it once is not a warning.
            gw.warning("Building default app (app is None). Run with --app default to silence.")
            app = gw.web.app.setup(app=None)
        else:
            app = all_apps[0]  # Run the first (or only) app normally

        # 2. Wrap with proxy if requested
        if proxy:
            from .proxy import setup_app as setup_proxy
            app = setup_proxy(endpoint=proxy, app=app)

        # 3. If app is a zero-arg factory, invoke it
        if callable(app):
            sig = inspect.signature(app)
            if len(sig.parameters) == 0:
                gw.info(f"Calling app factory: {app}")
                maybe_app = app()
                if inspect.isawaitable(maybe_app):
                    maybe_app = asyncio.get_event_loop().run_until_complete(maybe_app)
                app = maybe_app
            else:
                gw.info(f"Detected callable WSGI/ASGI app: {app}")

        gw.info(f"Starting {app=} @ {host}:{port}")

        # 4. Detect ASGI/FastAPI
        try:
            from fastapi import FastAPI
            is_asgi = isinstance(app, FastAPI)
        except ImportError:
            is_asgi = False

        if is_asgi:
            try:
                import uvicorn
            except ImportError:
                raise RuntimeError("uvicorn is required to serve ASGI apps. Please install uvicorn.")

            uvicorn.run(
                app,
                host=host,
                port=int(port),
                log_level="debug" if debug else "info",
                workers=workers or 1,
                reload=debug,
            )
            return

        # 5. Fallback to WSGI servers
        from bottle import run as bottle_run, Bottle
        try:
            from paste import httpserver
        except ImportError:
            httpserver = None

        try:
            from ws4py.server.wsgiutils import WebSocketWSGIApplication
            ws4py_available = True
        except ImportError:
            ws4py_available = False

        if httpserver:
            httpserver.serve(
                app, host=host, port=int(port), 
                threadpool_workers=(workers or 5), 
            )
        elif isinstance(app, Bottle):
            bottle_run(
                app,
                host=host,
                port=int(port),
                debug=debug,
                threaded=threaded,
            )
        else:
            raise TypeError(f"Unsupported WSGI app type: {type(app)}")



    if daemon:
        return asyncio.to_thread(run_server)
    else:
        run_server()


...


def config_external(template=None, *,
    enable=True,
    sites_enabled="/etc/nginx/sites-enabled/[WEBSITE_DOMAIN].conf",
    sites_available="/etc/nginx/sites-available/[WEBSITE_DOMAIN].conf",
    host="[WEBSITE_HOST|127.0.0.1]",
    port="[WEBSITE_PORT|8888]",
    use_ssl=True,
    ssl_certificate="/etc/letsencrypt/live/[WEBSITE_DOMAIN]/fullchain.pem",
    ssl_certificate_key="/etc/letsencrypt/live/[WEBSITE_DOMAIN]/privkey.pem",
    dry_run=False,
    check_only=False,
):
    """
    Configure nginx to serve the resolved site config from a template.

    - Backs up previous config in `sites-available`.
    - Optionally creates/removes symlink in `sites-enabled`.
    - Handles SSL cert verification.
    - Tests nginx config and reloads it using `systemctl` or `service`.
    - Flags:
        - dry_run: Log actions, but don't write or execute.
        - check_only: Only test the resolved configuration; no changes made.
        - template: If None, defaults to:
            - 'secure.conf' if use_ssl is True
            - 'basic.conf' if use_ssl is False
    """
    import os, shutil, subprocess, time, platform

    def log_prefix():
        return "[DRY RUN] " if dry_run else ""

    if template is None:
        template = "secure.conf" if use_ssl else "basic.conf"
        gw.info(f"No template provided. Using default: {template}")

    # Resolve paths and template
    sa_path = gw.resolve(sites_available)
    se_path = gw.resolve(sites_enabled)
    ssl_cert = gw.resolve(ssl_certificate)
    ssl_key = gw.resolve(ssl_certificate_key)

    template_code = gw.resource('data', 'nginx', f"{template}.conf", text=True)
    resolved_code = gw.resolve(template_code)

    gw.info(f"{log_prefix()}Resolved nginx template:\n{resolved_code[:240]}{'...' if len(resolved_code) > 240 else ''}")

    if check_only:
        gw.info("Check-only mode: skipping write, symlink, cert, and reload steps.")
        return

    # 1. Backup and write config
    if os.path.exists(sa_path):
        bkp_path = f"{sa_path}.bkp.{time.strftime('%Y%m%d-%H%M%S')}"
        gw.info(f"{log_prefix()}Backing up {sa_path} → {bkp_path}")
        if not dry_run:
            shutil.copy(sa_path, bkp_path)

    gw.info(f"{log_prefix()}Writing resolved config to {sa_path}")
    if not dry_run:
        os.makedirs(os.path.dirname(sa_path), exist_ok=True)
        with open(sa_path, "w") as f:
            f.write(resolved_code)

    # 2. Create/remove symlink
    if enable:
        if not os.path.exists(se_path):
            gw.info(f"{log_prefix()}Creating symlink: {se_path} → {sa_path}")
            if not dry_run:
                os.symlink(sa_path, se_path)
    else:
        if os.path.islink(se_path):
            gw.info(f"{log_prefix()}Removing symlink: {se_path}")
            if not dry_run:
                os.unlink(se_path)

    # 3. SSL check and optional cert renewal
    if use_ssl:
        cert_ok = os.path.exists(ssl_cert) and os.path.exists(ssl_key)
        if not cert_ok:
            gw.error("SSL cert missing. Try: `sudo certbot --nginx -d yourdomain.com -d '*.yourdomain.com'`")
            return
        gw.info(f"{log_prefix()}SSL certificate and key found.")
        if not dry_run:
            try:
                subprocess.run(
                    ["sudo", "certbot", "renew", "--quiet", "--no-self-upgrade"],
                    check=True,
                )
                gw.info("Certbot renewal completed.")
            except subprocess.CalledProcessError as e:
                gw.warning(f"Certbot renewal failed or not needed: {e}")

    # 4. Test and reload nginx
    try:
        if not dry_run:
            subprocess.run(["sudo", "nginx", "-t"], check=True)
        gw.info("Nginx config test passed.")
    except subprocess.CalledProcessError as e:
        gw.error(f"Nginx config test failed: {e}")
        return

    reload_cmd = (
        ["sudo", "systemctl", "reload", "nginx"]
        if platform.system() != "Linux" or os.path.exists("/bin/systemctl")
        else ["sudo", "service", "nginx", "reload"]
    )

    try:
        gw.info(f"{log_prefix()}Reloading nginx using: {' '.join(reload_cmd)}")
        if not dry_run:
            subprocess.run(reload_cmd, check=True)
        gw.info("Nginx reload successful.")
    except subprocess.CalledProcessError as e:
        gw.error(f"Failed to reload nginx: {e}")

