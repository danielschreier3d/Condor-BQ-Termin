# Termin-Monitor – Interpersonal BQ

Überwacht eine Buchungsseite auf neue Termin-Slots und sendet bei jedem
neuen Termin eine E-Mail. Läuft **vollständig kostenlos auf GitHub Actions**
– kein eigener Server nötig.

## Funktionsweise

```
GitHub Actions Cron (alle 5 Min)
        │
        ▼
   src/main.py  ──▶  HTML laden (requests)
                       │
                       ▼
                  parsen (BeautifulSoup) ──▶ Liste von Terminen
                       │
                       ▼
                  SQLite-DB abgleichen
                       │
                       ▼
                  Neu? → E-Mail (SMTP)
                       │
                       ▼
                  DB committen → Repo
```

Die SQLite-Datei (`data/appointments.sqlite`) wird nach jedem Lauf
automatisch ins Repo zurückcommittet – so bleibt der Stand zwischen den
Läufen erhalten, ohne dass eine externe Datenbank nötig ist.

## Projektstruktur

```
.
├── .github/workflows/monitor.yml   # Cron-Job (alle 5 Min)
├── src/
│   ├── config.py                   # Settings aus ENV
│   ├── scraper.py                  # HTTP + HTML-Parsing  ◀── HIER ANPASSEN
│   ├── storage.py                  # SQLite-Persistenz
│   ├── notifier.py                 # SMTP-E-Mail
│   └── main.py                     # Orchestrierung
├── tests/test_smoke.py             # pytest – läuft offline
├── data/appointments.sqlite        # State (wird automatisch erzeugt)
├── requirements.txt
├── .env.example                    # Template für lokales Testen
└── .gitignore
```

## Setup (≈ 10 Minuten)

### 1. Repo anlegen
1. Erstelle ein **privates GitHub-Repo** (private wegen E-Mail-Adressen,
   Free-Tier-Repos haben 2000 Action-Minuten pro Monat – mehr als genug).
2. Pushe diesen Ordner als ersten Commit hinein.

### 2. Gmail-App-Passwort erzeugen
1. Aktiviere **2-Faktor-Authentifizierung** auf deinem Google-Konto
   (Pflicht für App-Passwörter).
2. Öffne https://myaccount.google.com/apppasswords
3. Erzeuge ein neues App-Passwort namens „Termin-Monitor". Du bekommst
   einen **16-stelligen** Code – kopiere ihn (er wird nur einmal gezeigt).

### 3. GitHub-Repo-Secrets setzen
`Settings → Secrets and variables → Actions → New repository secret`

| Name             | Wert                                                       |
|------------------|------------------------------------------------------------|
| `TARGET_URL`     | `https://shop.interpersonal.aero/de/BQ-ip-Ab-Initio/BQI10020` |
| `SMTP_HOST`      | `smtp.gmail.com`                                           |
| `SMTP_PORT`      | `587`                                                      |
| `SMTP_USE_TLS`   | `true`                                                     |
| `SMTP_USER`      | deine Gmail-Adresse                                        |
| `SMTP_PASSWORD`  | das 16-stellige App-Passwort                               |
| `NOTIFY_FROM`    | deine Gmail-Adresse                                        |
| `NOTIFY_TO`      | `daniel.schreier@exentra.de`                               |

Optional (`Settings → Secrets and variables → Actions → Variables`):

| Name        | Wert                                                |
|-------------|-----------------------------------------------------|
| `DRY_RUN`   | `true` während der Einrichtung (sendet keine Mail)  |
| `LOG_LEVEL` | `DEBUG` für mehr Logs                               |

### 4. Workflow zum ersten Mal triggern
- `Actions` → **Termin-Monitor** → **Run workflow** (manuell starten,
  damit du nicht 5 Min warten musst).
- Im Log siehst du, wie viele Termine die Default-Heuristik findet.

### 5. Parser an deine Seite anpassen (wichtig!)
Der Default-Parser in `src/scraper.py → parse_appointments` ist
generisch und funktioniert evtl. nicht 1:1 mit `shop.interpersonal.aero`.
So passt du ihn an:

1. Öffne die Zielseite im Browser, Rechtsklick → **Untersuchen**.
2. Identifiziere ein Element, das einen einzelnen Termin umschließt
   (z. B. `<div class="product-tile">…</div>`).
3. Identifiziere innerhalb dieses Elements:
   - den **Titel** (z. B. `h2.product-name`)
   - das **Datum/Zeit** (z. B. `span.product-date`)
   - optional: **Ort** und **Buchungs-Link**
4. Ersetze in `parse_appointments` Strategie 1 mit deinen Selektoren.

> Tipp: Wenn die Seite Termine erst per JavaScript nachlädt, kommen
> sie im rohen HTML nicht an. In dem Fall musst du im Network-Tab die
> JSON-Endpoint-URL identifizieren und stattdessen direkt diese
> abfragen (mit `requests.get(json_url).json()`).

## Lokal testen

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Werte eintragen
DRY_RUN=true python -m src.main      # läuft, aber sendet keine Mail
pytest                                # offline-Smoketests
```

## Häufige Fragen

**Warum 5 Minuten und nicht 60 Sekunden?**
GitHub Actions akzeptiert nur Cron-Schedules ≥ 5 Min und kann unter
Last sogar 10–15 Min Verzögerung haben. Für Termin-Monitoring ist das
trotzdem schnell genug. 60 s wäre nur mit einer dauerhaft laufenden VM
möglich (Oracle Cloud Free, Fly.io o. ä.).

**Wer bezahlt das?**
Niemand. Private Repos haben 2000 freie Action-Minuten/Monat. Ein
Lauf dauert ~30 s ⇒ ≈ 4 320 Min/Monat bei 5-Min-Takt. Bei einem
**öffentlichen Repo** ist GitHub Actions komplett unbegrenzt kostenlos.

**Was passiert, wenn die Website kurzzeitig down ist?**
Der Lauf endet mit Exit-Code 1, es wird nichts gespeichert und nichts
gesendet. Beim nächsten Lauf wird neu versucht.

**Spam-Schutz: Bekomme ich für denselben Termin mehrfach Mails?**
Nein. Sobald ein Termin in der DB landet, gilt er nicht mehr als „neu".
Verschwindet der Termin und taucht später wieder auf, wird er aufgrund
desselben Fingerprints **nicht** erneut gemeldet (der Eintrag bleibt in
der DB). Wenn du das wünschst, lässt sich `filter_new` leicht anpassen.

**Wie deaktiviere ich das Tool kurz?**
`Actions → Termin-Monitor → ⋯ → Disable workflow`
