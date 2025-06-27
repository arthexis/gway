# file: projects/web/monitor.py

import asyncio
import subprocess
import time
from gway import gw

def ping_internet(iface, target="8.8.8.8", count=2, timeout=2):
    """Ping through a specific interface. Return True if internet is reachable."""
    try:
        result = subprocess.run(
            ["ping", "-I", iface, "-c", str(count), "-W", str(timeout), target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except Exception as e:
        gw.info(f"[monitor] Ping failed ({iface}): {e}")
        return False

def nmcli(*args):
    """Run nmcli command and return stdout."""
    result = subprocess.run(["nmcli", *args], capture_output=True, text=True)
    return result.stdout.strip()

def get_wlan_ifaces():
    """Return a list of wlan interfaces (excluding wlan0, which is reserved for AP)."""
    output = nmcli("device", "status")
    wlans = []
    for line in output.splitlines():
        if line.startswith("wlan"):
            name = line.split()[0]
            if name != "wlan0":
                wlans.append(name)
    return wlans

def set_wlan0_mode(mode: str, ssid: str = "Gelectriic-HS", password: str = "YourPassword"):
    if mode == "ap":
        gw.info(f"[monitor] Setting wlan0 AP mode: {ssid}")
        nmcli("device", "wifi", "hotspot", "ifname", "wlan0", "ssid", ssid, "password", password)
    elif mode == "station":
        gw.info("[monitor] Setting wlan0 to station (managed) mode")
        nmcli("device", "set", "wlan0", "managed", "yes")
        nmcli("device", "disconnect", "wlan0")

def check_eth0_gateway():
    # Remove default route from eth0 if present
    try:
        routes = subprocess.check_output(["ip", "route", "show", "dev", "eth0"], text=True)
        if "default" in routes:
            subprocess.run(["ip", "route", "del", "default", "dev", "eth0"], stderr=subprocess.DEVNULL)
            nmcli("connection", "modify", "eth0", "ipv4.never-default", "yes")
            nmcli("connection", "up", "eth0")
            gw.info("[monitor] Removed default route from eth0")
    except Exception:
        pass  # ignore if no route

def clean_and_reconnect_wifi(iface, ssid, password=None):
    """
    Clean up and re-add a WiFi connection on iface.
    Useful if we move to a new site with same SSID/password but stale config.
    """
    # List all connections for this interface/SSID
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
            break
    # Reset iface
    gw.info(f"[monitor] Resetting interface {iface}")
    nmcli("device", "disconnect", iface)
    nmcli("device", "set", iface, "managed", "yes")
    # Flush IP and DHCP lease
    subprocess.run(["ip", "addr", "flush", "dev", iface])
    subprocess.run(["dhclient", "-r", iface])
    # Re-add
    gw.info(f"[monitor] Re-adding {iface} to SSID '{ssid}'")
    if password:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface, "password", password)
    else:
        nmcli("device", "wifi", "connect", ssid, "ifname", iface)

def try_connect_wlan0_known_networks():
    """
    Try connecting wlan0 to any known WiFi (auto-fix stale configs if fails).
    """
    conns = nmcli("connection", "show")
    wifi_conns = [line.split()[0] for line in conns.splitlines()[1:] if "wifi" in line]
    for conn in wifi_conns:
        gw.info(f"[monitor] Trying wlan0 connect: {conn}")
        nmcli("device", "wifi", "connect", conn, "ifname", "wlan0")
        if ping_internet("wlan0"):
            gw.info(f"[monitor] wlan0 internet works via {conn}")
            return True
        # If it fails, clean up and try again (in case of stale config)
        clean_and_reconnect_wifi("wlan0", conn)
        if ping_internet("wlan0"):
            gw.info(f"[monitor] wlan0 internet works via {conn} after reset")
            return True
    return False

def watch_nmcli(block=True, daemon=True, interval=15, ap_ssid="Gelectriic-HS", ap_password="YourPassword"):
    """
    Monitor/maintain optimal network state:
    - Prefer wlanN (N>0) as internet gateway if possible, keep wlan0 as AP.
    - Fallback: use wlan0 for internet if needed.
    - Final fallback: set wlan0 as AP.
    Logs all changes using gw.info.
    Cleans up stale WiFi configs if needed.
    """
    async def monitor_loop():
        while True:
            check_eth0_gateway()
            wlan_ifaces = get_wlan_ifaces()
            gw.info(f"[monitor] WLAN ifaces detected: {wlan_ifaces}")

            # 1. Prefer wlanN (N>0) as internet gateway, keep wlan0 as AP
            found_inet = False
            for iface in wlan_ifaces:
                gw.info(f"[monitor] Checking internet on {iface}...")
                if ping_internet(iface):
                    gw.info(f"[monitor] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
                    set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                    found_inet = True
                    break
                else:
                    # Try cleaning up and reconnecting
                    clean_and_reconnect_wifi(iface, iface)
                    if ping_internet(iface):
                        gw.info(f"[monitor] {iface} internet works after reset")
                        set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                        found_inet = True
                        break

            # 2. If no wlanN, try wlan0 as internet
            if not found_inet:
                gw.info("[monitor] No internet via wlanN, trying wlan0 as client")
                set_wlan0_mode("station")
                if try_connect_wlan0_known_networks():
                    gw.info("[monitor] wlan0 now has internet")
                    found_inet = True
                else:
                    gw.info("[monitor] wlan0 cannot connect as client")

            # 3. Fallback: set wlan0 to AP mode if no internet found
            if not found_inet:
                gw.info("[monitor] No internet found, switching wlan0 to AP")
                set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)

            await asyncio.sleep(interval)

    def blocking_loop():
        while True:
            check_eth0_gateway()
            wlan_ifaces = get_wlan_ifaces()
            gw.info(f"[monitor] WLAN ifaces detected: {wlan_ifaces}")

            found_inet = False
            for iface in wlan_ifaces:
                gw.info(f"[monitor] Checking internet on {iface}...")
                if ping_internet(iface):
                    gw.info(f"[monitor] {iface} has internet, keeping wlan0 as AP ({ap_ssid})")
                    set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                    found_inet = True
                    break
                else:
                    clean_and_reconnect_wifi(iface, iface)
                    if ping_internet(iface):
                        gw.info(f"[monitor] {iface} internet works after reset")
                        set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                        found_inet = True
                        break

            if not found_inet:
                gw.info("[monitor] No internet via wlanN, trying wlan0 as client")
                set_wlan0_mode("station")
                if try_connect_wlan0_known_networks():
                    gw.info("[monitor] wlan0 now has internet")
                    found_inet = True
                else:
                    gw.info("[monitor] wlan0 cannot connect as client")

            if not found_inet:
                gw.info("[monitor] No internet found, switching wlan0 to AP")
                set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)

            time.sleep(interval)

    if daemon:
        return monitor_loop()
    if block:
        blocking_loop()
    else:
        check_eth0_gateway()
        wlan_ifaces = get_wlan_ifaces()
        for iface in wlan_ifaces:
            if ping_internet(iface):
                set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                return
            else:
                clean_and_reconnect_wifi(iface, iface)
                if ping_internet(iface):
                    set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)
                    return
        set_wlan0_mode("station")
        if not try_connect_wlan0_known_networks():
            set_wlan0_mode("ap", ssid=ap_ssid, password=ap_password)

if __name__ == "__main__":
    watch_nmcli()
