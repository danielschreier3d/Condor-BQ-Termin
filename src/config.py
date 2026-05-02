"""Zentrale Konfiguration.

Liest alle benötigten Werte aus Umgebungsvariablen. Bei lokaler Ausführung
können die Variablen aus einer optionalen .env-Datei geladen werden
(über python-dotenv); auf GitHub Actions kommen sie aus den Repo-Secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# python-dotenv ist optional – nur für lokales Testen praktisch.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


# Wurzelverzeichnis des Projekts (eine Ebene über src/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "appointments.sqlite"


def _require(name: str) -> str:
    """Hole eine Pflicht-Umgebungsvariable oder wirf einen Fehler."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Pflicht-Umgebungsvariable {name!r} ist nicht gesetzt. "
            "Bitte als GitHub-Secret oder in der .env-Datei hinterlegen."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """Container für alle Laufzeit-Einstellungen."""

    # ---- Ziel-Website ----------------------------------------------------
    target_url: str
    user_agent: str
    request_timeout_s: int

    # ---- E-Mail (SMTP) ---------------------------------------------------
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_use_tls: bool
    notify_from: str
    notify_to: str

    # ---- Speicher --------------------------------------------------------
    db_path: Path

    # ---- Verhalten -------------------------------------------------------
    dry_run: bool  # True = keine Mails senden, nur loggen
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Baue Settings-Objekt aus Umgebungsvariablen."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        return cls(
            target_url=_require("TARGET_URL"),
            user_agent=os.environ.get(
                "USER_AGENT",
                "Mozilla/5.0 (compatible; CondorWatch/1.0; "
                "+https://github.com/danielschreier3d/Condor-BQ-Termin)",
            ),
            request_timeout_s=int(os.environ.get("REQUEST_TIMEOUT_S", "30")),
            smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=_require("SMTP_USER"),
            smtp_password=_require("SMTP_PASSWORD"),
            smtp_use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
            notify_from=os.environ.get("NOTIFY_FROM") or _require("SMTP_USER"),
            notify_to=_require("NOTIFY_TO"),
            db_path=Path(os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))),
            dry_run=os.environ.get("DRY_RUN", "false").lower() == "true",
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
