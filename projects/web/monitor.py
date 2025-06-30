# file: projects/web/monitor.py
# web path: /monitor

import asyncio
import subprocess
import time
import datetime
from gway import gw

# --- Global state tracker ---
NMCLI_STATE = {
    "last_config_change": None,      # ISO8601 string
    "last_config_action": None,      # Text summary of change
    "last_monitor_check": None,      # ISO8601 string (new)
    "wlan0_mode": None,              # "ap", "station", or None
    "wlan0_ssid": None,
    "wlan0_connected": None,
    "wlan0_inet": None,              # bool
    "wlanN": {},                     # {iface: {ssid, connected, inet}}
    "eth0_gateway": None,            # bool
    "eth0_ip": None,
    "last_inet_ok": None,            # timestamp
    "last_inet_fail": None,          # timestamp
    "last_error": None,
}

def update_state(key, value):
    NMCLI_STATE[key] = value

def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")

def ping_internet(iface, target="8.8.8.8", count=2, timeout=2):
    try:
        result = subprocess.run(
            ["ping", "-I", iface, "-c", str(count), "-W", str(timeout), target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ok = (result.returncode == 0)
        if ok:
            update_state("last_inet_ok", now_iso())
        else:
            update_state("last_inet_fail", now_iso())
        return ok
    except Exception as e:
        gw.info(f"[monitor] Ping failed ({iface}): {e}")
        update_state("last_error", f"Ping failed ({iface}): {e}")
        update_state("last_inet_fail", now_iso())
        return False

def nmcli(*args):
    result = subprocess.run(["nmcli", *args], capture_output=True, text=True)
    return result.stdout.strip()

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

def get_wlan_status(iface):
    # Returns dict: {ssid, connected, inet}
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
            inet = ping_internet(iface)
            return {"ssid": ssid, "connected": conn, "inet": inet}
    return {"ssid": None, "connected": False, "inet": False}

def ap_profile_exists(ap_conn, ap_ssid, ap_password):
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        fields = line.split()
        if len(fields) < 4: continue
        name, uuid, ctype, device = fields[:4]
        if name == ap_conn and ctype == "wifi":
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

def ensure_ap_profile(ap_conn, ap_ssid, ap_password):
    if not ap_conn:
        raise ValueError("AP_CONN must be specified.")
    if not ap_ssid or not ap_password:
        gw.info("[monitor] Missing AP_SSID or AP_PASSWORD. Skipping AP profile creation.")
        return
    if ap_profile_exists(ap_conn, ap_ssid, ap_password):
        return
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        if line.startswith(ap_conn + " "):
            gw.info(f"[monitor] Removing existing AP connection profile: {ap_conn}")
            nmcli("connection", "down", ap_conn)
            nmcli("connection", "delete", ap_conn)
            break
    gw.info(f"[monitor] Creating AP profile: name={ap_conn} ssid={ap_ssid}")
    nmcli("connection", "add", "type", "wifi", "ifname", "wlan0",
          "con-name", ap_conn, "autoconnect", "no", "ssid", ap_ssid)
    nmcli("connection", "modify", ap_conn,
          "mode", "ap", "802-11-wireless.band", "bg",
          "wifi-sec.key-mgmt", "wpa-psk",
          "wifi-sec.psk", ap_password)

def set_wlan0_ap(ap_conn, ap_ssid, ap_password):
    ensure_ap_profile(ap_conn, ap_ssid, ap_password)
    gw.info(f"[monitor] Activating wlan0 AP: conn={ap_conn}, ssid={ap_ssid}")
    nmcli("device", "disconnect", "wlan0")
    nmcli("connection", "up", ap_conn)
    update_state("wlan0_mode", "ap")
    update_state("wlan0_ssid", ap_ssid)
    update_state("last_config_change", now_iso())
    update_state("last_config_action", f"Activated AP {ap_ssid}")

def set_wlan0_station():
    gw.info("[monitor] Setting wlan0 to station (managed) mode")
    nmcli("device", "set", "wlan0", "managed", "yes")
    nmcli("device", "disconnect", "wlan0")
    update_state("wlan0_mode", "station")
    update_state("last_config_change", now_iso())
    update_state("last_config_action", "Set wlan0 to station")

def check_eth0_gateway():
    try:
        routes = subprocess.check_output(["ip", "route", "show", "dev", "eth0"], text=True)
        ip_addr = get_eth0_ip()
        if "default" in routes:
            subprocess.run(["ip", "route", "del", "default", "dev", "eth0"], stderr=subprocess.DEVNULL)
            nmcli("connection", "modify", "eth0", "ipv4.never-default", "yes")
            nmcli("connection", "up", "eth0")
            gw.info("[monitor] Removed default route from eth0")
            update_state("last_config_change", now_iso())
            update_state("last_config_action", "Removed eth0 default route")
        update_state("eth0_ip", ip_addr)
        update_state("eth0_gateway", "default" in routes)
    except Exception as e:
        update_state("last_error", f"eth0 gateway: {e}")

def clean_and_reconnect_wifi(iface, ssid, password=None):
    conns = nmcli("connection", "show")
    for line in conns.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        name, uuid, conn_type, device = fields[:4]
        if conn_type == "wifi" and (device == iface or name == ssid):
            gw.info(f"[monitor] Removing stale connection {name} ({uuid}) on {iface}")
            nmcli("connection", "down", name)
            nmcli("connection", "delete", name)
            update_state("last_config_change", now_iso())
            update_state("last_config_action", f"Removed stale WiFi {name} on {iface}")
            break
    gw.info(f"[monitor] Resetting interface {iface}")
    nmcli("device", "disconnect", iface)
    nmcli("device", "set", iface, "managed", "yes")
    subprocess.run(["ip", "addr", "flush", "dev", iface])
    subprocess.run(["dhclient", "-r", iface])
    gw.info(f"[monitor] Re-adding {iface} to SSID '{ssid}'")
    if password:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface, "password", password)
    else:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface)
    update_state("last_config_change", now_iso())
    update_state("last_config_action", f"Re-added {iface} to {ssid}")

def try_connect_wlan0_known_networks():
    conns = nmcli("connection", "show")
    wifi_conns = [line.split()[0] for line in conns.splitlines()[1:] if "wifi" in line]
    for conn in wifi_conns:
        gw.info(f"[monitor] Trying wlan0 connect: {conn}")
        nmcli("device", "wifi", "connect", conn, "ifname", "wlan0")
        if ping_internet("wlan0"):
            gw.info(f"[monitor] wlan0 internet works via {conn}")
            update_state("wlan0_mode", "station")
            update_state("wlan0_ssid", conn)
            update_state("wlan0_inet", True)
            update_state("last_config_change", now_iso())
            update_state("last_config_action", f"wlan0 connected to {conn}")
            return True
        clean_and_reconnect_wifi("wlan0", conn)
        if ping_internet("wlan0"):
            gw.info(f"[monitor] wlan0 internet works via {conn} after reset")
            update_state("wlan0_mode", "station")
            update_state("wlan0_ssid", conn)
            update_state("wlan0_inet", True)
            update_state("last_config_change", now_iso())
            update_state("last_config_action", f"wlan0 reconnected to {conn}")
            return True
    update_state("wlan0_inet", False)
    return False

def watch_nmcli(*, 
        block=True, daemon=True, interval=15, 
        ap_ssid=None, ap_password=None, ap_conn=None,
        startup_delay=30
    ):
    """
    Monitor nmcli state and manage AP/client fallback for wlan0.
    :param startup_delay: Seconds to wait before starting monitor loop.
    """

    ap_conn = gw.resolve(ap_conn or '[AP_CONN]')
    ap_ssid = gw.resolve(ap_ssid or '[AP_SSID]')
    ap_password = gw.resolve(ap_password or '[AP_PASSWORD]')
    if not ap_conn:
        raise ValueError("Missing ap_conn (AP_CONN). Required for AP operation.")

    async def monitor_loop():
        # --- Startup delay ---
        if startup_delay > 0:
            gw.info(f"[monitor] Waiting {startup_delay}s before starting monitor loop...")
            await asyncio.sleep(startup_delay)
        while True:
            NMCLI_STATE["last_monitor_check"] = now_iso()   # Update monitor check time
            check_eth0_gateway()
            wlan_ifaces = get_wlan_ifaces()
            gw.info(f"[monitor] WLAN ifaces detected: {wlan_ifaces}")
            # -- Update wlanN status
            NMCLI_STATE["wlanN"] = {}
            found_inet = False
            for iface in wlan_ifaces:
                s = get_wlan_status(iface)
                NMCLI_STATE["wlanN"][iface] = s
                gw.info(f"[monitor] {iface} status: {s}")
                if s["inet"]:
                    gw.info(f"[monitor] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
                    set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                    found_inet = True
                    break
                else:
                    clean_and_reconnect_wifi(iface, iface)
                    s2 = get_wlan_status(iface)
                    NMCLI_STATE["wlanN"][iface] = s2
                    if s2["inet"]:
                        gw.info(f"[monitor] {iface} internet works after reset")
                        set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                        found_inet = True
                        break
            # 2. If no wlanN, try wlan0 as internet
            if not found_inet:
                gw.info("[monitor] No internet via wlanN, trying wlan0 as client")
                set_wlan0_station()
                if try_connect_wlan0_known_networks():
                    gw.info("[monitor] wlan0 now has internet")
                    found_inet = True
                else:
                    gw.info("[monitor] wlan0 cannot connect as client")
            if not found_inet:
                gw.info("[monitor] No internet found, switching wlan0 to AP")
                set_wlan0_ap(ap_conn, ap_ssid, ap_password)
            await asyncio.sleep(interval)

    def blocking_loop():
        # --- Startup delay ---
        if startup_delay > 0:
            gw.info(f"[monitor] Waiting {startup_delay}s before starting monitor loop...")
            time.sleep(startup_delay)
        while True:
            NMCLI_STATE["last_monitor_check"] = now_iso()
            check_eth0_gateway()
            wlan_ifaces = get_wlan_ifaces()
            gw.info(f"[monitor] WLAN ifaces detected: {wlan_ifaces}")
            NMCLI_STATE["wlanN"] = {}
            found_inet = False
            for iface in wlan_ifaces:
                s = get_wlan_status(iface)
                NMCLI_STATE["wlanN"][iface] = s
                gw.info(f"[monitor] {iface} status: {s}")
                if s["inet"]:
                    gw.info(f"[monitor] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
                    set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                    found_inet = True
                    break
                else:
                    clean_and_reconnect_wifi(iface, iface)
                    s2 = get_wlan_status(iface)
                    NMCLI_STATE["wlanN"][iface] = s2
                    if s2["inet"]:
                        gw.info(f"[monitor] {iface} internet works after reset")
                        set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                        found_inet = True
                        break
            if not found_inet:
                gw.info("[monitor] No internet via wlanN, trying wlan0 as client")
                set_wlan0_station()
                if try_connect_wlan0_known_networks():
                    gw.info("[monitor] wlan0 now has internet")
                    found_inet = True
                else:
                    gw.info("[monitor] wlan0 cannot connect as client")
            if not found_inet:
                gw.info("[monitor] No internet found, switching wlan0 to AP")
                set_wlan0_ap(ap_conn, ap_ssid, ap_password)
            time.sleep(interval)

    if daemon:
        return monitor_loop()
    if block:
        blocking_loop()
    else:
        NMCLI_STATE["last_monitor_check"] = now_iso()
        check_eth0_gateway()
        wlan_ifaces = get_wlan_ifaces()
        for iface in wlan_ifaces:
            s = get_wlan_status(iface)
            NMCLI_STATE["wlanN"][iface] = s
            if s["inet"]:
                set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                return
            else:
                clean_and_reconnect_wifi(iface, iface)
                s2 = get_wlan_status(iface)
                NMCLI_STATE["wlanN"][iface] = s2
                if s2["inet"]:
                    set_wlan0_ap(ap_conn, ap_ssid, ap_password)
                    return
        set_wlan0_station()
        if not try_connect_wlan0_known_networks():
            set_wlan0_ap(ap_conn, ap_ssid, ap_password)

# -- HTML report fragment --
def _color_icon(status):
    """Return a green/yellow/red dot HTML for boolean or status."""
    if status is True or status == "ok":
        return '<span style="color:#0b0;">&#9679;</span>'
    if status is False or status == "fail":
        return '<span style="color:#b00;">&#9679;</span>'
    return '<span style="color:#bb0;">&#9679;</span>'

def view_nmcli_report(**_):
    """
    Returns a diagnostic HTML fragment with the current nmcli state.
    Includes time of last monitor check and colored indicators for key values.
    """

    s = NMCLI_STATE
    html = [
        '<div class="nmcli-report">',
        f"<b>Last monitor check:</b> {s.get('last_monitor_check') or '-'}<br>",
        f"<b>Last config change:</b> {s.get('last_config_change') or 'Never'}<br>",
        f"<b>Last action:</b> {s.get('last_config_action') or '-'}<br>",
        f"<b>wlan0 mode:</b> {s.get('wlan0_mode') or '-'}<br>",
        f"<b>wlan0 ssid:</b> {s.get('wlan0_ssid') or '-'}<br>",
        f"<b>wlan0 internet:</b> {_color_icon(s.get('wlan0_inet'))} {s.get('wlan0_inet')}<br>",
        f"<b>eth0 IP:</b> {s.get('eth0_ip') or '-'}<br>",
        f"<b>eth0 gateway:</b> {_color_icon(s.get('eth0_gateway'))} {'yes' if s.get('eth0_gateway') else 'no'}<br>",
        f"<b>Last internet OK:</b> {_color_icon(bool(s.get('last_inet_ok')))} {s.get('last_inet_ok') or '-'}<br>",
        f"<b>Last internet fail:</b> {_color_icon(bool(s.get('last_inet_fail')))} {s.get('last_inet_fail') or '-'}<br>",
        f"<b>Last error:</b> {_color_icon(s.get('last_error') is None)} {s.get('last_error') or '-'}<br>",
        "<b>WLANN status:</b><br><ul>",
    ]
    for iface, state in (s.get("wlanN") or {}).items():
        html.append(f"<li>{iface}: ssid={state.get('ssid')}, conn={_color_icon(state.get('connected'))} {state.get('connected')}, inet={_color_icon(state.get('inet'))} {state.get('inet')}</li>")
    html.append("</ul></div>")
    return "\n".join(html)

