# JARVIS_REMOTE — research

[Wersja polska](PL/RESEARCH.md)

Remote control of a computer with local AI (models on llama.cpp).
Research from 2026-10-19. Hardware: 24 GB VRAM, 256 GB RAM, Manjaro.

## Architecture (agent loop)

```
screenshot / a11y tree  ->  VLM (llama-server, OpenAI API)  ->  JSON action  ->  executor (mouse/keyboard/shell)  ->  screenshot again
```

Each step is one action, then verification with a new screenshot.

## Models (GGUF + mmproj)

- **UI-TARS-1.5-7B**: a ByteDance model trained specifically for GUIs. Available as GGUF from bartowski and mradermacher. Good start.
- **Qwen2.5-VL / Qwen3-VL**: strong grounding (click coordinates). Qwen3-VL-8B or 30B-A3B gives a good quality-to-VRAM ratio.
- **Holo1.5 / Holo2 (H Company)**: small 3B–7B models for locating elements. Suitable as a cheap "localizer".
- **GUI-Actor, OS-Atlas, ShowUI**: grounding-only models, worth checking.
- **Role split**: a large model plans ("what to click"), a small VLM returns coordinates ("where"). This split gives much better results than one model for everything.

Running (single model):

```bash
llama-server -m Qwen3-VL-8B-Q5_K_M.gguf --mmproj mmproj-Qwen3-VL-8B-f16.gguf \
  --jinja -c 16384 -ngl 99 --host 127.0.0.1 --port 8080
```

Coordinate pitfall:

- Qwen2.5-VL returns pixels of the resized image.
- Qwen3-VL returns a 0–1000 scale.
- UI-TARS works on the image after smart_resize.

Rescale the coordinates to the screen resolution, otherwise clicks land next to the target.

## Ready-made frameworks (plug in the llama-server endpoint)

- **UI-TARS-desktop** (ByteDance): desktop app, accepts any OpenAI-compatible endpoint.
- **Agent S2/S3** (Simular): planner/grounder split, high scores on OSWorld.
- **OmniParser v2** (Microsoft): detects UI elements and numbers them (set-of-marks). Then even a weak text model only picks "click #14".
- **Browser Use**: browser only, but very reliable.
- **computer_use_ootb** (showlab), **Computer-Use-Agent** (Holo2-4B): lightweight and local.
- **open-computer-use** (E2B): cloud sandbox, not local, but the architecture is worth a look.
- **MCP**: desktop-control servers plus a client (OpenCode, Jan) with a local model.

## Executor on Linux (Manjaro)

- X11: `xdotool`, `scrot`/`maim`.
- Wayland: `ydotool` (uinput, works everywhere), `dotool`, `wtype`, `grim` for screenshots. KDE has `kdotool` and `spectacle -b`.
- The proper Wayland solution: the `org.freedesktop.portal.RemoteDesktop` portal + libei.
- **AT-SPI (pyatspi)**: GTK/Qt/Firefox accessibility tree with button names and positions. It is 10x cheaper than vision. Try a11y first, keep vision as a fallback.
- Shell as a tool: `xdg-open`, `playerctl` or `kdialog` often do the job faster than clicking.

## "Remote" ideas

- Telegram/Matrix bot on the computer. You write from the phone "open X and do Y", the agent sends back a screenshot and the result.
- Voice: whisper.cpp (STT) + piper (TTS), all local.
- Web app over Tailscale: live preview (noVNC) + command field + STOP button.
- "Record and replay" mode: the agent watches your steps and turns them into a macro.
- Agent as an extra monitor: a virtual output (Xvfb or a headless output in KWin), so the agent works alongside you and does not take your mouse.

## Safety

An agent with access to the mouse, keyboard and shell can do any damage. Prompt injection also works through on-screen content: a web page can "tell" the agent to do something.

- Test in a VM or container first (Xvfb + noVNC).
- Add a command allowlist and confirmation of destructive actions.
- Provide a kill switch (hotkey).
- Expose the llama-server endpoint only on `127.0.0.1` or in Tailscale, never publicly.

## Quick MVP (1 evening)

1. Start llama-server with Qwen3-VL-8B or UI-TARS-1.5-7B.
2. Write a loop in Python: `grim` takes a screenshot, you send base64 to `/v1/chat/completions` with the prompt "return one JSON action: click(x,y) | type(text) | key(combo) | done", then `ydotool`.
3. Add a step limit and a screenshot log.
4. Only then build the Telegram bot, a11y and the planner/grounder split.

---

## Role split on 24 GB VRAM + 256 GB RAM

UI-TARS-1.5-7B alone fits with plenty of headroom, but the role split works best.

### UI-TARS-1.5-7B alone

- Q8_0 is about 8 GB, mmproj about 1.3 GB, context a few GB. About 12 GB in total, the whole model on the GPU.
- **For the grounder use Q8 or F16, not Q4.** Quantization hurts coordinate precision, and the planner is not as sensitive to it.
- Weaknesses: planning long tasks. The model gets lost after 10+ steps and "reasons" poorly. That is why the split is used.

### Grounder (fully on GPU, about 10–12 GB)

- UI-TARS-1.5-7B Q8, or
- Qwen3-VL-8B Q8. Similar grounding, keeps the JSON format better, returns 0–1000 coordinates.
- Test Holo2 as an alternative (smaller and faster).

### Planner (MoE experts in RAM, attention on GPU, about 8–10 GB VRAM)

- **Qwen3-VL-30B-A3B** (Q6/Q8): sees the screenshot, is fast (3B active), does tens of t/s. Start with this one.
- **Qwen3-VL-235B-A22B** (Q4 about 130 GB in RAM): the smartest planner with vision. Slow, a few t/s, depending on RAM bandwidth. Enough, because the planner returns short answers.
- **gpt-oss-120b / GLM-4.5-Air**: text only. They make sense with an a11y tree (AT-SPI) or OmniParser instead of a screenshot.

### Running (two servers)

```bash
# grounder: fully on GPU
llama-server -m UI-TARS-1.5-7B-Q8_0.gguf --mmproj mmproj-UI-TARS-1.5-7B-f16.gguf \
  -ngl 99 -c 8192 --port 8081 --host 127.0.0.1

# planner: MoE experts on CPU, the rest on GPU
llama-server -m Qwen3-VL-30B-A3B-Instruct-Q8_0.gguf --mmproj mmproj-Qwen3-VL-30B-A3B-f16.gguf \
  -ngl 99 --n-cpu-moe 48 -c 32768 --jinja --port 8080 --host 127.0.0.1
```

Tune `--n-cpu-moe`: lower the value while the combined VRAM of both servers fits in about 22 GB. For 235B put almost all layers on the CPU and set `-t` to the number of physical cores.

### Division of work

1. The planner gets the goal, step history and a screenshot (downscaled, e.g. 1280x720). It returns `{"action":"click","target":"Save button in the top right corner"}` or `type` / `key` / `shell` / `done`.
2. The grounder gets the screenshot and the `target` description. It returns only coordinates.
3. The executor scales the coordinates to the screen resolution and performs the action (`ydotool`/`xdotool`).
4. The planner gets a new screenshot and judges whether the action worked.

### Pitfalls

- **Scaling:** downscale the screenshot yourself to a known resolution before sending it. Then you know which coordinate system you are in. Check that your llama.cpp version does not rescale the image on its own (`--image-min-tokens`/`--image-max-tokens` flags in newer builds).
- **UI-TARS prompt:** the model expects its own format (`Thought: ... Action: click(start_box='(x,y)')`). Use the official template from the repo, not your own JSON.
- **Shared GPU:** two servers compete for the GPU. For a single step this does not matter, because the planner and grounder run one after another.

### Test order

1. Qwen3-VL-30B-A3B alone as planner and grounder in one, to get a baseline.
2. Add UI-TARS as the grounder and compare click accuracy.
3. For complex tasks swap the planner for 235B.

---

## Downloading models

Target: `/home/lenerystia/Models/llama.cpp-cache`. File names checked against the HF API.

### Option A: `hf` CLI

```bash
uv tool install huggingface_hub   # or: pipx install huggingface_hub
export HF_XET_HIGH_PERFORMANCE=1   # HF_HUB_ENABLE_HF_TRANSFER is deprecated
M=/home/lenerystia/Models/llama.cpp-cache

# Grounder 1: UI-TARS-1.5-7B Q8 (~8 GB + ~1.3 GB mmproj)
hf download mradermacher/UI-TARS-1.5-7B-GGUF \
  UI-TARS-1.5-7B.Q8_0.gguf UI-TARS-1.5-7B.mmproj-f16.gguf \
  --local-dir $M/UI-TARS-1.5-7B

# Grounder 2: Qwen3-VL-8B Q8 (~9 GB)
hf download unsloth/Qwen3-VL-8B-Instruct-GGUF \
  Qwen3-VL-8B-Instruct-Q8_0.gguf mmproj-F16.gguf \
  --local-dir $M/Qwen3-VL-8B-Instruct

# Planner: Qwen3-VL-30B-A3B Q8 (~32 GB)
hf download unsloth/Qwen3-VL-30B-A3B-Instruct-GGUF \
  Qwen3-VL-30B-A3B-Instruct-Q8_0.gguf mmproj-F16.gguf \
  --local-dir $M/Qwen3-VL-30B-A3B-Instruct

# Large planner (optional): Qwen3-VL-235B-A22B UD-Q4_K_XL (~135 GB, 3 shards)
hf download unsloth/Qwen3-VL-235B-A22B-Instruct-GGUF \
  --include "UD-Q4_K_XL/*" "mmproj-F16.gguf" \
  --local-dir $M/Qwen3-VL-235B-A22B-Instruct
```

Each model in its own folder: the unsloth repos have an mmproj with the same name (`mmproj-F16.gguf`).

### Option B: built-in `-hf` in llama.cpp

```bash
export LLAMA_CACHE=/home/lenerystia/Models/llama.cpp-cache
llama-server -hf mradermacher/UI-TARS-1.5-7B-GGUF:Q8_0 --port 8081
llama-server -hf unsloth/Qwen3-VL-8B-Instruct-GGUF:Q8_0 --port 8082
llama-server -hf unsloth/Qwen3-VL-30B-A3B-Instruct-GGUF:Q8_0 --port 8080
llama-server -hf unsloth/Qwen3-VL-235B-A22B-Instruct-GGUF:UD-Q4_K_XL --port 8083
```

llama.cpp downloads the model and the matching mmproj itself. The commands start the server right away.

About 185 GB in total with 235B, about 50 GB without it. UI-TARS and 30B-A3B are enough to start.

---

## Sources

- [Computer-Use-Agent (Holo2-4B)](https://github.com/BrAtUkA/Computer-Use-Agent)
- [Local GUI agent, LLM-as-Judge (arXiv)](https://arxiv.org/html/2506.03095v1)
- [Control computer with AI agents 2026 (pinggy)](https://pinggy.io/amp/blog/control_computer_with_ai_agents/)
- [computer_use_ootb](https://www.sourcepulse.org/projects/1842021)
- [UI-TARS-7B-DPO-GGUF](https://huggingface.co/bartowski/UI-TARS-7B-DPO-GGUF)
- [UI-TARS-7B-SFT-GGUF](https://huggingface.co/bartowski/UI-TARS-7B-SFT-GGUF)
- [ui-tars-1.5-7b GGUF](https://huggingface.co/mradermacher/ui-tars-1.5-7b-idm-full-sft-i1-GGUF)
- [open-computer-use](https://github.com/solizardking/open-computer-use)
- [Running Agentic AI Offline on Linux](https://2026.everythingopen.au/schedule/presentation/9/)
