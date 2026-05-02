"""Minimale Smoke-Tests, die ohne Internet/SMTP laufen."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from src.scraper import parse_appointments
from src.storage import Appointment, filter_new, init_db, upsert_all


SAMPLE_HTML = """
<html><head><title>Ab Initio Termine</title></head>
<body>
  <div class="appointment">
    <h3 class="title">Theorieprüfung Ab Initio</h3>
    <span class="date">12.05.2026 09:00</span>
    <span class="location">Frankfurt</span>
    <a href="/buchen/123">Buchen</a>
  </div>
  <div class="appointment">
    <h3 class="title">Theorieprüfung Ab Initio</h3>
    <span class="date">19.05.2026 09:00</span>
    <span class="location">München</span>
    <a href="/buchen/124">Buchen</a>
  </div>
</body></html>
"""


def test_parse_finds_two_appointments():
    items = parse_appointments(SAMPLE_HTML, base_url="https://example.com/")
    assert len(items) == 2
    assert items[0].title.startswith("Theorieprüfung")
    assert items[0].url.startswith("https://example.com/")


def test_filter_new_and_upsert(tmp_path: Path):
    db = tmp_path / "test.sqlite"
    init_db(db)

    a = Appointment(title="X", date="01.01.2026", location="Berlin")
    b = Appointment(title="X", date="02.01.2026", location="Berlin")

    assert filter_new(db, [a, b]) == [a, b]
    upsert_all(db, [a, b])

    # Beim zweiten Lauf darf nichts mehr "neu" sein.
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
