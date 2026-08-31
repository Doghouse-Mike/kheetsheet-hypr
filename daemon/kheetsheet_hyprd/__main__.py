import json
import sys

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from .hypr import get_active_window
from .native_overlay import focus_window, send_key_combo, synthetic_input_available
from .service import ensure_accessibility_enabled, invoke_shortcut, shortcuts_for_pid

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
        self._last_accessibles = []
        # Remembered so the opt-in native-overlay path (triggered later, by
        # a button click, well after the focused app may have changed) still
        # knows which app to go back to.
        self._last_pid = None
        self._last_app_id = None

    @dbus.service.method(IFACE, in_signature="", out_signature="s")
    def GetShortcuts(self):
        pid, app_id = get_active_window()
        self._last_pid, self._last_app_id = pid, app_id
        if pid is None:
            self._last_accessibles = []
            return json.dumps({"app": None, "items": []})

        app_name, shortcuts = shortcuts_for_pid(pid, app_id)
        self._last_accessibles = [s[3] for s in shortcuts]
        items = [
            {"group": group, "label": label, "key": key}
            for (group, label, key, _accessible) in shortcuts
        ]
        return json.dumps({"app": app_name or app_id, "items": items})

    @dbus.service.method(IFACE, in_signature="i", out_signature="b")
    def InvokeShortcut(self, index):
        if index < 0 or index >= len(self._last_accessibles):
            return False
        return invoke_shortcut(self._last_accessibles[index])

    @dbus.service.method(IFACE, in_signature="", out_signature="s")
    def TryNativeOverlay(self):
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
        pid, app_id = self._last_pid, self._last_app_id
        if pid is None:
            return json.dumps({"app": None, "ok": False, "error": "no active window known"})
        if not synthetic_input_available():
            return json.dumps({
                "app": app_id, "ok": False,
                "error": "ydotool isn't installed - can't send the native shortcut combo",
            })

        if not focus_window(pid):
            return json.dumps({
                "app": app_id, "ok": False,
                "error": "couldn't refocus the original window (it may have closed)",
            })

        send_key_combo(["ctrl", "shift"], "slash")
        return json.dumps({"app": app_id, "ok": True})


def main():
    DBusGMainLoop(set_as_default=True)
    ensure_accessibility_enabled()

    bus = dbus.SessionBus()
    bus_name = dbus.service.BusName(BUS_NAME, bus)
    KheetSheetService(bus_name)

    GLib.MainLoop().run()


if __name__ == "__main__":
    sys.exit(main())
