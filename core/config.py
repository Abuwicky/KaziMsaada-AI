"""Shared configuration for the KaziMsaada AI CLI and web application.

Paths are resolved from the project root so the CLI and Streamlit always use
the same SQLite database, regardless of the process working directory.
"""

from pathlib import Path

APP_NAME = "KAZIMSAADA AI"
APP_DISPLAY_NAME = "KaziMsaada AI"
APP_TAGLINE = "Career readiness, made practical."
APP_VERSION = "0.5.0"
BUILD_STAMP = "2026-11-24 privacy-and-cv"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Existing JSON backup retained as the migration source. Never overwritten.
PROFILE_FILE = DATA_DIR / "profiles.json"

# Single primary database shared by the CLI and the web application.
DATABASE_FILE = DATA_DIR / "kazimsaada.db"

# Generated CV files (text + PDF).
CV_DIR = DATA_DIR / "cvs"

ASSETS_DIR = BASE_DIR / "assets"
