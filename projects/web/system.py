# projects/web/system.py

from gway import gw


def config(template=None, *,
    enable=True,
    sites_enabled="/etc/nginx/sites-enabled/[WEBSITE_DOMAIN].conf",
    sites_available="/etc/nginx/sites-available/[WEBSITE_DOMAIN].conf",
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

