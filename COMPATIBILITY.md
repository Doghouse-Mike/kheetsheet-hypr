# Making your app work with kheetsheet

kheetsheet (and this Hyprland port of it) doesn't have a plugin system, a
config file, or an opt-in flag for apps. It works or it doesn't, purely as a
byproduct of how your app exposes itself to **AT-SPI** — the same
accessibility tree screen readers use. If your app already does the things
below, kheetsheet already works against it; nothing to install, no
dependency on this project at all.

## What kheetsheet actually looks for

Walking your app's AT-SPI tree, it looks for a node with accessible role
**`menu bar`**, then walks its children for **`menu` / `menu item` / `check
menu item` / `radio menu item`** nodes that each have a non-empty
**key-binding** (accelerator) string. No menu bar → nothing to show, however
many keyboard shortcuts your app actually has.

That's the whole contract:

1. A `menu bar`-rooted accessible structure...
2. ...whose menu items carry a real keyboard accelerator, not just a click
   handler.

## Toolkit notes

- **Qt / KDE Frameworks** (`QMenuBar` + `QAction` with `setShortcut`):
  works out of the box. This is what Qt's accessibility bridge exposes by
  default for any app with a real menu bar.
- **GTK3** with a traditional `GtkMenuBar`: also works out of the box, same
  reason.
- **GTK4 / libadwaita, header-bar-only apps**: this is the toolkit-level gap.
  Modern GNOME-style apps (Nautilus, GNOME Text Editor, and most libadwaita
  apps) don't use a menu bar at all — actions live behind a hamburger button
  or aren't menu-backed at all (`GtkShortcutController` bound directly to a
  widget). Two ways to close this gap, different amounts of work:
  - **Full support**: build a real `Gio.Menu` and expose it via
    `Gtk.PopoverMenuBar` (GTK4's menu-bar-shaped widget for a `GMenu`
    model), with each action's shortcut set via
    `app.set_accels_for_action("app.foo", ["<Control>N"])`. That accelerator
    is what surfaces through AT-SPI as the item's key-binding. Heavier: it
    means keeping a real menu around even if your UI is otherwise chrome-free.
  - **Cheap partial support**: add a `Gtk.ShortcutsWindow` (or a hand-rolled
    dialog) bound to `Ctrl+Shift+/` — the de facto GNOME convention (it's
    what Nautilus does). kheetsheet-hypr's opt-in "native-overlay fallback"
    specifically looks for that convention: on the empty state, the user can
    ask it to trigger your app's own `Ctrl+Shift+/` dialog directly, and it's
    left on screen as-is. You get *some* discoverability with a few lines of
    code and no restructuring, at the cost of it being a static list instead
    of a live, clickable one.
- **Electron**: no known path. Chromium's accessibility tree only carries a
  keyboard shortcut if the web content annotates it via the ARIA
  `aria-keyshortcuts` attribute, which essentially nothing does in practice
  — confirmed empirically against Obsidian, including with
  `--force-renderer-accessibility` forced on. Not worth chasing.

## Checking whether your app already qualifies

Focus your app and toggle kheetsheet (or run upstream
[kheetsheet](https://github.com/Doghouse-Mike/kheetsheet) if you're not on
Hyprland) — if it says "no shortcuts found", that's your answer, live. To
check without kheetsheet installed at all, the same query it runs is a few
lines of Python:

```python
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if app.get_process_id() == YOUR_APP_PID:
        print(app.get_name())  # confirms AT-SPI sees your app at all
```

If your app's name shows up but nothing has role `menu bar`, that's the gap
to close, not a registration problem — most GTK4 apps register with AT-SPI
automatically the moment the accessibility bus is active, whether or not
they expose a menu.
