"""Quick actions: common tasks done with a command instead of the vision model.

Only short, single-step tasks match ("pause youtube", "głośniej", "open wp.pl").
Anything longer or with "and"/"then" goes to the agent.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Callable

from . import windows


@dataclass
class Quick:
    name: str
    label: str              # shown to the user
    run: Callable[[], None]


def _sh(*cmd: str) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _players() -> list[str]:
    out = subprocess.run(["playerctl", "-l"], capture_output=True, text=True).stdout.split()
    # plasma-browser-integration and the browser's own MPRIS entry control the same
    # tab, so prefer the integration and never send play to both.
    return sorted(out, key=lambda p: p != "plasma-browser-integration")


def _status(player: str) -> str:
    return subprocess.run(["playerctl", "-p", player, "status"], capture_output=True, text=True).stdout.strip()


def media_pause() -> None:
    _sh("playerctl", "-a", "pause")


def media_play() -> None:
    players = _players()
    if not players:
        raise RuntimeError("No media player found (playerctl -l is empty)")
    _sh("playerctl", "-p", players[0], "play")


def media_toggle() -> None:
    if any(_status(p) == "Playing" for p in _players()):
        media_pause()
    else:
        media_play()


def _playing_or_first() -> str:
    players = _players()
    if not players:
        raise RuntimeError("No media player found (playerctl -l is empty)")
    return next((p for p in players if _status(p) == "Playing"), players[0])


def media_next() -> None:
    _sh("playerctl", "-p", _playing_or_first(), "next")


def media_previous() -> None:
    _sh("playerctl", "-p", _playing_or_first(), "previous")


SINK = "@DEFAULT_AUDIO_SINK@"

ACTIONS: dict[str, Quick] = {q.name: q for q in [
    Quick("toggle", "Play/pause (playerctl)", media_toggle),
    Quick("pause", "Pause media (playerctl)", media_pause),
    Quick("play", "Play media (playerctl)", media_play),
    Quick("next", "Next track (playerctl)", media_next),
    Quick("previous", "Previous track (playerctl)", media_previous),
    Quick("vol_up", "Volume +5%", lambda: _sh("wpctl", "set-volume", "-l", "1.0", SINK, "5%+")),
    Quick("vol_down", "Volume -5%", lambda: _sh("wpctl", "set-volume", SINK, "5%-")),
    Quick("mute", "Mute on/off", lambda: _sh("wpctl", "set-mute", SINK, "toggle")),
    Quick("lock", "Lock screen", lambda: _sh("loginctl", "lock-session")),
]}

# (regex on the whole task, action name). Polish and English.
PATTERNS = [
    (r"(play ?/ ?pause|toggle)", "toggle"),
    (r"(pause|pauza|zapauzuj|wstrzymaj|zatrzymaj|stop)", "pause"),
    (r"(play|unpause|resume|wznów|odtwórz|odpauzuj|puść)", "play"),
    (r"(next|skip|następn\w*|kolejn\w*)", "next"),
    (r"(previous|prev|poprzedni\w*)", "previous"),
    (r"(volume up|louder|głośniej|podgłośnij)", "vol_up"),
    (r"(volume down|quieter|ciszej|przycisz|ścisz)", "vol_down"),
    (r"(mute|unmute|wycisz|wyłącz dźwięk|włącz dźwięk)", "mute"),
    (r"(lock( the)? screen|zablokuj( ekran| komputer)?)", "lock"),
]
# Words allowed around the verb: "pause the youtube video in vivaldi", "pauza na yt".
FILLER = (r"(the|a|it|this|video|music|song|track|film|wideo|muzyk\w*|piosenk\w*|utw[óo]r|"
          r"youtube|yt|spotify|vivaldi|firefox|browser|przeglądar\w*|in|on|w|na|we|please|proszę|"
          r"track|song|media|dźwięk|ekran|screen)")


def _url_action(task: str) -> Quick | None:
    m = re.fullmatch(r"(open|go to|otwórz|wejdź na|idź na)\s+(https?://\S+|[\w.-]+\.[a-z]{2,}(/\S*)?)", task)
    if not m:
        return None
    url = m[2] if m[2].startswith("http") else "https://" + m[2]
    return Quick("open_url", f"Open {url} (xdg-open)", lambda: _sh("xdg-open", url))


# Generic words to skip when looking for the app name: "odpal terminal kitty" -> kitty.
GENERIC = {"terminal", "app", "the", "a", "program", "aplikację", "aplikacje", "apkę", "new", "nowy", "nową", "nowe"}
DEFAULT_APPS = {"terminal": "kitty", "terminala": "kitty", "przeglądarkę": "vivaldi-stable", "browser": "vivaldi-stable",
                "pliki": "dolphin", "files": "dolphin", "edytor": "kate", "editor": "kate"}


def _desktop_id(name: str) -> str | None:
    """Find a .desktop entry whose file name or Name= matches name."""
    dirs = [Path.home() / ".local/share/applications", Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications")]
    for d in dirs:
        for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
            if name in f.stem.lower().split("."):
                return f.stem
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            m = re.search(r"^Name=(.+)$", text, re.M)
            if m and m[1].strip().lower() == name:
                return f.stem
    return None


def _launcher(word: str) -> tuple[str, list[str]] | None:
    word = DEFAULT_APPS.get(word, word)
    if desktop := _desktop_id(word):
        return desktop, ["gtk-launch", desktop]
    if path := shutil.which(word):
        return word, [path]
    return None


def _launch_action(task: str) -> Quick | None:
    m = re.fullmatch(r"(odpal|uruchom|włącz|otwórz|open|launch|start|run)\s+(.+)", task)
    if not m:
        return None
    words = m[2].split()
    specific = [w for w in words if w not in GENERIC]
    # Prefer the specific name ("kitty"), fall back to a generic one ("terminal" -> kitty).
    for w in specific + [w for w in words if w in DEFAULT_APPS]:
        if found := _launcher(w):
            name, cmd = found
            return Quick("launch", f"Launch {name}", lambda: subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=os.environ))
    return None


def _focus_action(task: str) -> Quick | None:
    m = re.fullmatch(r"(switch to|focus|show|przełącz( się)? na|pokaż)\s+(.+)", task)
    if not m:
        return None
    win = windows.find_app(m[3])
    if not win:
        return None
    wid, rect = win
    return Quick("focus", f"Activate window {rect.name}", lambda: windows.activate(wid))


def match(task: str) -> Quick | None:
    t = re.sub(r"[.!?,]+$", "", task.strip().lower())
    if len(t.split()) > 8 or re.search(r"\b(and|then|i|potem|a potem|oraz)\b", t):
        return None
    if q := _url_action(t) or _focus_action(t) or _launch_action(t):
        return q
    for pattern, name in PATTERNS:
        if re.fullmatch(rf"({FILLER}\s+)*{pattern}(\s+{FILLER})*", t):
            return ACTIONS[name]
    return None
