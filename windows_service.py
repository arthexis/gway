import argparse
import subprocess
import re
from pathlib import Path


def run(cmd, check=True):
    print(' '.join(cmd))
    subprocess.run(cmd, check=check)


def safe_name(recipe: str) -> str:
    name = re.sub(r'[\\/]', '-', recipe)
    name = re.sub(r'[^a-zA-Z0-9_-]', '-', name)
    return f"gway-{name}"


def install_service(name: str, recipe: str):
    script_dir = Path(__file__).resolve().parent
    batpath = script_dir / 'gway.bat'
    cmd = f'cmd /c "\"{batpath}\" -r {recipe}"'
    run(['sc.exe', 'create', name, 'binPath=', cmd, 'start=', 'auto'])
    run(['sc.exe', 'failure', name, 'reset=', '0', 'actions=', 'restart/5000'])
    run(['sc.exe', 'failureflag', name, '1'])
    run(['sc.exe', 'start', name])
    run(['sc.exe', 'query', name])


def remove_service(name: str, force: bool = False):
    if force:
        subprocess.run(['sc.exe', 'stop', name], check=False)
    run(['sc.exe', 'delete', name])


def list_recipes():
    out = subprocess.run(['sc.exe', 'query', 'state=', 'all'], capture_output=True, text=True, check=True).stdout
    names = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('SERVICE_NAME:'):
            svc = line.split(':', 1)[1].strip()
            if svc.lower().startswith('gway-'):
                names.append(svc)
    for name in names:
        qc = subprocess.run(['sc.exe', 'qc', name], capture_output=True, text=True, check=True).stdout
        m = re.search(r'-r\s+([^\s\"]+)', qc)
        if m:
            print(m.group(1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)

    pi = sub.add_parser('install')
    pi.add_argument('--name', required=True)
    pi.add_argument('--recipe', required=True)

    pr = sub.add_parser('remove')
    pr.add_argument('--name', required=True)
    pr.add_argument('--recipe', required=True)
    pr.add_argument('--force', action='store_true')

    pl = sub.add_parser('list-recipes')

    args = p.parse_args()

    if args.cmd == 'install':
        install_service(args.name, args.recipe)
    elif args.cmd == 'remove':
        remove_service(args.name, args.force)
    elif args.cmd == 'list-recipes':
        list_recipes()


if __name__ == '__main__':
    main()
