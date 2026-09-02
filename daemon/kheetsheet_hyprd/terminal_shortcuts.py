import os

# Narrow, deliberately-scoped fallback for the one blind spot AT-SPI can
# never see into: what's actually running inside a terminal (vim, tmux, a
# REPL - all invisible to the accessibility tree). Approved in principle in
# HANDOVER.md's 2026-09-02 note specifically as "detect nvim/tmux via the
# focused terminal's child processes and show a small built-in keymap only
# in that case" - explicitly NOT a general per-app catalog (that idea, and a
# hardcoded list of Omarchy's own default keybinds, were both rejected there
# as maintenance burdens this project's AT-SPI approach exists to avoid).
# Borrows the /proc child-tree-walking technique from
# https://github.com/fze-fze/omarchy-shortcut-sheet, not its hand-curated
# per-app catalog.

KNOWN_TERMINAL_CLASSES = {
    "foot",
    "footclient",
    "kitty",
    "alacritty",
    "wezterm",
    "org.wezfurlong.wezterm",
    "ghostty",
    "com.mitchellh.ghostty",
    "konsole",
    "gnome-terminal-server",
    "xterm",
}

# Bounds on the /proc walk - matches the bounding principle used for AT-SPI
# and hyprctl elsewhere in this project (see service.py, hypr.py): a
# process tree is attacker-influenceable (any process the user runs), so
# none of this is trusted to stay small on its own.
MAX_PROC_SCAN = 4000
MAX_BFS_NODES = 500
MAX_BFS_DEPTH = 12
MAX_STAT_BYTES = 4096

TERMINAL_KEYMAPS = {
    "nvim": [
        ("File", "Save", ":w"),
        ("File", "Save and quit", ":wq"),
        ("File", "Quit without saving", ":q!"),
        ("Edit", "Undo", "u"),
        ("Edit", "Delete line", "dd"),
        ("Edit", "Yank (copy) line", "yy"),
        ("Edit", "Paste", "p"),
        ("Navigate", "Search forward", "/"),
        ("Navigate", "Go to top", "gg"),
        ("Navigate", "Go to bottom", "G"),
        ("Navigate", "Command mode", ":"),
    ],
    "tmux": [
        ("Pane", "Split horizontal", "Prefix %"),
        ("Pane", "Split vertical", "Prefix \""),
        ("Pane", "Close pane", "Prefix x"),
        ("Pane", "Cycle panes", "Prefix o"),
        ("Window", "New window", "Prefix c"),
        ("Window", "Next window", "Prefix n"),
        ("Window", "Previous window", "Prefix p"),
        ("Window", "Rename window", "Prefix ,"),
        ("Session", "Detach", "Prefix d"),
        ("Session", "List sessions", "Prefix s"),
        ("Copy mode", "Enter copy mode", "Prefix ["),
    ],
}


def is_known_terminal_class(app_id):
    return bool(app_id) and app_id.strip().lower() in KNOWN_TERMINAL_CLASSES


def _read_stat(pid):
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            data = f.read(MAX_STAT_BYTES)
    except Exception:
        return None
    # comm (field 2) is parenthesized and can itself contain spaces/parens,
    # so isolate it via the *last* ')' rather than splitting on whitespace.
    close = data.rfind(")")
    if close == -1:
        return None
    open_paren = data.find("(")
    if open_paren == -1 or open_paren > close:
        return None
    comm = data[open_paren + 1 : close]
    # tmux (confirmed live, this machine's tmux build) renames its comm to
    # "tmux: client" / "tmux: server" rather than leaving it as plain
    # "tmux" - normalize by dropping anything from the first ":" onward so
    # TERMINAL_KEYMAPS's plain "tmux" key still matches. Leaves comm values
    # with no colon (e.g. "nvim") unchanged.
    comm = comm.split(":", 1)[0].strip()
    # Immediately after the ")" comes the single-char state field, then
    # ppid - not ppid directly (an off-by-one here silently reads the state
    # letter as a pid and every pid ends up "parentless").
    rest = data[close + 2 :].split()
    if len(rest) < 2:
        return None
    try:
        ppid = int(rest[1])
    except (ValueError, IndexError):
        return None
    return comm, ppid


def _build_process_tree():
    comm_of = {}
    children_of = {}
    scanned = 0
    try:
        entries = os.listdir("/proc")
    except Exception:
        return comm_of, children_of
    for name in entries:
        if not name.isdigit():
            continue
        scanned += 1
        if scanned > MAX_PROC_SCAN:
            break
        pid = int(name)
        info = _read_stat(pid)
        if info is None:
            continue
        comm, ppid = info
        comm_of[pid] = comm
        children_of.setdefault(ppid, []).append(pid)
    return comm_of, children_of


def find_descendant_tool(root_pid, tools=("nvim", "tmux")):
    """BFS the real process tree rooted at `root_pid` for a descendant whose
    comm matches one of `tools`. Returns the matched tool name, or None.

    Content-blind beyond the process name itself - never reads what's
    actually on screen or in the terminal's scrollback, consistent with the
    rest of this project's "read structure, not content" posture.
    """
    if not root_pid:
        return None
    comm_of, children_of = _build_process_tree()
    if root_pid not in children_of and root_pid not in comm_of:
        return None
    seen = {root_pid}
    queue = [(root_pid, 0)]
    visited = 0
    while queue:
        pid, depth = queue.pop(0)
        visited += 1
        if visited > MAX_BFS_NODES or depth > MAX_BFS_DEPTH:
            break
        for child in children_of.get(pid, []):
            if child in seen:
                continue
            seen.add(child)
            comm = comm_of.get(child)
            if comm in tools:
                return comm
            queue.append((child, depth + 1))
    return None
