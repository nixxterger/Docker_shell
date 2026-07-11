# Rettungsplan: Docker-Shell Tool

> **ABGESCHLOSSEN — dieses Dokument ist Projekthistorie.** Das Tool wurde
> anschließend für GitHub portabel gemacht (XDG-Pfade, compose.yaml-Varianten,
> Preflight-Checks, de/en per Systemsprache, generisches Setup, Tests) und
> als v1.0.0 nach https://github.com/nixxterger/Docker_shell gepusht.
> Aktueller Stand: siehe README.md im Repo-Root.
>
> **STATUS: UMGESETZT (11.07.2026).** Alle unten beschriebenen Fixes sind in
> `current/docker_shell.py` implementiert, mit 10 End-to-End-Tests gegen einen
> echten Wegwerf-Container verifiziert und via `setup.sh` nach
> `/home/chris/scripts/docker_shell/` deployed (inkl. Nemo-Action + venv).
> **Ein manueller Schritt offen:** `sudo apt install python3-tk` — ohne das
> startet die GUI nicht (tkinter fehlt systemweit). Details am Dokumentende.

## Ausgangslage

Das Tool sollte lokal (ohne Cloud-KI) umgesetzt werden. Bei der Prüfung zeigt sich: es gibt **vier** unabhängige Umsetzungsversuche verschiedener lokaler Modelle, verstreut über zwei Verzeichnisse. Keiner davon ist aktuell installiert oder einsatzbereit.

| # | Ort | Modell | Datum | Umfang | Spec-Treue |
|---|---|---|---|---|---|
| 1 | `Hermes_input/docker-shell/docker_shell (gemma431bq6)/current` | gemma3 q6 | 23.06., ~06:25 | 2 Dateien, ~380 Zeilen | mittel |
| 2 | `Hermes_input/docker-shell/docker_shell (gemma431bq4km)/current` | gemma3 q4km | 23.06., ~05:27 | 2 Dateien, ~420 Zeilen | mittel |
| 3 | `Hermes_input/docker-shell/docker_shell (qwopus3.6coder27b)/current` | "qwopus3.6coder27b" | 23.06., ~05:39 | 1 Datei, 858 Zeilen + `.nemo_action` + `setup.sh` | **hoch — beste Basis** |
| 4 | `Hermes_output/docker_shell/*.py` (Projekt-Root) | unbekannt/neuer Versuch | 07.07., 04:08–04:26 | 9 verstreute Dateien (`main.py`, `main_new.py`, `final_main.py`, `docker_shell.py`, `docker_shell_ui.py`, `backend.py`, …) | **niedrig** |

Versuch 4 ist der jüngste, aber der schwächste — er wirkt wie ein Neustart "bei Null", der die bessere Vorarbeit aus Versuch 3 nicht kannte oder ignoriert hat. Mehrere Datei-Timestamps (4-Minuten-Abstände zwischen main.py, main_new.py, final_main.py) deuten darauf hin, dass das Modell mehrfach "nochmal von vorne" angefangen hat, statt eine Datei gezielt zu reparieren.

Am realen System ist **nichts** davon aktiv: `/home/chris/scripts/docker_shell/` enthält nur den leeren `temp_leer`-Ordner, kein Skript, keine Nemo-Action.

## Bewertung der Kandidaten

**Versuch 4 (Projekt-Root) — verwerfen.** Konkrete Abweichungen von der Spec:
- Keine Nemo-Integration (`.nemo_action` fehlt komplett).
- Die "Maskierungs-Funktion" ist funktional falsch: sie schreibt einen übergebenen String in eine per `tempfile.mkdtemp()` neu erzeugte Zufallsdatei (`backend.py:132`). Das hat mit dem eigentlichen Sicherheitsmechanismus (fester `temp_leer`-Ordner wird per Bind-Mount über den Zielordner gelegt) nichts zu tun.
- Kein `network_mode`-Handling, keine Ordner-Scan-Logik für "Nur Hauptordner", keine Demaskierung, keine Status-Anzeige — mehrere Kernanforderungen aus dem Q&A fehlen vollständig.
- Fünf sich überschneidende Einstiegspunkte (`main.py`, `main_new.py`, `final_main.py`, `docker_shell.py`, `docker_shell_ui.py`) ohne erkennbare Aufgabenteilung — Wartungsrisiko.

**Versuch 3 (qwopus3.6coder27b) — als Basis empfohlen.** Trifft die meisten Q&A-Vorgaben korrekt:
- UID/GID wird zur Laufzeit via `os.getuid()/getgid()` aufgelöst (Q&A F2 ✓).
- `network_mode` wird direkt und strukturiert per PyYAML in der Haupt-`docker-compose.yml` editiert, inkl. automatischem Backup vor der ersten Änderung (F1 ✓, sogar besser als gefordert).
- Fester `temp_leer`-Pfad als Konstante, Auto-Erstellung falls fehlend (F6 ✓).
- Demaskierung setzt hart auf Read-Only zurück, kein Merken des Vorzustands (F3 ✓).
- Nicht auswählbare Container werden ausgegraut mit Warnhinweis (F5 ✓).
- RAM-Minimum 1 GB (F9 ✓), stilles Schließen bei Erfolg / Warn-Popup bei Fehler (F10 ✓).
- Bringt bereits `.nemo_action` und ein funktionierendes `setup.sh` mit, das venv anlegt und die Nemo-Action installiert.

Trotzdem ist auch dieser Kandidat **nicht fertig** — es gibt einen strukturellen Bug, der vor dem produktiven Einsatz behoben werden muss:

### Kritischer Bug in Versuch 3: Maskierung ist nicht reversibel erkennbar

`get_status()` und `write_override()` identifizieren den "Zielordner-Mount" ausschließlich darüber, dass die **Host-Quelle** eines aktuellen Docker-Mounts exakt dem angeklickten Ordner entspricht (`src_path == real_target`). Sobald der Ordner einmal maskiert wurde, ist die Quelle im laufenden Container aber `temp_leer`, nicht mehr der echte Ordner-Pfad. Damit:
- erkennt `get_status()` einen aktuell maskierten Hauptordner nicht mehr korrekt (Status-Header zeigt fälschlich "Read-Write" an),
- kann `write_override()` beim Umschalten von "Temp versteckt" zurück auf "Read-Write" oder "Read-Only" den betroffenen Mount-Eintrag nicht mehr finden, weil er nach der Quelle statt nach dem Container-Zielpfad sucht — der Volume-Eintrag bleibt dadurch unverändert auf `temp_leer` stehen.
- Der separate "Demaskieren"-Button in `_on_demask()` umgeht das Problem zufällig, weil er stur `mount_mode="ro"` erzwingt statt den vorherigen Zustand zu erkennen — der Dropdown-Pfad ("Temp versteckt" → "Read-Write" wählen → OK) ist aber weiterhin kaputt.

Die Ursache: Der Container-Zielpfad (`target_dest`) muss aus der **ursprünglichen** `docker-compose.yml`-Volume-Definition abgeleitet werden (die ändert sich nie), nicht aus dem aktuell laufenden `docker inspect`-Mount-Zustand (der sich durch Maskierung verändert). Das ist ein Architekturfehler, kein Tippfehler — die Reparatur braucht eine stabile Zuordnung Host-Ordner ↔ Container-Pfad, unabhängig vom aktuellen Mount-Zustand.

## Empfehlung an Fable

1. **Versuch 4 (Projekt-Root) verwerfen**, nicht weiter reparieren. Als Referenz aufheben, nicht als Basis nutzen.
2. **Versuch 3 (`qwopus3.6coder27b`) als Basis übernehmen** — Pfad: `/mnt/Daten/ai/Hermes_input/docker-shell/docker_shell (qwopus3.6coder27b)/current/docker_shell.py` (+ `docker_konfig.nemo_action`, `setup.sh`).
3. **Den Mount-Tracking-Bug beheben**, bevor irgendetwas auf einem echten Container getestet wird: Container-Zielpfad für den geklickten Host-Ordner einmalig aus der Original-`docker-compose.yml` (`volumes:`-Liste des Service, nicht aus `docker inspect`) auflösen und diese Zuordnung für alle Modi (rw/ro/masked/main_only) konsistent verwenden.
4. Danach gegen die Q&A-Punkte F1–F10 in `docs/evo2 (inkl. Q&A).md` und `/home/chris/docker_shell_design_final.md` querchecken — beide Dokumente sind deckungsgleich, letzteres ist die aufgeräumte Endfassung und eignet sich besser als alleinige Spec-Referenz.
5. Deployment: `setup.sh` erwartet die Quelldateien unter `/mnt/Daten/ai/Hermes_output/docker_shell/current/` — diesen Ordner vor dem nächsten Lauf tatsächlich befüllen (aktuell leer), sonst schlägt die Installation fehl.
6. **Vor dem ersten Live-Test unbedingt in einer Wegwerf-Umgebung prüfen** (Testcontainer + Test-`docker-compose.yml`, keine echten Hermes-/Produktiv-Container), da das Tool automatisiert `docker-compose.yml`-Dateien überschreibt und `docker compose up -d` auslöst.

## Update: Aufräumen abgeschlossen (Stand jetzt)

- Alle vier Versuche geprüft, drei davon **gelöscht**: der schwache Root-Versuch (`main.py`, `main_new.py`, `final_main.py`, `backend.py`, `docker_shell_ui.py`, `helpers.py`, `config.py`, `__init__.py`, `test_backend.py`, alte `README.md`/`IMPLEMENTATION.md`) sowie die beiden unterlegenen gemma-Versuche (`gemma431bq6`, `gemma431bq4km`) inkl. ihrer venvs.
- Ein Sicherheits-Backup aller gelöschten Dateien liegt (nur für diese Session) im Scratchpad-Verzeichnis, falls doch nochmal ein Blick zurück nötig ist — danach ist es weg.
- Die **qwopus3.6coder27b-Version ist jetzt im Arbeitsverzeichnis**: `/mnt/Daten/ai/Hermes_output/docker_shell/current/` enthält `docker_shell.py`, `docker_konfig.nemo_action`, `setup.sh`, `README.md`, `requirements.txt`. Das ist die einzige verbliebene Codebasis — Fable muss nicht mehr zwischen Versionen wählen.
- `Hermes_input/docker-shell/` ist jetzt komplett leer (Dubletten der Spec-Doku dort ebenfalls gelöscht, identisch zu `docs/evo2 (inkl. Q&A).md`).

## Für Fable: Alles für eine schnelle, korrekte Umsetzung

**Einstiegspunkt:** `/mnt/Daten/ai/Hermes_output/docker_shell/current/docker_shell.py` (858 Zeilen, eine Datei, Klassen `DockerBackend` + `DockerShellApp`). Das ist die Basis — nicht neu schreiben, sondern gezielt reparieren.

**Deployment (bereits vorbereitet, sollte unverändert funktionieren):**
```bash
cd /mnt/Daten/ai/Hermes_output/docker_shell/current
bash setup.sh
```
Legt venv unter `/home/chris/scripts/docker_shell/venv` an, kopiert `docker_shell.py` dorthin, installiert `docker_konfig.nemo_action` nach `~/.local/share/nemo/actions/`. `temp_leer` existiert bereits unter `/home/chris/scripts/docker_shell/temp_leer` — nicht neu anlegen.

**Der einzige bekannte Bug, der vor dem Test behoben werden muss** (siehe Abschnitt oben "Kritischer Bug"):

- Betroffene Methoden: `DockerBackend.get_status()` (ca. Zeile 145–211) und `DockerBackend.write_override()` (ca. Zeile 232–332) in `docker_shell.py`.
- Problem konkret: Beide Methoden bestimmen den "ist das der Ziel-Mount"-Match über `src_path == real_target`, wobei `src_path` aus dem **aktuell laufenden** `docker inspect`-Mount kommt. Sobald der Mount maskiert ist, ist die Quelle `temp_leer`, nicht mehr der echte Ordner — der Vergleich schlägt fehl, der Code "verliert" den Ordner.
- **Fix-Ansatz:** Den Container-Zielpfad (`target_dest`) einmalig aus der **Original-`docker-compose.yml`** ableiten (dem `volumes:`-Eintrag des Service, der den Host-Ordner referenziert), nicht aus dem live inspizierten Mount-Zustand. Diese Zuordnung ändert sich nie, unabhängig vom aktuellen Masking-Zustand. Praktisch:
  ```python
  # Neue Hilfsmethode statt "aus current_volumes/inspect raten":
  def resolve_container_dest(self, compose_dir, service_name, host_folder):
      """Liest die ORIGINAL docker-compose.yml (nicht docker inspect!),
      findet den volumes-Eintrag mit source == host_folder,
      gibt den container-seitigen dest-Pfad zurück. Bleibt stabil,
      auch wenn der Mount aktuell maskiert ist."""
      with open(Path(compose_dir) / "docker-compose.yml") as f:
          compose = yaml.safe_load(f)
      for vol in compose["services"][service_name].get("volumes", []):
          parts = vol.split(":") if isinstance(vol, str) else [vol["source"], vol["target"]]
          if Path(parts[0]).resolve() == Path(host_folder).resolve():
              return parts[1]
      return None
  ```
  Diesen `target_dest` dann sowohl in `get_status()` (statt der Suche über `mounts`) als auch in `write_override()` (statt `target_dest = None` + Suche in `current_volumes`) als Ausgangspunkt verwenden. Die Ist-Zustands-Erkennung (RW/RO/Masked) kann weiterhin über `docker inspect` erfolgen — aber immer anhand von `dest == target_dest`, nie anhand der Host-Quelle.
- **Testfall zum Verifizieren des Fixes:** Ordner maskieren (OK klicken) → Panel verlassen und neu öffnen → Status-Header muss "Masked" korrekt anzeigen (aktuell zeigt er fälschlich "Read-Write"). Dann Dropdown auf "Read-Write" zurückstellen → OK → Mount muss tatsächlich wieder auf den echten Ordner zeigen (aktuell bleibt er auf `temp_leer` hängen).

**Spec-Referenzen für Fable (beide inhaltlich deckungsgleich, letztere ist die aufgeräumte Fassung):**
- `docs/evo2 (inkl. Q&A).md` — Rohfassung inkl. allen Q&A-Runden.
- `/home/chris/docker_shell_design_final.md` — konsolidierte Endversion, als primäre Referenz empfohlen.
- Die Q&A-Punkte F1–F10 sind bereits im mitgelieferten `current/README.md` tabellarisch den Implementierungsentscheidungen zugeordnet — guter Ausgangspunkt für einen Abgleich Code ↔ Spec.

**Bereits korrekt umgesetzt (nicht anfassen, nur verifizieren):**
- UID/GID-Auflösung zur Laufzeit (`__init__`, Zeile 47).
- `network_mode`-Direktbearbeitung der Haupt-compose mit automatischem Backup vor erster Änderung (`edit_network_in_main`, Zeile 336).
- Ausgegraute, nicht auswählbare Container ohne Compose-Label (`_refresh_container_list`, Zeile 493).
- RAM-Stepper mit Minimum 1 GB (`_set_ram_stepper`, `_ram_decrease`).
- Stilles Schließen bei Erfolg, Warn-Popup bei Fehler (`_on_apply`, Zeile 743).
- Reset/Demaskierung löscht die Override-Datei statt sie zu leeren (`reset_compose`, Zeile 395) — wird aktuell aber nicht von `_on_demask()` aufgerufen, das stattdessen `write_override()` mit `mount_mode="ro"` nutzt. Kurz prüfen, ob `reset_compose()` obsolet ist oder ob `_on_demask()` eigentlich `reset_compose()` aufrufen sollte (`reset_compose` stellt zusätzlich das Netzwerk-Backup wieder her, `_on_demask()` aktuell nicht).

**Nach dem Bugfix, vor dem Live-Einsatz:**
1. Unbedingt zuerst gegen einen **Wegwerf-Container** mit eigener Test-`docker-compose.yml` testen — nicht gegen Hermes oder andere Produktiv-Container. Das Tool schreibt automatisiert in `docker-compose.yml` und triggert `docker compose up -d`.
2. Testreihenfolge empfohlen: (a) Container ohne Compose-Label → muss ausgegraut sein, (b) Read-Write → Read-Only → Read-Write durchschalten, (c) Temp versteckt setzen und wieder zurück (der Bugfix-Testfall oben), (d) "Nur Hauptordner" mit mehreren Unterordnern, (e) Netzwerk an/aus mit einem Service, der `network_mode: host` in der Original-compose hat, (f) RAM-Limit setzen und via `docker inspect` verifizieren, (g) Demaskieren-Button.
3. `pip install -r requirements.txt` im venv installiert `customtkinter>=5.2.0` und `PyYAML>=6.0` — beides bereits in `setup.sh` verankert.

## Offene Fragen an dich

Keine akuten. Eine Sache zur Entscheidung, falls Fable danach fragt: Soll `_on_demask()` künftig `reset_compose()` aufrufen (löscht Override-Datei + stellt Netzwerk-Backup wieder her) statt wie aktuell nur `write_override(mount_mode="ro")` zu schreiben? Das wäre konsistenter mit Q&A F7, ändert aber das Verhalten leicht (Netzwerk-Zustand würde beim Demaskieren mit zurückgesetzt statt nur Mounts). **Entscheidung bei der Umsetzung: Ist-Verhalten beibehalten** — Q&A F3 verlangt beim Demaskieren nur "zurück auf RO", ein Mit-Zurücksetzen des Netzwerks wäre eine Überraschung für den User. `reset_compose()` bleibt als separate Funktion für einen künftigen "Reset"-Button erhalten.

---

## Umsetzungsprotokoll (11.07.2026, Fable)

### Behobene Fehler in `current/docker_shell.py`

1. **Mount-Tracking-Bug (der geplante Kern-Fix):** Neue Methoden `_compose_volumes()` und `resolve_container_dest()` leiten den Container-Zielpfad aus der Original-`docker-compose.yml` ab (unterstützt Kurz-/Lang-Syntax, relative Pfade, `~`, Unterpfade eines Volumes). `get_status()` und `write_override()` matchen jetzt über den stabilen Container-Pfad (`dest`), nie mehr über die Live-Mount-Quelle. Beim Zurückschalten auf RW/RO wird explizit der echte Host-Ordner wieder eingehängt.
2. **`scan_containers()`-Filter (Folgefehler derselben Ursache, beim Umsetzen gefunden):** Der Filter matchte nur Live-Mount-Quellen — ein maskierter Ordner (Quelle = `temp_leer`) ließ den Container aus der Auswahlliste verschwinden, Demaskieren wäre unmöglich gewesen. Jetzt: Match über Live-Mounts ODER Original-compose.
3. **Ungültiger Compose-Key `log_driver: local`** in der Override (Compose-v1-Relikt) — hätte jeden `docker compose up`-Apply mit Schema-Fehler scheitern lassen. Ersetzt durch korrektes `logging: {driver: json-file, options: …}` gemäß Spec.
4. **`ctk.CTkInputDialog(...).open()` existiert nicht** — das Fehler-Popup (Q&A F10) wäre selbst gecrasht. Ersetzt durch `tkinter.messagebox.showerror`.
5. **Veraltete Container-ID nach Apply:** `docker compose up -d` erstellt den Container neu → alte ID ungültig. `_on_demask()` löst den Container jetzt über `_find_container()` (Service + Compose-Dir) neu auf, bevor der Status neu geladen wird.
6. **Leere Mount-Modes** aus `docker inspect` (`src:dest:`) werden beim Durchreichen bereinigt (hätten Compose-Parse-Fehler ausgelöst).

### Verifikation

Headless-Testlauf (Backend ohne GUI) gegen einen echten Alpine-Wegwerf-Container mit eigener Test-compose — alle 10 Tests bestanden:
resolve_container_dest, RW-Ausgangszustand, Maskieren (Daten im Container unsichtbar, Status korrekt als "Masked" erkannt, Container bleibt in Scan-Liste), **Masked→RW-Umschaltung (der Bugfix-Kernfall)**, Read-Only (Schreiben blockiert), "Nur Hauptordner" (Haupt-RO + 2 Subdirs maskiert, Dateien der obersten Ebene sichtbar), Netzwerk aus/an inkl. Backup-Mechanik, RAM-Limit 2 GB via inspect bestätigt, Override-Inhalt (user/logging korrekt, kein `log_driver`), Reset (Override gelöscht, Haupt-compose restauriert). Testcontainer danach entfernt.

### Deployment (erledigt)

- `setup.sh` gelaufen: venv unter `/home/chris/scripts/docker_shell/venv` (Python 3.12.3, customtkinter 6.0.0, PyYAML 6.0.3), App kopiert, Nemo-Action installiert (`~/.local/share/nemo/actions/docker_konfig.nemo_action`). `temp_leer` existierte bereits und ist leer.

### Verbleibender manueller Schritt

```bash
sudo apt install python3-tk
```
`tkinter` fehlt systemweit (in keinem der installierten Python 3.10/3.11/3.12 vorhanden) — customtkinter kann ohne nicht starten. Danach zum Verifizieren: Rechtsklick in Nemo auf einen gemounteten Ordner → "Docker Konfig". Erster GUI-Test idealerweise wieder gegen einen Testcontainer, nicht direkt gegen Hermes.

**Nachtrag 11.07.:** `python3-tk` installiert (User), GUI-Stack im venv verifiziert. Danach fiel ein weiterer Fehler der lokalen KI auf: die `.nemo_action` enthielt das ungültige `Selection=dir_nonempty` und es fehlte die `Extensions`-Zeile — Nemo ignorierte die Datei stillschweigend, kein Kontextmenü-Eintrag. Korrigiert auf `Selection=s` + `Extensions=dir;` (in `current/` und in `~/.local/share/nemo/actions/`), Nemo per `nemo -q` neu geladen. GUI-Test durch den User erfolgreich.

### Feature-Erweiterung (11.07., nach GUI-Test, auf User-Wunsch)

1. **Neuaufnahme nicht gemounteter Ordner:** Die Container-Liste zeigt jetzt alle laufenden Compose-Container, nicht nur die, die den angeklickten Ordner bereits mounten. Ist der Ordner im gewählten Container noch kein Volume, wird er beim OK neu aufgenommen — Container-Pfad = Host-Pfad (User-Entscheidung: identische Sicht wie am Host). UI zeigt dies per Hinweis in der Liste ("➕ Ordner wird bei OK neu aufgenommen") und im Status-Header an. Alle Mount-Modi (RW/RO/Masked/Nur Hauptordner) funktionieren auch für neu aufgenommene Ordner.
2. **Fenster öffnet an der Cursor-Position** (an Bildschirmränder geklemmt) statt an der Fensterstandard-Position.

Verifiziert mit 5 neuen E2E-Tests (Scan-Flags, Neuaufnahme RW mit Host-Pfad im Container, RO, masked→rw auf neuem Mount, Regressionscheck bestehender Mount) plus Regressionslauf des Kern-Testsatzes (masked→rw auf bestehendem Mount, "Nur Hauptordner", Reset) — alle bestanden. Neu deployed nach `/home/chris/scripts/docker_shell/`.
