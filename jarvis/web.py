"""Phone web app for JARVIS_REMOTE (LAN, no extra dependencies).

  python -m jarvis.web --monitor DP-5

Prints a URL with an access token (and a QR code). Open it on the phone once;
the token is then kept in a cookie. Anyone with the token controls this PC.
"""

import argparse
import hmac
import io
import json
import os
import re
import secrets
import subprocess
import threading
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image

from . import actions, quick, screen
from .agent import RUNS, RunOptions, run_task
from .uitars import UITars

STATIC = Path(__file__).resolve().parent / "static"
TOKEN_FILE = Path.home() / ".config" / "jarvis" / "token"


def load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(token + "\n")
    TOKEN_FILE.chmod(0o600)
    return token


class WebUI:
    """Shared state between the agent thread and HTTP handlers."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"        # idle, thinking, waiting, acting
        self.task = ""
        self.monitor = ""
        self.run_id = ""
        self.steps: list[dict] = []
        self.log: list[str] = []
        self.result = ""
        self.version = 0            # bumped on every change, lets the page skip redraws
        self._choice: str | None = None
        self._decided = threading.Event()
        self._stop = threading.Event()
        self.thread: threading.Thread | None = None

    def _changed(self) -> None:
        self.version += 1

    # --- interface used by agent.run_task ---
    def event(self, kind: str, **d) -> None:
        with self.lock:
            match kind:
                case "start":
                    self.run_id = Path(d["log_dir"]).name
                    self.monitor = d["monitor"]
                    self.status = "thinking"
                case "note":
                    self.log.append(d["text"].strip())
                case "step":
                    self.steps.append({
                        "i": d["i"], "secs": round(d["secs"], 1), "thought": d["thought"], "action": d["action"],
                        "image": f"/img/{self.run_id}/{Path(d['image']).name}",
                        "zoom": f"/img/{self.run_id}/{Path(d['zoom']).name}" if d["zoom"] else None,
                    })
                    self.status = "acting"
                case "finished" | "end":
                    self.result = d["text"]
                    self.status = "idle"
            self.log = self.log[-50:]
            self._changed()

    def decide(self) -> str:
        with self.lock:
            self.status = "waiting"
            self._choice = None
            self._decided.clear()
            self._changed()
        while not self._decided.wait(0.2):
            if self._stop.is_set():
                return "q"
        with self.lock:
            self.status = "thinking" if self._choice == "s" else "acting"
            self._changed()
            return self._choice or "q"

    def stopped(self) -> bool:
        return self._stop.is_set()

    # --- called from HTTP handlers ---
    def set_choice(self, choice: str) -> None:
        with self.lock:
            if self.status == "waiting":
                self._choice = choice
                self._decided.set()

    def stop(self) -> None:
        self._stop.set()
        self._decided.set()

    def clear(self) -> None:
        with self.lock:
            self.task, self.monitor, self.steps, self.log, self.result = "", "", [], [], ""
            self._changed()

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, target, task: str) -> None:
        with self.lock:
            self.task, self.steps, self.log, self.result = task, [], [], ""
            self.status = "thinking"
            self._stop.clear()
            self._changed()
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def snapshot(self) -> dict:
        with self.lock:
            return {"version": self.version, "status": self.status, "task": self.task, "monitor": self.monitor,
                    "steps": self.steps, "log": self.log, "result": self.result}


class App:
    def __init__(self, args):
        self.args = args
        self.token = load_token()
        self.ui = WebUI()
        self.model = UITars(args.server, args.coords, args.history)

    def monitor(self) -> screen.Monitor:
        return screen.find_monitor(self.args.monitor or os.environ.get("JARVIS_MONITOR"), actions.cursor())

    def run(self, task: str, auto: bool, max_steps: int) -> None:
        opt = RunOptions(max_side=self.args.max_side, max_steps=max_steps, refine=self.args.refine, auto=auto)

        def target():
            try:
                run_task(self.model, task, self.ui, opt, self.args.monitor)
            except Exception as e:  # report to the phone instead of dying silently
                self.ui.event("end", text=f"Error: {type(e).__name__}: {e}")

        self.ui.start(target, task)


def jpeg(img: Image.Image, max_width: int = 1280) -> bytes:
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):  # keep the terminal quiet
            pass

        def _authed(self) -> bool:
            c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
            given = c["jarvis"].value if "jarvis" in c else self.headers.get("X-Token", "")
            return hmac.compare_digest(given, app.token)

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                token = parse_qs(url.query).get("t", [""])[0]
                if token and hmac.compare_digest(token, app.token):
                    # Move the token into a cookie and drop it from the address bar.
                    self._send(303, b"", "text/plain", {
                        "Location": "/",
                        "Set-Cookie": f"jarvis={app.token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict",
                    })
                    return
                if not self._authed():
                    self._send(401, "Brak dostępu. Otwórz link z tokenem z terminala.".encode(), "text/plain; charset=utf-8")
                    return
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                return
            if url.path in ("/manifest.json", "/icon.svg"):
                ctype = "application/manifest+json" if url.path.endswith(".json") else "image/svg+xml"
                self._send(200, (STATIC / url.path[1:]).read_bytes(), ctype)
                return
            if not self._authed():
                self._json({"error": "unauthorized"}, 401)
                return
            if url.path == "/api/state":
                self._json(app.ui.snapshot())
            elif m := re.fullmatch(r"/img/(\d{8}-\d{6})/(\d{2}(?:-zoom)?\.png)", url.path):
                path = RUNS / m[1] / m[2]
                if path.exists():
                    self._send(200, jpeg(Image.open(path)), "image/jpeg")
                else:
                    self._json({"error": "not found"}, 404)
            elif url.path == "/api/live":
                shot = screen.capture(app.monitor(), 1792)
                self._send(200, jpeg(shot.native), "image/jpeg")
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if not self._authed():
                self._json({"error": "unauthorized"}, 401)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "bad json"}, 400)
                return
            path = urlparse(self.path).path
            if path == "/api/run":
                task = str(body.get("task", "")).strip()
                if not task:
                    self._json({"error": "empty task"}, 400)
                elif app.ui.busy():
                    self._json({"error": "agent is busy"}, 409)
                else:
                    app.run(task, bool(body.get("auto")), int(body.get("max_steps", 15)))
                    self._json({"ok": True})
            elif path == "/api/decide":
                choice = body.get("choice")
                if choice in ("y", "s", "q"):
                    app.ui.set_choice(choice)
                    self._json({"ok": True})
                else:
                    self._json({"error": "choice must be y, s or q"}, 400)
            elif path == "/api/quick":
                q = quick.ACTIONS.get(body.get("name"))
                if not q:
                    self._json({"error": f"unknown quick action, one of {list(quick.ACTIONS)}"}, 400)
                    return
                try:
                    q.run()
                except Exception as e:
                    self._json({"error": f"{type(e).__name__}: {e}"}, 500)
                    return
                self._json({"ok": True, "label": q.label})
            elif path == "/api/clear":
                if app.ui.busy():
                    self._json({"error": "agent is busy"}, 409)
                else:
                    app.ui.clear()
                    self._json({"ok": True})
            elif path == "/api/stop":
                app.ui.stop()
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def lan_ip() -> str:
    out = subprocess.run(["ip", "-4", "route", "get", "1.1.1.1"], capture_output=True, text=True).stdout
    m = re.search(r"src (\S+)", out)
    return m[1] if m else "127.0.0.1"


def main() -> None:
    p = argparse.ArgumentParser(prog="jarvis.web")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--server", default="http://127.0.0.1:8081", help="llama-server with UI-TARS")
    p.add_argument("--monitor", help="KWin output name (default: $JARVIS_MONITOR, else monitor under the cursor)")
    p.add_argument("--max-side", type=int, default=1792)
    p.add_argument("--coords", choices=["absolute", "relative"], default="absolute")
    p.add_argument("--history", type=int, default=3)
    p.add_argument("--no-refine", dest="refine", action="store_false")
    args = p.parse_args()

    app = App(args)
    url = f"http://{lan_ip()}:{args.port}/?t={app.token}"
    print(f"JARVIS web: {url}")
    subprocess.run(["qrencode", "-t", "ANSIUTF8", url])
    print(f"Token file: {TOKEN_FILE} (delete it to revoke access)")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        app.ui.stop()
        print("\nBye.")


if __name__ == "__main__":
    main()
