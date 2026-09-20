"""
Instellingen, allemaal uit de omgeving.

Twee dingen die op deze server al eens fout zijn gegaan en hier daarom
expliciet staan (zie hopsakee-server/DEPLOYING.md):

* `APP_PORT` is de conventie op de box, maar fasthtml leest alleen `PORT`, en
  alleen als het `port`-argument leeg is. Dus lezen we `APP_PORT` zelf en geven
  we het door. De default hier moet gelijk zijn aan wat de Caddyfile belt.
* `SESSION_SECRET` moet gezet zijn. Zonder secret schrijft fasthtml een
  `.sesskey` in de werkmap, en die is root-eigendom terwijl de container als
  een gewone gebruiker draait: PermissionError tijdens de import, crashloop,
  502 bij Caddy. Liever meteen falen met een leesbare regel.
"""

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parent
STATIC_DIR = APP_DIR / "static"

APP_PORT = int(os.getenv("APP_PORT", "8080"))
DB_PATH = Path(os.getenv("BG3_DB_PATH", REPO_DIR / "uitvoer" / "bg3web.db"))

# Uploads van savegames. Een .lsv is normaal 1-15 MB; 64 MB is ruim en
# voorkomt dat een verkeerd bestand het geheugen opeet.
MAX_SAVE_BYTES = int(os.getenv("BG3_MAX_SAVE_BYTES", str(64 * 1024 * 1024)))
# Een --slim itemstats-export van de hele spelinstallatie is een paar MB.
MAX_STATS_BYTES = int(os.getenv("BG3_MAX_STATS_BYTES", str(96 * 1024 * 1024)))

# Authelia zet deze header als de gebruiker binnen is. Puur om te laten zien
# wie je bent; de poort zelf zit in Caddy, niet hier.
USER_HEADER = "Remote-Name"


def session_secret():
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        path = os.getenv("SESSION_SECRET_FILE")
        if path and Path(path).is_file():
            secret = Path(path).read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET is niet gezet. Zonder sessiesleutel schrijft "
            "fasthtml een .sesskey in /app en crasht de container. Zet "
            "SESSION_SECRET (of SESSION_SECRET_FILE) in de omgeving."
        )
    return secret
