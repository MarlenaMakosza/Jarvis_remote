"""Mouse and keyboard executor for KDE Plasma (Wayland) via ydotool + kdotool.

`ydotool mousemove --absolute` is unreliable on KWin and relative moves are
distorted by pointer acceleration. We read the real pointer position with
`kdotool getmouselocation` and correct in a damped loop until we are on target.
"""

import os
import re
import subprocess
import time

SOCKET = os.environ.setdefault(
    "YDOTOOL_SOCKET", os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket"))

# Linux input-event-codes for keys the model is likely to use.
KEYCODES = {
    "esc": 1, "escape": 1, "backspace": 14, "tab": 15, "enter": 28, "return": 28,
    "ctrl": 29, "control": 29, "shift": 42, "alt": 56, "space": 57, "capslock": 58,
    "super": 125, "meta": 125, "win": 125, "cmd": 125,
    "home": 102, "up": 103, "pageup": 104, "left": 105, "right": 106, "end": 107,
    "down": 108, "pagedown": 109, "insert": 110, "delete": 111, "del": 111,
    "-": 12, "=": 13, "[": 26, "]": 27, ";": 39, "'": 40, "`": 41, "\\": 43,
    ",": 51, ".": 52, "/": 53,
}
KEYCODES.update({str(d): 2 + (d - 1) % 10 for d in range(10)})  # 1..9 -> 2..10, 0 -> 11
KEYCODES.update({f"f{i}": 58 + i for i in range(1, 11)} | {"f11": 87, "f12": 88})
for row, start in (("qwertyuiop", 16), ("asdfghjkl", 30), ("zxcvbnm", 44)):
    KEYCODES.update({ch: start + i for i, ch in enumerate(row)})

BUTTON_CLICK = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}
LEFT_DOWN, LEFT_UP = "0x40", "0x80"


def _ydotool(*args: str) -> None:
    subprocess.run(["ydotool", *args], check=True, capture_output=True)


def ensure_daemon() -> None:
    if os.path.exists(SOCKET):
        return
    subprocess.Popen(
        ["ydotoold", f"--socket-path={SOCKET}", f"--socket-own={os.getuid()}:{os.getgid()}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if os.path.exists(SOCKET):
            return
        time.sleep(0.1)
    raise RuntimeError(f"ydotoold did not create {SOCKET}")


def cursor() -> tuple[int, int]:
    # kdotool sometimes returns empty output; retry a few times.
    for _ in range(10):
        out = subprocess.run(["kdotool", "getmouselocation"], capture_output=True, text=True).stdout
        m = re.search(r"x:(-?\d+) y:(-?\d+)", out)
        if m:
            return int(m[1]), int(m[2])
        time.sleep(0.05)
    raise RuntimeError("kdotool getmouselocation returned no position")


def move(tx: int, ty: int, tolerance: int = 1, max_iter: int = 40) -> tuple[int, int]:
    for _ in range(max_iter):
        x, y = cursor()
        dx, dy = tx - x, ty - y
        if abs(dx) <= tolerance and abs(dy) <= tolerance:
            return x, y
        dist = max(abs(dx), abs(dy))
        # Cap step size and damp big moves so acceleration does not overshoot.
        k = min(1.0, 300 / dist) * (0.8 if dist > 20 else 1.0)
        _ydotool("mousemove", "-x", str(round(dx * k)), "-y", str(round(dy * k)))
        time.sleep(0.03)  # let KWin process the event before reading back
    return cursor()


def click(x: int, y: int, button: str = "left", count: int = 1) -> None:
    move(x, y)
    _ydotool("click", "--repeat", str(count), "--next-delay", "80", BUTTON_CLICK[button])


def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    move(x1, y1)
    _ydotool("click", LEFT_DOWN)
    time.sleep(0.1)
    move(x2, y2)
    time.sleep(0.1)
    _ydotool("click", LEFT_UP)


def scroll(x: int, y: int, direction: str, amount: int = 5) -> None:
    move(x, y)
    # REL_WHEEL > 0 scrolls up. TODO: verify direction on this machine.
    dx, dy = {"up": (0, amount), "down": (0, -amount),
              "left": (-amount, 0), "right": (amount, 0)}[direction]
    _ydotool("mousemove", "--wheel", "-x", str(dx), "-y", str(dy))


def hotkey(combo: str) -> None:
    """Press a combo like 'ctrl+shift+t' or 'ctrl c' (UI-TARS uses spaces)."""
    keys = [k for k in re.split(r"[+\s]+", combo.lower().strip()) if k]
    try:
        codes = [KEYCODES[k] for k in keys]
    except KeyError as e:
        raise ValueError(f"Unknown key {e.args[0]!r} in {combo!r}") from None
    events = [f"{c}:1" for c in codes] + [f"{c}:0" for c in reversed(codes)]
    _ydotool("key", *events)


def type_text(text: str) -> None:
    """Type text. A trailing newline presses Enter (UI-TARS convention)."""
    submit = text.endswith("\n")
    text = text.rstrip("\n")
    if text:
        if text.isascii():
            _ydotool("type", "--key-delay=5", "--key-hold=5", "--escape=0", "--", text)
        else:
            # ydotool cannot type characters like ą/ę; paste through the clipboard.
            subprocess.run(["wl-copy", "--", text], check=True)
            time.sleep(0.1)
            hotkey("ctrl+v")
    if submit:
        time.sleep(0.3)  # web search boxes (YouTube) drop an Enter sent right after typing
        hotkey("enter")
