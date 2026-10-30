# JARVIS_REMOTE — draft

[Wersja polska](PL/README.md)

Local computer-use agent: UI-TARS-1.5-7B on llama-server drives the mouse and keyboard on KDE Plasma (Wayland).
Research and plan: [RESEARCH.md](RESEARCH.md).

## Requirements (verified on this machine)

- KDE Plasma 6, Wayland, 2560x1440 monitors (DP-3, DP-4, DP-5)
- `spectacle` (screenshots; `grim` does not work on KWin)
- `ydotool` + `ydotoold` (mouse/keyboard via uinput), `kdotool` (cursor position, active window)
- `qdbus6` (monitor geometry from KWin), `wl-copy` (pasting Polish characters)
- Python with `pillow` and `requests` (the system Python has them)

## Running

```bash
./start_uitars.sh                      # llama-server with UI-TARS on :8081

python -m jarvis.agent shot            # save what the model sees (runs/shot.png)
python -m jarvis.agent ground "Save As button"      # move the cursor to an element, no click
python -m jarvis.agent run "Open Firefox and go to wikipedia.org"
python -m jarvis.agent run "..." --dry-run          # only print the actions
python -m jarvis.agent run "In Vivaldi ..."          # app named in the task: the agent activates its window and sees only that window
python -m jarvis.agent run "..." --screen           # whole monitor instead of the window
python -m jarvis.agent run "pause youtube"          # quick action: playerctl, no model (--no-quick disables)
python -m jarvis.agent --monitor DP-4 run "..."     # pick a monitor when the task names no app
export JARVIS_MONITOR=DP-5                          # or set it permanently (default: monitor under the cursor)
```

From a phone (same Wi-Fi network):

```bash
python -m jarvis.web --monitor DP-5        # prints a link with a token and a QR code, port 8765
```

Scan the QR code with the phone. The token goes into a cookie, and you can add the link to the home screen as an app.
The web app has a task field, a screenshot with the target marked, Run / Skip buttons, STOP and a screen preview.
The token is stored in `~/.config/jarvis/token`. Deleting the file and restarting the server invalidates old links.
Whoever has the token controls the computer: do not share the link and do not expose the port outside the home network.

## Safety

Confirmation modes (`--mode` in the CLI, a switch in the web app):

- `ask` (default): asks before every action (Enter = run, s = skip, q = stop).
- `auto`: asks only about risky actions: text that looks like a dangerous command (`sudo`, `rm -rf`, `curl | sh`, `git push`…), a command typed into the launcher, shortcuts that close or delete (`alt+f4`, `ctrl+w`, `ctrl+q`, Delete, Super).
- `full` (or `--yolo`): never asks.

The rules are in `jarvis/safety.py`. Typing in a terminal is allowed.

Stopping the agent before its next action:

```bash
python -m jarvis.agent stop       # or scripts/jarvis-stop.sh, or STOP in the web app
```

For a global KDE shortcut: System Settings → Shortcuts → Add New → Command or Script → `scripts/jarvis-stop.sh`.
`scripts/install-killswitch.sh [shortcut]` does the same from the command line, but the shortcut may only work after logging in again, and it does not check for conflicts with default KDE shortcuts.
Every run is saved in `runs/<date>/`: screenshots with the click point marked and `steps.jsonl` with the raw model responses.
Runs older than 7 days are deleted automatically when a task starts (`JARVIS_KEEP_DAYS` changes the limit). Manually: `python -m jarvis.agent clean [--days N]`, `--days 0` deletes all of them.

## Structure

- `jarvis/screen.py`: monitor geometry from KWin, screenshot, rescaling to multiples of 28 px.
- `jarvis/actions.py`: mouse and keyboard. Cursor movement in a correction loop: ydotool moves relatively, kdotool reads the position.
- `jarvis/uitars.py`: UI-TARS prompts, llama-server requests, action parser.
- `jarvis/agent.py`: agent loop (`run_task`, pluggable UI interface) and CLI.
- `jarvis/windows.py`: finding, activating and measuring app windows (kdotool).
- `jarvis/quick.py`: quick actions without the model: media, volume, opening pages, launching and switching apps.
- `jarvis/safety.py`: confirmation modes, action risk checks, kill switch (file `$XDG_RUNTIME_DIR/jarvis.stop`).
- `scripts/`: `jarvis-stop.sh` (kill switch with a notification) and `install-killswitch.sh`.
- `jarvis/web.py` + `jarvis/static/`: phone web app (stdlib `http.server`, no extra dependencies).

## Test findings (2026-10-19)

- `ydotool mousemove --absolute` on KWin lands in the wrong place, and relative movement is distorted by acceleration. A correction loop that reads the position with `kdotool getmouselocation` is pixel-accurate in about 0.4 s.
- Image resolution for the model matters a lot. At 1288 px (long side) UI-TARS missed half of the targets, at 1792 px it hit all 4 test targets. At the full 2560 px llama.cpp downscales the image itself and the coordinates stop matching. The default is 1792.
- Step time on an RX 7900 XTX: about 2.3 s grounding, about 3 s for a full agent step, +1.1 s for click refinement.
- UI-TARS-7B misses thin targets (a bar about 20 px high) by about 20 px vertically. A second grounding pass on a 630x350 px crop magnified 2x fixes this: from four deliberately wrong starting points (up to 40 px off) all of them hit the Terminal tab in Kate. Enabled by default, `--no-refine` disables it.
- Without context UI-TARS confuses similar elements (the "Terminal" tab in Kate vs terminal icons on the taskbar) and announces success without checking. The agent compares screenshots before and after an action and tells the model when the action changed nothing.
- UI-TARS ignores the request for English in `finished(content=...)` and often writes in Chinese. The agent then prints the Thought instead.

## TODO

Plan for further work: [PLAN.md](PLAN.md).
