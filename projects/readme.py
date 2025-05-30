import os
import inspect
from textwrap import shorten
from gway import gw


def collect_projects(project_dir="projects"):
    """Update README.rst to include the INCLUDED PROJECTS section."""

    readme_path = gw.resource("README.rst")
    if not os.path.exists(readme_path):
        gw.abort(f"README.rst not found at {readme_path}")

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove existing INCLUDED PROJECTS section if it exists
    start_marker = "INCLUDED PROJECTS"
    end_marker = "LICENSE"
    lower = content.lower()
    if start_marker.lower() in lower and end_marker.lower() in lower:
        start = lower.index(start_marker.lower())
        end = lower.index(end_marker.lower())
        content = content[:start] + content[end:]

    # Gather project documentation
    lines = []
    lines.append("INCLUDED PROJECTS")
    lines.append("=================")
    lines.append("")

    projects_path = gw.resource(project_dir)
    for entry in sorted(os.listdir(projects_path)):
        if entry.startswith("_") or not (entry.endswith(".py") or os.path.isdir(os.path.join(projects_path, entry))):
            continue

        project = entry[:-3] if entry.endswith(".py") else entry
        try:
            project_obj = gw.load_project(project)
        except Exception as e:
            gw.warning(f"Skipping {project}: {e}")
            continue

        lines.append("")
        header = f"Project: {project}"
        underline = "=" * len(header)
        lines.append(underline)
        lines.append(header)
        lines.append(underline)
        lines.append("")

        lines.append("+----------------------+--------------------------------------+")
        lines.append("| Function             | Docstring                            |")
        lines.append("+======================+======================================+")

        for fname in dir(project_obj):
            if fname.startswith("_"):
                continue
            func = getattr(project_obj, fname)
            if not callable(func):
                continue

            raw_func = getattr(func, "__wrapped__", func)
            doc = inspect.getdoc(raw_func) or ""
            short_doc = shorten(doc.splitlines()[0] if doc else "", width=38, placeholder="...")

            lines.append(f"| {fname:<20} | {short_doc:<38} |")
            lines.append(f"| {'':<20} | gway {project} {fname:<30} |")
            lines.append("+----------------------+--------------------------------------+")
        lines.append("")

    # Re-insert LICENSE section
    license_index = content.lower().find("license")
    license_section = content[license_index:].lstrip() if license_index >= 0 else "\nLICENSE\n=======\n"

    updated_content = content.strip() + "\n\n" + "\n".join(lines) + "\n\n" + license_section

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    gw.info(f"README.rst updated with INCLUDED PROJECTS section.")
