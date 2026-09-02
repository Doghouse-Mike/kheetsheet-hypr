import json
import subprocess


def run_hyprctl_bounded(args, max_bytes=1_000_000, timeout=2):
    """Run `hyprctl <args>` with a hard cap on stdout size and a deadline.

    Window titles/classes come from whatever app happens to be focused, not
    from anything this project controls - a hostile app could stuff an
    enormous string into a title and hyprctl would report it verbatim.
    subprocess.run's capture_output has no size limit of its own, so this
    reads via communicate() (which already bounds wall-clock time via
    `timeout`) and then rejects anything over `max_bytes` rather than
    trusting the output to stay small.
    """
    try:
        proc = subprocess.Popen(
            ["hyprctl"] + args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except Exception:
        return None
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.communicate(timeout=1)
        except Exception:
            pass
        return None
    except Exception:
        proc.kill()
        return None
    if proc.returncode != 0 or out is None:
        return None
    if len(out) > max_bytes:
        return None
    return out.decode(errors="replace")


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
    out = run_hyprctl_bounded(["-j", "activewindow"])
    if out is None:
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
