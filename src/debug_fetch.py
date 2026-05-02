"""Diagnose-Skript für die Parser-Entwicklung.

Lädt die TARGET_URL, gibt eine Reihe von Statistiken auf STDOUT aus
(Status, Länge, Title, vorhandene CSS-Klassen, JSON-Endpoints …) und
schreibt das vollständige HTML nach `data/last_page.html`. Der GitHub-
Actions-Workflow lädt diese Datei dann als Artifact hoch, sodass wir
sie offline analysieren können.

Aufruf:  python -m src.debug_fetch
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

from .config import Settings
from .scraper import fetch_html


def main() -> int:
    settings = Settings.from_env()
    print(f"[debug] Lade {settings.target_url} …")

    try:
        html = fetch_html(
            settings.target_url,
            user_agent=settings.user_agent,
            timeout_s=settings.request_timeout_s,
        )
    except Exception as exc:
        print(f"[debug] FEHLER beim Laden: {exc}", file=sys.stderr)
        return 1

    out = settings.db_path.parent / "last_page.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"[debug] HTML gespeichert: {out}  ({len(html)} Zeichen)")

    soup = BeautifulSoup(html, "html.parser")

    # ---- Basics ----------------------------------------------------------
    title = soup.title.get_text(strip=True) if soup.title else "(kein <title>)"
    print(f"[debug] <title>: {title}")

    # ---- Wichtige Hinweise auf JS-gerenderte Inhalte --------------------
    body_text_len = len(soup.get_text(strip=True))
    print(f"[debug] sichtbarer Text im rohen HTML: {body_text_len} Zeichen")
    if body_text_len < 500:
        print("[debug] HINWEIS: Sehr wenig Text – Seite lädt vermutlich "
              "Inhalte per JavaScript nach.")

    js_frameworks = []
    for needle, label in [
        ("data-react", "React"),
        ("ng-app", "Angular"),
        ("vue", "Vue"),
        ("__NEXT_DATA__", "Next.js"),
        ("__NUXT__", "Nuxt"),
    ]:
        if needle in html:
            js_frameworks.append(label)
    if js_frameworks:
        print(f"[debug] JS-Framework-Indikatoren: {', '.join(js_frameworks)}")

    # ---- Häufige CSS-Klassen --------------------------------------------
    classes = Counter()
    for el in soup.find_all(class_=True):
        for c in el.get("class", []):
            classes[c] += 1
    print("[debug] Top 25 CSS-Klassen (Hinweis auf Container für Termine):")
    for cls, n in classes.most_common(25):
        print(f"          {n:4d}× .{cls}")

    # ---- Strukturelle Hinweise auf Termine ------------------------------
    # Wir suchen nach IDs/Klassen, die typische Wörter enthalten.
    KEYWORDS = ("termin", "appointment", "slot", "booking", "datum", "date",
                "kurs", "event", "verfueg", "available", "buchen", "kalender")
    print("[debug] Klassen/IDs mit termin-relevanten Schlüsselwörtern:")
    for el in soup.find_all(True):
        attrs = []
        for key in ("id", "class"):
            val = el.get(key)
            if not val:
                continue
            joined = " ".join(val) if isinstance(val, list) else val
            if any(k in joined.lower() for k in KEYWORDS):
                attrs.append(f"{key}={joined!r}")
        if attrs:
            print(f"          <{el.name} {' '.join(attrs)}>")

    # ---- Skript-/JSON-Daten im HTML --------------------------------------
    # Manche Shops betten den State als JSON ein.
    for tag in soup.find_all("script"):
        s = tag.string or ""
        if not s.strip():
            continue
        if any(k in s.lower() for k in ("termin", "available", "slot",
                                        "appointment", "booking")):
            preview = s.strip()[:200].replace("\n", " ")
            print(f"[debug] <script> mit Hinweis: {preview!r}")

    # ---- JSON-Endpoint-Kandidaten in JS ---------------------------------
    api_paths = set(re.findall(
        r'["\']((?:/[^"\'\s]*?(?:api|rest|json|graphql)[^"\'\s]*))["\']',
        html, flags=re.IGNORECASE))
    if api_paths:
        print("[debug] Mögliche API-Endpoints im HTML/JS:")
        for p in sorted(api_paths)[:20]:
            print(f"          {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
