import json
import os
import shutil
import subprocess
import time


def _hypr_socket_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if not sig:
        return None
    return os.path.join(runtime, "hypr", sig, ".socket.sock")


def _hypr_command(command):
    # Hyprland's IPC on this version routes plain "dispatch <text>" through
    # an embedded Lua evaluator (`return hl.dispatch(<text>)`), not the
    # classic space-separated dispatcher syntax - confirmed by reverse-
    # engineering the real API live (see HANDOVER.md). No selector-based
    # "focus this window" dispatcher exists in it; window.cycle_next() is
    # the reliable, selector-free way to move focus.
    path = _hypr_socket_path()
    if not path:
        return None
    try:
        import socket

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(path)
            s.sendall(command.encode() + b"\n")
            return s.recv(65536).decode(errors="replace")
    except Exception:
        return None


def _active_window():
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "activewindow"], capture_output=True, text=True, timeout=2
        ).stdout
        data = json.loads(out)
        return data.get("pid"), data.get("class")
    except Exception:
        return None, None


def focus_window(target_pid, max_cycles=40):
    """Cycle focus until target_pid is the active window, or give up.

    No selector-based focus-by-pid/class dispatcher exists in this
    Hyprland version's Lua API (confirmed by introspecting it directly -
    hl.dsp.focus is direction-only). window.cycle_next() acting on
    whatever's currently focused, checked after each step, is the robust
    alternative: it needs no selector and works for any already-open
    window regardless of which workspace it's on.
    """
    pid, _ = _active_window()
    if pid == target_pid:
        return True
    for _ in range(max_cycles):
        if _hypr_command("dispatch hl.dsp.window.cycle_next()") is None:
            return False
        time.sleep(0.05)
        pid, _ = _active_window()
        if pid == target_pid:
            return True
    return False


# Linux input-event-codes.h keycodes for the handful of keys this needs.
_KEYCODES = {
    "ctrl": 29,
    "shift": 42,
    "slash": 53,
}


def synthetic_input_available():
    return shutil.which("ydotool") is not None


def window_snapshot():
    """Addresses of all current toplevel windows, per `hyprctl clients`.

    Used only to detect *whether a new window appeared* after triggering an
    app's native shortcuts overlay - never to read what's inside it. Kept
    content-blind on purpose (see HANDOVER.md session 7): this project reads
    AT-SPI content for its own panel, but the opt-in native-overlay path is
    meant to trigger the target app's own dialog and leave it alone,
    unscraped.
    """
    try:
        out = subprocess.run(
            ["hyprctl", "-j", "clients"], capture_output=True, text=True,
            timeout=2, check=True,
        ).stdout
        return {w["address"] for w in json.loads(out) if "address" in w}
    except Exception:
        return set()


def new_window_appeared(before, settle=0.4):
    """True if a window not in `before` exists after a short settle delay.

    GTK4/libadwaita's Ctrl+Shift+/ shortcuts dialog is a real toplevel
    window, so a new address showing up is a cheap way to tell "the app
    opened something" apart from "nothing happened" (e.g. the app has no
    such binding) - without caring what that something is.
    """
    time.sleep(settle)
    return len(window_snapshot() - before) > 0


def _ydotool_key(sequence):
    if not synthetic_input_available():
        return False
    try:
        subprocess.run(["ydotool", "key"] + sequence, timeout=2, check=True,
                        capture_output=True)
        return True
    except Exception:
        # Most common real-world cause: ydotoold isn't running (it's not a
        # systemd-managed service on every system - installed as a
        # dependency of unrelated tools sometimes, like voxtype here).
        # Surfaced to the caller as a plain False; TryNativeOverlay turns
        # that into a specific, honest error message rather than pretending
        # the dialog just didn't exist.
        return False


def send_key_combo(mods, key):
    """Send a real synthetic key event via ydotool (kernel-level uinput
    injection), the one action in this whole project that isn't a passive
    AT-SPI read. Only ever called from the explicit, user-triggered opt-in
    path, never automatically. Used to trigger a focused app's own native
    shortcuts overlay (commonly Ctrl+Shift+/ on GTK4/libadwaita apps) so it
    shows on screen as itself - kheetsheet does not scrape or re-render it.

    wtype (the Wayland virtual-keyboard-protocol tool) was tried first and
    is NOT used: confirmed unreliable in real testing here - it worked
    once, then failed to trigger Nautilus's shortcuts dialog on every
    repeated attempt afterward (fresh app instances, longer settle delays,
    simplified modifier sequences - nothing made it reliable again).
    ydotool's kernel-level injection worked consistently on the first try
    and every retry. Likely explanation: GTK's shortcut controller (or the
    compositor itself) treats a wlr-virtual-keyboard-protocol event as
    distinguishably synthetic in a way a real uinput event isn't - not
    confirmed against GTK/Hyprland source, just an empirical result.
    """
    codes = [_KEYCODES[m] for m in mods] + [_KEYCODES[key]]
    press = [f"{c}:1" for c in codes]
    release = [f"{c}:0" for c in reversed(codes)]
    return _ydotool_key(press + release)
