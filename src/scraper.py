"""HTTP-Abruf und HTML-Parsing für shop.interpersonal.aero (Shopware-Shop).

Erkenntnisse aus der Analyse der echten Seite:

1. Das Buchungsformular liegt in `<form id="productDetailPageBuyProductForm">`.
2. Innerhalb des Formulars gibt es eine `<ul class="list-group …">`, die
   die buchbaren Termin-Slots als `<li>`-Einträge enthält. Ist sie leer,
   wird stattdessen das Badge „Momentan gibt es keine Termine" angezeigt.
3. Die Auswahl eines Slots ruft `reloadPageWithSlot(<id>)` auf und hängt
   `?slotId=<id>` an die URL – darüber bekommen wir den Buchungslink.
4. Zusätzlich gibt es Schema.org-`Event`-Objekte als JSON-LD im Head.
   Diese listen *alle* geplanten Termine, auch wenn aktuell nichts
   buchbar ist – wir nutzen sie nur informativ in den Logs.

Daher: **Primärsignal** = Items in `form#productDetailPageBuyProductForm
ul.list-group li`. Genau die werden im E-Mail-Alarm verwendet.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, Tag

from .storage import Appointment

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def fetch_html(url: str, *, user_agent: str, timeout_s: int) -> str:
    """Lade die Zielseite und gib das HTML zurück."""
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    if not resp.encoding:
        resp.encoding = resp.apparent_encoding
    return resp.text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# CSS-Selektor für die buchbaren Slot-Einträge.
# Wir bleiben absichtlich breit: jedes <li> innerhalb der list-group im
# Buy-Form gilt als Slot. Das ist robust gegen minimale Markup-Änderungen.
SLOT_LIST_SELECTOR = "form#productDetailPageBuyProductForm ul.list-group"

# Erkennt 06.05.2026, 6.5.2026 (mit/ohne Zeit) und ISO 2026-05-06[T09:00].
DATE_DE_RE = re.compile(
    r"\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}(?:\s+\d{1,2}:\d{2})?\b"
)
DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2})?\b")

# Erkennt slotId in JS-Aufrufen oder Attributen
SLOT_ID_RE = re.compile(
    r"(?:reloadPageWithSlot\(|slotId[^0-9]{0,4})(\d+)", re.IGNORECASE
)


def parse_appointments(html: str, *, base_url: str = "") -> List[Appointment]:
    """Extrahiere die aktuell buchbaren Termine aus dem HTML.

    Rückgabe ist eine Liste von `Appointment`-Objekten – nur Termine, die
    laut Slot-Liste *jetzt buchbar* sind. JSON-LD-Events werden nur in den
    Logs erwähnt (zur Orientierung), aber nicht als verfügbar gemeldet,
    weil der Shop Events listet, die gar nicht bookbar sein müssen.
    """
    soup = BeautifulSoup(html, "html.parser")

    # ---- Diagnoselauf: Schema.org-Events fürs Log ------------------------
    scheduled = _extract_scheduled_events(soup)
    if scheduled:
        log.info(
            "Schema.org listet %d geplante Events (nur Info, kein Alarm): %s",
            len(scheduled),
            ", ".join(e["startDate"] for e in scheduled[:10]),
        )

    # ---- Primärsignal: list-group im Buchungsformular --------------------
    appointments: list[Appointment] = []
    list_group = soup.select_one(SLOT_LIST_SELECTOR)

    if list_group is None:
        log.warning(
            "Slot-Liste nicht gefunden (%s) – evtl. Markup geändert.",
            SLOT_LIST_SELECTOR,
        )
        return []

    items = list_group.find_all("li", recursive=False) or list_group.find_all("li")
    log.info("Slot-Liste hat %d <li>-Einträge.", len(items))

    page_title = _extract_event_name(soup) or "Termin"

    for li in items:
        text = _clean(li.get_text(" ", strip=True))
        if not text:
            # Leere Platzhalter-LIs überspringen (Shopware lässt manchmal
            # gerenderte Hülsen ohne Inhalt im DOM).
            continue

        date_str = _extract_date(text) or text
        slot_id = _extract_slot_id(li)
        url = _build_slot_url(base_url, slot_id)

        appointments.append(
            Appointment(
                title=page_title,
                date=date_str,
                location=_extract_location(soup),
                url=url,
                extra=text if text != date_str else "",
            )
        )

    if not appointments:
        # Sanity: prüfe das „keine Termine"-Badge – dann ist das Ergebnis
        # erwartungskonform „leer".
        no_slots = soup.find(
            string=re.compile(r"keine\s+Termine", re.IGNORECASE)
        )
        if no_slots:
            log.info("Bestätigt: Seite zeigt 'keine Termine' an.")
        else:
            log.warning(
                "Slot-Liste leer, aber auch kein 'keine Termine'-Badge – "
                "ggf. Markup geändert."
            )

    return _dedupe(appointments)


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _extract_scheduled_events(soup: BeautifulSoup) -> list[dict]:
    """Lies die Schema.org-Event-Objekte aus dem JSON-LD-Block."""
    out: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") == "Event" and item.get("startDate"):
                out.append(item)
    return out


def _extract_event_name(soup: BeautifulSoup) -> str:
    """Bevorzugt den Event-Namen aus JSON-LD, sonst <title>."""
    for ev in _extract_scheduled_events(soup):
        if ev.get("name"):
            return str(ev["name"]).strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def _extract_location(soup: BeautifulSoup) -> str:
    """Hole den Veranstaltungsort aus dem JSON-LD."""
    for ev in _extract_scheduled_events(soup):
        loc = ev.get("location")
        if isinstance(loc, dict):
            name = loc.get("name", "")
            addr = loc.get("address", "")
            return ", ".join(p for p in (name, addr) if p)
    return ""


def _extract_date(text: str) -> str:
    """Finde das wahrscheinlichste Datum im Text."""
    m = DATE_DE_RE.search(text) or DATE_ISO_RE.search(text)
    return m.group(0) if m else ""


def _extract_slot_id(li: Tag) -> str:
    """Finde die slotId aus onclick/data-Attributen."""
    for attr_name in ("onclick", "data-slot-id", "data-id", "value"):
        val = li.get(attr_name)
        if val:
            m = SLOT_ID_RE.search(val if isinstance(val, str) else " ".join(val))
            if m:
                return m.group(1)
    # auch in Kindelementen suchen
    for child in li.find_all(True):
        for attr_name in ("onclick", "data-slot-id", "data-id", "value"):
            val = child.get(attr_name)
            if val:
                m = SLOT_ID_RE.search(
                    val if isinstance(val, str) else " ".join(val)
                )
                if m:
                    return m.group(1)
    return ""


def _build_slot_url(base_url: str, slot_id: str) -> str:
    """Baue die Buchungs-URL im Format <base>?slotId=<id>."""
    if not base_url:
        return ""
    if not slot_id:
        return base_url
    parsed = urlparse(base_url)
    # bestehende Query-Params plump überschreiben (es gibt nur slotId)
    new_query = f"slotId={slot_id}"
    return urlunparse(parsed._replace(query=new_query))


def _clean(text: str) -> str:
    """Whitespace normalisieren."""
    return re.sub(r"\s+", " ", text).strip()


def _dedupe(items: list[Appointment]) -> list[Appointment]:
    """Entferne identische Termine (gleicher Fingerprint)."""
    seen: set[str] = set()
    out: list[Appointment] = []
    for a in items:
        if a.fingerprint not in seen:
            seen.add(a.fingerprint)
            out.append(a)
    return out
