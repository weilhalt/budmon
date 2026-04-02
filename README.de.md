# BudMon — Anleitung

## Warum BudMon?

Claude Code Nutzer mit Max-Plan haben ein Token-Budget das alle 5 Stunden
und alle 7 Tage zurückgesetzt wird. Wird das Budget überschritten, wird man
gedrosselt oder blockiert. Das Problem: Claude Code zeigt keine Echtzeit-
Rückmeldung darüber, wie schnell das Budget verbraucht wird.

BudMon füllt diese Lücke. Es erfasst die Rate-Limit-Header aus jeder
API-Antwort und visualisiert sie als Live-Dashboard. Auf einen Blick sieht man:

- Wie viel vom 5h- und 7d-Kontingent verbraucht ist
- Wie schnell es verbraucht wird
- Wann das Kontingent zurückgesetzt wird
- Ob es vor dem Reset aufgebraucht sein wird
- Wie viel in Dollar ausgegeben wird

BudMon läuft als eigenständiges Fenster neben Claude Code. Es benötigt
keine API-Keys, keinen Netzwerkzugang und keine externen Dienste.

## Features

- **5h / 7d Quota-Balken** — Fortschrittsbalken mit konfigurierbaren Warn- (Standard 75%) und Alarm-Schwellen (Standard 90%)
- **Verbrauch** — Verbrauchsrate in %/Stunde (5h) oder %/Tag (7d)
- **Ablauf-Schätzung** — Voraussichtlicher Zeitpunkt der Quota-Erschöpfung, mit Datum bei 7d
- **Reserve** — Zeitdifferenz zwischen Ablauf und nächstem Reset (positiv = sicher, negativ = wird knapp)
- **Countdown-Ring** — Kreisförmiger Timer, zeigt Reset oder Ablauf (je nachdem was zuerst kommt)
- **Letzte Anfrage / Anfragen gesamt** — Token-Aufschlüsselung pro Turn und kumuliert (Input, Output, Cache Create, Cache Read)
- **Kostenanzeige** — Dollar-Kosten pro Anfrage und kumuliert, basierend auf modellspezifischen Token-Preisen
- **Cache-Ratio Sparkline** — Historischer Graph der Cache-Trefferquote mit Durchschnitt
- **Mehrsprachig** — Deutsch und Englisch, zur Laufzeit umschaltbar, erkennt Systemsprache
- **Modell-Presets** — Opus, Sonnet, Haiku Token-Preise oder benutzerdefiniert
- **Dark Theme** — Terminal-inspiriertes dunkles Farbschema
- **HiDPI / 4K** — Automatische DPI-Skalierung auf Windows, Linux und macOS
- **Fensterposition** — Merkt sich die letzte Position
- **Konfigurierbar** — Alle Schwellen, Preise, Sprache und Aktualisierungsrate über INI-Datei

## Unterstützte Plattformen

| Plattform | Status | Hinweise |
|---|---|---|
| **Linux** (X11) | Vollständig | Primäre Entwicklungsplattform. Getestet auf Ubuntu 24.04. |
| **Linux** (Wayland) | Sollte funktionieren | tkinter läuft unter XWayland. |
| **macOS** | Sollte funktionieren | Retina-Skalierung nativ über tk. |
| **Windows** | Sollte funktionieren | DPI via ctypes/shcore. Wrapper ist `.cmd` statt Shell-Alias. |

## Voraussetzungen

- **Python 3.10+** mit tkinter
- **Claude Code** (CLI-Version, installiert über npm)
- **Node.js** (kommt mit Claude Code)

### tkinter installieren

tkinter ist bei den meisten Python-Installationen enthalten. Falls nicht:

| Betriebssystem | Befehl |
|---|---|
| Ubuntu / Debian | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |
| macOS (Homebrew) | `brew install python-tk` |
| Windows | Python neu installieren mit "tcl/tk" Option |

## Installation

### Von PyPI (empfohlen)

```bash
pip install budmon
```

### Aus dem Quellcode

```bash
git clone https://github.com/weilhalt/budmon.git
cd budmon
pip install .
```

## Einrichtung

BudMon braucht einen kleinen Interceptor um Rate-Limit-Daten aus den
API-Antworten von Claude Code zu erfassen. Einmalig nach der Installation:

```bash
budmon --setup
```

Das macht drei Dinge:

1. **Installiert den Interceptor** (`~/.claude/budmon-interceptor.mjs`) — ein
   rein lesender Node.js Fetch-Wrapper. Er **verändert keine ausgehenden Anfragen**.

2. **Erstellt den `claude-budmon` Befehl**:
   - Linux/macOS: Shell-Alias in `.bashrc`/`.zshrc` + Wrapper in `~/.local/bin/`
   - Windows: `.cmd` Wrapper in einem PATH-Verzeichnis

3. **Erstellt einen Desktop-Eintrag** (nur Linux), damit BudMon im
   Anwendungsmenü erscheint.

### Bereits vorhandener Interceptor

Wer bereits `cache-fix-preload.mjs` oder einen ähnlichen Community-Interceptor
nutzt der `~/.claude/usage-limits.json` schreibt: kein zusätzliches Setup nötig.
BudMon erkennt das automatisch.

## Benutzung

### Schritt 1: Claude Code mit Interceptor starten

```bash
claude-budmon
```

Identisch mit `claude`, aber mit geladenem Interceptor. Alle Argumente
werden durchgereicht.

### Schritt 2: Dashboard starten

In einem zweiten Terminal (oder über das Anwendungsmenü):

```bash
budmon
```

Das Dashboard öffnet sich und pollt jede Sekunde nach Daten. Beim ersten
Start ohne Daten wird automatisch die Einrichtung angeboten.

### Täglicher Workflow

1. Claude Code immer über `claude-budmon` statt `claude` starten
2. `budmon` starten wenn man sein Budget überwachen will
3. BudMon läuft unabhängig — kann jederzeit gestartet und beendet werden

## Was die Anzeigen bedeuten

### Quota-Balken (5h und 7d)

Zwei horizontale Fortschrittsbalken zeigen die aktuelle Kontingentauslastung
in Prozent. Markierungen an den konfigurierbaren Warn- und Alarmschwellen.

- **Grün** — unter Warnschwelle (Standard <75%)
- **Gelb** — zwischen Warnung und Alarm (Standard 75-90%)
- **Rot** — über Alarmschwelle (Standard >90%)

### Reset

Zeitpunkt des nächsten Quota-Resets mit Countdown. Bei 7d mit Datum
(z.B. "Fr. 04.04. 13:00 Uhr").

### Ablauf

Geschätzte Zeit bis das Kontingent bei aktuellem Verbrauch aufgebraucht ist.
Hellblau (normal), gelb (Warnung) oder rot (Alarm).

### Reserve

Differenz zwischen Ablauf und Reset. Positiv heißt genug Puffer.
Negativ heißt: das Kontingent wird vor dem Reset aufgebraucht.

- **+2 Std 30 Min** — sicher, 2,5 Stunden Puffer
- **-45 Min** — wird 45 Minuten vor Reset aufgebraucht

### Verbrauch (Burn-Rate)

Verbrauchsgeschwindigkeit. Für 5h: Prozent pro Stunde. Für 7d: Prozent pro Tag.

### Countdown-Ring

Kreisförmiger Timer über dem 5h-Quota-Balken. Zeigt entweder:

- **RESET** (grün) — Countdown bis zum Quota-Reset
- **ABLAUF** (gelb/rot) — Countdown bis zur Quota-Erschöpfung (falls vor dem Reset)

### Letzte Anfrage / Anfragen gesamt

Zwei Spalten mit Token-Aufschlüsselung:

- **Anfragen** — Anzahl API-Turns
- **Seit** — Wann die Session oder das Tracking begann
- **input** — Input-Tokens (Nutzernachrichten, System-Prompts)
- **output** — Output-Tokens (Assistenten-Antworten)
- **cache_c** — Cache-Creation-Tokens (erstmalige Zwischenspeicherung)
- **cache_r** — Cache-Read-Tokens (Wiederverwendung zwischengespeicherter Prompts)
- **Kosten** — Dollar-Betrag basierend auf Modell-Preisen

### Cache-Ratio Sparkline

Liniengraph der historischen Cache-Trefferquote. Höher ist besser (und günstiger).

- Die **aktuelle Ratio** wird als große Prozentzahl angezeigt
- Der **Durchschnitt** daneben
- Eine gestrichelte Linie markiert die 50%-Schwelle
- Der Punkt am Ende ist farbcodiert (grün/gelb/rot)

## Kommandozeile

```
budmon              Dashboard starten
budmon --setup      Claude Code Interceptor installieren
budmon --uninstall  Interceptor und Aliase entfernen
budmon --version    Version anzeigen
budmon --help       Hilfe anzeigen
```

## Konfiguration

Alle Einstellungen sind in `~/.claude/budmon.ini` gespeichert. Die Datei
wird beim ersten Start automatisch mit kommentierten Standardwerten erstellt.

Bearbeiten über:
- Dashboard: **Einstellungen > INI**
- Oder manuell mit jedem Texteditor

### Aufbau der Konfigurationsdatei

```ini
[general]
# Sprache: "auto" (Systemerkennung), "de", "en"
language = auto

# Aktualisierungsintervall in Millisekunden
refresh_ms = 1000

[model]
# Modell bestimmt Token-Preise: opus, sonnet, haiku, custom
model = opus

[prices]
# Nur bei model = custom. Auskommentieren um zu aktivieren.
# Preise pro 1M Token in USD.
#
# price_input = 15.0
# price_output = 75.0
# price_cache_read = 1.5
# price_cache_create = 18.75

[thresholds]
# Quota Warnung/Alarm (Prozent)
quota_warn_pct = 75.0
quota_alarm_pct = 90.0

# Cache-Ratio Warnung/Alarm (0.0 - 1.0)
cache_warn_ratio = 0.50
cache_alarm_ratio = 0.20

# Burn-Rate sicher/Warnung (Prozent pro Stunde)
burn_safe_pct_h = 15.0
burn_warn_pct_h = 25.0

[window]
# Fensterposition (wird automatisch verwaltet)
geometry =
```

### Modell-Presets

| Modell | Input | Output | Cache Read | Cache Create |
|---|---|---|---|---|
| **Opus** | $15,00 | $75,00 | $1,50 | $18,75 |
| **Sonnet** | $3,00 | $15,00 | $0,30 | $3,75 |
| **Haiku** | $0,80 | $4,00 | $0,08 | $1,00 |

Preise pro 1M Token in USD. Auswahl über Einstellungen > Modell oder in der INI-Datei.
Für eigene Preise: `model = custom` setzen und die Werte in `[prices]` einkommentieren.

## Menü

### Logs

- **Session-Log** — Öffnet das Token-Protokoll der aktuellen Session
- **History-Log** — Öffnet das persistente Protokoll über alle Sessions
- **Ordner** — Öffnet das Log-Verzeichnis im Dateimanager

### Einstellungen

- **Sprache** — Zwischen Deutsch und Englisch wechseln (UI wird neu aufgebaut)
- **Modell** — Opus, Sonnet, Haiku oder Custom wählen (Preise sofort aktualisiert)
- **INI** — Konfigurationsdatei im System-Texteditor öffnen

### Hilfe

- **Anleitung** — Diese Hilfedatei (in der aktuellen Sprache)
- **Info** — Version, Autor, Lizenz, Homepage, Laufzeit-Informationen

## Wie es funktioniert

BudMon besteht aus zwei unabhängigen Teilen:

### 1. Interceptor (`budmon-interceptor.mjs`)

Ein Node.js-Modul das über `NODE_OPTIONS="--import ..."` beim Start von
Claude Code geladen wird. Es klinkt sich in die globale `fetch()`-Funktion
ein und:

- **Erfasst Rate-Limit-Header** aus jeder `/v1/messages` API-Antwort
  (z.B. `anthropic-ratelimit-unified-5h-utilization`)
- **Extrahiert Token-Nutzung** aus SSE-Stream-Events (`message_start`,
  `message_delta`)
- **Schreibt alles in lokale JSON-Dateien** — sendet nie Daten irgendwohin

Der Interceptor ist strikt **nur-lesend**: Er reicht alle Anfragen und
Antworten unverändert durch. Er liest nur aus dem Antwort-Stream.

### 2. Dashboard (`budmon`)

Eine Python/tkinter Desktop-Anwendung die:

- `~/.claude/usage-limits.json` jede Sekunde abfragt (konfigurierbar)
- Quota-Prozente, Reset-Zeiten und Token-Zähler ausliest
- Burn-Rate, Ablaufzeit und Reserve berechnet
- Alles als dunkles GUI mit Fortschrittsbalken, Sparkline und
  Countdown-Ring darstellt

### Datendateien

Alle Daten liegen in `~/.claude/`:

| Datei | Geschrieben von | Inhalt |
|---|---|---|
| `usage-limits.json` | Interceptor | Aktuelle Quota, Header, Token pro Turn und kumuliert |
| `usage-cumulative.json` | Interceptor | Kumulative Token-Summen (überlebt Session-Neustarts) |
| `usage-session.jsonl` | Interceptor | Turn-Protokoll der aktuellen Session |
| `usage-history.jsonl` | Interceptor | Persistentes Turn-Protokoll über alle Sessions |
| `budmon.ini` | BudMon | Konfiguration |

## Datenschutz

BudMon erfasst **ausschließlich technische Metadaten** aus Claude Code API-Antworten:

- Rate-Limit-Header (Quota-Prozente, Reset-Zeitstempel)
- Token-Zähler (Input, Output, Cache Read, Cache Create)
- Zeitstempel der API-Aufrufe

BudMon erfasst **nicht**:

- Nachrichteninhalte (Prompts, Antworten, Tool-Aufrufe)
- API-Schlüssel oder Authentifizierungs-Tokens
- Persönliche Daten
- Dateiinhalte oder Code

Alle Daten bleiben lokal in `~/.claude/`. BudMon hat **keinen Netzwerkzugang** —
es verbindet sich nie mit einem Server, sendet keine Telemetrie, keine Analysen,
keine Absturzberichte. Der Interceptor arbeitet vollständig innerhalb des
Claude Code Node.js-Prozesses und schreibt nur in lokale Dateien.

Der Quellcode des Interceptors ist im Paket enthalten (`budmon/interceptor.mjs`)
und kann jederzeit überprüft werden.

## Sicherheit

Der Interceptor ist ein **nur-lesender** Durchreicher. Er klinkt sich in
`globalThis.fetch` ein um Antwort-Header und SSE-Stream-Daten zu lesen, aber:

- Er **verändert nie ausgehende Anfragen** (keine Payload-Änderungen, keine Header-Injektion)
- Er **blockiert oder verzögert nie** Anfragen oder Antworten
- Er **scheitert offen** — jeder Fehler im Interceptor wird still abgefangen,
  Claude Code funktioniert immer weiter

## Problemlösung

**Status "WAIT", alle Werte "--", unten "Warten auf Daten..."**

Das ist der normale Startzustand. BudMon wartet darauf dass Claude Code
Daten liefert. Das ist kein Fehler wenn BudMon vor Claude Code gestartet wurde.

Wenn der Zustand bestehen bleibt nachdem Claude Code laeuft:

1. **Wurde `budmon --setup` ausgefuehrt?**
   Pruefen: Existiert `~/.claude/budmon-interceptor.mjs`?
   Falls nicht: `budmon --setup` ausfuehren.

2. **Wurde Claude Code ueber `claude-budmon` gestartet?**
   Nur `claude-budmon` laedt den Interceptor. Ein normales `claude`
   schreibt keine Daten fuer BudMon.

3. **Wurde mindestens eine Nachricht gesendet?**
   Der Interceptor schreibt erst bei der ersten API-Antwort.
   Vor dem ersten Turn existiert die Datendatei noch nicht.

4. **Existiert die Datendatei?**
   Pruefen: `ls -la ~/.claude/usage-limits.json`
   Falls sie existiert aber alt ist: Claude Code wurde vermutlich ohne
   Interceptor gestartet. Neu starten ueber `claude-budmon`.

5. **Hatte BudMon vorher Daten und jetzt nicht mehr?**
   Die Claude Code Session wurde beendet. Starte eine neue
   Session ueber `claude-budmon`.

**Dashboard zeigt Quota-Balken aber Token-Details sind "--"**

Das ist kurzzeitig normal. Rate-Limit-Header werden sofort bei der API-Antwort
geschrieben, aber Token-Zähler erst nach Ende der Streaming-Antwort. Es gibt
ein kurzes Zeitfenster in dem Quota-Balken funktionieren aber Token-Details
noch nicht angekommen sind.

Falls es dauerhaft so bleibt: Claude Code muss über `claude-budmon` gestartet
worden sein. Eine reguläre `claude`-Session lädt den Interceptor nicht.

**Burn-Rate / Ablauf / Reserve zeigen "--"**

Burn-Rate benötigt zwei Dinge:
- Der Quota-Verbrauch muss über ~0,01% liegen (keine Berechnung bei Null-Verbrauch)
- Der Reset-Zeitstempel muss in den API-Headern vorhanden sein

Wenn Reset angezeigt wird aber Burn-Rate nicht: der Quota-Verbrauch ist zu
gering für eine sinnvolle Berechnung. Das löst sich nach mehr Nutzung von selbst.

**Fenster öffnet sich an falscher Stelle**

- Die `geometry`-Zeile in `~/.claude/budmon.ini` löschen um zur Mitte zurückzusetzen
- Oder über Einstellungen > INI bearbeiten

## Deinstallation

```bash
budmon --uninstall
pip uninstall budmon
```

`budmon --uninstall` entfernt:
- `~/.claude/budmon-interceptor.mjs`
- Den `claude-budmon` Alias aus `.bashrc`/`.zshrc`
- Das Wrapper-Script in `~/.local/bin/`
- Die `.desktop`-Datei (Linux)

Datendateien in `~/.claude/` werden **nicht** entfernt.

## Lizenz

GPL-3.0 — siehe [LICENSE](https://github.com/weilhalt/budmon/blob/main/LICENSE)

Copyright (c) 2026 weilhalt
