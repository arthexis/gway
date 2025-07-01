# file: monitor/nmcli.py

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

import os
import subprocess
from gway import gw

def now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")

# --- Utility functions ---

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
            return {"ssid": ssid, "connected": conn, "inet": inet}
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

def ensure_ap_profile(ap_con, ap_ssid, ap_password):
    if not ap_con:
        raise ValueError("AP_CON must be specified.")
    if not ap_ssid or not ap_password:
        gw.info("[nmcli] Missing AP_SSID or AP_PASSWORD. Skipping AP profile creation.")
        return
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
    nmcli("connection", "add", "type", "wifi", "ifname", "wlan0",
          "con-name", ap_con, "autoconnect", "no", "ssid", ap_ssid)
    nmcli("connection", "modify", ap_con,
          "mode", "ap", "802-11-wireless.band", "bg",
          "wifi-sec.key-mgmt", "wpa-psk",
          "wifi-sec.psk", ap_password)

def set_wlan0_ap(ap_con, ap_ssid, ap_password):
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

def clean_and_reconnect_wifi(iface, ssid, password=None):
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
    conns = nmcli("connection", "show")
    wifi_conns = [line.split()[0] for line in conns.splitlines()[1:] if "wifi" in line]
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
            return True
        clean_and_reconnect_wifi("wlan0", conn)
        if ping("wlan0"):
            gw.info(f"[nmcli] wlan0 internet works via {conn} after reset")
            gw.monitor.set_states('nmcli', {
                "wlan0_mode": "station",
                "wlan0_ssid": conn,
                "wlan0_inet": True,
                "last_config_change": now_iso(),
                "last_config_action": f"wlan0 reconnected to {conn}"
            })
            return True
    gw.monitor.set_states('nmcli', {"wlan0_inet": False})
    return False

# --- Main single-run monitor functions ---

def monitor_nmcli(**kwargs):
    ap_ssid = kwargs.get("ap_ssid") or gw.resolve('[AP_SSID]')
    ap_con = kwargs.get("ap_con") or ap_ssid or gw.resolve('[AP_CON]')
    ap_password = kwargs.get("ap_password") or gw.resolve('[AP_PASSWORD]')
    if not ap_con:
        raise ValueError("Missing ap_con (AP_CON). Required for AP operation.")

    check_eth0_gateway()
    wlan_ifaces = get_wlan_ifaces()
    gw.info(f"[nmcli] WLAN ifaces detected: {wlan_ifaces}")
    wlanN = {}
    found_inet = False
    for iface in wlan_ifaces:
        s = get_wlan_status(iface)
        wlanN[iface] = s
        gw.info(f"[nmcli] {iface} status: {s}")
        if s["inet"]:
            gw.info(f"[nmcli] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
            set_wlan0_ap(ap_con, ap_ssid, ap_password)
            found_inet = True
            break
        else:
            clean_and_reconnect_wifi(iface, iface)
            s2 = get_wlan_status(iface)
            wlanN[iface] = s2
            if s2["inet"]:
                gw.info(f"[nmcli] {iface} internet works after reset")
                set_wlan0_ap(ap_con, ap_ssid, ap_password)
                found_inet = True
                break
    gw.monitor.set_states('nmcli', {"wlanN": wlanN})
    if not found_inet:
        gw.info("[nmcli] No internet via wlanN, trying wlan0 as client")
        set_wlan0_station()
        if try_connect_wlan0_known_networks():
            gw.info("[nmcli] wlan0 now has internet")
            found_inet = True
        else:
            gw.info("[nmcli] wlan0 cannot connect as client")
    if not found_inet:
        gw.info("[nmcli] No internet found, switching wlan0 to AP")
        set_wlan0_ap(ap_con, ap_ssid, ap_password)
    gw.monitor.set_states('nmcli', {"last_monitor_check": now_iso()})
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
    html = ['<div class="nmcli-report">']
    html.append("<h2>Network State Monitor</h2>")
    html.append(f"<b>Last monitor check:</b> {s.get('last_monitor_check') or '-'}<br>")
    html.append(f"<b>Last config change:</b> {s.get('last_config_change') or 'Never'}<br>")
    html.append(f"<b>Last action:</b> {s.get('last_config_action') or '-'}<br>")
    html.append(f"<b>wlan0 mode:</b> {s.get('wlan0_mode') or '-'}<br>")
    html.append(f"<b>wlan0 ssid:</b> {s.get('wlan0_ssid') or '-'}<br>")
    html.append(f"<b>wlan0 internet:</b> {_color_icon(s.get('wlan0_inet'))} {s.get('wlan0_inet')}<br>")
    html.append(f"<b>eth0 IP:</b> {s.get('eth0_ip') or '-'}<br>")
    html.append(f"<b>eth0 gateway:</b> {_color_icon(s.get('eth0_gateway'))} {'yes' if s.get('eth0_gateway') else 'no'}<br>")
    html.append(f"<b>Last internet OK:</b> {_color_icon(bool(s.get('last_inet_ok')))} {s.get('last_inet_ok') or '-'}<br>")
    html.append(f"<b>Last internet fail:</b> {_color_icon(bool(s.get('last_inet_fail')))} {s.get('last_inet_fail') or '-'}<br>")
    html.append(f"<b>Last error:</b> {_color_icon(s.get('last_error') is None)} {s.get('last_error') or '-'}<br>")
    html.append("<b>WLANN status:</b><br><ul>")
    for iface, st in (s.get("wlanN") or {}).items():
        html.append(f"<li>{iface}: ssid={st.get('ssid')}, conn={_color_icon(st.get('connected'))} {st.get('connected')}, inet={_color_icon(st.get('inet'))} {st.get('inet')}</li>")
    html.append("</ul></div>")
    return "\n".join(html)

def render_status():
    s = gw.monitor.get_state('nmcli')
    mode = s.get('wlan0_mode') or '-'
    ssid = s.get('wlan0_ssid') or '-'
    inet = _color_icon(s.get('wlan0_inet'))
    last = s.get('last_monitor_check') or '-'
    return (f"<div class='status-summary'>"
            f"<b>Mode:</b> {mode} <b>SSID:</b> {ssid} <b>INET:</b> {inet} <b>Last:</b> {last}</div>")

def render_monitor():
    return render_nmcli()
