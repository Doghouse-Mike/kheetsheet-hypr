#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="doghouse-mike.kheetsheet"
SERVICE_NAME="kheetsheet-hypr-daemon.service"
PLUGIN_DEST="$HOME/.config/omarchy/plugins/$PLUGIN_ID"
DAEMON_DEST="$HOME/.local/share/kheetsheet-hypr/daemon"
CONFIG_DIR="$HOME/.config/kheetsheet-hypr"
CONFIG_FILE="$CONFIG_DIR/config.json"
SHELL_JSON="$HOME/.config/omarchy/shell.json"
UNIT_DEST="$HOME/.config/systemd/user/$SERVICE_NAME"

MODE="install"
if [ $# -gt 0 ]; then
    if [ "$1" = "--uninstall" ]; then
        MODE="uninstall"
    else
        echo "Usage: $0 [--uninstall]" >&2
        exit 1
    fi
fi

# --- shared helpers --------------------------------------------------------

# Removes leftovers from a previous interrupted run (restoring a ".bak" back
# to the live path if a swap didn't finish) so re-running this script, or
# recovering from a failed one, is always safe. Registered as an EXIT trap
# below, so it also acts as this installer's rollback: if anything later
# fails mid-run, whatever swap was in flight gets put back rather than left
# half-done.
cleanup_stale() {
    rm -rf "$PLUGIN_DEST.new" "$DAEMON_DEST.new"
    if [ -d "$PLUGIN_DEST.bak" ]; then
        [ -e "$PLUGIN_DEST" ] || mv "$PLUGIN_DEST.bak" "$PLUGIN_DEST"
        rm -rf "$PLUGIN_DEST.bak"
    fi
    if [ -d "$DAEMON_DEST.bak" ]; then
        [ -e "$DAEMON_DEST" ] || mv "$DAEMON_DEST.bak" "$DAEMON_DEST"
        rm -rf "$DAEMON_DEST.bak"
    fi
}
trap cleanup_stale EXIT

# Swaps a fully-staged "$dest.new" (populated by the caller) into place.
# Never deletes the live "$dest" until the replacement already exists on
# disk under a different name, so a project checked out *at* "$dest" itself
# (the marketplace-clone case) is never read from after it's gone - by the
# time it's removed, everything needed from it is already copied elsewhere.
swap_into_place() {
    local dest="$1"
    if [ -e "$dest" ]; then
        mv "$dest" "$dest.bak"
    fi
    mv "$dest.new" "$dest"
    rm -rf "$dest.bak"
}

a11y_is_enabled() {
    busctl --user get-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled 2>/dev/null \
        | grep -q '^b true$'
}

a11y_set_enabled() {
    busctl --user set-property org.a11y.Bus /org/a11y/bus org.a11y.Status IsEnabled b "$1" >/dev/null 2>&1 || true
}

# Atomic, symlink-safe, mode-preserving write: refuses to write through a
# symlink or over a non-regular file, writes to a temp file in the same
# directory, fsyncs it, then os.replace()s it into place - which unlinks
# the destination name rather than following it, so this is still safe even
# if something planted a symlink at $1 between the check and the write.
atomic_write() {
    local dest="$1" content_path="$2"
    python3 - "$dest" "$content_path" <<'PYEOF'
import os
import stat
import sys
import tempfile

dest, content_path = sys.argv[1], sys.argv[2]
with open(content_path, "rb") as f:
    content = f.read()

mode = 0o644
if os.path.exists(dest):
    if os.path.islink(dest):
        print(f"Refusing to write through symlink: {dest}", file=sys.stderr)
        sys.exit(1)
    if not os.path.isfile(dest):
        print(f"Refusing to overwrite non-regular file: {dest}", file=sys.stderr)
        sys.exit(1)
    mode = stat.S_IMODE(os.stat(dest).st_mode)

dest_dir = os.path.dirname(dest) or "."
os.makedirs(dest_dir, exist_ok=True)
fd, tmp_path = tempfile.mkstemp(dir=dest_dir, prefix=".kheetsheet-tmp-")
try:
    with os.fdopen(fd, "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, dest)
except Exception:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
PYEOF
}

# Adds/removes the plugin's entry in shell.json. $1 is "add" or "remove".
update_shell_json() {
    local action="$1"
    if [ ! -f "$SHELL_JSON" ] || [ -L "$SHELL_JSON" ]; then
        if [ "$action" = "add" ]; then
            echo "Refusing to touch $SHELL_JSON (missing, or a symlink)." >&2
            exit 1
        fi
        return 0
    fi
    local scratch
    scratch="$(mktemp)"
    python3 - "$SHELL_JSON" "$PLUGIN_ID" "$scratch" "$action" <<'PYEOF'
import json
import sys

path, plugin_id, scratch_path, action = sys.argv[1:5]
MAX_BYTES = 5 * 1024 * 1024

with open(path, "r") as f:
    raw = f.read(MAX_BYTES + 1)
if len(raw) > MAX_BYTES:
    print(f"{path} is larger than expected ({MAX_BYTES} bytes) - refusing to touch it", file=sys.stderr)
    sys.exit(1)

config = json.loads(raw)
plugins = config.get("plugins", [])

if action == "add":
    if not any(p.get("id") == plugin_id for p in plugins):
        config["plugins"] = plugins + [{"id": plugin_id}]
        with open(scratch_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        print(f"  Added {plugin_id} to shell.json")
    else:
        with open(scratch_path, "w") as f:
            f.write(raw)
        print(f"  {plugin_id} already present in shell.json")
else:
    new_plugins = [p for p in plugins if p.get("id") != plugin_id]
    if new_plugins != plugins:
        config["plugins"] = new_plugins
        with open(scratch_path, "w") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        print(f"  Removed {plugin_id} from shell.json")
    else:
        with open(scratch_path, "w") as f:
            f.write(raw)
PYEOF
    atomic_write "$SHELL_JSON" "$scratch"
    rm -f "$scratch"
}

# --- uninstall --------------------------------------------------------------

uninstall() {
    echo "==> Stopping and removing the systemd user service..."
    systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$UNIT_DEST"
    systemctl --user daemon-reload 2>/dev/null || true

    echo "==> Removing plugin and daemon files..."
    rm -rf "$PLUGIN_DEST" "$DAEMON_DEST"
    rmdir "$(dirname "$DAEMON_DEST")" 2>/dev/null || true

    echo "==> Removing plugin entry from shell.json..."
    update_shell_json remove

    echo "==> Reloading the Omarchy shell's plugin list..."
    omarchy-shell -q shell rescanPlugins 2>/dev/null || true

    if [ -f "$CONFIG_FILE" ] && [ ! -L "$CONFIG_FILE" ]; then
        was_enabled_before="$(python3 -c "
import json, sys
try:
    print('true' if json.load(open(sys.argv[1])).get('a11y_was_enabled_before_install') else 'false')
except Exception:
    print('unknown')
" "$CONFIG_FILE" 2>/dev/null || echo unknown)"

        if [ "$was_enabled_before" = "false" ]; then
            read -r -p "Disable system accessibility (AT-SPI) now, since kheetsheet was the one that turned it on? [y/N] " reply
            case "$reply" in
                [yY]|[yY][eE][sS])
                    a11y_set_enabled false
                    echo "  Accessibility disabled."
                    ;;
                *)
                    echo "  Leaving accessibility enabled."
                    ;;
            esac
        else
            echo "==> Leaving system accessibility as-is (already enabled by something else before kheetsheet's install, or unknown)."
        fi
        rm -f "$CONFIG_FILE"
    fi
    rmdir "$CONFIG_DIR" 2>/dev/null || true

    cat <<EOF

==> Uninstall complete.

If you added a keybind for this in ~/.config/hypr/bindings.lua, remove that
o.bind(...) line yourself and run 'hyprctl reload'.
EOF
}

# --- install ------------------------------------------------------------

require_deps() {
    echo "==> Checking dependencies..."
    missing=()
    python3 -c "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi" 2>/dev/null || missing+=("python-gobject + AT-SPI typelib (at-spi2-core)")
    python3 -c "import dbus" 2>/dev/null || missing+=("python-dbus")
    command -v hyprctl >/dev/null 2>&1 || missing+=("hyprctl (part of Hyprland)")
    command -v busctl >/dev/null 2>&1 || missing+=("busctl (part of systemd)")
    command -v omarchy-shell >/dev/null 2>&1 || missing+=("omarchy-shell (part of Omarchy)")

    if [ ${#missing[@]} -ne 0 ]; then
        echo "Missing dependencies, install these and re-run:"
        printf '  - %s\n' "${missing[@]}"
        exit 1
    fi

    # Optional, soft-checked: only needed for the opt-in "try this app's own
    # shortcuts overlay" fallback (TryNativeOverlay), never for the core
    # AT-SPI path. Not installed by this script - ydotoold in particular
    # often comes from an unrelated tool (e.g. voxtype) rather than being a
    # normal Omarchy default, so its absence shouldn't block installing
    # everything else.
    if ! command -v ydotool >/dev/null 2>&1; then
        echo "Note: ydotool not found - the opt-in \"try this app's own shortcuts"
        echo "  overlay\" fallback won't be available (everything else will work fine)."
        echo "  Whether ydotoold is actually running is checked at runtime instead,"
        echo "  since it's commonly started by other tools rather than at boot."
    fi
}

consent_a11y() {
    local was_enabled="false"
    if a11y_is_enabled; then
        was_enabled="true"
    fi

    echo
    echo "kheetsheet's daemon enables system accessibility (AT-SPI) session-wide"
    echo "every time it starts - the same interface screen readers use. Once on,"
    echo "any AT-SPI-aware app or tool on your session can read other apps'"
    echo "accessibility trees, not just kheetsheet. It stays on until you log"
    echo "out, reboot, or explicitly turn it off ('$0 --uninstall' offers to,"
    echo "if kheetsheet was the one that turned it on)."
    echo
    read -r -p "Enable accessibility and continue installing? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted - nothing was changed."; exit 1 ;;
    esac

    mkdir -p "$CONFIG_DIR"
    local scratch
    scratch="$(mktemp)"
    python3 - "$scratch" "$was_enabled" <<'PYEOF'
import json
import sys

path, was_enabled = sys.argv[1], sys.argv[2]
with open(path, "w") as f:
    json.dump({
        "a11y_consent": True,
        "a11y_was_enabled_before_install": was_enabled == "true",
    }, f)
PYEOF
    atomic_write "$CONFIG_FILE" "$scratch"
    rm -f "$scratch"
}

install() {
    require_deps
    consent_a11y

    echo "==> Staging plugin files..."
    rm -rf "$PLUGIN_DEST.new"
    mkdir -p "$PLUGIN_DEST.new"
    cp "$PROJECT_DIR/manifest.json" "$PROJECT_DIR/Kheetsheet.qml" "$PROJECT_DIR/i18n.js" "$PLUGIN_DEST.new/"

    echo "==> Staging daemon..."
    rm -rf "$DAEMON_DEST.new"
    mkdir -p "$(dirname "$DAEMON_DEST")"
    cp -a "$PROJECT_DIR/daemon" "$DAEMON_DEST.new"

    # Everything above reads only from $PROJECT_DIR and writes only to the
    # sibling ".new" paths - $PLUGIN_DEST/$DAEMON_DEST themselves aren't
    # touched yet. That's what makes this safe even when $PROJECT_DIR *is*
    # $PLUGIN_DEST (installing straight from a marketplace clone): by the
    # time the swap below removes the old directory, nothing further needs
    # to be read from it.
    echo "==> Installing plugin and daemon..."
    mkdir -p "$(dirname "$PLUGIN_DEST")"
    swap_into_place "$PLUGIN_DEST"
    swap_into_place "$DAEMON_DEST"

    echo "==> Enabling plugin in shell.json..."
    update_shell_json add

    echo "==> Installing systemd user service..."
    local unit_scratch
    unit_scratch="$(mktemp)"
    python3 - "$PROJECT_DIR/systemd/kheetsheet-hypr-daemon.service" "$DAEMON_DEST" "$unit_scratch" <<'PYEOF'
import sys

template_path, daemon_dest, scratch_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(template_path, "r") as f:
    template = f.read()
# Plain literal replacement, not sed: DAEMON_DEST is a fixed path under
# $HOME this script controls, but a regex-based substitution (sed) would
# still mishandle metacharacters in it for no benefit.
rendered = template.replace("__DAEMON_DIR__", daemon_dest)
with open(scratch_path, "w") as f:
    f.write(rendered)
PYEOF
    mkdir -p "$HOME/.config/systemd/user"
    atomic_write "$UNIT_DEST" "$unit_scratch"
    rm -f "$unit_scratch"
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user restart "$SERVICE_NAME"

    echo "==> Reloading the Omarchy shell's plugin list..."
    omarchy-shell -q shell rescanPlugins || true

    cat <<EOF

==> Install complete.

The daemon and plugin now live under $DAEMON_DEST and $PLUGIN_DEST - this
checkout ($PROJECT_DIR) can be deleted (or left alone) from here on, install.sh
no longer depends on it after this point.

Try it now:
  omarchy-shell shell toggle $PLUGIN_ID '{}'

One manual step remains: binding a hotkey. There's no single default key
that's safe on every Omarchy install - "SUPER + SLASH" and "SUPER + SHIFT +
SLASH" were both already taken by other plugins on the Omarchy setup this
was developed against (monitor scaling, and a password manager's default
bind, respectively), and Omarchy's own default bindings differ by version
and by which plugins you have installed. "SUPER + CTRL + SLASH" was free
there, for what that's worth. Pick a free key, then add one line to
~/.config/hypr/bindings.lua:

  o.bind("<YOUR KEY>", "Kheetsheet", "omarchy-shell shell toggle $PLUGIN_ID '{}'")

Run \`omarchy menu keybindings --print\` first to see what's already taken.
Then \`hyprctl reload\` to apply it.

To remove everything this installed: $0 --uninstall
EOF
}

cleanup_stale
if [ "$MODE" = "uninstall" ]; then
    uninstall
else
    install
fi
