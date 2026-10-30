# JARVIS_REMOTE — plan

[English version](../PLAN.md)

Stan na 2026-10-19: działa UI-TARS-1.5-7B (sam, bez plannera) z drugim etapem celowania, CLI i webapka na telefon w LAN.

Proponowana kolejność: 0 → 1 → 2 → 5 → 8, reszta potem.

## 0. Do zrobienia od razu

- [ ] `git init` w `JARVIS_REMOTE`. Teraz katalog nie jest repo, więc zmian nie da się cofnąć bez kopii.
- [ ] Pobrać planner Qwen3-VL-30B-A3B-Instruct (komenda w [RESEARCH.md](RESEARCH.md#pobieranie-modeli)).

## Niezawodność (największy zysk)

1. [~] **Narzędzia zamiast klikania.** Proste zadania przez komendy, bez modelu wizyjnego. Zrobione jako szybkie akcje (`jarvis/quick.py`, dopasowanie krótkich poleceń + przyciski w webapce): media przez playerctl, głośność przez wpctl, `xdg-open`, uruchamianie i przełączanie aplikacji, blokada ekranu. Zostaje: wybór narzędzia przez planner zamiast sztywnych wzorców.
   - `playerctl play-pause` dla "pauza YouTube" (MPRIS w Vivaldi),
   - `xdg-open URL` dla "otwórz stronę X",
   - `kdotool search <app> windowactivate` dla "przełącz na okno".

   Agent najpierw próbuje narzędzia, a klika dopiero wtedy, gdy żadne nie pasuje.
2. [x] **Automatyczny wybór monitora.** Agent widzi jeden monitor, więc zadanie w aplikacji na innym monitorze się nie uda. Znaleźć okno aplikacji przez `kdotool search`, wziąć jego monitor i aktywować okno.
3. [x] **Tryb okna.** Zrzut samego okna aplikacji zamiast całego monitora: znika pasek zadań (źródło pomyłek "Terminal" w Kate vs ikona terminala), a rozdzielczość rośnie przy tej samej liczbie tokenów.
4. [ ] **Planner Qwen3-VL-30B-A3B** (port 8080). Planner opisuje cel i weryfikuje efekt kroku, UI-TARS (`UITars.ground` + refinement) tylko zwraca współrzędne. Rozwiązuje ogłaszanie sukcesu bez sprawdzenia i niejednoznaczne cele.

## Wygoda

5. [-] (pominięte: autostart niepotrzebny) **Usługi systemd `--user`** dla UI-TARS (llama-server), `ydotoold` i webapki, żeby wszystko startowało z systemem bez otwartych terminali.
6. [ ] **Szybkość.** Kroki zwalniają z ok. 4 s do ok. 9 s, bo przesuwane okno historii zmienia początek promptu i cache llama.cpp nie działa (ok. 7.5k tokenów liczone od zera co krok). Opcje: `--history 2` albo stabilny prompt (jeden zrzut + historia samym tekstem).
7. [x] **Sprzątanie `runs/`.** Przy starcie każdego zadania znikają przebiegi starsze niż 7 dni (`JARVIS_KEEP_DAYS`), ręcznie `python -m jarvis.agent clean`.

## Bezpieczeństwo

8. [x] **Kill-switch.** `python -m jarvis.agent stop`, `scripts/jarvis-stop.sh` (pod własny skrót KDE) i STOP w webapce. Agent zatrzymuje się przed kolejną akcją.
9. [x] **Blokady akcji** (`jarvis/safety.py`). Pisanie w terminalu jest dozwolone. Potwierdzenia wymagają: tekst wyglądający na groźną komendę (`sudo`, `rm -rf`, `curl | sh`, `git push`…), polecenia wpisywane w launcher oraz skróty zamykające lub usuwające (`alt+f4`, `ctrl+w`, `ctrl+q`, Delete, Super). Tryb ask pyta o wszystko, auto tylko o te, full o nic.

## Niesprawdzone (kod jest, testu brak)

10. [ ] Kierunek scrolla (`actions.scroll`, znak REL_WHEEL).
11. [ ] Polskie znaki: wklejanie przez `wl-copy` + ctrl+v. W terminalach potrzebne jest ctrl+shift+v.
12. [ ] Drag i double-click.

## Później

13. [ ] AT-SPI: drzewo dostępności zamiast zrzutów tam, gdzie aplikacja je udostępnia (GTK/Qt/Firefox).
14. [ ] Głos przez whisper.cpp. Nagrywanie w przeglądarce wymaga HTTPS na stronie, na razie zostaje dyktowanie z klawiatury telefonu.

## Pomysły z gotowych projektów

Przegląd open source z 2026-10-19: żaden projekt nie łączy lokalnego modelu z llama.cpp, KDE Wayland, prawdziwego pulpitu i sterowania z telefonu, więc rozwijamy własny. Warto podebrać:

15. [ ] **Tryb ręczny na telefonie** (z [contop](https://github.com/slopedrop/contop)): dotknięcie podglądu ekranu klika w to miejsce na komputerze, bez modelu. Do poprawiania agenta, gdy utknie.
16. [ ] **Podgląd na żywo** (z contop): odświeżany zrzut lub strumień zamiast jednorazowego "Screen preview".
17. [x] **Tryby ask / auto / full** (z [Open WebUI Computer](https://docs.openwebui.com/ecosystem/computer/)) zamiast jednego przełącznika "bez pytania". Na przykład: ask pyta o wszystko, auto pyta tylko o ryzykowne akcje (punkt 9), full nie pyta wcale.
18. [ ] **Sandbox do testów** (z [Bytebot](https://github.com/bytebot-ai/bytebot)): osobny pulpit w kontenerze lub VM do sprawdzania ryzykownych zadań, zanim agent dostanie prawdziwy pulpit.

Do podejrzenia w kodzie: [UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) (prompty i parser akcji dla tego samego modelu).
