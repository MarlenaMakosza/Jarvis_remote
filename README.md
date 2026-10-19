# JARVIS_REMOTE — draft

Lokalny agent computer-use: UI-TARS-1.5-7B na llama-server steruje myszą i klawiaturą na KDE Plasma (Wayland).
Research i plan: [RESEARCH.md](RESEARCH.md).

## Wymagania (sprawdzone na tej maszynie)

- KDE Plasma 6, Wayland, monitory 2560x1440 (DP-3, DP-4, DP-5)
- `spectacle` (zrzuty ekranu; `grim` nie działa na KWin)
- `ydotool` + `ydotoold` (mysz/klawiatura przez uinput), `kdotool` (odczyt pozycji kursora, aktywne okno)
- `qdbus6` (geometria monitorów z KWin), `wl-copy` (wklejanie polskich znaków)
- Python z `pillow` i `requests` (systemowy Python je ma)

## Uruchomienie

```bash
./start_uitars.sh                      # llama-server z UI-TARS na :8081

python -m jarvis.agent shot            # zapisz to, co widzi model (runs/shot.png)
python -m jarvis.agent ground "Save As button"      # przesuń kursor na element, bez klikania
python -m jarvis.agent run "Open Firefox and go to wikipedia.org"
python -m jarvis.agent run "..." --dry-run          # tylko wypisuje akcje
python -m jarvis.agent --monitor DP-4 run "..."     # wybór monitora
export JARVIS_MONITOR=DP-5                          # albo na stałe (domyślnie: monitor pod kursorem)
```

Z telefonu (ta sama sieć Wi-Fi):

```bash
python -m jarvis.web --monitor DP-5        # wypisuje link z tokenem i kod QR, port 8765
```

Zeskanuj QR telefonem. Token trafia do ciasteczka, a link można dodać do ekranu głównego jako apkę.
Webapka ma pole polecenia, zrzut z zaznaczonym celem, przyciski Wykonaj / Pomiń, STOP i podgląd ekranu.
Token leży w `~/.config/jarvis/token`. Usunięcie pliku i restart serwera unieważnia stare linki.
Kto ma token, ten steruje komputerem: nie udostępniaj linku i nie wystawiaj portu poza sieć domową.

`run` domyślnie pyta przed każdą akcją (Enter = wykonaj, s = pomiń, q = stop). `--yolo` wyłącza pytanie.
Każdy przebieg zapisuje się w `runs/<data>/`: zrzuty z zaznaczonym punktem kliknięcia i `steps.jsonl` z surowymi odpowiedziami modelu.

## Struktura

- `jarvis/screen.py`: geometria monitorów z KWin, zrzut ekranu, przeskalowanie do wielokrotności 28 px.
- `jarvis/actions.py`: mysz i klawiatura. Ruch kursora w pętli korekcji: ydotool rusza względnie, kdotool odczytuje pozycję.
- `jarvis/uitars.py`: prompty UI-TARS, zapytania do llama-server, parser akcji.
- `jarvis/agent.py`: pętla agenta (`run_task`, wymienny interfejs UI) i CLI.
- `jarvis/web.py` + `jarvis/static/`: webapka na telefon (stdlib `http.server`, bez dodatkowych zależności).

## Ustalenia z testów (2026-10-19)

- `ydotool mousemove --absolute` na KWin trafia w złe miejsce, a ruch względny zniekształca akceleracja. Pętla korekcji z odczytem przez `kdotool getmouselocation` trafia co do piksela w ok. 0.4 s.
- Rozdzielczość obrazu dla modelu ma duże znaczenie. Przy 1288 px (dłuższy bok) UI-TARS chybiał w połowie celów, przy 1792 px trafił wszystkie 4 testowe. Przy pełnych 2560 px llama.cpp sam zmniejsza obraz i współrzędne przestają się zgadzać. Domyślnie jest 1792.
- Czas kroku na RX 7900 XTX: ok. 2.3 s grounding, ok. 3 s pełny krok agenta, +1.1 s na refinement kliknięcia.
- UI-TARS-7B chybia cienkie cele (pasek ok. 20 px) o ok. 20 px w pionie. Drugi etap groundingu na wycinku 630x350 px powiększonym 2x poprawia to: z czterech celowo złych punktów startowych (do 40 px obok) wszystkie trafiły w zakładkę Terminal w Kate. Domyślnie włączony, `--no-refine` wyłącza.
- Bez kontekstu UI-TARS myli podobne elementy (zakładka "Terminal" w Kate vs ikony terminala na pasku zadań) i ogłasza sukces bez sprawdzenia. Agent porównuje zrzuty przed akcją i po niej i mówi modelowi, gdy akcja nic nie zmieniła.
- UI-TARS ignoruje prośbę o angielski w `finished(content=...)` i często pisze po chińsku. Agent wypisuje wtedy Thought.

## TODO

Plan dalszych prac: [PLAN.md](PLAN.md).
