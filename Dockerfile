# De webapp. De losse CLI-scripts hebben deze image niet nodig -- die draaien
# op je eigen machine via hun PEP 723-blok.
#
# Vorm gelijk aan de andere Python-apps op hopsakee.top: uv-image, installeren
# als root, draaien als een gewone gebruiker. Zie hopsakee-server/DEPLOYING.md.
#
# De pythonversie in deze tag MOET gelijk zijn aan .python-version in deze repo.
# Doe je dat niet, dan haalt `uv sync` alsnog de gevraagde versie op, zet hem in
# /root/.local/share/uv/python en laat de venv daarheen wijzen. Als root werkt
# dat; als de uid hieronder niet. /root is 0700, de standalone interpreter kan
# zijn eigen installatiemap dan niet uitlezen, valt terug op het pad waarmee hij
# ooit gebouwd is (/install), vindt daar geen stdlib en sterft op
# "ModuleNotFoundError: No module named 'encodings'". Dat ziet er niet uit als
# een versieprobleem, maar dat is het wel. Gebeurd op 2026-09-20.
FROM ghcr.io/astral-sh/uv:python3.11-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Geen interpreter ophalen: gebruik wat er in de image zit. Komt
    # .python-version ooit niet meer overeen met de tag hierboven, dan faalt
    # de BUILD met een leesbare melding -- in plaats van een image te maken die
    # alleen als root werkt.
    UV_PYTHON_DOWNLOADS=never \
    # En mocht dat ooit toch weer aangezet worden: niet in /root.
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Eerst alleen de afhankelijkheden, zodat een codewijziging deze laag niet
# ongeldig maakt.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# Niet als root draaien. /app blijft eigendom van root en dus onschrijfbaar
# voor het proces -- dat is de bedoeling. De app schrijft alleen in /data, en
# die map is een volume dat buiten de image op uid 10001 staat.
RUN adduser --disabled-password --gecos "" --uid 10001 appuser
USER appuser

# Deze regel is het vangnet, en hij staat hier met opzet NA `USER appuser`:
# alles hierboven werkt ook prima als root, en precies daarom is de kapotte
# image van 2026-09-20 door de bouw en de deploy heen gekomen en pas in een
# herstartlus zichtbaar geworden. Draait de app niet als de gebruiker die hem
# straks draait, dan faalt nu de build.
RUN SESSION_SECRET=build-check BG3_DB_PATH=/tmp/build-check.db \
    /app/.venv/bin/python -c "import sys, webapp.main; \
print('startcontrole ok:', sys.version.split()[0], 'als uid', __import__('os').getuid())"

ENV APP_PORT=8080 \
    BG3_DB_PATH=/data/bg3.db
EXPOSE 8080

# Bewijst dat het proces echt antwoordt, niet alleen dat de container leeft.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request,os; \
urllib.request.urlopen('http://127.0.0.1:%s/gezond' % os.environ['APP_PORT']).read()"

# Rechtstreeks de python uit de venv, niet `uv run`: uv wil bij het starten
# de omgeving kunnen bijwerken, en /app is root-eigendom terwijl dit proces dat
# niet is.
CMD ["/app/.venv/bin/python", "-m", "webapp.main"]
