# JARVIS_REMOTE — plan

[Wersja polska](PL/PLAN.md)

Status as of 2026-10-19: UI-TARS-1.5-7B works (alone, no planner) with a second targeting pass, a CLI and a phone web app on the LAN.

Proposed order: 0 → 1 → 2 → 5 → 8, the rest later.

## 0. To do right away

- [ ] `git init` in `JARVIS_REMOTE`. The directory is not a repo yet, so changes cannot be undone without a copy.
- [ ] Download the Qwen3-VL-30B-A3B-Instruct planner (command in [RESEARCH.md](RESEARCH.md#downloading-models)).

## Reliability (biggest win)

1. [~] **Tools instead of clicking.** Simple tasks through commands, without the vision model. Done as quick actions (`jarvis/quick.py`, matching short commands + buttons in the web app): media through playerctl, volume through wpctl, `xdg-open`, launching and switching apps, screen lock. Remaining: the planner picks the tool instead of fixed patterns.
   - `playerctl play-pause` for "pause YouTube" (MPRIS in Vivaldi),
   - `xdg-open URL` for "open site X",
   - `kdotool search <app> windowactivate` for "switch to window".

   The agent tries a tool first and clicks only when no tool fits.
2. [x] **Automatic monitor selection.** The agent sees one monitor, so a task in an app on another monitor fails. Find the app window with `kdotool search`, take its monitor and activate the window.
3. [x] **Window mode.** Screenshot of the app window only instead of the whole monitor: the taskbar disappears (a source of "Terminal" in Kate vs terminal icon mix-ups), and resolution goes up for the same number of tokens.
4. [ ] **Qwen3-VL-30B-A3B planner** (port 8080). The planner describes the target and verifies the result of each step, UI-TARS (`UITars.ground` + refinement) only returns coordinates. Fixes announcing success without checking and ambiguous targets.

## Convenience

5. [-] (skipped: autostart not needed) **systemd `--user` services** for UI-TARS (llama-server), `ydotoold` and the web app, so everything starts with the system without open terminals.
6. [ ] **Speed.** Steps slow down from about 4 s to about 9 s, because the sliding history window changes the start of the prompt and the llama.cpp cache stops working (about 7.5k tokens computed from scratch every step). Options: `--history 2` or a stable prompt (one screenshot + text-only history).
7. [x] **Cleaning up `runs/`.** When each task starts, runs older than 7 days are deleted (`JARVIS_KEEP_DAYS`), manually `python -m jarvis.agent clean`.

## Safety

8. [x] **Kill switch.** `python -m jarvis.agent stop`, `scripts/jarvis-stop.sh` (for a custom KDE shortcut) and STOP in the web app. The agent stops before its next action.
9. [x] **Action guards** (`jarvis/safety.py`). Typing in a terminal is allowed. Confirmation is required for: text that looks like a dangerous command (`sudo`, `rm -rf`, `curl | sh`, `git push`…), commands typed into the launcher, and shortcuts that close or delete (`alt+f4`, `ctrl+w`, `ctrl+q`, Delete, Super). Ask mode asks about everything, auto only about these, full about nothing.

## Untested (code exists, no test)

10. [ ] Scroll direction (`actions.scroll`, sign of REL_WHEEL).
11. [ ] Polish characters: pasting through `wl-copy` + ctrl+v. Terminals need ctrl+shift+v.
12. [ ] Drag and double-click.

## Later

13. [ ] AT-SPI: accessibility tree instead of screenshots where the app exposes it (GTK/Qt/Firefox).
14. [ ] Voice through whisper.cpp. Recording in the browser requires HTTPS on the page, so for now dictation from the phone keyboard stays.

## Ideas from existing projects

Open source review from 2026-10-19: no project combines a local model on llama.cpp, KDE Wayland, a real desktop and phone control, so we build our own. Worth borrowing:

15. [ ] **Manual mode on the phone** (from [contop](https://github.com/slopedrop/contop)): tapping the screen preview clicks that spot on the computer, without the model. For correcting the agent when it gets stuck.
16. [ ] **Live preview** (from contop): a refreshing screenshot or a stream instead of the one-off "Screen preview".
17. [x] **ask / auto / full modes** (from [Open WebUI Computer](https://docs.openwebui.com/ecosystem/computer/)) instead of a single "no prompts" switch. For example: ask asks about everything, auto asks only about risky actions (item 9), full never asks.
18. [ ] **Test sandbox** (from [Bytebot](https://github.com/bytebot-ai/bytebot)): a separate desktop in a container or VM for checking risky tasks before the agent gets the real desktop.

Worth reading the code of: [UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) (prompts and action parser for the same model).
