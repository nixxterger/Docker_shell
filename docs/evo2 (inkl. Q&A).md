dein arbeitsverzeichnis ist: "/mnt/Daten/ai/Hermes_output/docker_shell/current"
dokumentationen; "/mnt/Daten/ai/Hermes_output/docker_shell/docs"
temp-verzeichnis: "/mnt/Daten/ai/Hermes_output/docker_shell/temp"

Design Document: "Docker-Shell" (Docker Management Tool)
1. Projektübersicht
Das Docker-Shell Tool ist ein Lightweight-Utility für Linux Mint (Nemo), das es ermöglicht, Docker-Container-Konfigurationen dynamisch über den Dateimanager zu steuern. Der Fokus liegt auf der Sicherheit von KI-Agenten durch Ressourcenlimitierung, Netzwerkisolation und einen speziellen "Maskierungs-Trick" zum Schutz von Daten vor versehentlichem Löschen oder Halluzinationen.

2. Funktionale Anforderungen
2.1 Integration & Trigger
Einstieg: Integration in den Nemo-Dateimanager via .nemo_action.
Trigger: Rechtsklick auf einen Ordner
→
→ Menüpunkt "Docker Konfig".
Input: Der Pfad des angeklickten Ordners wird als Argument an das Tool übergeben.
2.2 Workflow & UI (CustomTkinter)
Das Tool besteht aus einem zweistufigen Prozess in einer modernen Dark-Mode GUI:

Container-Auswahl: Dynamische Liste aller aktuell laufenden Docker-Container.
Konfigurations-Panel: Nach Auswahl eines Containers erscheinen folgende Optionen für den gewählten Ordner:
Web/Netzwerk: Toggle (An/Aus)
→
→ Steuert --network none. (default = web on)
RAM-Limit: Toggle (An/Aus) + Numerisches Feld mit +/- Buttons (1 gb-schritte). (default =no limit)
Mount-Modus (Dropdown):
Read-Write: Standard Mount.
Read-Only: Mount als :ro.
Temp Versteckt (Masked): Maskierung des Ordners via Temp-Mount. (/tmp/leer:)
Nur Hauptordner: ro freigabe aber, Automatisches Maskieren aller Unterverzeichnisse.
2.3 Backend & Logik
tool liegt im Bertieb in: "/home/chris/scripts/docker_shell"
Dynamischer Scan: Nutzung von docker inspect, um laufende Container zu finden und den Pfad zur docker-compose.yml über das Label com.docker.compose.project.working_dir auszulesen.
Sicherheits-Defaults:
Zwingendes UID/GID Mapping: --user $(id -u):$(id -g).
Log-Rotation: --log-opt max-size=10m --log-opt max-file=3.
Der Maskierungs-Trick (The Temp-Trick): Um Ordner "unsichtbar" zu machen, ohne sie physisch zu löschen, muss das Tool einen leeren temporären Ordner auf dem Host erstellen und diesen im Container über den Zielpfad mounten. Dies verhindert rm -rf Angriffe (da nur der Temp-Ordner geleert wird) und blockiert das Löschen des Mount-Punkts (Device or resource busy).
Apply-Logik: Beim Klick auf "OK" führt das Tool im Projektverzeichnis des Containers einen docker compose up -d Rebuild aus, um die neuen Parameter (RAM, Network, Mounts) zu übernehmen und den docker umgehend neu zu starten.
3. Technische Spezifikationen
Sprache: Python 3.x.
UI Framework: CustomTkinter (Modern Dark Theme).
Umgebung: Installation in einem isolierten venv.
OS: Linux (speziell Linux Mint / Nemo).
Abhängigkeiten: docker-py oder direkte Docker-CLI Aufrufe via subprocess.

Finale User Journey: "Docker-Shell"
Schritt 1: Der Trigger (Einstieg)
Aktion: Du befindest dich in deinem Dateimanager (Nemo unter Linux Mint Cinnamon).
Interaktion: Du machst einen Rechtsklick auf einen Ordner (oder im Inneren eines Ordners).
Auswahl: Du klickst auf den Menüpunkt "Docker Konfig".
Technik: Eine .nemo_action Datei startet das Tool aus einer isolierten Python venv, wobei der Pfad des aktuellen Ordners automatisch als Argument übergeben wird.
Schritt 2: Fenster 1 – Die Container-Auswahl
Ansicht: Es öffnet sich ein modernes, schlankes Fenster (CustomTkinter / Dark Mode).
Inhalt: Du siehst eine Liste aller aktuell laufenden Docker-Container.
Technik: Das Tool scannt im Hintergrund via docker inspect alle aktiven Prozesse und erkennt automatisch über die Labels (com.docker.compose.project.working_dir), wo die dazugehörige docker-compose.yml auf deiner Festplatte liegt. Du musst keinen Pfad manuell suchen oder eingeben.
Aktion: Du wählst den gewünschten Container aus
→
→ und es öffnet sich Fenster 2.
Schritt 3: Fenster 2 – Das Konfigurations-Menü
Nun öffnet sich das Einstellungs-Panel für die Kombination aus dem ausgewählten Ordner und dem ausgewählten Container. Du hast folgende Optionen:

Web / Netzwerk (Sicherheitsfeature):
Ein Toggle-Schalter An/Aus.
defaut=an (an = webzugriff an)
→
→ Der Container wird mit --network none (neu) gestartet (komplette Isolation von z.B. Hermes Desktop vom web).
Speicherschutz (RAM-Limit):
Ein Toggle-Schalter An/Aus. (default = aus) (aus = kein limit)
Wenn An: Ein Eingabefeld, in dem du den RAM-Wert bequem mit + und - Buttons hoch- und runterklicken kannst.(1 gb-schritte)
Mount-Modus (Dateizugriff): Du wählst per Dropdown aus, wie der Ordner im Container gemountet werden soll:
Read-Write: Standardzugriff (Lesen & Schreiben).
Read-Only: Docker darf nur lesen (:ro).
Temp versteckt (Maskiert): Der "Unsichtbar"-Trick. Ein leerer Temp-Ordner wird über den echten Ordner gelegt. Die Daten sind physisch da, aber für z.B. Hermes unsichtbar und vor rm -rf geschützt.
Nur Hauptordner: Nur die Dateien der obersten Ebene sind sichtbar; alle Unterordner werden automatisch maskiert/versteckt.
Schritt 4: Abschluss & Umsetzung (Der "OK"-Klick)
Aktion: Du klickst auf "OK".
Technik im Hintergrund:
Das Tool schreibt die neuen Parameter in die Konfiguration bzw. bereitet den Befehl vor.
Es führt automatisch einen Docker Compose Rebuild/Restart aus, damit die Änderungen (RAM, Netzwerk, Mounts) sofort aktiv werden.
Zusätzlich wird sichergestellt, dass das UID/GID Mapping (--user $(id -u):$(id -g)) und die Log-Rotation aktiv sind, um Root-Dateien und Festplatten-Überfüllung zu vermeiden.

Q&A1:
# Technisches Addendum: Docker-Shell (Ergänzung zum Design Document)

Dieses Dokument ergänzt das ursprüngliche Design Document für das Tool "Docker-Shell". Es enthält die im Review-Prozess präzisierten technischen Entscheidungen und Implementierungsdetails, um eine 1:1 Umsetzung ohne Interpretationsspielraum zu ermöglichen.

## 1. Status-Anzeige (UI/UX)
*   **Header-Status:** In der ersten Zeile des Konfigurations-Panels (Fenster 2) muss zwingend der aktuelle Zustand des gewählten Ordners im ausgewählten Container angezeigt werden.
*   **Datenquelle:** Die Informationen werden via `docker inspect <container_id>` in Echtzeit abgefragt.
*   **Anzeigefelder:** Aktueller Mount-Modus (RW/RO/Masked), Netzwerkstatus (Isoliert/Web) und RAM-Limit.

## 2. Konfigurations-Logik & Persistenz
*   **Override-Strategie:** Um die originale `docker-compose.yml` nicht zu beschädigen oder durch Regex-Operationen zu korrumpieren, nutzt das Tool eine **`docker-compose.override.yml`**.
*   **Implementierung:**
    *   Änderungen werden mittels der Python-Library **PyYAML** als strukturierte Objekte geschrieben und nicht als einfacher Text.
    *   Das Tool schreibt die gewünschten Parameter in die Override-Datei im Projektverzeichnis des Containers.
*   **Apply-Prozess:** Die Umsetzung erfolgt über den Befehl `docker compose up -d`. Docker Compose verschmilzt automatisch die Hauptdatei mit der Override-Datei.

## 3. Maskierungs-Mechanismus (The Temp-Trick)
*   **Opferordner:** Es wird ein permanenter, leerer Ordner auf dem Host verwendet: `/home/chris/scripts/docker_shell/temp_leer`.
*   **Hardcore-Maskierung:** Wenn die Option "Nur Hauptordner" gewählt wird, führt das Tool einen Scan des Zielverzeichnisses durch und mountet **jedes einzelne Unterverzeichnis der ersten Ebene** individuell als den oben genannten Opferordner. Dies garantiert maximale Sicherheit gegen versehentliche Zugriffe auf tieferliegende Daten.
*   **Demaskierung:**
    *   Es gibt eine explizite Funktion zur Demaskierung.
    *   Diese setzt sowohl den Hauptordner als auch alle maskierten Unterordner der ersten Ebene standardmäßig zurück auf **Read-Only (:ro)**.

## 4. Systemvoraussetzungen & Berechtigungen
*   **Docker-Zugriff:** Es wurde verifiziert, dass der ausführende User in der `docker`-Gruppe ist (`docker ps` funktioniert ohne `sudo`). Das Tool operiert daher ohne Root-Privilegien/Sudo-Prompts.
*   **UID/GID Mapping:** Die Erzwingung von `--user $(id -u):$(id -g)` wird ebenfalls über die `override.yml` gesteuert, um Root-Dateien im Host-System zu vermeiden.

## 5. Zusammenfassung der technischen Kette
`Nemo Trigger` $\rightarrow$ `docker inspect (Status)` $\rightarrow$ `PyYAML Edit (override.yml)` $\rightarrow$ `docker compose up -d` $\rightarrow$ `Verifikation`.

Q%A2:
Netzwerk-Isolation:--network none. Das ist ein CLI-Flag. Da wir aber eine docker-compose.override.yml nutzen, muss dies als network_mode: "none" implementiert werden.

Der "Nur Hauptordner"-Modus: Hier steht, dass alle Unterverzeichnisse maskiert werden. Frage: Welchen Status hat in diesem Moment der Hauptordner selbst? "Read-Only"

Die "Demaskierungs"-Funktion: Im Addendum steht, es gibt eine "explizite Funktion zur Demaskierung". Frage: Wo befindet sich dieser Button in der UI? "ein separater Button in Fenster 2"

Dynamik der Maskierung: Da die Maskierung von Unterordnern einen Scan des Dateisystems erfordert, bedeutet das: Die override.yml ist nicht statisch, sondern wird bei jedem "OK"-Klick basierend auf dem aktuellen Inhalt des Ordners neu generiert. Das ist logisch korrekt, sollte aber als "dynamische Generierung" im Dokument stehen, damit klar ist, dass die Override-Datei ständig überschrieben wird. "ok, passt"

Fallback-Szenario: Was passiert, wenn ein laufender Container das Label com.docker.compose.project.working_dir nicht besitzt?
"Der Container wird in der Liste einfach mit einem Warnhinweis "Kein Compose-Projekt gefunden" markiert."

Q%A3:
Q&A: Docker-Shell — Review-Klärungen
F1: Netzwerk-Isolation — wie lösen wir den Konflikt zwischen network_mode: host in der compose.yml und network_mode: "none" in der override.yml?

A: Das Tool bearbeitet den network_mode-Parameter direkt in der Haupt-docker-compose.yml — bei „Netzwerk aus" wird network_mode: host auskommentiert und network_mode: "none" eingetragen, bei „Netzwerk an" umgekehrt. Nur für diesen Parameter, alles andere bleibt in der override.yml.
F2: UID/GID Mapping — $(id -u):$(id -g) wird in der YAML nicht als Shell-Ausdruck ausgewertet. Wie soll das gelöst werden?

A: Wird zur Laufzeit des Tools aufgelöst und als konkrete Zahlen (z.B. 1000:1000) in die YAML geschrieben.
F3: Demaskierung — soll der vorherige Zustand wiederhergestellt werden, oder wird immer auf einen festen Zustand zurückgesetzt?

A: Setzt immer auf Read-Only zurück. Kein Merken des vorherigen Zustands — zu kompliziert, wäre User-Error. Wer RW braucht, stellt das bewusst manuell zurück.
F4: Neu erstellte Unterordner im „Nur Hauptordner"-Modus — sind die automatisch maskiert?

A: Nein. Wenn ich später einen Ordner erstelle, muss ich den direkt selbst einstellen. Bewusst akzeptiert.
F5: Fallback bei fehlendem Compose-Label — kann man den Container trotzdem auswählen, und wie wird das in der UI dargestellt?

A: Nein, nicht auswählbar. Container wird ausgegraut dargestellt.
F6: temp_leer-Ordner — muss der vom Tool beim ersten Start erstellt werden, oder existiert er bereits?

A: Existiert bereits unter /home/chris/scripts/docker_shell/temp_leer.
F7: Override-Datei beim Reset — löschen oder auf leer setzen?

A: Löschen ist sauberer.
F8: Fenster 1 und 2 — zwei separate Fenster oder ein Panel-Wechsel im selben Fenster?

A: Ein Panel, das wechselt.
F9: RAM-Limit — welches Minimum, kann man auf 0 GB klicken?

A: Minimum ist 1 GB.
F10: Fehlerhandling und Verifikation nach dem Apply — was passiert bei Fehler, was bei Erfolg?

A: Bei Fehler: Warn-Popup mit Info was fehlgeschlagen ist. Bei Erfolg: stilles Schließen — keine Beschwerde ist ein Lob.

