import subprocess, json, re


def export_connections(*, filter=None, security=False):
    """
    Export NetworkManager connections into a JSON-serializable list of dicts.

    :param filter:   Optional substring to match against connection name or UUID (case-insensitive).
    :param security: If True, include secret fields by passing --show-secrets to nmcli.
    :return:         List of dicts, one per connection.
    """
    def fetch_raw():
        # build base command
        cmd = ['nmcli']
        if security:
            # ask nmcli to include secrets
            cmd.append('--show-secrets')
        cmd += ['-t', '-f', 'ALL', 'connection', 'show']
        raw = subprocess.check_output(cmd, text=True)
        # split blocks by blank line
        return [blk for blk in raw.strip().split('\n\n') if blk.strip()]

    def block_to_dict(block):
        d = {}
        for line in block.splitlines():
            if ':' not in line:
                continue
            key, val = line.split(':', 1)
            d[key.strip().lower()] = val.strip()
        return d

    # 1) fetch all raw blocks
    blocks = fetch_raw()
    # 2) parse into dicts
    conns = [block_to_dict(b) for b in blocks]

    # 3) apply filter on name or uuid if requested
    if filter:
        pat = re.compile(re.escape(filter), re.IGNORECASE)
        filtered = []
        for c in conns:
            name = c.get('name', '')
            uuid = c.get('uuid', '')
            if pat.search(name) or pat.search(uuid):
                filtered.append(c)
        conns = filtered

    return conns
