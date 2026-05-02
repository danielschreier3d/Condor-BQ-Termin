"""Einstiegspunkt der Anwendung.

Wird *einmal pro Cron-Aufruf* ausgeführt (z. B. alle 5 Minuten via
GitHub Actions). Der Ablauf ist bewusst linear und idempotent:

    1. Konfiguration laden
    2. SQLite-DB initialisieren
    3. Website laden
    4. Termine parsen
    5. Mit DB abgleichen → neue Termine ermitteln
    6. E-Mail bei neuen Treffern verschicken
    7. DB aktualisieren
"""

from __future__ import annotations

import logging
import sys

from .config import Settings
from .notifier import send_new_appointments_email
from .scraper import fetch_html, parse_appointments
from .storage import filter_new, init_db, upsert_all


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def run() -> int:
    """Hauptablauf. Rückgabewert ist der Exit-Code."""
    try:
        settings = Settings.from_env()
    except RuntimeError as exc:
        # Konfigurationsfehler -> sofort raus
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    _configure_logging(settings.log_level)
    log = logging.getLogger("condorwatch")

    log.info("Starte Lauf für %s", settings.target_url)
    init_db(settings.db_path)

    # 1) Seite laden
    try:
        html = fetch_html(
            settings.target_url,
            user_agent=settings.user_agent,
            timeout_s=settings.request_timeout_s,
        )
    except Exception:
        log.exception("Konnte Seite nicht laden – Lauf wird übersprungen.")
        return 1

    # 2) Termine extrahieren
    found = parse_appointments(html, base_url=settings.target_url)
    log.info("Gefunden: %d Termin-Kandidaten", len(found))

    # 3) Neue Termine ermitteln
    new_ones = filter_new(settings.db_path, found)
    log.info("Davon NEU: %d", len(new_ones))

    # 4) Bei Bedarf E-Mail senden
    if new_ones:
        try:
            send_new_appointments_email(
                new_ones,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                smtp_use_tls=settings.smtp_use_tls,
                notify_from=settings.notify_from,
                notify_to=settings.notify_to,
                target_url=settings.target_url,
                dry_run=settings.dry_run,
            )
        except Exception:
            # E-Mail-Fehler darf den Status nicht zerstören – wir
            # speichern nicht, damit beim nächsten Lauf erneut versucht wird.
            log.exception("E-Mail-Versand fehlgeschlagen.")
            return 1

    # 5) DB aktualisieren (alle aktuell sichtbaren Termine)
    upsert_all(settings.db_path, found)
    log.info("Lauf abgeschlossen.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
