"""
Controles op de Dockerfile zelf.

Allemaal geschreven naar aanleiding van één storing (2026-09-20): de image
gebruikte python3.12 terwijl `.python-version` 3.11 zegt. `uv sync` haalde
daarop een eigen 3.11 op, zette die in /root/.local/share/uv/python en liet de
venv daarheen wijzen. Als root werkte dat, dus de build slaagde, de deploy
meldde groen, en pas de container in een herstartlus liet zien wat er mis was:
/root is 0700, de opgehaalde interpreter kon zijn eigen installatiemap niet
lezen, viel terug op zijn buildpad en vond geen stdlib.

Dit zijn tekstcontroles, geen echte build -- maar precies de dingen die je
stilletjes verkeerd zet.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_image_gebruikt_dezelfde_python_als_de_repo():
    wanted = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    match = re.search(r"^FROM\s+\S+:python(\d+\.\d+)-", DOCKERFILE, re.M)
    assert match, "geen FROM-regel met een pythonversie gevonden"
    assert match.group(1) == wanted, (
        "Dockerfile draait op python%s maar .python-version zegt %s. Bij een "
        "verschil haalt uv de gevraagde versie op naar /root en wijst de venv "
        "daarheen -- onleesbaar voor de niet-root gebruiker die de app draait."
        % (match.group(1), wanted)
    )


def test_uv_mag_geen_interpreter_ophalen():
    """Zodat een toekomstig verschil de build breekt in plaats van de app."""
    assert "UV_PYTHON_DOWNLOADS=never" in DOCKERFILE


def test_startcontrole_draait_als_de_gebruiker_die_de_app_draait():
    """
    De hele storing kwam erdoor omdat elke buildstap als root liep. Een
    controle die óók als root draait had niets gevangen.
    """
    body = DOCKERFILE.replace("\\\n", " ")
    lines = [l.strip() for l in body.splitlines()]
    user_at = next((i for i, l in enumerate(lines)
                    if l.startswith("USER ") and "root" not in l), None)
    check_at = next((i for i, l in enumerate(lines)
                     if l.startswith("RUN ") and "webapp.main" in l), None)
    assert user_at is not None, "de image dropt geen privileges"
    assert check_at is not None, "er is geen startcontrole in de build"
    assert check_at > user_at, "de startcontrole staat vóór USER en draait dus als root"


def test_app_draait_niet_als_root():
    assert re.search(r"^USER\s+appuser\s*$", DOCKERFILE, re.M)
    assert "--uid 10001" in DOCKERFILE, "uid moet vastliggen; het volume is ervan"


@pytest.mark.parametrize("pattern", [".venv/", ".git/", "*.lsv", ".env"])
def test_dockerignore_houdt_de_rommel_buiten(pattern):
    """Een meegekopieerde host-venv landt precies waar de image de zijne bouwt."""
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert pattern in text


def test_entrypoint_gebruikt_de_venv_python_niet_uv_run():
    """`uv run` wil de omgeving bijwerken; /app is root-eigendom."""
    cmd = re.search(r"^CMD\s+(\[.*\])", DOCKERFILE, re.M)
    assert cmd, "geen CMD gevonden"
    assert "/app/.venv/bin/python" in cmd.group(1)
    assert "uv" not in cmd.group(1).replace("/app/.venv", "")
