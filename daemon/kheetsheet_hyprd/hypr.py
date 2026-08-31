import json
import subprocess


def get_active_window():
    """Return (pid, app_id) for Hyprland's currently focused toplevel window.

    Queried synchronously, on demand, rather than tracked continuously: a
    Quickshell layer-shell overlay (like this project's own plugin) never
    appears in `hyprctl clients` and never becomes `activewindow` even while
    it holds exclusive keyboard focus - confirmed live against an existing
    Omarchy overlay plugin (Keysmith) before relying on it here. So there is
    no risk of this query racing against our own overlay opening, and no
    need for a KWin-script-style push watcher at all.
    """
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "activewindow"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout
    except Exception:
        return None, None
    try:
        data = json.loads(out)
    except Exception:
        return None, None
    pid = data.get("pid")
    app_id = data.get("class")
    if not pid or pid < 0:
        return None, app_id
    return pid, app_id
