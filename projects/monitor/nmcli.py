# file: projects/monitor/nmcli.py

"""
GWAY NMCLI Network Monitor Project

Single-run monitor and render functions for Linux systems using nmcli.
Works with monitor/monitor.py. All state is read/written via gw.monitor.get_state/set_states('nmcli', {...}).

Monitors:
    - monitor_nmcli: Full network check/fallback logic (AP/station/repair).
    - monitor_ap_only: Ensure wlan0 is in AP mode.
    - monitor_station_only: Ensure wlan0 is in station/client mode.

Renders:
    - render_nmcli: Main network diagnostic report (HTML).
    - render_status: Short summary/status indicator.
    - render_monitor: Fallback renderer.
"""

import subprocess
from gway import gw
from gway.sigils import _unquote

def now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")

# --- Utility functions ---

def nmcli(*args):
    result = subprocess.run(["nmcli", *args], capture_output=True, text=True)
    return result.stdout.strip()

def _sanitize(val):
    return _unquote(val.strip()) if isinstance(val, str) else val

def get_wlan_ifaces():
    output = nmcli("device", "status")
    wlans = []
    for line in output.splitlines():
        if line.startswith("wlan"):
            name = line.split()[0]
            if name != "wlan0":
                wlans.append(name)
    return wlans

def get_eth0_ip():
    output = nmcli("device", "show", "eth0")
    for line in output.splitlines():
        if "IP4.ADDRESS" in line:
            return line.split(":")[-1].strip()
    return None

def get_device_info(dev):
    """
    Returns a dict with relevant info for a network device, such as state, type, driver, path, mac, etc.
    """
    info = {
        'device': dev,
        'type': '-',
        'state': '-',
        'driver': '-',
        'mac': '-',
        'path': '-',
        'connection': '-',
    }
    try:
        output = nmcli('device', 'show', dev)
        for line in output.splitlines():
            if line.startswith('GENERAL.TYPE'):
                info['type'] = line.split(':', 1)[-1].strip()
            elif line.startswith('GENERAL.STATE'):
                info['state'] = line.split(':', 1)[-1].strip()
            elif line.startswith('GENERAL.HWADDR'):
                info['mac'] = line.split(':', 1)[-1].strip()
            elif line.startswith('GENERAL.DRIVER'):
                info['driver'] = line.split(':', 1)[-1].strip()
            elif line.startswith('GENERAL.PATH'):
                info['path'] = line.split(':', 1)[-1].strip()
            elif line.startswith('GENERAL.CONNECTION'):
                info['connection'] = line.split(':', 1)[-1].strip()
    except Exception as e:
        info['error'] = str(e)
    return info

def get_all_devices():
    """
    Returns a list of all device names from nmcli (regardless of status).
    """
    devices = []
    out = nmcli('device', 'status')
    for line in out.splitlines():
        parts = line.split()
        if parts:
            devices.append(parts[0])
    return devices

def get_default_route_iface():
    """Return the interface used for the default route, or None."""
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], text=True)
        for line in out.splitlines():
            if line.startswith("default"):
                parts = line.split()
                if "dev" in parts:
                    idx = parts.index("dev")
                    if idx + 1 < len(parts):
                        return parts[idx + 1]
    except Exception:
        pass
    return None

def ping(iface, target="8.8.8.8", count=2, timeout=2):
    try:
        result = subprocess.run(
            ["ping", "-I", iface, "-c", str(count), "-W", str(timeout), target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception:
        return False

def get_wlan_status(iface):
    output = nmcli("device", "status")
    for line in output.splitlines():
        if line.startswith(iface):
            fields = line.split()
            conn = (fields[2] == "connected")
            # Try to get SSID (from nmcli device show iface)
            ssid = None
            info = nmcli("device", "show", iface)
            for inf in info.splitlines():
                if "GENERAL.CONNECTION" in inf:
                    conn_name = inf.split(":")[-1].strip()
                    if conn_name and conn_name != "--":
                        # Try nmcli connection show <name> for ssid
                        det = nmcli("connection", "show", conn_name)
                        for dline in det.splitlines():
                            if "802-11-wireless.ssid" in dline:
                                ssid = dline.split(":")[-1].strip()
                                break
            inet = ping(iface)
            status = {"ssid": ssid, "connected": conn, "inet": inet}
            gw.debug(f"[nmcli] status for {iface}: {status}")
            return status
    return {"ssid": None, "connected": False, "inet": False}

def check_eth0_gateway():
    try:
        routes = subprocess.check_output(["ip", "route", "show", "dev", "eth0"], text=True)
        ip_addr = get_eth0_ip()
        state_update = {
            "eth0_ip": ip_addr,
            "eth0_gateway": "default" in routes
        }
        if "default" in routes:
            subprocess.run(["ip", "route", "del", "default", "dev", "eth0"], stderr=subprocess.DEVNULL)
            nmcli("connection", "modify", "eth0", "ipv4.never-default", "yes")
            nmcli("connection", "up", "eth0")
            state_update.update({
                "last_config_change": now_iso(),
                "last_config_action": "Removed eth0 default route"
            })
        gw.monitor.set_states('nmcli', state_update)
    except Exception as e:
        gw.monitor.set_states('nmcli', {"last_error": f"eth0 gateway: {e}"})

def ap_profile_exists(ap_con, ap_ssid, ap_password):
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        fields = line.split()
        if len(fields) < 4: continue
        name, uuid, ctype, device = fields[:4]
        if name == ap_con and ctype == "wifi":
            details = nmcli("connection", "show", name)
            details_dict = {}
            for detline in details.splitlines():
                if ':' in detline:
                    k, v = detline.split(':', 1)
                    details_dict[k.strip()] = v.strip()
            ssid_ok = (details_dict.get("802-11-wireless.ssid") == ap_ssid)
            pwd_ok  = (not ap_password or details_dict.get("802-11-wireless-security.psk") == ap_password)
            return ssid_ok and pwd_ok
    return False

def ensure_ap_profile(ap_con, ap_ssid, ap_password, ap_ip=None):
    ap_con = _sanitize(ap_con)
    ap_ssid = _sanitize(ap_ssid)
    ap_password = _sanitize(ap_password)
    if not ap_con:
        raise ValueError("AP_CON must be specified.")
    if not ap_ssid or not ap_password:
        gw.info("[nmcli] Missing AP_SSID or AP_PASSWORD. Skipping AP profile creation.")
        return
    ap_ip = gw.resolve('[LOCAL_IP]', default=ap_ip)
    if ap_profile_exists(ap_con, ap_ssid, ap_password):
        return
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        if line.startswith(ap_con + " "):
            gw.info(f"[nmcli] Removing existing AP connection profile: {ap_con}")
            nmcli("connection", "down", ap_con)
            nmcli("connection", "delete", ap_con)
            break
    gw.info(f"[nmcli] Creating AP profile: name={ap_con} ssid={ap_ssid}")
    nmcli(
        "connection",
        "add",
        "type",
        "wifi",
        "ifname",
        "wlan0",
        "con-name",
        ap_con,
        "autoconnect",
        "no",
        "ssid",
        ap_ssid,
    )
    nmcli(
        "connection",
        "modify",
        ap_con,
        "mode",
        "ap",
        "802-11-wireless.band",
        "bg",
        "wifi-sec.key-mgmt",
        "wpa-psk",
        "wifi-sec.psk",
        ap_password,
        "ipv4.method",
        "shared",
        "ipv4.addresses",
        f"{ap_ip or '10.42.0.1'}/24",
    )

def set_wlan0_ap(ap_con, ap_ssid, ap_password):
    ap_con = _sanitize(ap_con)
    ap_ssid = _sanitize(ap_ssid)
    ap_password = _sanitize(ap_password)
    ensure_ap_profile(ap_con, ap_ssid, ap_password)
    gw.info(f"[nmcli] Activating wlan0 AP: conn={ap_con}, ssid={ap_ssid}")
    nmcli("device", "disconnect", "wlan0")
    nmcli("connection", "up", ap_con)
    gw.monitor.set_states('nmcli', {
        "wlan0_mode": "ap",
        "wlan0_ssid": ap_ssid,
        "last_config_change": now_iso(),
        "last_config_action": f"Activated AP {ap_ssid}"
    })

def set_wlan0_station():
    gw.info("[nmcli] Setting wlan0 to station (managed) mode")
    nmcli("device", "set", "wlan0", "managed", "yes")
    nmcli("device", "disconnect", "wlan0")
    gw.monitor.set_states('nmcli', {
        "wlan0_mode": "station",
        "last_config_change": now_iso(),
        "last_config_action": "Set wlan0 to station"
    })

def maybe_notify_ap_switch(ap_ssid, email=None):
    state = gw.monitor.get_state('nmcli')
    prev_mode = state.get("wlan0_mode")
    prev_ssid = state.get("wlan0_ssid")
    prev_inet = state.get("wlan0_inet")
    recipient = email if email else gw.resolve('[ADMIN_EMAIL]', default=None)
    if not recipient:
        return
    if prev_mode == "station" and prev_inet:
        subject = "[nmcli] wlan0 switching to AP mode"
        body = (
            f"Previous mode: station\n"
            f"SSID: {prev_ssid}\n"
            f"Internet: {prev_inet}\n\n"
            f"New mode: ap\n"
            f"AP SSID: {ap_ssid}\n"
        )
        try:
            gw.mail.send(subject, body=body, to=recipient)
        except Exception as e:
            gw.error(f"[nmcli] Email notification failed: {e}")

def clean_and_reconnect_wifi(iface, ssid, password=None):
    gw.debug(f"[nmcli] clean_and_reconnect_wifi({iface}, ssid={ssid})")
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        name, uuid, conn_type, device = fields[:4]
        if conn_type == "wifi" and (device == iface or name == ssid):
            gw.info(f"[nmcli] Removing stale connection {name} ({uuid}) on {iface}")
            nmcli("connection", "down", name)
            nmcli("connection", "delete", name)
            gw.monitor.set_states('nmcli', {
                "last_config_change": now_iso(),
                "last_config_action": f"Removed stale WiFi {name} on {iface}"
            })
            break
    gw.info(f"[nmcli] Resetting interface {iface}")
    nmcli("device", "disconnect", iface)
    nmcli("device", "set", iface, "managed", "yes")
    subprocess.run(["ip", "addr", "flush", "dev", iface])
    subprocess.run(["dhclient", "-r", iface])
    gw.info(f"[nmcli] Re-adding {iface} to SSID '{ssid}'")
    if password:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface, "password", password)
    else:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface)
    gw.monitor.set_states('nmcli', {
        "last_config_change": now_iso(),
        "last_config_action": f"Re-added {iface} to {ssid}"
    })

def try_connect_wlan0_known_networks():
    """Try connecting wlan0 using known WiFi profiles.

    Returns the SSID if connection succeeds, otherwise None.
    """
    conns = nmcli("connection", "show")
    wifi_conns = [line.split()[0] for line in conns.splitlines()[1:] if "wifi" in line]
    gw.debug(f"[nmcli] known wifi profiles: {wifi_conns}")
    for conn in wifi_conns:
        gw.info(f"[nmcli] Trying wlan0 connect: {conn}")
        nmcli("device", "wifi", "connect", conn, "ifname", "wlan0")
        if ping("wlan0"):
            gw.info(f"[nmcli] wlan0 internet works via {conn}")
            gw.monitor.set_states('nmcli', {
                "wlan0_mode": "station",
                "wlan0_ssid": conn,
                "wlan0_inet": True,
                "last_config_change": now_iso(),
                "last_config_action": f"wlan0 connected to {conn}"
            })
            return conn
        clean_and_reconnect_wifi("wlan0", conn)
        gw.debug(f"[nmcli] retrying connection to {conn} after reset")
        if ping("wlan0"):
            gw.info(f"[nmcli] wlan0 internet works via {conn} after reset")
            gw.monitor.set_states('nmcli', {
                "wlan0_mode": "station",
                "wlan0_ssid": conn,
                "wlan0_inet": True,
                "last_config_change": now_iso(),
                "last_config_action": f"wlan0 reconnected to {conn}"
            })
            return conn
    gw.monitor.set_states('nmcli', {"wlan0_inet": False})
    return None

# --- Main single-run monitor functions ---

def monitor_nmcli(**kwargs):
    ap_ssid = kwargs.get("ap_ssid") or gw.resolve('[AP_SSID]')
    ap_con = kwargs.get("ap_con") or ap_ssid or gw.resolve('[AP_CON]')
    ap_password = kwargs.get("ap_password") or gw.resolve('[AP_PASSWORD]')
    email = kwargs.get("email")
    if not ap_con:
        raise ValueError("Missing ap_con (AP_CON). Required for AP operation.")

    check_eth0_gateway()
    wlan_ifaces = get_wlan_ifaces()
    gw.info(f"[nmcli] WLAN ifaces detected: {wlan_ifaces}")
    wlanN = {}
    found_inet = False
    internet_iface = None
    internet_ssid = None
    for iface in wlan_ifaces:
        s = get_wlan_status(iface)
        wlanN[iface] = s
        gw.info(f"[nmcli] {iface} status: {s}")
        if s["inet"]:
            gw.info(f"[nmcli] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
            maybe_notify_ap_switch(ap_ssid, email)
            set_wlan0_ap(ap_con, ap_ssid, ap_password)
            found_inet = True
            internet_iface = iface
            internet_ssid = s.get("ssid")
            break
        else:
            clean_and_reconnect_wifi(iface, s.get("ssid") or iface)
            s2 = get_wlan_status(iface)
            wlanN[iface] = s2
            if s2["inet"]:
                gw.info(f"[nmcli] {iface} internet works after reset")
                maybe_notify_ap_switch(ap_ssid, email)
                set_wlan0_ap(ap_con, ap_ssid, ap_password)
                found_inet = True
                internet_iface = iface
                internet_ssid = s2.get("ssid")
                break
    gw.monitor.set_states('nmcli', {"wlanN": wlanN})
    if not found_inet:
        gw.info("[nmcli] No internet via wlanN, trying wlan0 as client")
        set_wlan0_station()
        conn = try_connect_wlan0_known_networks()
        if conn:
            gw.info("[nmcli] wlan0 now has internet")
            found_inet = True
            internet_iface = "wlan0"
            internet_ssid = conn
        else:
            gw.info("[nmcli] wlan0 cannot connect as client")
            # Keep wlan0 in station mode. It will switch back to AP
            # only when another interface provides internet.

    # Fallback to system default route
    gw_iface = get_default_route_iface()
    gw.debug(f"[nmcli] default route iface: {gw_iface}")
    if gw_iface and not internet_iface:
        if ping(gw_iface):
            found_inet = True
        internet_iface = gw_iface
        if gw_iface in wlanN:
            internet_ssid = wlanN[gw_iface].get("ssid")
        elif gw_iface == "wlan0":
            internet_ssid = gw.monitor.get_state('nmcli').get("wlan0_ssid")
            
    gw.monitor.set_states('nmcli', {
        "last_monitor_check": now_iso(),
        "internet_iface": internet_iface,
        "internet_ssid": internet_ssid,
    })
    gw.debug(
        f"[nmcli] monitor results: found_inet={found_inet}, "
        f"internet_iface={internet_iface}, internet_ssid={internet_ssid}"
    )
    state = gw.monitor.get_state('nmcli')
    return {
        "ok": found_inet,
        "action": state.get("last_config_action"),
        "wlan0_mode": state.get("wlan0_mode"),
    }

def monitor_ap_only(**kwargs):
    ap_ssid = kwargs.get("ap_ssid") or gw.resolve('[AP_SSID]')
    ap_con = kwargs.get("ap_con") or ap_ssid or gw.resolve('[AP_CON]')
    ap_password = kwargs.get("ap_password") or gw.resolve('[AP_PASSWORD]')
    set_wlan0_ap(ap_con, ap_ssid, ap_password)
    gw.monitor.set_states('nmcli', {"last_monitor_check": now_iso()})
    state = gw.monitor.get_state('nmcli')
    return {"wlan0_mode": state.get("wlan0_mode"), "ssid": ap_ssid}

def monitor_station_only(**kwargs):
    set_wlan0_station()
    gw.monitor.set_states('nmcli', {"last_monitor_check": now_iso()})
    state = gw.monitor.get_state('nmcli')
    return {"wlan0_mode": state.get("wlan0_mode")}

# --- Renderers (for dashboard, html output) ---

def _color_icon(status):
    if status is True or status == "ok":
        return '<span style="color:#0b0;">&#9679;</span>'
    if status is False or status == "fail":
        return '<span style="color:#b00;">&#9679;</span>'
    return '<span style="color:#bb0;">&#9679;</span>'


def render_nmcli():
    s = gw.monitor.get_state('nmcli')
    wlanN = s.get("wlanN") or {}
    internet_iface = s.get("internet_iface")
    internet_ssid = s.get("internet_ssid")

    # Fallback detection from wlan statuses
    if not internet_iface:
        for iface, st in wlanN.items():
            if st.get('inet'):
                internet_iface = iface
                internet_ssid = st.get('ssid')
                break
    if not internet_iface and s.get('wlan0_inet'):
        internet_iface = 'wlan0'
        internet_ssid = s.get('wlan0_ssid')

    # Gather device info for eth0, wlan0, all wlanN, and any other network devices
    devices = get_all_devices()
    device_info = {dev: get_device_info(dev) for dev in devices}
    wlan_count = len([d for d in devices if d.startswith('wlan') and d != 'wlan0'])

    html = ['<div class="nmcli-report">']
    html.append("<h2>Network Manager</h2>")
    html.append(f"<b>Last monitor check:</b> {s.get('last_monitor_check') or '-'}<br>")
    last_action = s.get('last_config_action')
    last_change = s.get('last_config_change')
    if last_action and last_change:
        html.append(f"<b>Last action:</b> {last_change} - {last_action}<br>")
    else:
        html.append(f"<b>Last action:</b> {last_action or '-'}<br>")
    html.append(f"<b>wlan0 mode:</b> {s.get('wlan0_mode') or '-'}<br>")
    # AP info
    wlan0_info = device_info.get('wlan0', {})
    html.append(
        f"<b>wlan0 ssid:</b> {s.get('wlan0_ssid') or '-'} "
        f"(state: {wlan0_info.get('state','-')}, driver: {wlan0_info.get('driver','-')}, "
        f"mac: {wlan0_info.get('mac','-')})<br>"
    )
    html.append(f"<b>wlan0 internet:</b> {_color_icon(s.get('wlan0_inet'))} {s.get('wlan0_inet')}<br>")

    # eth0 info
    eth0_ip = s.get('eth0_ip')
    eth0_color = _color_icon(bool(eth0_ip))
    eth0_info = device_info.get('eth0', {})
    html.append(
        f"<b>eth0 IP:</b> {eth0_color} {eth0_ip or '-'} "
        f"(state: {eth0_info.get('state','-')}, driver: {eth0_info.get('driver','-')}, "
        f"mac: {eth0_info.get('mac','-')})<br>"
    )
    eth0_gw = s.get('eth0_gateway')
    html.append(f"<b>eth0 gateway:</b> {_color_icon(eth0_gw)} {'yes' if eth0_gw else 'no'}<br>")

    html.append(f"<b>Last internet OK:</b> {_color_icon(bool(s.get('last_inet_ok')))} {s.get('last_inet_ok') or '-'}<br>")
    html.append(f"<b>Last internet fail:</b> {_color_icon(bool(s.get('last_inet_fail')))} {s.get('last_inet_fail') or '-'}<br>")
    html.append(f"<b>Last error:</b> {_color_icon(s.get('last_error') is None)} {s.get('last_error') or '-'}<br>")

    # All wlanN and relevant info (including disconnected/disabled)
    html.append(f"<b>WLANN interfaces:</b> {wlan_count}<br>")
    html.append('<table style="border-collapse:collapse;margin-top:4px;font-size:90%;">'
                '<tr>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">iface</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">SSID</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">Connected</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">INET</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">State</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">Driver</th>'
                '<th style="border:1px solid #ccc;padding:2px 4px;">MAC</th>'
                '</tr>')
    for dev in sorted([d for d in devices if d.startswith('wlan')]):
        st = wlanN.get(dev, {})
        dinfo = device_info.get(dev, {})
        gw_mark = ' <b>(gw)</b>' if dev == internet_iface else ''
        html.append(
            f"<tr>"
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{dev}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{st.get("ssid") or "-"}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{_color_icon(st.get("connected"))} {st.get("connected") if "connected" in st else dinfo.get("state", "-")}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{_color_icon(st.get("inet")) if "inet" in st else _color_icon(dinfo.get("state")=="connected")} {st.get("inet") if "inet" in st else "-"}{gw_mark}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{dinfo.get("state", "-")}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{dinfo.get("driver", "-")}</td>'
            f'<td style="border:1px solid #ccc;padding:2px 4px;">{dinfo.get("mac", "-")}</td>'
            f"</tr>"
        )
    html.append('</table>')

    # Internet gateway info (with device detail)
    if internet_iface:
        gwdev = device_info.get(internet_iface, {})
        html.append(
            f"<b>Internet via:</b> {internet_iface} (SSID: {internet_ssid}) "
            f"(driver: {gwdev.get('driver','-')}, mac: {gwdev.get('mac','-')}, state: {gwdev.get('state','-')})<br>"
        )
    else:
        html.append(f"<b>Internet via:</b> <span style='color:#b00;'>No gateway detected</span><br>")

    html.append("</div>")
    return "\n".join(html)
