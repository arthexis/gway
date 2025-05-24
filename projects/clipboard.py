import subprocess
import os
from gway import requires, gw


@requires("pyperclip")
def copy(value=None, *, notify=True):
    """Extracts the contents of the clipboard and returns it."""
    import pyperclip

    original = pyperclip.paste()
    if value is not None:
        gw.warning(f"Clipboard accessed ->\n{original=}\n{value=}.")
        pyperclip.copy(value)
        distance = len(value) - len(original)
        if abs(distance) <= 40:
            gw.gui.notify(f"Clipboard modified: {value}")
        else:
            gw.gui.notify("Clipboard modified (%+d bytes)" % distance)
    else:
        gw.debug("Clipboard called with no value.")
    return original


@requires("pyperclip")
def patch(repo_path=None, patch_filename="temp.patch"):
    """
    Grab a unified diff from the clipboard, save as a .patch file, preview with `git apply --check`,
    and if it passes, run `git apply` for real.

    Args:
      repo_path (str): root of your git repo; defaults to cwd.
      patch_filename (str): name for the temporary patch file.
    """
    import pyperclip

    repo_path = repo_path or os.getcwd()
    patch_text = pyperclip.paste()
    if not patch_text.strip().startswith(("diff --git", "--- ", "+++ ")):
        print("Clipboard does not look like a git patch; aborting.")
        return

    patch_path = os.path.join(repo_path, patch_filename)
    with open(patch_path, "w", encoding="utf-8") as f:
        f.write(patch_text)
    print(f"Saved clipboard to {patch_path!r}")

    # 1) Dry run
    check = subprocess.run(
        ["git", "apply", "--check", patch_path],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if check.returncode != 0:
        print("⚠️  Patch failed preview. Here’s the output:\n")
        print(check.stderr)
        os.remove(patch_path)
        return

    # 2) Apply for real
    apply = subprocess.run(
        ["git", "apply", patch_path],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    if apply.returncode == 0:
        print("✅ Patch applied successfully!")
    else:
        print("❌ git apply errored:\n", apply.stderr)

    # cleanup
    os.remove(patch_path)
