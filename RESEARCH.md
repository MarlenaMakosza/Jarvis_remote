# JARVIS_REMOTE — research

Zdalne sterowanie komputerem za pomocą lokalnego AI (modele na llama.cpp).
Research z 2026-10-19. Sprzęt: 24 GB VRAM, 256 GB RAM, Manjaro.

## Architektura (pętla agenta)

```
screenshot / drzewo a11y  ->  VLM (llama-server, OpenAI API)  ->  akcja JSON  ->  executor (mysz/klawiatura/shell)  ->  znowu screenshot
```

Każdy krok to jedna akcja, potem weryfikacja nowym screenshotem.

## Modele (GGUF + mmproj)

- **UI-TARS-1.5-7B**: model od ByteDance trenowany specjalnie pod GUI. Jest w GGUF od bartowski i mradermacher. Dobry start.
- **Qwen2.5-VL / Qwen3-VL**: mocny grounding (współrzędne kliknięć). Qwen3-VL-8B lub 30B-A3B daje dobry stosunek jakości do VRAM.
- **Holo1.5 / Holo2 (H Company)**: małe modele 3B–7B pod lokalizację elementów. Nadają się na tani "localizer".
- **GUI-Actor, OS-Atlas, ShowUI**: modele tylko do groundingu, warte sprawdzenia.
- **Split ról**: duży model planuje ("co kliknąć"), mały VLM zwraca współrzędne ("gdzie"). Taki split daje dużo lepsze wyniki niż jeden model do wszystkiego.

Odpalanie (pojedynczy model):

```bash
llama-server -m Qwen3-VL-8B-Q5_K_M.gguf --mmproj mmproj-Qwen3-VL-8B-f16.gguf \
  --jinja -c 16384 -ngl 99 --host 127.0.0.1 --port 8080
```

Pułapka ze współrzędnymi:

- Qwen2.5-VL zwraca piksele obrazu po resize.
- Qwen3-VL zwraca skalę 0–1000.
- UI-TARS liczy na obrazie po smart_resize.

Przeskaluj współrzędne do rozdzielczości ekranu, inaczej kliknięcia lądują obok celu.

## Gotowe frameworki (podpinasz endpoint llama-server)

- **UI-TARS-desktop** (ByteDance): apka desktopowa, przyjmuje dowolny endpoint OpenAI-compatible.
- **Agent S2/S3** (Simular): split planner/grounder, wysokie wyniki na OSWorld.
- **OmniParser v2** (Microsoft): wykrywa elementy UI i numeruje je (set-of-marks). Wtedy nawet słaby model tekstowy wybiera tylko "kliknij #14".
- **Browser Use**: tylko przeglądarka, za to bardzo niezawodny.
- **computer_use_ootb** (showlab), **Computer-Use-Agent** (Holo2-4B): lekkie i lokalne.
- **open-computer-use** (E2B): sandbox w chmurze, nie lokalnie, ale architekturę warto podejrzeć.
- **MCP**: serwery desktop-control plus klient (OpenCode, Jan) z lokalnym modelem.

## Executor na Linuxie (Manjaro)

- X11: `xdotool`, `scrot`/`maim`.
- Wayland: `ydotool` (uinput, działa wszędzie), `dotool`, `wtype`, `grim` do screenshotów. Na KDE są `kdotool` i `spectacle -b`.
- Porządne rozwiązanie pod Wayland: portal `org.freedesktop.portal.RemoteDesktop` + libei.
- **AT-SPI (pyatspi)**: drzewo dostępności GTK/Qt/Firefox z nazwami i pozycjami przycisków. Jest 10x tańsze niż vision. Najpierw próbuj a11y, vision zostaw jako fallback.
- Shell jako narzędzie: często `xdg-open`, `playerctl` czy `kdialog` zrobią robotę szybciej niż klikanie.

## Pomysły na "remote"

- Bot Telegram/Matrix na kompie. Piszesz z telefonu "otwórz X i zrób Y", agent odsyła screenshot i wynik.
- Głos: whisper.cpp (STT) + piper (TTS), wszystko lokalne.
- Webapp na Tailscale: podgląd na żywo (noVNC) + pole komendy + przycisk STOP.
- Tryb "nagraj i powtórz": agent obserwuje twoje kroki i robi z nich makro.
- Agent jako dodatkowy monitor: wirtualny output (Xvfb albo headless output w KWin), więc agent działa obok i nie zabiera ci myszy.

## Bezpieczeństwo

Agent z dostępem do myszy, klawiatury i shella może zrobić dowolną szkodę. Prompt injection działa też przez treść na ekranie: strona może "kazać" agentowi coś wykonać.

- Testuj najpierw w VM albo kontenerze (Xvfb + noVNC).
- Dodaj allowlistę komend i potwierdzanie akcji destrukcyjnych.
- Daj kill-switch (hotkey).
- Endpoint llama-server wystaw tylko na `127.0.0.1` lub w Tailscale, nigdy publicznie.

## Szybki MVP (1 wieczór)

1. Postaw llama-server z Qwen3-VL-8B lub UI-TARS-1.5-7B.
2. Napisz pętlę w Pythonie: `grim` robi screenshot, wysyłasz base64 do `/v1/chat/completions` z promptem "zwróć jedną akcję JSON: click(x,y) | type(text) | key(combo) | done", potem `ydotool`.
3. Dodaj limit kroków i log screenshotów.
4. Dopiero potem rób bota Telegram, a11y i split planner/grounder.

---

## Split ról na 24 GB VRAM + 256 GB RAM

UI-TARS-1.5-7B sam da radę z dużym zapasem, ale split ról wychodzi najlepiej.

### Sam UI-TARS-1.5-7B

- Q8_0 to ok. 8 GB, mmproj ok. 1.3 GB, kontekst kilka GB. Razem ok. 12 GB, cały model na GPU.
- **Dla groundera bierz Q8 albo F16, nie Q4.** Kwantyzacja psuje precyzję współrzędnych, a planner nie jest na nią tak wrażliwy.
- Słabe strony: planowanie długich zadań. Model gubi się po 10+ krokach i słabo się "zastanawia". Dlatego robi się split.

### Grounder (cały na GPU, ok. 10–12 GB)

- UI-TARS-1.5-7B Q8, albo
- Qwen3-VL-8B Q8. Ma podobny grounding, lepiej trzyma format JSON, zwraca współrzędne 0–1000.
- Jako alternatywę testuj Holo2 (mniejszy i szybszy).

### Planner (eksperci MoE w RAM, attention na GPU, ok. 8–10 GB VRAM)

- **Qwen3-VL-30B-A3B** (Q6/Q8): widzi screenshot, jest szybki (3B aktywnych), zrobi kilkadziesiąt t/s. Start od tego.
- **Qwen3-VL-235B-A22B** (Q4 ok. 130 GB w RAM): najmądrzejszy planner z wizją. Wolny, rzędu kilku t/s, zależnie od przepustowości RAM. Wystarczy, bo planner zwraca krótkie odpowiedzi.
- **gpt-oss-120b / GLM-4.5-Air**: tylko tekst. Mają sens z drzewem a11y (AT-SPI) albo OmniParserem zamiast screenshota.

### Odpalanie (dwa serwery)

```bash
# grounder: cały na GPU
llama-server -m UI-TARS-1.5-7B-Q8_0.gguf --mmproj mmproj-UI-TARS-1.5-7B-f16.gguf \
  -ngl 99 -c 8192 --port 8081 --host 127.0.0.1

# planner: eksperci MoE na CPU, reszta na GPU
llama-server -m Qwen3-VL-30B-A3B-Instruct-Q8_0.gguf --mmproj mmproj-Qwen3-VL-30B-A3B-f16.gguf \
  -ngl 99 --n-cpu-moe 48 -c 32768 --jinja --port 8080 --host 127.0.0.1
```

Stroisz `--n-cpu-moe`: zmniejszaj wartość, dopóki suma VRAM obu serwerów mieści się w ok. 22 GB. Dla 235B ustaw prawie wszystkie warstwy na CPU i `-t` równe liczbie fizycznych rdzeni.

### Podział pracy

1. Planner dostaje cel, historię kroków i screenshot (zmniejszony, np. 1280x720). Zwraca `{"action":"click","target":"przycisk Zapisz w prawym górnym rogu"}` albo `type` / `key` / `shell` / `done`.
2. Grounder dostaje screenshot i opis `target`. Zwraca tylko współrzędne.
3. Executor skaluje współrzędne do rozdzielczości ekranu i wykonuje akcję (`ydotool`/`xdotool`).
4. Planner dostaje nowy screenshot i ocenia, czy akcja zadziałała.

### Pułapki

- **Skalowanie:** sam zmniejszaj screenshot do znanej rozdzielczości przed wysłaniem. Wtedy wiesz, w jakim układzie są współrzędne. Sprawdź, czy twoja wersja llama.cpp nie skaluje obrazu po swojemu (flagi `--image-min-tokens`/`--image-max-tokens` w nowszych buildach).
- **Prompt UI-TARS:** model oczekuje swojego formatu (`Thought: ... Action: click(start_box='(x,y)')`). Używaj oficjalnego szablonu z repo, nie własnego JSON.
- **Wspólne GPU:** dwa serwery konkurują o GPU. Na pojedynczym kroku to nie przeszkadza, bo planner i grounder działają po kolei.

### Kolejność testów

1. Sam Qwen3-VL-30B-A3B jako planner i grounder w jednym, żeby mieć baseline.
2. Dodaj UI-TARS jako grounder i porównaj trafność kliknięć.
3. Przy złożonych zadaniach podmień planner na 235B.

---

## Pobieranie modeli

Cel: `/home/lenerystia/Models/llama.cpp-cache`. Nazwy plików sprawdzone w HF API.

### Opcja A: `hf` CLI

```bash
uv tool install huggingface_hub   # albo: pipx install huggingface_hub
export HF_XET_HIGH_PERFORMANCE=1   # HF_HUB_ENABLE_HF_TRANSFER jest deprecated
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

# Duży planner (opcjonalny): Qwen3-VL-235B-A22B UD-Q4_K_XL (~135 GB, 3 shardy)
hf download unsloth/Qwen3-VL-235B-A22B-Instruct-GGUF \
  --include "UD-Q4_K_XL/*" "mmproj-F16.gguf" \
  --local-dir $M/Qwen3-VL-235B-A22B-Instruct
```

Każdy model do osobnego folderu: repo unsloth mają mmproj o tej samej nazwie (`mmproj-F16.gguf`).

### Opcja B: wbudowane `-hf` w llama.cpp

```bash
export LLAMA_CACHE=/home/lenerystia/Models/llama.cpp-cache
llama-server -hf mradermacher/UI-TARS-1.5-7B-GGUF:Q8_0 --port 8081
llama-server -hf unsloth/Qwen3-VL-8B-Instruct-GGUF:Q8_0 --port 8082
llama-server -hf unsloth/Qwen3-VL-30B-A3B-Instruct-GGUF:Q8_0 --port 8080
llama-server -hf unsloth/Qwen3-VL-235B-A22B-Instruct-GGUF:UD-Q4_K_XL --port 8083
```

llama.cpp sam pobiera model i pasujący mmproj. Komendy od razu uruchamiają serwer.

Razem ok. 185 GB z 235B, ok. 50 GB bez niego. Na start wystarczy UI-TARS i 30B-A3B.

---

## Źródła

- [Computer-Use-Agent (Holo2-4B)](https://github.com/BrAtUkA/Computer-Use-Agent)
- [Local GUI agent, LLM-as-Judge (arXiv)](https://arxiv.org/html/2506.03095v1)
- [Control computer with AI agents 2026 (pinggy)](https://pinggy.io/amp/blog/control_computer_with_ai_agents/)
- [computer_use_ootb](https://www.sourcepulse.org/projects/1842021)
- [UI-TARS-7B-DPO-GGUF](https://huggingface.co/bartowski/UI-TARS-7B-DPO-GGUF)
- [UI-TARS-7B-SFT-GGUF](https://huggingface.co/bartowski/UI-TARS-7B-SFT-GGUF)
- [ui-tars-1.5-7b GGUF](https://huggingface.co/mradermacher/ui-tars-1.5-7b-idm-full-sft-i1-GGUF)
- [open-computer-use](https://github.com/solizardking/open-computer-use)
- [Running Agentic AI Offline on Linux](https://2026.everythingopen.au/schedule/presentation/9/)
