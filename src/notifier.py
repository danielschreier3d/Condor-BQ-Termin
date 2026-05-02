"""E-Mail-Versand via SMTP.

Funktioniert mit Gmail (App-Passwort), Outlook, eigenem Mailserver, …
Für Gmail:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=<deine@gmail.com>
    SMTP_PASSWORD=<App-Passwort>  (https://myaccount.google.com/apppasswords)
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable

from .storage import Appointment

log = logging.getLogger(__name__)


def send_new_appointments_email(
    new_appointments: Iterable[Appointment],
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_use_tls: bool,
    notify_from: str,
    notify_to: str,
    target_url: str,
    dry_run: bool = False,
) -> None:
    """Sende eine Benachrichtigung über neu entdeckte Termine.

    Wird nichts übergeben oder ist `dry_run=True`, wird nichts versendet.
    """
    items = list(new_appointments)
    if not items:
        log.info("Keine neuen Termine – keine E-Mail nötig.")
        return

    subject = f"[CondorWatch] {len(items)} neue(r) Termin(e) verfügbar"
    plain, html = _render_bodies(items, target_url)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = notify_from
    msg["To"] = notify_to
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    if dry_run:
        log.warning("DRY_RUN aktiv – E-Mail wird NICHT gesendet:\n%s", plain)
        return

    log.info("Sende E-Mail an %s über %s:%d …", notify_to, smtp_host, smtp_port)
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.ehlo()
        if smtp_use_tls:
            server.starttls(context=context)
            server.ehlo()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
    log.info("E-Mail erfolgreich gesendet.")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def _render_bodies(items: list[Appointment], target_url: str) -> tuple[str, str]:
    """Erzeuge Plain-Text- und HTML-Variante des Mailbodys."""
    plain_lines = [f"Es wurden {len(items)} neue Termine gefunden:\n"]
    for a in items:
        plain_lines.append(f"• {a.title}")
        plain_lines.append(f"  Datum:  {a.date}")
        if a.location:
            plain_lines.append(f"  Ort:    {a.location}")
        if a.url:
            plain_lines.append(f"  Link:   {a.url}")
        plain_lines.append("")
    plain_lines.append(f"Quelle: {target_url}")
    plain = "\n".join(plain_lines)

    html_items = []
    for a in items:
        html_items.append(
            f"<li><strong>{_esc(a.title)}</strong><br>"
            f"Datum: {_esc(a.date)}"
            + (f"<br>Ort: {_esc(a.location)}" if a.location else "")
            + (f"<br><a href='{_esc(a.url)}'>{_esc(a.url)}</a>" if a.url else "")
            + "</li>"
        )

    html = f"""\
<!doctype html>
<html><body style="font-family: -apple-system, Segoe UI, sans-serif;">
  <h2>Neue Termine verfügbar ({len(items)})</h2>
  <ul>
    {''.join(html_items)}
  </ul>
  <p style="color:#666;font-size:12px">Quelle:
    <a href="{_esc(target_url)}">{_esc(target_url)}</a></p>
</body></html>
"""
    return plain, html


def _esc(s: str) -> str:
    """Minimale HTML-Escapes."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
