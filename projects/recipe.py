# Helper functions for working with GWAY Recipes (.gwr) files

import platform
import subprocess
from pathlib import Path
from gway import gw


def register_gwr():
    """
    Register the .gwr file extension so that double-click launches:
        gway -r "<full path to file>"
    Works on Windows (via registry) and Linux (via desktop entry + MIME).
    """
    system = platform.system()

    if system == "Windows":
        _register_windows()
    elif system == "Linux":
        _register_linux()
    else:
        raise NotImplementedError(f"Auto-association not implemented for {system!r}")
    

def _register_windows():
    import winreg

    # 1) Associate .gwr with a ProgID
    prog_id = "gway.Recipe"
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, ".gwr") as ext_key:
        winreg.SetValue(ext_key, "", winreg.REG_SZ, prog_id)

    # 2) Define the command for the ProgID
    cmd = f'"gway" -r "%1"'
    key_path = f"{prog_id}\\shell\\open\\command"
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path) as cmd_key:
        winreg.SetValue(cmd_key, "", winreg.REG_SZ, cmd)

    gw.info(".gwr association registered in the Windows registry.")


def _register_linux():
    """
    1) Write a ~/.local/share/mime/packages/gwr.xml to declare text/x-gwr MIME type
    2) Update the MIME database
    3) Write a ~/.local/share/applications/gway-recipe.desktop
    4) Update the desktop database
    """
    home = Path.home()
    mime_dir = home / ".local" / "share" / "mime" / "packages"
    app_dir  = home / ".local" / "share" / "applications"
    mime_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)

    # 1) MIME-type declaration
    gwr_mime = mime_dir / "gwr.xml"
    gwr_mime.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="text/x-gwr">
    <comment>GWAY Recipe</comment>
    <glob pattern="*.gwr"/>
  </mime-type>
</mime-info>
""")

    # 2) update the MIME database
    subprocess.run(["update-mime-database", str(home / ".local" / "share" / "mime")],
                   check=True)

    # 3) Desktop entry
    desktop_file = app_dir / "gway-recipe.desktop"
    desktop_file.write_text(f"""[Desktop Entry]
Name=GWAY Recipe
Comment=Execute GWAY recipe file
Exec=gway -r %f
Terminal=true
Type=Application
MimeType=text/x-gwr
Icon=accessories-text-editor
""")

    # 4) update desktop database (some distros)
    subprocess.run(["update-desktop-database", str(app_dir)], check=True)

    gw.info(".gwr association registered in your Linux desktop environment.")
