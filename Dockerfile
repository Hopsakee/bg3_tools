# De webapp. De losse CLI-scripts hebben deze image niet nodig -- die draaien
# op je eigen machine via hun PEP 723-blok.
#
# Vorm gelijk aan de andere Python-apps op hopsakee.top: uv-image, installeren
# als root, draaien als een gewone gebruiker. Zie hopsakee-server/DEPLOYING.md.
FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

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

ENV APP_PORT=8080 \
    BG3_DB_PATH=/data/bg3.db
EXPOSE 8080

# Bewijst dat het proces echt antwoordt, niet alleen dat de container leeft.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; \
urllib.request.urlopen('http://127.0.0.1:%s/gezond' % os.environ['APP_PORT']).read()"

# Rechtstreeks de python uit de venv, niet `uv run`: uv wil bij het starten
# de omgeving kunnen bijwerken, en /app is root-eigendom terwijl dit proces dat
# niet is. Dat zou dezelfde klasse fout geven als de .sesskey-crash in
# DEPLOYING.md -- falen tijdens het starten, eindeloos herstarten, 502.
CMD ["/app/.venv/bin/python", "-m", "webapp.main"]
