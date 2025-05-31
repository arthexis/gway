import re
from gway import gw


def find(*paths, **patterns):
    if len(paths) < 2:
        raise ValueError("At least two path elements are required: file path(s) and key")

    key = str(paths[-1]).strip().lower()
    file_parts = [str(p).strip() for p in paths[:-1]]
    if not file_parts[-1].endswith('.cdv'):
        file_parts[-1] += '.cdv'

    cdv_file = gw.resource(*file_parts)

    with open(cdv_file, 'r') as f:
        for line in reversed(f.readlines()):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(':')]
            record_key = parts[0].lower()
            values = parts[1:] if len(parts) > 1 else []
            if record_key != key:
                continue
            if not patterns:
                if not values:
                    return True
                elif len(values) == 1:
                    return values[0]
                else:
                    return tuple(values)

            result = {}
            compiled = {k: (v if isinstance(v, re.Pattern) else re.compile(str(v)))
                        for k, v in patterns.items()}
            for i, val in enumerate(values):
                for field, regex in compiled.items():
                    if i == field or str(i) == str(field):
                        if regex.search(val):
                            result[field] = val

            if not result:
                continue
            if len(result) == 1:
                return next(iter(result.values()))
            return result

    return None


def store(*paths, sep='=', value):
    if len(paths) < 2:
        raise ValueError("At least two path elements are required: file path(s) and key")

    key = str(paths[-1]).strip()
    file_parts = [str(p).strip() for p in paths[:-1]]
    if not file_parts[-1].endswith('.cdv'):
        file_parts[-1] += '.cdv'

    cdv_file = gw.resource(*file_parts)
    cdv_file.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(value, bool):
        val_str = ''
    elif isinstance(value, (tuple, list, set)):
        val_str = ':'.join(str(v) for v in value)
    elif isinstance(value, dict):
        val_str = ':'.join(f'{k}{sep}{v}' for k, v in value.items())
    else:
        val_str = str(value)

    with open(cdv_file, 'a') as f:
        f.write(f"{key}:{val_str}\n")

def remove(*paths):
    if len(paths) < 2:
        raise ValueError("At least two path elements are required: file path(s) and key")

    key = str(paths[-1]).strip().lower()
    file_parts = [str(p).strip() for p in paths[:-1]]
    if not file_parts[-1].endswith('.cdv'):
        file_parts[-1] += '.cdv'

    cdv_file = gw.resource(*file_parts)

    if not cdv_file.exists():
        return

    lines = cdv_file.read_text().splitlines()
    updated = [line for line in lines if not line.strip().lower().startswith(f"{key}:")]

    cdv_file.write_text('\n'.join(updated) + '\n' if updated else '')

def pop(*paths, **patterns):
    result = find(*paths, **patterns)
    if result is not None:
        remove(*paths)
    return result
