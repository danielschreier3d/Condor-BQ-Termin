"""HTTP-Abruf und HTML-Parsing.

`fetch_html` lädt die Seite. `parse_appointments` extrahiert die Termin-Slots
aus dem HTML. Diese Datei ist die *einzige Stelle*, an der du Anpassungen
vornehmen musst, sobald du die genaue HTML-Struktur deiner Zielseite kennst.

Strategie:
1. Wir laden die Seite mit `requests`.
2. Wir versuchen mehrere Heuristiken, um Termine zu finden.
3. Falls keine der Heuristiken passt, kannst du `parse_appointments`
   einfach durch deine eigene Implementierung ersetzen – Rückgabewert ist
   eine Liste von `Appointment`-Objekten.
"""

from __future__ import annotations

import logging
import re
from typing import List

import requests
from bs4 import BeautifulSoup

from .storage import Appointment

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_html(url: str, *, user_agent: str, timeout_s: int) -> str:
    """Lade die Zielseite und gib das HTML zurück."""
    headers = {
        "User-Agent": user_agent,
        # Viele Shops liefern leere/abweichende Inhalte, wenn diese Header fehlen:
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    # Encoding aus dem HTTP-Header bevorzugen, sonst Auto-Detect:
    if not resp.encoding:
        resp.encoding = resp.apparent_encoding
    return resp.text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Datums-/Zeit-Muster, das wir grob als Heuristik nutzen.
# Beispiele die getroffen werden:
#   "12.05.2026"    "12.05.2026 09:00"    "Mo, 12.05.2026"
DATE_RE = re.compile(
    r"\b(?:(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?,?\s*)?"
    r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}"
    r"(?:\s+\d{1,2}:\d{2})?\b"
)


def parse_appointments(html: str, *, base_url: str = "") -> List[Appointment]:
    """Extrahiere Termine aus dem HTML.

    Diese Default-Implementierung versucht zuerst typische Selektoren für
    Buchungsshops und fällt dann auf eine Datums-Regex zurück.

    --> ANPASSEN: Sobald du die HTML-Struktur kennst, ersetze den Body
        dieser Funktion durch eine zielgerichtete BeautifulSoup-Abfrage.
    """
    soup = BeautifulSoup(html, "html.parser")
    appointments: list[Appointment] = []

    # ---- Strategie 1: bekannte Klassen/Datenattribute --------------------
    # Viele Shop-/Booking-Systeme nutzen Klassen wie .appointment, .slot,
    # .product-item, .availability. Erweitere die Liste nach Bedarf.
    candidate_blocks = soup.select(
        ".appointment, .slot, .booking-slot, .product-item, "
        ".event, .event-item, [data-appointment], [data-slot]"
    )

    for block in candidate_blocks:
        title = _first_text(block, ["h1", "h2", "h3", ".title", ".name"])
        date_text = _first_text(block, [".date", ".datetime", "time", ".when"])
        location = _first_text(block, [".location", ".venue", ".place"])
        link = block.find("a", href=True)
        url = _absolutize(base_url, link["href"]) if link else ""

        if title and date_text:
            appointments.append(
                Appointment(
                    title=title.strip(),
                    date=date_text.strip(),
                    location=(location or "").strip(),
                    url=url,
                )
            )

    if appointments:
        log.info("Strategie 1 (CSS-Selektoren) hat %d Termine gefunden.",
                 len(appointments))
        return _dedupe(appointments)

    # ---- Strategie 2: Regex-Fallback -------------------------------------
    # Wir suchen alle Vorkommen eines Datums im sichtbaren Text und nehmen
    # die nächstliegende Überschrift als Titel. Das ist absichtlich grob
    # und soll nur den Prototyp lebendig halten.
    page_title = (soup.title.get_text(strip=True) if soup.title else "Termin")

    for match in DATE_RE.finditer(soup.get_text(" ", strip=True)):
        appointments.append(
            Appointment(
                title=page_title,
                date=match.group(0).strip(),
                url=base_url,
            )
        )

    if appointments:
        log.info("Strategie 2 (Regex-Fallback) hat %d Termine gefunden.",
                 len(appointments))

    return _dedupe(appointments)


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _first_text(node, selectors: list[str]) -> str:
    """Gib den Text des ersten passenden Selektors zurück (oder '')."""
    for sel in selectors:
        found = node.select_one(sel)
        if found and found.get_text(strip=True):
            return found.get_text(" ", strip=True)
    return ""


def _absolutize(base_url: str, href: str) -> str:
    """Mache einen relativen Link absolut."""
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    if not base_url:
        return href
    from urllib.parse import urljoin
    return urljoin(base_url, href)


def _dedupe(items: list[Appointment]) -> list[Appointment]:
    """Entferne identische Termine (gleicher Fingerprint)."""
    seen: set[str] = set()
    out: list[Appointment] = []
    for a in items:
        if a.fingerprint not in seen:
            seen.add(a.fingerprint)
            out.append(a)
    return out
