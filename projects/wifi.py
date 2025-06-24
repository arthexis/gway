# file: projects/wifi.py

import asyncio
import os
import re
import subprocess
import ipaddress
from typing import List, Dict
from gway import gw

def _run(cmd: List[str], check=False, capture_output=True, text=True, timeout=20):
    try:
        out = subprocess.run(cmd, check=check, capture_output=capture_output, text=text, timeout=timeout)
        return out.stdout.strip()
    except Exception as e:
        gw.error(f"Subprocess error: {e} (cmd: {cmd})")
        return ""

def _parse_nmcli_conns():
    out = _run(['nmcli', '-t', '-f', 'NAME,UUID,TYPE,DEVICE', 'connection', 'show'])
    lines = out.splitlines()
    conns = []
    for line in lines:
        fields = line.split(':')
        if len(fields) == 4:
            conns.append(dict(name=fields[0], uuid=fields[1], type=fields[2], device=fields[3]))
    return conns

def _parse_nmcli_devices():
    out = _run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device'])
    lines = out.splitlines()
    devs = []
    for line in lines:
        fields = line.split(':')
        if len(fields) == 4:
            devs.append(dict(device=fields[0], type=fields[1], state=fields[2], connection=fields[3]))
    return devs

def _role_from_name(name):
    m = re.match(r"^(AP|LAN|GATE)\b(\+*)\b", name, re.I)
    if m:
        base = m.group(1).upper()
        plusses = m.group(2)
        plus_count = len(plusses)
        return base, plus_count
    return "OTHER", 0

def _priority(role, plus):
    if role == "OTHER":
        return 0
    return 10 + 40 * plus

def _pick_highest(conns, role):
    cands = [(c, _priority(role, c['plus'])) for c in conns if c['role'] == role]
    if not cands:
        return None
    return max(cands, key=lambda x: x[1])[0]

def _check_gateway(dev, target_ip):
    ret = _run(['ping', '-c', '2', '-I', dev, target_ip])
    return '0% packet loss' in ret or '1 received' in ret

def _set_static_ip(dev, ip, mask='255.255.255.0'):
    # No-op if already configured
    out = _run(['nmcli', '-f', 'IP4.ADDRESS[1]', 'device', 'show', dev])
    if ip in out:
        return
    return _run(['nmcli', 'con', 'mod', dev, 'ipv4.addresses', f"{ip}/24", 'ipv4.method', 'manual'])

def _scan_lan(ip_mask='192.168.198.0/24'):
    net = ipaddress.ip_network(ip_mask, strict=False)
    _run(['ping', '-c', '1', '-b', str(net.network_address)])
    neighs = _run(['ip', 'neigh'])
    return neighs

async def watchdog(*,
        interval=120, hs="wlan0", lan="eth0", gate="wlan1", other=True,
        test_gate_ip='8.8.8.8', test_lan_ip='192.168.198.0/24', mail=None
    ):
    """
    Async WiFi watchdog for GWAY networks (nmcli-based).
    Periodically enforces: 1 AP, 1 LAN, 1 GATE; resets connections as needed.
    Logs state changes to gw.info/error/debug. Sends email on stable recovery.
    """
    last_state = {
        'ap_ok': None,
        'lan_ok': None,
        'gate_ok': None,
        'all_stable': None,
    }

    async def notify(subject, body):
        try:
            if mail is True or mail is None:
                to = os.environ.get("ADMIN_EMAIL")
            elif isinstance(mail, str):
                to = mail
            else:
                to = None
            if not to:
                gw.error("Cannot send watchdog email: No recipient.")
                return
            await gw.mail.send(subject=subject, body=body, to=to, async_=True)
            gw.info(f"Watchdog notification sent to {to}")
        except Exception as e:
            gw.error(f"Failed to send watchdog notification: {e}")

    while True:
        gw.debug("wifi.watchdog: starting new scan...")
        conns = _parse_nmcli_conns()
        devs = _parse_nmcli_devices()

        # Tag role/priority
        for c in conns:
            role, plus = _role_from_name(c['name'])
            c['role'] = role
            c['plus'] = plus
            c['prio'] = _priority(role, plus)
        ap_conns = [c for c in conns if c['role'] == 'AP']
        lan_conns = [c for c in conns if c['role'] == 'LAN']
        gate_conns = [c for c in conns if c['role'] == 'GATE']
        other_conns = [c for c in conns if c['role'] == 'OTHER']

        # ----- AP
        best_ap = _pick_highest(ap_conns, "AP")
        ap_dev = next((d for d in devs if d['device'] == hs), None)
        ap_ok = False
        if best_ap:
            if ap_dev and ap_dev['connection'] == best_ap['name'] and ap_dev['state'] == 'connected':
                ap_ok = True
                gw.debug(f"AP already up on {hs}: {best_ap['name']}")
            else:
                gw.info(f"AP {best_ap['name']} not active on {hs}. Will reconnect.")
                _run(['nmcli', 'connection', 'up', best_ap['uuid']])
        else:
            gw.error("No AP connection defined!")

        # Disconnect any other APs
        for c in ap_conns:
            if c != best_ap and c['device']:
                gw.info(f"Disabling stray AP connection: {c['name']}")
                _run(['nmcli', 'connection', 'down', c['uuid']])

        # ----- LAN
        best_lan = _pick_highest(lan_conns, "LAN")
        lan_dev = next((d for d in devs if d['device'] == lan), None)
        lan_ok = False
        if best_lan:
            if lan_dev and lan_dev['connection'] == best_lan['name'] and lan_dev['state'] == 'connected':
                lan_ok = True
                gw.debug(f"LAN already up on {lan}: {best_lan['name']}")
                # Ensure static IP
                _set_static_ip(lan, "192.168.198.10")
            else:
                gw.info(f"LAN {best_lan['name']} not active on {lan}. Will reconnect.")
                _run(['nmcli', 'connection', 'up', best_lan['uuid']])
        else:
            gw.error("No LAN connection defined!")

        # Disconnect other LANs
        for c in lan_conns:
            if c != best_lan and c['device']:
                gw.info(f"Disabling stray LAN connection: {c['name']}")
                _run(['nmcli', 'connection', 'down', c['uuid']])

        # ----- GATE
        best_gate = _pick_highest(gate_conns, "GATE")
        gate_dev = next((d for d in devs if d['device'] == gate), None)
        gate_ok = False
        if best_gate:
            if gate_dev and gate_dev['connection'] == best_gate['name'] and gate_dev['state'] == 'connected':
                if _check_gateway(gate, test_gate_ip):
                    gate_ok = True
                    gw.debug(f"GATE already up and internet OK on {gate}: {best_gate['name']}")
                else:
                    gw.error(f"GATE {best_gate['name']} up on {gate} but internet unreachable. Reconnecting.")
                    _run(['nmcli', 'device', 'disconnect', gate])
                    await asyncio.sleep(5)
                    _run(['nmcli', 'connection', 'up', best_gate['uuid']])
            else:
                gw.info(f"GATE {best_gate['name']} not active on {gate}. Will reconnect.")
                _run(['nmcli', 'connection', 'up', best_gate['uuid']])
        else:
            gw.error("No GATE connection defined!")

        # Disconnect other GATEs
        for c in gate_conns:
            if c != best_gate and c['device']:
                gw.info(f"Disabling stray GATE connection: {c['name']}")
                _run(['nmcli', 'connection', 'down', c['uuid']])

        # ----- OTHER
        if not other:
            for c in other_conns:
                if c['device']:
                    gw.info(f"Disabling OTHER connection: {c['name']}")
                    _run(['nmcli', 'connection', 'down', c['uuid']])
            for d in devs:
                if d['type'] in {'wifi', 'ethernet'} and d['device'] not in (hs, lan, gate):
                    if d['connection']:
                        gw.info(f"Disconnecting OTHER device: {d['device']}")
                        _run(['nmcli', 'device', 'disconnect', d['device']])

        # ----- SCAN LAN for EVCS
        if best_lan and lan_ok:
            neighs = _scan_lan(test_lan_ip)
            gw.debug(f"LAN neighbor scan: {neighs}")

        # ----- State transition and notification -----
        all_stable = ap_ok and lan_ok and gate_ok
        state_changed = (all_stable != last_state['all_stable'])
        last_state['ap_ok'] = ap_ok
        last_state['lan_ok'] = lan_ok
        last_state['gate_ok'] = gate_ok
        last_state['all_stable'] = all_stable

        if state_changed and all_stable and mail:
            subject = "WiFi Watchdog: Network Restored"
            body = "All required network roles (AP, LAN, GATE) are now up and healthy."
            await notify(subject, body)

        await asyncio.sleep(interval)

