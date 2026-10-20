"""Screen capture and monitor geometry for KDE Plasma (Wayland).

grim does not work on KWin (no wlr-screencopy), so we capture with spectacle
and crop the target monitor. Monitor geometry comes from KWin itself because
kscreen-doctor reports stale offsets that do not match pointer coordinates.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass

from PIL import Image

# Qwen2.5-VL (and UI-TARS) work on 28x28 patches. If we send an image whose
# sides are already multiples of 28 and below the pixel limit, the model sees
# exactly this image and its absolute coordinates refer to it.
PATCH = 28


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


def monitors() -> list[Monitor]:
    info = subprocess.run(
        ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.supportInformation"],
        capture_output=True, text=True, check=True,
    ).stdout
    result = []
    for block in re.split(r"\nScreen \d+:\n-+\n", info)[1:]:
        name = re.search(r"Name: (\S+)", block)
        enabled = re.search(r"Enabled: (\d)", block)
        geo = re.search(r"Geometry: (-?\d+),(-?\d+),(\d+)x(\d+)", block)
        if name and enabled and enabled[1] == "1" and geo:
            result.append(Monitor(name[1], *map(int, geo.groups())))
    return sorted(result, key=lambda m: (m.y, m.x))


def find_monitor(name: str | None, cursor: tuple[int, int] | None) -> Monitor:
    mons = monitors()
    if name:
        for m in mons:
            if m.name == name:
                return m
        raise SystemExit(f"Unknown monitor {name!r}. Available: {[m.name for m in mons]}")
    if cursor:
        for m in mons:
            if m.contains(*cursor):
                return m
    return mons[0]


def model_size(width: int, height: int, max_side: int) -> tuple[int, int]:
    """Scale (width, height) so the longer side is about max_side, sides multiple of PATCH."""
    scale = min(1.0, max_side / max(width, height))
    w = max(PATCH, round(width * scale / PATCH) * PATCH)
    h = max(PATCH, round(height * scale / PATCH) * PATCH)
    return w, h


@dataclass
class Shot:
    image: Image.Image   # resized image sent to the model
    monitor: Monitor     # captured region: a whole monitor or one window
    native: Image.Image  # region crop at full resolution, used for zoom-in refinement

    def to_global(self, mx: float, my: float) -> tuple[int, int]:
        """Map model-image pixel coordinates to global KWin pointer coordinates."""
        gx = self.monitor.x + mx * self.monitor.width / self.image.width
        gy = self.monitor.y + my * self.monitor.height / self.image.height
        return round(gx), round(gy)


def capture(monitor: Monitor, max_side: int) -> Shot:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        # -b background, -n no notification, -f full desktop (all monitors)
        subprocess.run(["spectacle", "-b", "-n", "-f", "-o", path],
                       check=True, capture_output=True)
        full = Image.open(path).convert("RGB")
    finally:
        os.unlink(path)

    # The full screenshot starts at the top-left of the bounding box of all monitors.
    mons = monitors()
    ox = min(m.x for m in mons)
    oy = min(m.y for m in mons)
    left, top = monitor.x - ox, monitor.y - oy
    crop = full.crop((left, top, left + monitor.width, top + monitor.height))
    return Shot(crop.resize(model_size(monitor.width, monitor.height, max_side), Image.LANCZOS), monitor, crop)


@dataclass
class Zoom:
    image: Image.Image   # magnified region sent to the model
    left: int            # region origin in global coordinates
    top: int
    scale: float         # model pixels per screen pixel

    def to_global(self, mx: float, my: float) -> tuple[int, int]:
        return round(self.left + mx / self.scale), round(self.top + my / self.scale)


def zoom(shot: Shot, gx: int, gy: int, width: int = 630, height: int = 350, scale: float = 2.0) -> Zoom:
    """Cut a width x height screen region centered on (gx, gy) and magnify it."""
    m = shot.monitor
    width, height = min(width, m.width), min(height, m.height)  # small windows
    left = min(max(gx - width // 2, m.x), m.x + m.width - width)
    top = min(max(gy - height // 2, m.y), m.y + m.height - height)
    region = shot.native.crop((left - m.x, top - m.y, left - m.x + width, top - m.y + height))
    size = (round(width * scale / PATCH) * PATCH, round(height * scale / PATCH) * PATCH)
    return Zoom(region.resize(size, Image.LANCZOS), left, top, size[0] / width)
