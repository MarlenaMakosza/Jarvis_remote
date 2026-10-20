"""Find, activate and measure application windows on KWin via kdotool."""

import re
import subprocess
import time

from . import screen

# Window classes that are never a task target (desktop, panels, helpers).
IGNORED = {"plasmashell", "xwaylandvideobridge", "org.kde.plasmashell", "krunner"}

# Words people use for an app -> substrings of its window class.
ALIASES = {
    "browser": ["vivaldi", "firefox", "chromium", "chrome", "brave"],
    "przeglądark": ["vivaldi", "firefox", "chromium", "chrome", "brave"],
    "youtube": ["vivaldi", "firefox", "chromium", "chrome", "brave"],
    "discord": ["vesktop", "discord"],
    "terminal": ["kitty", "konsole", "alacritty"],
    "editor": ["kate", "code"],
    "files": ["dolphin"],
    "pliki": ["dolphin"],
}


def _kdotool(*args: str) -> str:
    # kdotool sometimes returns empty output; queries are cheap, so retry.
    for _ in range(5):
        out = subprocess.run(["kdotool", *args], capture_output=True, text=True).stdout.strip()
        if out:
            return out
        time.sleep(0.05)
    return ""


def info(wid: str) -> screen.Monitor | None:
    """Window geometry as a rect; `name` holds the window class."""
    geo = _kdotool("getwindowgeometry", wid)
    pos = re.search(r"Position: (-?\d+),(-?\d+)", geo)
    size = re.search(r"Geometry: (\d+)x(\d+)", geo)
    if not (pos and size):
        return None
    return screen.Monitor(_kdotool("getwindowclassname", wid), *map(int, pos.groups()), *map(int, size.groups()))


def list_windows() -> list[tuple[str, screen.Monitor]]:
    result = []
    for wid in _kdotool("search", "--class", ".").split():
        rect = info(wid)
        if rect and rect.name.lower() not in IGNORED and rect.width > 50 and rect.height > 50:
            result.append((wid, rect))
    return result


def _short(cls: str) -> str:
    """'Vivaldi-stable' -> 'vivaldi', 'org.kde.dolphin' -> 'dolphin'."""
    return re.sub(r"-(stable|beta|bin)$", "", cls.lower().split(".")[-1])


def find_app(task: str) -> tuple[str, screen.Monitor] | None:
    """Window of the app named in the task ("In Vivaldi ...", "w Kate ..."), largest if several."""
    words = set(re.findall(r"[\wąćęłńóśźż-]+", task.lower()))
    wins = list_windows()

    def matches(cls: str) -> bool:
        short = _short(cls)
        if short in words:
            return True
        return any(w.startswith(alias) and any(s in short for s in subs)
                   for alias, subs in ALIASES.items() for w in words)

    found = [(wid, r) for wid, r in wins if matches(r.name)]
    return max(found, key=lambda x: x[1].width * x[1].height) if found else None


def active() -> tuple[str, screen.Monitor] | None:
    wid = _kdotool("getactivewindow")
    rect = info(wid) if wid else None
    return (wid, rect) if rect else None


def activate(wid: str) -> None:
    subprocess.run(["kdotool", "windowactivate", wid], capture_output=True)
    time.sleep(0.3)


def monitor_of(rect: screen.Monitor) -> screen.Monitor:
    cx, cy = rect.x + rect.width // 2, rect.y + rect.height // 2
    mons = screen.monitors()
    return next((m for m in mons if m.contains(cx, cy)), mons[0])


def clip(rect: screen.Monitor, mon: screen.Monitor) -> screen.Monitor:
    """Part of a window that is visible on its monitor."""
    x1, y1 = max(rect.x, mon.x), max(rect.y, mon.y)
    x2 = min(rect.x + rect.width, mon.x + mon.width)
    y2 = min(rect.y + rect.height, mon.y + mon.height)
    return screen.Monitor(rect.name, x1, y1, max(1, x2 - x1), max(1, y2 - y1))
