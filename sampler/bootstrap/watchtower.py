"""Installer catalog helpers for the public bootstrap recipe."""

import json


_INSTALLERS = {
    "gway": "Install the GWAY command and orchestration framework.",
    "satellite": (
        "Install Arthexis for an edge or remote Satellite node. "
        "Satellite is a configuration identity, not a separate application bundle."
    ),
    "control": (
        "Install Arthexis for a Control node associated with local equipment "
        "or a focused operational task. Control is a configuration identity."
    ),
}


def _title(slug):
    if slug == "gway":
        return "GWAY"
    return slug.replace("-", " ").title()


def catalog():
    """Return the public installer catalog for the static discovery page."""
    installers = [
        {
            "installer": slug,
            "title": _title(slug),
            "description": description,
        }
        for slug, description in _INSTALLERS.items()
    ]
    return {
        "installers": installers,
        "installers_json": json.dumps(
            installers,
            ensure_ascii=True,
            separators=(",", ":"),
        ),
    }


def installer(name, yes=False):
    """Publish one validated installer identity for endpoint rendering."""
    try:
        description = _INSTALLERS[name]
    except KeyError as exception:
        raise ValueError(f"Unknown installer: {name}") from exception
    return {
        "installer": name,
        "installer_title": _title(name),
        "installer_description": description,
        "installer_yes": "1" if yes else "0",
    }
