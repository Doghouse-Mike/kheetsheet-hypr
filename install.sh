#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="doghouse-mike.kheetsheet"
SERVICE_NAME="kheetsheet-hypr-daemon.service"
PLUGIN_DEST="$HOME/.config/omarchy/plugins/$PLUGIN_ID"
SHELL_JSON="$HOME/.config/omarchy/shell.json"

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
# AT-SPI path. Not installed by this script - ydotoold in particular often
# comes from an unrelated tool (e.g. voxtype) rather than being a normal
# Omarchy default, so its absence shouldn't block installing everything
# else.
if ! command -v ydotool >/dev/null 2>&1; then
    echo "Note: ydotool not found - the opt-in \"try this app's own shortcuts"
    echo "  overlay\" fallback won't be available (everything else will work fine)."
    echo "  Whether ydotoold is actually running is checked at runtime instead,"
    echo "  since it's commonly started by other tools rather than at boot."
fi

echo "==> Installing plugin..."
# A symlink here is NOT enough: confirmed during development that Omarchy's
# shell plugin scanner enumerates ~/.config/omarchy/plugins/*/ but something
# in that path (glob expansion or a later realpath-sensitive check) silently
# excludes a symlinked plugin directory from ever actually opening, with no
# error anywhere - it shows up as "installed" and "enabled" in every
# introspection command, but its Loader never activates. A real copy works.
rm -rf "$PLUGIN_DEST"
mkdir -p "$PLUGIN_DEST"
cp "$PROJECT_DIR/manifest.json" "$PROJECT_DIR/Kheetsheet.qml" "$PLUGIN_DEST/"

echo "==> Enabling plugin in shell.json..."
python3 - "$SHELL_JSON" "$PLUGIN_ID" <<'PYEOF'
import json
import sys

path, plugin_id = sys.argv[1], sys.argv[2]
with open(path) as f:
    config = json.load(f)

plugins = config.setdefault("plugins", [])
if not any(p.get("id") == plugin_id for p in plugins):
    plugins.append({"id": plugin_id})
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    print(f"  Added {plugin_id} to shell.json")
else:
    print(f"  {plugin_id} already present in shell.json")
PYEOF

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
sed "s|__DAEMON_DIR__|$PROJECT_DIR/daemon|" "$PROJECT_DIR/systemd/kheetsheet-hypr-daemon.service" \
    > "$HOME/.config/systemd/user/$SERVICE_NAME"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

echo "==> Reloading the Omarchy shell's plugin list..."
omarchy-shell -q shell rescanPlugins || true

cat <<EOF

==> Install complete.

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
EOF
