import json
import sys
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from .hypr import get_active_window
from .native_overlay import (
    focus_window,
    send_key_combo,
    synthetic_input_available,
    window_snapshot,
)
from .service import (
    CONFIG_PATH,
    ensure_accessibility_enabled,
    has_dialog_descendant,
    invoke_shortcut,
    make_session_token,
    shortcuts_for_pid,
    token_still_valid,
)
from .terminal_shortcuts import (
    TERMINAL_KEYMAPS,
    find_descendant_tool,
    is_known_terminal_class,
)

BUS_NAME = "com.kheetsheet.Daemon"
OBJECT_PATH = "/KheetSheet"
IFACE = "com.kheetsheet.Daemon"


class KheetSheetService(dbus.service.Object):
    def __init__(self, bus_name):
        super().__init__(bus_name, OBJECT_PATH)
        # Index-addressable cache of the accessible objects behind the last
        # GetShortcuts() call, so InvokeShortcut(i) can call back into the
        # real widget across the D-Bus boundary between this daemon and the
        # QML overlay process, the same way upstream's in-process PyQt6
        # overlay holds onto the accessible refs it got from collect_shortcuts.
        # A `None` entry means "not a real AT-SPI action" (the terminal
        # builtin-keymap fallback) - invoke_shortcut(None) safely no-ops.
        self._last_accessibles = []
        # Remembered so the opt-in native-overlay path (triggered later, by
        # a button click, well after the focused app may have changed) still
        # knows which app to go back to.
        self._last_pid = None
        self._last_app_id = None
        # Short-lived, single-use capability minted by GetShortcuts() and
        # required by InvokeShortcut/TryNativeOverlay - see _consume_token.
        # Neither the D-Bus session-bus name nor the object path is secret,
        # so without this, any process on the same session bus could invoke
        # whatever's cached here, or fire a synthetic keypress, at a moment
        # of its own choosing.
        self._session = {"token": None, "pid": None, "created": 0.0}

    def _consume_token(self, token):
        # "Current target identity" is enforced structurally, not by a live
        # recheck here: both callers act on what was *recorded* at
        # GetShortcuts() time (self._last_accessibles / self._last_pid), not
        # on whatever happens to be focused right this instant. A live
        # get_active_window() recheck was tried here and removed - closing
        # the panel (Kheetsheet.qml releases exclusive keyboard focus right
        # before firing this call) races the compositor's focus handoff back
        # to the real target, so the recheck could see a transient
        # not-yet-settled focus and reject almost every real click, for no
        # actual security benefit the token+ttl+single-use already lacked.
        now = time.monotonic()
        if not token_still_valid(self._session, token, now):
            return False
        # Single-use: a successful check burns the token immediately, before
        # the caller's actual side effect runs.
        self._session["token"] = None
        return True

    @dbus.service.method(IFACE, in_signature="", out_signature="s")
    def GetShortcuts(self):
        pid, app_id = get_active_window()
        self._last_pid, self._last_app_id = pid, app_id
        self._session = {
            "token": make_session_token(),
            "pid": pid,
            "created": time.monotonic(),
        }
        if pid is None:
            self._last_accessibles = []
            return json.dumps({"app": None, "items": [], "token": self._session["token"]})

        app_name, shortcuts = shortcuts_for_pid(pid, app_id)
        self._last_accessibles = [s[3] for s in shortcuts]
        items = [
            {"group": group, "label": label, "key": key}
            for (group, label, key, _accessible) in shortcuts
        ]

        source = None
        if not items and is_known_terminal_class(app_id):
            # Structural blind spot, not a bug: AT-SPI has nothing to say
            # about what's running inside a terminal. Narrow, hardcoded
            # fallback for the two cases explicitly approved for this (see
            # terminal_shortcuts.py) - never runs when the AT-SPI path
            # already found something real.
            tool = find_descendant_tool(pid)
            if tool and tool in TERMINAL_KEYMAPS:
                items = [
                    {"group": group, "label": label, "key": key}
                    for (group, label, key) in TERMINAL_KEYMAPS[tool]
                ]
                self._last_accessibles = [None] * len(items)
                app_name = app_name or app_id
                source = "builtin"

        payload = {"app": app_name or app_id, "items": items, "token": self._session["token"]}
        if source:
            payload["source"] = source
        return json.dumps(payload)

    @dbus.service.method(IFACE, in_signature="si", out_signature="b")
    def InvokeShortcut(self, token, index):
        if not self._consume_token(token):
            return False
        if index < 0 or index >= len(self._last_accessibles):
            return False
        return invoke_shortcut(self._last_accessibles[index])

    @dbus.service.method(IFACE, in_signature="s", out_signature="s")
    def TryNativeOverlay(self, token):
        # Explicit, user-triggered only (see HANDOVER.md for the full
        # reasoning) - this is the one path in the whole project that
        # injects real synthetic input rather than only reading AT-SPI.
        # Never called from GetShortcuts/automatically.
        #
        # This only triggers the focused app's own shortcuts overlay so it
        # shows on screen as itself - it deliberately does not scrape or
        # re-render it. Kheetsheet's own panel is expected to have hidden
        # itself before this is called (see Kheetsheet.qml's
        # tryNativeOverlay()), so the synthetic keypress reaches the target
        # app instead of being swallowed here.
        # `error` stays plain English throughout - it's a debugging aid
        # (visible in journalctl) and a last-resort fallback for a QML build
        # too old to recognize `error_code`. `error_code` is the stable,
        # locale-independent value the QML side actually displays (see
        # Kheetsheet.qml's resolveDaemonError() / i18n.js) - never add a
        # translated string here, that would defeat the point.
        if not self._consume_token(token):
            return json.dumps({
                "app": self._last_app_id, "ok": False,
                "error": "this request is no longer valid - reopen the panel and try again",
                "error_code": "invalid_session",
            })

        pid, app_id = self._last_pid, self._last_app_id
        if pid is None:
            return json.dumps({
                "app": None, "ok": False,
                "error": "no active window known", "error_code": "no_active_window",
            })
        if not synthetic_input_available():
            return json.dumps({
                "app": app_id, "ok": False,
                "error": "ydotool isn't installed - can't send the native shortcut combo",
                "error_code": "ydotool_missing",
            })

        if not focus_window(pid):
            return json.dumps({
                "app": app_id, "ok": False,
                "error": "couldn't refocus the original window (it may have closed)",
                "error_code": "refocus_failed",
            })

        before_windows = window_snapshot()
        # Content-blind presence check, not a scrape: some apps (confirmed:
        # Nautilus on GNOME 50+) now present this dialog as an in-window
        # AdwDialog rather than a separate toplevel window, so a
        # hyprctl-clients window diff alone can never see it - only whether
        # an AT-SPI dialog-role node exists, never what's inside it.
        before_dialog = has_dialog_descendant(pid, app_id)
        if not send_key_combo(["ctrl", "shift"], "slash"):
            return json.dumps({
                "app": app_id, "ok": False,
                "error": "failed to send the synthetic key combo (is ydotoold running?)",
                "error_code": "send_failed",
            })
        time.sleep(0.4)
        new_window = len(window_snapshot() - before_windows) > 0
        new_dialog = has_dialog_descendant(pid, app_id) and not before_dialog
        if not (new_window or new_dialog):
            # The keypress went out fine, but nothing new showed up on
            # screen - most likely this app just has no shortcuts overlay
            # of its own bound to Ctrl+Shift+/. Reported as ok:True (the
            # send itself didn't fail) with shown:False so the caller can
            # tell "nothing to display" apart from a real error.
            return json.dumps({
                "app": app_id, "ok": True, "shown": False,
                "error": f"{app_id} doesn't seem to have its own shortcuts overlay",
                "error_code": "no_native_overlay",
            })
        return json.dumps({"app": app_id, "ok": True, "shown": True})


def main():
    DBusGMainLoop(set_as_default=True)
    if not ensure_accessibility_enabled():
        print(
            "kheetsheet-hyprd: accessibility consent not granted "
            f"(see {CONFIG_PATH}) - run install.sh again to grant it. Exiting.",
            file=sys.stderr,
        )
        return 0

    bus = dbus.SessionBus()
    bus_name = dbus.service.BusName(BUS_NAME, bus)
    KheetSheetService(bus_name)

    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
