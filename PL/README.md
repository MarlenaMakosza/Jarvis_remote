# JARVIS_REMOTE — draft

[English version](../README.md)

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
python -m jarvis.agent run "In Vivaldi ..."          # aplikacja z polecenia: agent aktywuje jej okno i widzi tylko je
python -m jarvis.agent run "..." --screen           # cały monitor zamiast okna
python -m jarvis.agent run "pause youtube"          # szybka akcja: playerctl, bez modelu (--no-quick wyłącza)
python -m jarvis.agent --monitor DP-4 run "..."     # wybór monitora, gdy w poleceniu nie ma aplikacji
export JARVIS_MONITOR=DP-5                          # albo na stałe (domyślnie: monitor pod kursorem)
```

Z telefonu (ta sama sieć Wi-Fi):

```bash
python -m jarvis.web --monitor DP-5        # wypisuje link z tokenem i kod QR, port 8765
```

Zeskanuj QR telefonem. Token trafia do ciasteczka, a link można dodać do ekranu głównego jako apkę.
Webapka ma pole polecenia, zrzut z zaznaczonym celem, przyciski Run / Skip, STOP i podgląd ekranu (Screen preview).
Token leży w `~/.config/jarvis/token`. Usunięcie pliku i restart serwera unieważnia stare linki.
Kto ma token, ten steruje komputerem: nie udostępniaj linku i nie wystawiaj portu poza sieć domową.

## Bezpieczeństwo

Tryby potwierdzeń (`--mode` w CLI, przełącznik w webapce):

- `ask` (domyślny): pyta przed każdą akcją (Enter = wykonaj, s = pomiń, q = stop).
- `auto`: pyta tylko o ryzykowne akcje: tekst wyglądający na groźną komendę (`sudo`, `rm -rf`, `curl | sh`, `git push`…), polecenie wpisane w launcher, skróty zamykające lub usuwające (`alt+f4`, `ctrl+w`, `ctrl+q`, Delete, Super).
- `full` (albo `--yolo`): nie pyta wcale.

Reguły są w `jarvis/safety.py`. Pisanie w terminalu jest dozwolone.

Zatrzymanie agenta przed kolejną akcją:

```bash
python -m jarvis.agent stop       # albo scripts/jarvis-stop.sh, albo STOP w webapce
```

Pod globalny skrót KDE: Ustawienia systemowe → Skróty → Dodaj nowy → Polecenie lub skrypt → `scripts/jarvis-stop.sh`.
`scripts/install-killswitch.sh [skrót]` robi to samo z linii poleceń, ale skrót może zadziałać dopiero po ponownym zalogowaniu i nie sprawdza konfliktów z domyślnymi skrótami KDE.
Każdy przebieg zapisuje się w `runs/<data>/`: zrzuty z zaznaczonym punktem kliknięcia i `steps.jsonl` z surowymi odpowiedziami modelu.
Przebiegi starsze niż 7 dni znikają automatycznie przy starcie zadania (`JARVIS_KEEP_DAYS` zmienia limit). Ręcznie: `python -m jarvis.agent clean [--days N]`, `--days 0` usuwa wszystkie.

## Struktura

- `jarvis/screen.py`: geometria monitorów z KWin, zrzut ekranu, przeskalowanie do wielokrotności 28 px.
- `jarvis/actions.py`: mysz i klawiatura. Ruch kursora w pętli korekcji: ydotool rusza względnie, kdotool odczytuje pozycję.
- `jarvis/uitars.py`: prompty UI-TARS, zapytania do llama-server, parser akcji.
- `jarvis/agent.py`: pętla agenta (`run_task`, wymienny interfejs UI) i CLI.
- `jarvis/windows.py`: wyszukiwanie, aktywacja i geometria okien aplikacji (kdotool).
- `jarvis/quick.py`: szybkie akcje bez modelu: media, głośność, otwieranie stron, uruchamianie i przełączanie aplikacji.
- `jarvis/safety.py`: tryby potwierdzeń, ocena ryzyka akcji, kill-switch (plik `$XDG_RUNTIME_DIR/jarvis.stop`).
- `scripts/`: `jarvis-stop.sh` (kill-switch z powiadomieniem) i `install-killswitch.sh`.
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
