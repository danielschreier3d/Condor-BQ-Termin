"""Sendet eine echte Test-E-Mail mit einem Fake-Termin.

Zweck: einmaliger End-to-End-Test der SMTP-Pipeline (Login, TLS, Versand,
Zustellung). Berührt die SQLite-DB **nicht** – läuft komplett separat zum
normalen Monitor-Job.

Aufruf:  python -m src.test_notify
"""

from __future__ import annotations

import logging
import os
import sys

from .config import Settings
from .notifier import send_new_appointments_email
from .storage import Appointment


def main() -> int:
    # DRY_RUN für diesen Lauf zwangsweise abschalten – sonst würde die
    # Mail nicht abgeschickt werden, falls der Nutzer DRY_RUN=true gesetzt
    # hat.
    os.environ["DRY_RUN"] = "false"

    logging.basicConfig(
        level="INFO",
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("condorwatch.test_notify")

    settings = Settings.from_env()
    log.info("Sende Test-Mail an %s über %s:%d …",
             settings.notify_to, settings.smtp_host, settings.smtp_port)

    fake = Appointment(
        title="[CondorWatch TEST] Basic Qualification ip Ab-Initio",
        date="01.01.2099 09:00",
        location="Interpersonal, Hamburg (Test-Daten, kein echter Termin)",
        url=f"{settings.target_url}?slotId=TEST-0000",
        extra="Diese Mail bestätigt nur, dass die SMTP-Pipeline funktioniert. "
              "Bitte ignorieren – es wurde KEIN echter Termin gefunden.",
    )

    send_new_appointments_email(
        [fake],
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        smtp_use_tls=settings.smtp_use_tls,
        notify_from=settings.notify_from,
        notify_to=settings.notify_to,
        target_url=settings.target_url,
        dry_run=False,
    )
    log.info("Fertig. Bitte Posteingang von %s prüfen.", settings.notify_to)
    return 0


if __name__ == "__main__":
    sys.exit(main())
