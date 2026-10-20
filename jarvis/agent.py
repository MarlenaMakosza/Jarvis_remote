"""JARVIS_REMOTE: local computer-use agent (UI-TARS-1.5 on llama-server).

Usage:
  python -m jarvis.agent shot                       # save what the model sees
  python -m jarvis.agent ground "Firefox icon"      # move the cursor to an element, no click
  python -m jarvis.agent run "open Firefox and go to wikipedia.org"
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from . import actions, quick, safety, screen, windows
from .uitars import Step, UITars

RUNS = Path(__file__).resolve().parent.parent / "runs"
KEEP_DAYS = float(os.environ.get("JARVIS_KEEP_DAYS", 7))


def cleanup_runs(days: float = KEEP_DAYS) -> list[str]:
    """Delete run logs (runs/YYYYMMDD-HHMMSS) older than `days`. Returns removed names.

    Only directories named like a run are touched, judged by the time in the name.
    """
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    removed = []
    for d in sorted(RUNS.glob("[0-9]" * 8 + "-" + "[0-9]" * 6)):
        try:
            started = datetime.datetime.strptime(d.name, "%Y%m%d-%H%M%S")
        except ValueError:
            continue
        if d.is_dir() and started < cutoff:
            shutil.rmtree(d)
            removed.append(d.name)
    return removed


def active_window() -> str | None:
    out = subprocess.run(["kdotool", "getactivewindow"], capture_output=True, text=True).stdout.strip()
    return out or None


def window_center(window: str | None) -> tuple[int, int] | None:
    if not window:
        return None
    out = subprocess.run(["kdotool", "getwindowgeometry", window], capture_output=True, text=True).stdout
    pos = re.search(r"Position: (-?\d+),(-?\d+)", out)
    size = re.search(r"Geometry: (\d+)x(\d+)", out)
    if not (pos and size):
        return None
    return int(pos[1]) + int(size[1]) // 2, int(pos[2]) + int(size[2]) // 2


def pick_monitor(args) -> screen.Monitor:
    """--monitor, else $JARVIS_MONITOR, else the monitor under the cursor.

    Warn when the terminal that launched us is on that monitor: the model would
    see its own terminal instead of the app it should control.
    """
    mon = screen.find_monitor(args.monitor or os.environ.get("JARVIS_MONITOR"), actions.cursor())
    if args.monitor:
        return mon  # chosen explicitly, trust it
    term = window_center(active_window())
    if term and mon.contains(*term):
        others = [m.name for m in screen.monitors() if m.name != mon.name]
        print(f"WARNING: this terminal is on {mon.name}, the agent will see it. "
              f"Use --monitor {' / '.join(others)} or export JARVIS_MONITOR=...")
        if not getattr(args, "dry_run", False) and confirm("    Continue anyway?") != "y":
            sys.exit("Stopped.")
    return mon


def activate(window: str | None) -> None:
    if window:
        subprocess.run(["kdotool", "windowactivate", window], capture_output=True)
        time.sleep(0.2)


def mark(img: Image.Image, points: list[tuple[float, float]]) -> Image.Image:
    img = img.copy()
    d = ImageDraw.Draw(img)
    for x, y in points:
        d.ellipse((x - 8, y - 8, x + 8, y + 8), outline="red", width=3)
        d.line((x - 14, y, x + 14, y), fill="red", width=1)
        d.line((x, y - 14, x, y + 14), fill="red", width=1)
    return img


NO_CHANGE = ("Note: the screen did not visibly change after your previous action, so it probably had no effect. "
             "Check the screenshot carefully before declaring the task finished.")


def changed(before: Image.Image, after: Image.Image, threshold: float = 0.002) -> bool:
    """True if more than `threshold` of pixels differ noticeably."""
    size = (256, round(256 * before.height / before.width))
    diff = ImageChops.difference(before.convert("L").resize(size), after.convert("L").resize(size))
    moved = sum(diff.point(lambda v: 255 if v > 24 else 0).histogram()[255:])
    return moved / (size[0] * size[1]) > threshold


def target_of(step: Step, task: str) -> str:
    """Description of the click target: last sentence of the Thought, which UI-TARS
    uses to summarize the next action and its target element."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", step.thought) if x.strip()]
    return (sentences[-1] if sentences else "") + f" (Task: {task})"


def refine(model: UITars, shot: screen.Shot, g: tuple[int, int], description: str,
           log: Path | None = None) -> tuple[int, int]:
    """Second grounding pass on a magnified region around g."""
    z = screen.zoom(shot, *g)
    px = model.ground(description, z.image)
    if log:
        mark(z.image, [px]).save(log)
    if not (0 <= px[0] < z.image.width and 0 <= px[1] < z.image.height):
        return g
    return z.to_global(*px)


def describe(step: Step, gpoints: list[tuple[int, int]]) -> str:
    a = step.action
    parts = [a.kind]
    if gpoints:
        parts.append(" -> ".join(f"({x},{y})" for x, y in gpoints))
    if a.text:
        parts.append(repr(a.text))
    if a.direction:
        parts.append(a.direction)
    return " ".join(parts)


def execute(step: Step, gpoints: list[tuple[int, int]]) -> None:
    a = step.action
    match a.kind:
        case "click":
            actions.click(*gpoints[0])
        case "left_double":
            actions.click(*gpoints[0], count=2)
        case "right_single":
            actions.click(*gpoints[0], button="right")
        case "drag":
            actions.drag(*gpoints[0], *gpoints[1])
        case "scroll":
            actions.scroll(*gpoints[0], a.direction or "down")
        case "hotkey":
            actions.hotkey(a.text)
        case "type":
            actions.type_text(a.text)
        case "wait":
            time.sleep(5)
        case _:
            raise ValueError(f"Unsupported action {a.kind!r}")


def confirm(prompt: str) -> str:
    try:
        ans = input(f"{prompt}  [Enter=wykonaj, s=pomiń, q=stop] ").strip().lower()
    except EOFError:
        return "q"
    return {"": "y", "s": "s", "q": "q"}.get(ans, "q")


def cmd_shot(args, model: UITars) -> None:
    mon = pick_monitor(args)
    shot = screen.capture(mon, args.max_side)
    out = RUNS / "shot.png"
    out.parent.mkdir(exist_ok=True)
    shot.image.save(out)
    print(f"{mon.name} {mon.width}x{mon.height}+{mon.x}+{mon.y} -> {shot.image.size} saved {out}")


def cmd_ground(args, model: UITars) -> None:
    actions.ensure_daemon()
    mon = pick_monitor(args)
    shot = screen.capture(mon, args.max_side)
    t = time.time()
    px = model.ground(args.description, shot.image)
    g = shot.to_global(*px)
    print(f"model {px} on {shot.image.size} -> global {g}  ({time.time() - t:.1f}s)")
    RUNS.mkdir(exist_ok=True)
    mark(shot.image, [px]).save(RUNS / "ground.png")
    if args.refine:
        t = time.time()
        g = refine(model, shot, g, args.description, RUNS / "ground-zoom.png")
        print(f"refined -> global {g}  ({time.time() - t:.1f}s)")
    actions.move(*g)
    print(f"Cursor moved, no click. Marked screenshot: {RUNS / 'ground.png'}")


@dataclass
class RunOptions:
    max_side: int = 1792
    max_steps: int = 15
    settle: float = 1.0
    refine: bool = True
    dry_run: bool = False
    mode: str = "ask"           # ask, auto, full (see jarvis.safety)
    quick: bool = True         # try quick actions (jarvis.quick) before the model
    window: bool = True         # capture only the active app window, not the whole monitor


def resolve_target(task: str, monitor_hint: str | None) -> tuple[str | None, screen.Monitor]:
    """Window of the app named in the task (activated) and its monitor.

    Without a recognizable app: no window, monitor from the hint, $JARVIS_MONITOR
    or the cursor.
    """
    if app := windows.find_app(task):
        wid, rect = app
        windows.activate(wid)
        return wid, windows.monitor_of(rect)
    return None, screen.find_monitor(monitor_hint or os.environ.get("JARVIS_MONITOR"), actions.cursor())


def capture_region(opt: RunOptions, app: str | None, mon: screen.Monitor) -> screen.Monitor:
    """Region to screenshot this step.

    In window mode follow the active window (dialogs and new windows of the app
    become active), as long as it is a real window on the target monitor.
    """
    if not (opt.window and app):
        return mon
    act = windows.active()
    if not act or act[1].name.lower() in windows.IGNORED or windows.monitor_of(act[1]).name != mon.name:
        return mon
    region = windows.clip(act[1], mon)
    return region if region.width >= 400 and region.height >= 300 else mon


class CliUI:
    """Terminal front end. The web front end (jarvis.web) implements the same methods."""

    def event(self, kind: str, **d) -> None:
        match kind:
            case "start":
                print(f"Monitor {d['monitor']}, log {d['log_dir']}. Ctrl+C stops.")
            case "note":
                print(d["text"])
            case "step":
                print(f"\n[{d['i']}] ({d['secs']:.1f}s) {d['thought']}\n    -> {d['action']}")
                if d["risk"]:
                    print(f"    !! {d['risk']}")
            case "finished":
                print(f"Finished: {d['text']}")
            case "end":
                print(d["text"])

    def decide(self, reason: str = "") -> str:
        return confirm("   ")

    def stopped(self) -> bool:
        return safety.stop_requested()


def run_task(model: UITars, task: str, ui, opt: RunOptions, monitor_hint: str | None = None) -> None:
    safety.clear_stop()  # a stale kill-switch file must not stop a new task
    if opt.quick and (q := quick.match(task)):
        ui.event("note", text=f"Quick action: {q.label}")
        if not opt.dry_run:
            q.run()
        ui.event("finished", text=f"Done: {q.label}")
        return

    actions.ensure_daemon()
    if removed := cleanup_runs():
        ui.event("note", text=f"Removed {len(removed)} run log(s) older than {KEEP_DAYS:g} days")
    app, mon = resolve_target(task, monitor_hint)
    log_dir = RUNS / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_dir.mkdir(parents=True)
    (log_dir / "task.txt").write_text(task + "\n")
    where = mon.name + (f" / {windows.info(app).name}" if app else "")
    ui.event("start", monitor=where, log_dir=log_dir)

    past: list[tuple[Image.Image, str]] = []
    acted = False  # did we execute an action since the previous screenshot?
    blocked = ""   # reason the previous action was blocked, told to the model
    for i in range(1, opt.max_steps + 1):
        if ui.stopped():
            ui.event("end", text="Stopped.")
            return
        window = active_window()
        shot = screen.capture(capture_region(opt, app, mon), opt.max_side)
        note = NO_CHANGE if acted and not changed(past[-1][0], shot.image) else ""
        if note:
            ui.event("note", text=f"[{i}] screen unchanged after previous action")
        if blocked:
            note = (f"Note: your previous action was blocked by the safety policy ({blocked}). "
                    "Do not repeat it; choose a different approach or finish.")
            blocked = ""
        acted = False
        t = time.time()
        try:
            step = model.next_step(task, past, shot.image, note)
        except ValueError as e:
            ui.event("end", text=f"[{i}] parse error: {e}")
            return
        pts = [model.to_image_px(p, shot.image) for p in step.action.points]
        gpoints = [shot.to_global(*p) for p in pts]
        image = log_dir / f"{i:02d}.png"
        mark(shot.image, pts).save(image)
        zoom = None
        if opt.refine and step.action.kind in ("click", "left_double", "right_single") and gpoints:
            coarse = gpoints[0]
            zoom = log_dir / f"{i:02d}-zoom.png"
            gpoints[0] = refine(model, shot, coarse, target_of(step, task), zoom)
            ui.event("note", text=f"    refine {coarse} -> {gpoints[0]}")
        with open(log_dir / "steps.jsonl", "a") as f:
            f.write(json.dumps({"step": i, "raw": step.raw, "global": gpoints}, ensure_ascii=False) + "\n")

        focus = windows.info(window) if window else None
        verdict = safety.assess(step.action, focus.name if focus else "")
        risk = {"block": "BLOCKED: ", "confirm": "Risky: "}.get(verdict.level, "") + verdict.reason
        ui.event("step", i=i, secs=time.time() - t, thought=step.thought,
                 action=describe(step, gpoints), image=image, zoom=zoom, risk=risk)
        if step.action.kind == "finished":
            ui.event("finished", text=step.action.text if step.action.text.isascii() else step.thought)
            return
        if verdict.level == "block":
            blocked = verdict.reason
            past.append((shot.image, step.raw))
            continue
        if opt.dry_run:
            past.append((shot.image, step.raw))
            continue
        if safety.needs_confirm(opt.mode, verdict):
            choice = ui.decide(risk)
            if choice == "q":
                ui.event("end", text="Stopped.")
                return
            if choice == "s":
                past.append((shot.image, step.raw))
                continue
            activate(window)  # answering in the terminal stole focus
        if ui.stopped():
            ui.event("end", text="Stopped.")
            return
        execute(step, gpoints)
        acted = step.action.kind != "wait"
        past.append((shot.image, step.raw))
        time.sleep(opt.settle)
    ui.event("end", text=f"Step limit ({opt.max_steps}) reached.")


def cmd_run(args, model: UITars) -> None:
    opt = RunOptions(args.max_side, args.max_steps, args.settle, args.refine, args.dry_run,
                     "full" if args.yolo else args.mode, args.quick, args.window)
    hint = args.monitor
    if not hint and not (opt.quick and quick.match(args.task)) and not windows.find_app(args.task):
        hint = pick_monitor(args).name  # no app in the task: warn if the model would see this terminal
    run_task(model, args.task, CliUI(), opt, hint)


def main() -> None:
    p = argparse.ArgumentParser(prog="jarvis")
    p.add_argument("--server", default="http://127.0.0.1:8081", help="llama-server with UI-TARS")
    p.add_argument("--monitor", help="KWin output name (default: $JARVIS_MONITOR, else monitor under the cursor)")
    p.add_argument("--max-side", type=int, default=1792, help="longer side of the image sent to the model (1792 tested best for 2560x1440)")
    p.add_argument("--coords", choices=["absolute", "relative"], default="absolute")
    p.add_argument("--history", type=int, default=3, help="screenshots kept in context")
    p.add_argument("--language", default="English", help="language of the model's Thought")
    p.add_argument("--no-refine", dest="refine", action="store_false",
                   help="skip the zoom-in second grounding pass for clicks")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shot")
    sub.add_parser("stop", help="stop a running agent (kill switch)")
    c = sub.add_parser("clean", help="delete old run logs from runs/")
    c.add_argument("--days", type=float, default=KEEP_DAYS, help="keep runs newer than this (0 = delete all)")
    g = sub.add_parser("ground")
    g.add_argument("description")
    r = sub.add_parser("run")
    r.add_argument("task")
    r.add_argument("--max-steps", type=int, default=15)
    r.add_argument("--settle", type=float, default=1.0, help="seconds to wait after each action")
    r.add_argument("--dry-run", action="store_true", help="only print actions")
    r.add_argument("--mode", choices=safety.MODES, default="ask",
                   help="ask: confirm every action, auto: only risky ones, full: never ask (blocked stays blocked)")
    r.add_argument("--yolo", action="store_true", help="same as --mode full")
    r.add_argument("--no-quick", dest="quick", action="store_false", help="always use the model, no quick actions")
    r.add_argument("--screen", dest="window", action="store_false",
                   help="capture the whole monitor instead of the app window")
    args = p.parse_args()

    if args.cmd == "stop":
        safety.request_stop()
        print(f"Stop requested ({safety.STOP_FILE}).")
        return
    if args.cmd == "clean":
        removed = cleanup_runs(args.days)
        print(f"Removed {len(removed)} run log(s) older than {args.days:g} days.")
        return
    model = UITars(args.server, args.coords, args.history, args.language)
    try:
        {"shot": cmd_shot, "ground": cmd_ground, "run": cmd_run}[args.cmd](args, model)
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")


if __name__ == "__main__":
    main()
