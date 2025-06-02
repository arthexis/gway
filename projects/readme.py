# projects/readme.py
"""
GWAY project module to collect all projects and functions and update README.rst.
Usage (CLI): gway readme collect projects <projects_dir> [--readme READMENAME]
"""

import os
import importlib.util
import inspect
from gway import gw


def collect_projects(project_dir: str, readme: str = "README.rst"):
    """
    Scan `project_dir` for all modules/packages, collect public functions,
    build an RST section, and insert/update it in `readme` before the LICENSE heading.

    Args:
        project_dir: path to the GWAY projects directory.
        readme: path to the README file to update.
    """
    # 1) Gather projects and their public functions
    projects = {}
    for entry in os.scandir(project_dir):
        if entry.name.startswith("_"):
            continue
        name = entry.name[:-3] if entry.is_file() and entry.name.endswith(".py") else entry.name
        module_root = os.path.join(project_dir, *name.split("."))
        if os.path.isdir(module_root) and os.path.isfile(os.path.join(module_root, "__init__.py")):
            module_file = os.path.join(module_root, "__init__.py")
        else:
            module_file = module_root + ".py"
        try:
            spec = importlib.util.spec_from_file_location(name, module_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            gw.warning(f"Skipping project {name}: failed to import: {e}")
            continue

        funcs = []
        for fname, obj in inspect.getmembers(module, inspect.isfunction):
            if fname.startswith("_"):
                continue
            doc = inspect.getdoc(obj) or "(no description)"
            cli_path = ' '.join(name.replace('_', ' ').split('.'))
            cli_func = fname.replace('_', '-')
            funcs.append({
                "name": fname,
                "doc": doc,
                "cli": f"gway {cli_path} {cli_func}"
            })
        projects[name] = funcs

    # 2) Build RST lines for INCLUDED PROJECTS
    lines = ["INCLUDED PROJECTS\n", "=================\n\n"]
    for name, funcs in sorted(projects.items()):
        lines.append(f".. rubric:: {name}\n\n")
        for f in funcs:
            lines.append(f"- ``{f['name']}`` — {f['doc'].splitlines()[0]}\n\n")
            lines.append(f"  > ``{f['cli']}``\n\n")
        lines.append("\n")

    # 3) Read existing README and locate section boundaries
    with open(readme, 'r', encoding='utf-8') as f:
        content = f.readlines()

    license_idx = next((i for i, l in enumerate(content) if l.strip().upper() == 'LICENSE'), len(content))
    start_idx = next((i for i, l in enumerate(content) if l.strip() == 'INCLUDED PROJECTS'), None)
    if start_idx is not None:
        content = content[:start_idx] + content[license_idx:]
        license_idx = start_idx

    # 4) Insert the updated project section
    new_content = content[:license_idx] + lines + ['\n'] + content[license_idx:]
    with open(readme, 'w', encoding='utf-8') as f:
        f.writelines(new_content)

    gw.log(f"Updated {readme} with {len(projects)} projects.")
