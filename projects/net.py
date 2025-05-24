import subprocess, json, re


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
