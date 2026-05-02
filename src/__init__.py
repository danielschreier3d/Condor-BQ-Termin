"""Termin-Monitor – modulare Python-Anwendung zur Überwachung
neuer Termin-Slots auf einer Website mit E-Mail-Benachrichtigung.

Module:
    config    – zentrale Konfiguration aus Umgebungsvariablen
    storage   – SQLite-Persistenz der bekannten Termine
    scraper   – HTTP-Abruf und HTML-Parsing
    notifier  – Versand der E-Mail-Benachrichtigungen via SMTP
    main      – Einstiegspunkt / Orchestrierung
"""
