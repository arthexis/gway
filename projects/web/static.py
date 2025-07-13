# file: projects/web/static.py

import os
from gway import gw

def collect(*, css="global", js="global", root="data/static", target="work/shared", full=False):
    """Collect static assets from enabled projects or the entire tree."""
    gw.verbose(
        f"[static.collect] css={css} js={js} root={root} target={target} full={full}"
    )
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

    def gather(kind):
        if full:
            found = []
            seen = set()
            for rootdir, dirs, files in os.walk(static_root):
                rel_root = os.path.relpath(rootdir, static_root)
                proj = rel_root.replace(os.sep, ".") if rel_root != "." else ""
                for fname in files:
                    if kind == "css" and fname.endswith(".css"):
                        rel = os.path.join(rel_root, fname) if rel_root != "." else fname
                    elif kind == "js" and fname.endswith(".js"):
                        rel = os.path.join(rel_root, fname) if rel_root != "." else fname
                    else:
                        continue
                    if rel not in seen:
                        seen.add(rel)
                        found.append((proj, rel, os.path.join(rootdir, fname)))
            gw.verbose(f"[static.collect] full {kind} scan found {len(found)} files")
            return found
        else:
            collected = []
            for proj in enabled:
                gw.verbose(f"[static.collect] scanning {proj} for {kind}")
                collected.extend(find_files(kind, proj))
            gw.verbose(
                f"[static.collect] {kind} from enabled projects → {len(collected)} files"
            )
            return collected

    # --- Collect CSS ---
    if css:
        all_css = gather("css")
        seen_css = set()
        for entry in all_css:
            if entry[1] not in seen_css:
                seen_css.add(entry[1])
                report["css"].append(entry)
        if isinstance(css, str):
            bundle_path = gw.resource(target, f"{css}.css")
            gw.verbose(
                f"[static.collect] bundling {len(report['css'])} CSS files into {bundle_path}"
            )
            with open(bundle_path, "w", encoding="utf-8") as out:
                for proj, rel, full in reversed(report["css"]):
                    with open(full, "r", encoding="utf-8") as f:
                        out.write(f"/* --- {proj}:{rel} --- */\n")
                        out.write(f.read() + "\n\n")
            report["css_bundle"] = bundle_path

    # --- Collect JS ---
    if js:
        all_js = gather("js")
        seen_js = set()
        for entry in all_js:
            if entry[1] not in seen_js:
                seen_js.add(entry[1])
                report["js"].append(entry)
        if isinstance(js, str):
            bundle_path = gw.resource(target, f"{js}.js")
            gw.verbose(
                f"[static.collect] bundling {len(report['js'])} JS files into {bundle_path}"
            )
            with open(bundle_path, "w", encoding="utf-8") as out:
                for proj, rel, full in report["js"]:
                    with open(full, "r", encoding="utf-8") as f:
                        out.write(f"// --- {proj}:{rel} ---\n")
                        out.write(f.read() + "\n\n")
            report["js_bundle"] = bundle_path

    return report
