"""Minimale Smoke-Tests, die ohne Internet/SMTP laufen.

Sie validieren das Verhalten des Parsers gegen die echte Shopware-Struktur
von shop.interpersonal.aero (Form#productDetailPageBuyProductForm) sowie
die Persistenz-Logik in storage.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.scraper import parse_appointments
from src.storage import Appointment, filter_new, init_db, upsert_all


# ---------------------------------------------------------------------------
# HTML-Fixtures, die die echte Shop-Struktur nachbilden
# ---------------------------------------------------------------------------

JSONLD_HEAD = """\
<!doctype html>
<html><head>
  <title>BQ ip Ab-Initio | BQI10020</title>
  <script type="application/ld+json">
  [{
    "@context": "https://schema.org",
    "@type": "Event",
    "name": "Basic Qualification ip Ab-Initio",
    "startDate": "2026-05-06T09:00",
    "location": {"name": "Interpersonal", "address": "Hamburg, Germany"}
  }]
  </script>
</head><body>
"""

FORM_OPEN = """\
<form id="productDetailPageBuyProductForm" action="/de/checkout/line-item/add"
      method="post" class="buy-widget" data-add-to-cart="true">
  <ul class="list-group mt-2 mb-3" style="max-height: 23rem; overflow-y: auto">
"""

FORM_CLOSE = """\
  </ul>
</form>
</body></html>
"""

NO_SLOTS_BADGE = (
    '<span class="badge bg-warning mb-3">'
    'Momentan gibt es keine Termine für dieses Event.</span>'
)

WITH_SLOTS = """\
    <li class="list-group-item" onclick="reloadPageWithSlot(4711)">
      06.05.2026 09:00 – 17:00 Uhr · Hamburg
    </li>
    <li class="list-group-item" onclick="reloadPageWithSlot(4815)">
      11.05.2026 09:00 (Restplätze)
    </li>
"""

HTML_NO_SLOTS = JSONLD_HEAD + FORM_OPEN + FORM_CLOSE + NO_SLOTS_BADGE
HTML_WITH_SLOTS = JSONLD_HEAD + FORM_OPEN + WITH_SLOTS + FORM_CLOSE


BASE_URL = "https://shop.interpersonal.aero/de/BQ-ip-Ab-Initio/BQI10020"


# ---------------------------------------------------------------------------
# Parser-Tests
# ---------------------------------------------------------------------------

def test_parser_returns_empty_when_no_slots():
    """Aktuelle Live-Situation: leere Liste, 'keine Termine'-Badge sichtbar."""
    items = parse_appointments(HTML_NO_SLOTS, base_url=BASE_URL)
    assert items == []


def test_parser_extracts_slots_with_id_and_url():
    """Wenn Slots da sind: Datum, slotId-URL und Title aus JSON-LD."""
    items = parse_appointments(HTML_WITH_SLOTS, base_url=BASE_URL)
    assert len(items) == 2

    a = items[0]
    assert a.title == "Basic Qualification ip Ab-Initio"
    assert a.date == "06.05.2026 09:00"
    assert a.url == f"{BASE_URL}?slotId=4711"
    assert "Hamburg" in a.location

    b = items[1]
    assert b.date == "11.05.2026 09:00"
    assert b.url.endswith("?slotId=4815")


def test_parser_dedupes_identical_li():
    """Mehrere LIs mit gleicher slotId/Datum dürfen nur einmal vorkommen."""
    duplicate_html = (
        JSONLD_HEAD + FORM_OPEN + WITH_SLOTS + WITH_SLOTS + FORM_CLOSE
    )
    items = parse_appointments(duplicate_html, base_url=BASE_URL)
    assert len(items) == 2  # nicht 4


# ---------------------------------------------------------------------------
# Storage-Tests
# ---------------------------------------------------------------------------

def test_filter_new_and_upsert(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    init_db(db)

    a = Appointment(title="X", date="01.01.2026", location="Berlin")
    b = Appointment(title="X", date="02.01.2026", location="Berlin")

    assert filter_new(db, [a, b]) == [a, b]
    upsert_all(db, [a, b])

    # Beim zweiten Lauf darf nichts mehr „neu" sein.
    assert filter_new(db, [a, b]) == []

    # Aber ein dritter Termin muss als neu erkannt werden.
    c = Appointment(title="X", date="03.01.2026", location="Berlin")
    assert filter_new(db, [a, b, c]) == [c]


def test_db_schema_created(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    init_db(db)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert ("appointments",) in rows
