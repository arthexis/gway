import subprocess, re


# TODO: After testing, its too cumbersome to try to export each connection manually and fully
# but fortunately  nmcli already has an export option:
# nmcli connection export <connection-name> > my-connection.nmconnection
# Research this option and rewrite the export function to use that method. This would produce 1 file per
# connection. Call the export on each connection that matches a filter, using an initial call to 
# nmcli -t con show, that produces output like this:

# arthe@gway-001:~/gway $ nmcli -t con show 
# Gelectriic-HS:43a57141-fc84-45b1-9f5d-b3abdb41d525:802-11-wireless:wlan0
# IZZI-158E:571070f4-683c-4fcd-a26a-b77aefae553c:802-11-wireless:wlan1
# lo:4233fa84-4f8d-432c-8189-c22e47aea59a:loopback:lo
# Audi Center Calzada del Valle:ecbd7f9e-d909-4ed9-b31d-80592240e026:802-11-wireless:
# Audi Center Cumbres:2e1c24ed-b33d-4eff-a88b-a41bda98f417:802-11-wireless:
# Audi Center San Pedro:bc850a1b-7715-4c87-b42b-0a537738a09d:802-11-wireless:
# eth0 192.168.1.10:a75a53da-7a65-3b0b-b982-852f44ed4250:802-3-ethernet:
# eth0 192.168.129.10:8d8bf76f-4e57-4d43-8ca5-261c92ee9025:802-3-ethernet:
# Hyperline:1677e091-627c-4e8b-8500-45818c591ef0:802-11-wireless:
# IZZI-158E-5G:1190e964-b9f8-4049-b880-c52b7ae0e51f:802-11-wireless:
# Porsche Centre:332ab50b-5c3a-4144-a949-89efbabc5d0f:802-11-wireless:

# Allow filtering by name and type of device only, an show everything if no filter is given
# Store the 


def export_connections(filter=None, security=False):
    """
    Export NetworkManager connections into a JSON-serializable list of dicts.

    :param filter:   Optional substring or regex to match against connection name, UUID, or SSID (case-insensitive).
    :param security: If True, include secret fields by passing --show-secrets to nmcli (requires root).
    :return:         List of dicts, one per connection.
    """
    def fetch_raw():
        # build base nmcli command
        cmd = ['nmcli']
        if security:
            # include secrets in output
            cmd.append('--show-secrets')
        cmd += ['-t', '-f', 'ALL', 'connection', 'show']
        raw = subprocess.check_output(cmd, text=True)
        # split into blocks separated by blank lines
        return [blk for blk in raw.strip().split('\n\n') if blk.strip()]

    def block_to_dict(block):
        d = {}
        for line in block.splitlines():
            if ':' not in line:
                continue
            key, val = line.split(':', 1)
            d[key.strip().lower()] = val.strip()
        return d

    # fetch and parse all connections
    blocks = fetch_raw()
    conns = [block_to_dict(b) for b in blocks]

    # if filter provided, select only matching by name, uuid, or ssid
    if filter:
        pat = re.compile(filter, re.IGNORECASE)
        filtered = []
        for c in conns:
            for field in ('name', 'uuid', 'ssid'):
                val = c.get(field, '')
                if val and pat.search(val):
                    filtered.append(c)
                    break
        conns = filtered

    return conns
