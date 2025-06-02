# projects/gui.py

from gway import gw


def notify(message, *, title="GWAY Notice", timeout=8):
    """Show a user interface notification with the specified title and message."""
    from plyer import notification

    try:
        notification.notify(
            title=title, message=message, app_name="gway", timeout=timeout)
        gw.info(f"Notification: {title} - {message}")
    except Exception as e:
        gw.critical(f"Error displaying: {str(e)}")
        raise


def lookup_font(*prefix):
    """Look up fonts installed on a Windows system by partial name (prefix).
    >> gsol font lookup Ari
    """
    import winreg
    font_prefix = " ".join(prefix)

    try:
        font_key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, font_key_path) as font_key:
            num_values = winreg.QueryInfoKey(font_key)[1]
            matching_fonts = []

            prefix_lower = font_prefix.lower()
            for i in range(num_values):
                value_name, value_data, _ = winreg.EnumValue(font_key, i)
                name_only = value_name.split(" (")[0].strip()

                if prefix_lower in name_only.lower() or prefix_lower in value_data.lower():
                    matching_fonts.append(f"{name_only} -> {value_data}")

            return matching_fonts if matching_fonts else [f"No match for prefix: {font_prefix}"]

    except Exception as e:
        return [f"Error: {str(e)}"]
