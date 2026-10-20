"""Safety policy: kill switch and per-action risk checks.

Modes:
  ask   confirm every action
  auto  confirm only risky actions
  full  never ask; blocked actions stay blocked
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .uitars import Action

MODES = ("ask", "auto", "full")

# Touching this file stops a running agent (KDE shortcut, `jarvis.agent stop`).
STOP_FILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "jarvis.stop"

TERMINALS = {"kitty", "konsole", "alacritty", "foot", "wezterm", "org.wezfurlong.wezterm", "xterm",
             "gnome-terminal", "org.gnome.terminal", "yakuake", "tilix", "terminator", "ghostty",
             "com.mitchellh.ghostty", "org.kde.konsole"}
# Launchers run whatever you type in them.
LAUNCHERS = {"krunner", "org.kde.krunner", "plasmashell", "org.kde.plasmashell"}

# Hotkeys that close, quit or delete things, or open a command runner.
RISKY_HOTKEYS = {
    ("alt", "f4"): "closes the window",
    ("ctrl", "w"): "closes the tab",
    ("ctrl", "shift", "w"): "closes the window",
    ("ctrl", "q"): "quits the app",
    ("ctrl", "shift", "q"): "quits the app",
    ("ctrl", "alt", "delete"): "logout / power menu",
    ("ctrl", "alt", "backspace"): "kills the session",
    ("ctrl", "shift", "delete"): "clears browser data",
    ("shift", "delete"): "deletes permanently",
    ("delete",): "deletes the selection",
    ("alt", "f2"): "opens a command runner",
    ("alt", "space"): "opens a command runner",
    ("super",): "opens the launcher",
}

# Text that looks like a dangerous shell command.
RISKY_TEXT = re.compile(
    r"\b(rm\s+-\w*[rf]|sudo|mkfs|dd\s+if=|chmod\s+-R|chown\s+-R|shutdown|reboot|poweroff|"
    r"git\s+(push|reset\s+--hard|clean)|curl[^|]*\|\s*(ba)?sh|wget[^|]*\|\s*(ba)?sh|:\(\)\s*\{)", re.I)


@dataclass
class Verdict:
    level: str      # ok, confirm, block
    reason: str = ""


def _keys(combo: str) -> tuple[str, ...]:
    alias = {"control": "ctrl", "meta": "super", "win": "super", "cmd": "super", "del": "delete", "escape": "esc"}
    keys = [alias.get(k, k) for k in re.split(r"[+\s]+", combo.lower().strip()) if k]
    mods = [k for k in ("ctrl", "shift", "alt", "super") if k in keys]
    return tuple(mods + sorted(k for k in keys if k not in mods))


def assess(action: Action, window_class: str) -> Verdict:
    """Risk of executing action while window_class has keyboard focus."""
    cls = window_class.lower()
    if action.kind == "type":
        if RISKY_TEXT.search(action.text):
            where = " in a terminal" if cls in TERMINALS or cls.split(".")[-1] in TERMINALS else ""
            return Verdict("confirm", f"text looks like a dangerous command{where}: {action.text.strip()[:60]!r}")
        if cls in LAUNCHERS and action.text.endswith("\n"):
            return Verdict("confirm", f"typing a command into the launcher ({window_class})")
    if action.kind == "hotkey":
        keys = _keys(action.text)
        if keys in RISKY_HOTKEYS:
            return Verdict("confirm", f"{action.text} {RISKY_HOTKEYS[keys]}")
    return Verdict("ok")


def needs_confirm(mode: str, verdict: Verdict) -> bool:
    if verdict.level == "block":
        return False  # never executed, nothing to confirm
    return mode == "ask" or (mode == "auto" and verdict.level == "confirm")


def request_stop() -> None:
    STOP_FILE.touch()


def clear_stop() -> None:
    STOP_FILE.unlink(missing_ok=True)


def stop_requested() -> bool:
    return STOP_FILE.exists()
