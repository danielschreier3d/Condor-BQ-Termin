"""SQLite-Persistenz der bekannten Termine.

Wir speichern jeden Termin mit einer stabilen ID (Hash über die relevanten
Felder), damit ein Termin auch dann eindeutig wiederzuerkennen ist, wenn
das Markup leicht variiert. So werden keine Duplikate als „neu" erkannt.
"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List


@dataclass(frozen=True)
class Appointment:
    """Eine einzelne Termin-Information."""

    title: str          # z. B. "Ab Initio Theorieprüfung"
    date: str           # Roher Datums-/Zeit-String von der Website
    location: str = ""  # Optional: Ort / Standort
    url: str = ""       # Optional: Direktlink zur Buchungsseite
    extra: str = ""     # Optional: Freitext für sonstige Infos

    @property
    def fingerprint(self) -> str:
        """Stabile ID, die identische Termine erkennt."""
        raw = f"{self.title}|{self.date}|{self.location}|{self.url}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# DB-Initialisierung
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    fingerprint TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    date        TEXT NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    url         TEXT NOT NULL DEFAULT '',
    extra       TEXT NOT NULL DEFAULT '',
    first_seen  TEXT NOT NULL,    -- ISO-8601 UTC
    last_seen   TEXT NOT NULL     -- ISO-8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_appointments_first_seen
    ON appointments(first_seen);
"""


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Kontextmanager, der eine SQLite-Verbindung mit Row-Factory öffnet."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path) -> None:
    """Lege Schema an, falls es noch nicht existiert."""
    with _connect(db_path) as conn:
        conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Hauptlogik: neue Termine ermitteln und persistieren
# ---------------------------------------------------------------------------

def filter_new(
    db_path: Path, candidates: Iterable[Appointment]
) -> List[Appointment]:
    """Gib alle Termine zurück, deren Fingerprint noch unbekannt ist."""
    candidates = list(candidates)
    if not candidates:
        return []

    fingerprints = [c.fingerprint for c in candidates]
    placeholders = ",".join("?" for _ in fingerprints)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT fingerprint FROM appointments WHERE fingerprint IN ({placeholders})",
            fingerprints,
        ).fetchall()
        known = {row["fingerprint"] for row in rows}

    return [c for c in candidates if c.fingerprint not in known]


def upsert_all(db_path: Path, appointments: Iterable[Appointment]) -> None:
    """Speichere/aktualisiere alle aktuell beobachteten Termine.

    - Unbekannte werden eingefügt (mit first_seen = jetzt).
    - Bekannte werden in last_seen aktualisiert (so erkennen wir auch,
      welche Termine inzwischen wieder verschwunden sind).
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with _connect(db_path) as conn:
        for a in appointments:
            data = asdict(a)
            data["fingerprint"] = a.fingerprint
            data["first_seen"] = now
            data["last_seen"] = now
            conn.execute(
                """
                INSERT INTO appointments (fingerprint, title, date, location,
                                          url, extra, first_seen, last_seen)
                VALUES (:fingerprint, :title, :date, :location, :url, :extra,
                        :first_seen, :last_seen)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    last_seen = excluded.last_seen
                """,
                data,
            )
