import json
import os
import re
import secrets

import dbus
import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

# Ported near-verbatim from upstream kheetsheet's daemon/service.py
# (https://github.com/Doghouse-Mike/kheetsheet) - this module is entirely
# compositor-independent: it only ever talks to AT-SPI over D-Bus, never to
# KWin or Hyprland. The only thing upstream keeps here that we don't is
# ensure_kwin_script_loaded, which lives in kheetsheet_hyprd.hypr instead as
# a synchronous hyprctl query, not a push-based watcher.

A11Y_STATUS_BUS = "org.a11y.Bus"
A11Y_STATUS_PATH = "/org/a11y/bus"
A11Y_STATUS_IFACE = "org.a11y.Status"

CONFIG_PATH = os.path.expanduser("~/.config/kheetsheet-hypr/config.json")
CONFIG_MAX_BYTES = 1_000_000

# Bounds on what a single collect_shortcuts() call will walk/keep - AT-SPI
# tree shape and strings come from whatever app happens to be focused, not
# from anything this project controls, so none of these are trusted to stay
# small on their own.
MAX_DESKTOP_CHILDREN = 500
MAX_CHILDREN_PER_NODE = 500
MAX_SHORTCUTS = 1000
MAX_STRING_LEN = 300

SESSION_TOKEN_TTL = 20.0

MENU_ROLES = {"menu", "menu item", "check menu item", "radio menu item"}
MENU_BAR_ROLE = "menu bar"

_GTK_MODIFIER_LABELS = {
    "control": "Ctrl",
    "primary": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "super": "Super",
    "meta": "Meta",
}
_GTK_MODIFIER_TAG = re.compile(r"<(\w+)>")


def _normalize_key_binding(raw):
    if not raw:
        return None
    if ";" not in raw:
        # Qt/KDE apps' ATK-adjacent bridge already returns a clean,
        # human-readable string (e.g. "Ctrl+N") - nothing to parse.
        return raw
    # GTK/ATK's format is "mnemonic;menu-path;accelerator", three fields
    # meant to be parsed rather than displayed verbatim. Only the third
    # field is a real, always-available keyboard shortcut - the other two
    # are Alt-driven menu-navigation aids. Dynamic, non-command menu items
    # (browsing history entries, bookmark lists, ...) share the same
    # "menu item" role as real commands but have no accelerator at all, so
    # requiring a non-empty third field also filters those out.
    parts = raw.split(";")
    accel = parts[2] if len(parts) >= 3 else ""
    if not accel:
        return None
    mods = _GTK_MODIFIER_TAG.findall(accel)
    remainder = _GTK_MODIFIER_TAG.sub("", accel)
    labels = [_GTK_MODIFIER_LABELS.get(mod.lower(), mod) for mod in mods]
    if remainder:
        labels.append(remainder.upper() if len(remainder) == 1 else remainder)
    return "+".join(labels)


def _read_config():
    try:
        if os.path.islink(CONFIG_PATH) or not os.path.isfile(CONFIG_PATH):
            return {}
        with open(CONFIG_PATH) as f:
            data = f.read(CONFIG_MAX_BYTES + 1)
        if len(data) > CONFIG_MAX_BYTES:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def accessibility_consent_granted():
    return bool(_read_config().get("a11y_consent"))


def ensure_accessibility_enabled():
    # install.sh is where consent is actually requested (writes CONFIG_PATH) -
    # this only ever flips the real, system-wide a11y switch on if that
    # consent was already given. A missing/absent config means "not asked
    # yet", not "enable anyway".
    if not accessibility_consent_granted():
        return False
    bus = dbus.SessionBus()
    obj = bus.get_object(A11Y_STATUS_BUS, A11Y_STATUS_PATH)
    props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    if not bool(props.Get(A11Y_STATUS_IFACE, "IsEnabled")):
        props.Set(A11Y_STATUS_IFACE, "IsEnabled", True)
    return True


def make_session_token():
    return secrets.token_hex(16)


def token_still_valid(session, token, now, ttl=SESSION_TOKEN_TTL):
    if not session or not token:
        return False
    if session.get("token") != token:
        return False
    if now - session.get("created", 0) > ttl:
        return False
    return True


def find_app_node_by_pid(pid, app_id=None):
    # Flatpak-sandboxed apps route their D-Bus traffic through a per-instance
    # xdg-dbus-proxy process, so AT-SPI ends up reporting a different pid for
    # the same window than Hyprland does (the proxy's pid, not the real
    # app's), and they're not parent/child of each other, so there's no
    # reliable way to translate one into the other. An exact pid match is
    # still tried first since it's precise and unaffected for normal (non-
    # sandboxed) apps, but when it fails, fall back to a loose match between
    # the AT-SPI app's own name and the window's class - good enough to
    # recover Flatpak apps that would otherwise never be found.
    # Some apps (confirmed: Okular) register two AT-SPI application objects
    # under the *same* pid at once - one real (a window frame as its child)
    # and one an empty stub with zero children. Which one AT-SPI happens to
    # enumerate first isn't something callers control, so an exact pid match
    # is not enough on its own: among pid matches, prefer one that actually
    # has children over one that doesn't, rather than returning on the first
    # hit and risking a coin-flip "no shortcuts found".
    desktop = Atspi.get_desktop(0)
    normalized_app_id = app_id.strip().lower() if app_id else None
    pid_match = None
    fallback = None
    try:
        desktop_count = min(desktop.get_child_count(), MAX_DESKTOP_CHILDREN)
    except Exception:
        desktop_count = 0
    for i in range(desktop_count):
        app = desktop.get_child_at_index(i)
        try:
            if app.get_process_id() == pid:
                try:
                    has_children = app.get_child_count() > 0
                except Exception:
                    has_children = False
                if has_children:
                    return app
                if pid_match is None:
                    pid_match = app
        except Exception:
            pass
        if fallback is None and normalized_app_id:
            try:
                name = (app.get_name() or "").strip().lower()
            except Exception:
                continue
            if name and (name in normalized_app_id or normalized_app_id in name):
                fallback = app
    return pid_match or fallback


DIALOG_ROLE = "dialog"
MAX_DIALOG_SCAN_NODES = 2000


def _has_dialog_node(acc, depth, budget):
    if depth > 15 or budget[0] <= 0:
        return False
    budget[0] -= 1
    try:
        role = acc.get_role_name()
    except Exception:
        return False
    if role == DIALOG_ROLE:
        return True
    try:
        child_count = min(acc.get_child_count(), MAX_CHILDREN_PER_NODE)
    except Exception:
        return False
    for j in range(child_count):
        if budget[0] <= 0:
            return False
        try:
            child = acc.get_child_at_index(j)
        except Exception:
            continue
        if _has_dialog_node(child, depth + 1, budget):
            return True
    return False


def has_dialog_descendant(pid, app_id=None):
    """Content-blind presence check: does this app's AT-SPI tree currently
    contain any dialog-role node? Never reads names/labels, only role -
    used to detect a native shortcuts-overlay dialog for apps (confirmed:
    Nautilus on GNOME 50+) that present it as an in-window AdwDialog rather
    than a separate toplevel window, where a hyprctl-clients window diff
    can never see it. Bounded the same way as collect_shortcuts (depth,
    per-node child count, total nodes visited) since the tree shape isn't
    trusted to stay small.
    """
    try:
        app_node = find_app_node_by_pid(pid, app_id=app_id)
        if app_node is None:
            return False
        return _has_dialog_node(app_node, 0, [MAX_DIALOG_SCAN_NODES])
    except Exception:
        return False


def collect_shortcuts(app_node, max_depth=15):
    # KDE/Qt menu bars expose top-level entries (File, Edit, ...) as direct
    # children of the window, with the same "menu item" role as their
    # descendants - there is no separate "menu" container node to key off of.
    shortcuts = []

    def walk(acc, group, depth):
        if depth > max_depth or len(shortcuts) >= MAX_SHORTCUTS:
            return
        try:
            role = acc.get_role_name()
            name = acc.get_name()
        except Exception:
            return

        if role in MENU_ROLES and name and group is not None:
            try:
                key_binding = _normalize_key_binding(acc.get_key_binding(0))
            except Exception:
                key_binding = None
            if key_binding:
                shortcuts.append((
                    group[:MAX_STRING_LEN],
                    name[:MAX_STRING_LEN],
                    key_binding[:MAX_STRING_LEN],
                    acc,
                ))

        try:
            child_count = min(acc.get_child_count(), MAX_CHILDREN_PER_NODE)
        except Exception:
            return
        for j in range(child_count):
            if len(shortcuts) >= MAX_SHORTCUTS:
                return
            try:
                child = acc.get_child_at_index(j)
            except Exception:
                continue
            walk(child, group, depth + 1)

    def find_menu_bars(acc, depth):
        if depth > max_depth:
            return
        try:
            role = acc.get_role_name()
            child_count = min(acc.get_child_count(), MAX_CHILDREN_PER_NODE)
        except Exception:
            return
        if role == MENU_BAR_ROLE:
            for j in range(child_count):
                try:
                    top_menu = acc.get_child_at_index(j)
                    top_name = top_menu.get_name()
                    top_role = top_menu.get_role_name()
                except Exception:
                    continue
                if top_role not in MENU_ROLES or not top_name:
                    continue
                try:
                    sub_count = min(top_menu.get_child_count(), MAX_CHILDREN_PER_NODE)
                except Exception:
                    continue
                for k in range(sub_count):
                    if len(shortcuts) >= MAX_SHORTCUTS:
                        return
                    try:
                        sub_child = top_menu.get_child_at_index(k)
                    except Exception:
                        continue
                    walk(sub_child, top_name[:MAX_STRING_LEN], 0)
            return
        for j in range(child_count):
            try:
                child = acc.get_child_at_index(j)
            except Exception:
                continue
            find_menu_bars(child, depth + 1)

    find_menu_bars(app_node, 0)
    return shortcuts


_ACTIVATING_ACTION_NAMES = ("press", "click", "activate")


def invoke_shortcut(accessible):
    # Menu items consistently expose a single "Press" action in testing, but
    # other widget types can expose several (e.g. a button with "SetFocus"
    # at index 0 and "Press" at index 1) - searching by name rather than
    # assuming index 0 is what actually triggers the item's real handler
    # avoids just focusing something instead of activating it.
    try:
        count = accessible.get_n_actions()
    except Exception:
        return False
    action_index = 0
    for i in range(count):
        try:
            if accessible.get_action_name(i).lower() in _ACTIVATING_ACTION_NAMES:
                action_index = i
                break
        except Exception:
            continue
    try:
        accessible.do_action(action_index)
        return True
    except Exception:
        return False


def shortcuts_for_pid(pid, app_id=None):
    app_node = find_app_node_by_pid(pid, app_id=app_id)
    if app_node is None:
        return None, []
    try:
        app_name = app_node.get_name()
    except Exception:
        app_name = None
    return app_name, collect_shortcuts(app_node)
