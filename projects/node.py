import subprocess, json, argparse, re


def extract_nmcli(*, filter=None):

    def fetch_raw(filter_expr=None):
        cmd = ['nmcli', '-t', '-f', 'ALL', 'connection', 'show']
        raw = subprocess.check_output(cmd, text=True)
        blocks = raw.strip().split('\n\n')
        if filter_expr:
            pattern = re.compile(filter_expr)
            blocks = [b for b in blocks if pattern.search(b)]
        return blocks

    def block_to_dict(block):
        d = {}
        for line in block.splitlines():
            if ':' not in line: continue
            k, v = line.split(':',1)
            d[k.strip().lower()] = v.strip()
        return d
    
    blocks = fetch_raw(filter)
    data = [ block_to_dict(b) for b in blocks if b.strip() ]
    print(json.dumps(data, indent=2))


