# file: projects/web/static.py

import os
from gway import gw

def collect(*, css="global", js="global", root="data/static", target="work/shared"):
    enabled = getattr(gw.web.app, "enabled_projects", lambda: set())()
    static_root = gw.resource(root)

    def find_files(kind, proj):
        found = []
        seen = set()
        parts = proj.split('.')
        # Recursively walk project path
        if parts:
            proj_path = os.path.join(static_root, *parts)
            for rootdir, dirs, files in os.walk(proj_path):
                rel_root = os.path.relpath(rootdir, static_root)
                for fname in files:
                    if kind == "css" and fname.endswith(".css"):
                        rel = os.path.join(rel_root, fname)
                    elif kind == "js" and fname.endswith(".js"):
                        rel = os.path.join(rel_root, fname)
                    else:
                        continue
                    if rel not in seen:
                        seen.add(rel)
                        found.append((proj, rel, os.path.join(rootdir, fname)))
        # Ancestors, only direct files
        for i in range(len(parts)-1, -1, -1):
            ancestor_path = os.path.join(static_root, *parts[:i])
            if not os.path.isdir(ancestor_path):
                continue
            rel_ancestor = os.path.relpath(ancestor_path, static_root)
            for fname in os.listdir(ancestor_path):
                fpath = os.path.join(ancestor_path, fname)
                if not os.path.isfile(fpath):
                    continue
                if kind == "css" and fname.endswith(".css"):
                    rel = os.path.join(rel_ancestor, fname) if rel_ancestor != "." else fname
                elif kind == "js" and fname.endswith(".js"):
                    rel = os.path.join(rel_ancestor, fname) if rel_ancestor != "." else fname
                else:
                    continue
                if rel not in seen:
                    seen.add(rel)
                    found.append((proj, rel, fpath))
        return found

    report = {"css": [], "js": []}
    # --- Collect CSS ---
    if css:
        all_css = []
        for proj in enabled:
            all_css.extend(find_files("css", proj))
        seen_css = set()
        for entry in all_css:
            if entry[1] not in seen_css:
                seen_css.add(entry[1])
                report["css"].append(entry)
        if isinstance(css, str):
            bundle_path = gw.resource(target, f"{css}.css")
            with open(bundle_path, "w", encoding="utf-8") as out:
                for proj, rel, full in reversed(report["css"]):
                    with open(full, "r", encoding="utf-8") as f:
                        out.write(f"/* --- {proj}:{rel} --- */\n")
                        out.write(f.read() + "\n\n")
            report["css_bundle"] = bundle_path

    # --- Collect JS ---
    if js:
        all_js = []
        for proj in enabled:
            all_js.extend(find_files("js", proj))
        seen_js = set()
        for entry in all_js:
            if entry[1] not in seen_js:
                seen_js.add(entry[1])
                report["js"].append(entry)
        if isinstance(js, str):
            bundle_path = gw.resource(target, f"{js}.js")
            with open(bundle_path, "w", encoding="utf-8") as out:
                for proj, rel, full in report["js"]:
                    with open(full, "r", encoding="utf-8") as f:
                        out.write(f"// --- {proj}:{rel} ---\n")
                        out.write(f.read() + "\n\n")
            report["js_bundle"] = bundle_path

    return report
