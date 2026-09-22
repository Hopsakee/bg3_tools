"""
Van geupload bestand naar iets wat je kunt lezen.

Het echte werk staat in de CLI-modules van deze repo (`bg3_sheet`, `bg3_stats`,
`bg3_compare`, `bg3_wiki`); deze module is de laag ertussen. Niets van de
parsers is hier gekopieerd -- als het lezen van saves beter wordt, wordt de
webapp vanzelf beter.
"""

import hashlib
import json
import re
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from .config import REPO_DIR
from . import db

# De parsers liggen in de repo-root, naast de map `webapp`.
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

import bg3_compare      # noqa: E402
import bg3_sheet        # noqa: E402
import bg3_stats        # noqa: E402
import bg3_wiki         # noqa: E402

WIKI_KEY = "wiki"
STATS_KEY = "stats"

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class BadSave(Exception):
    """Het geuploade bestand is geen leesbare BG3-save."""


class WikiFailed(Exception):
    """bg3.wiki gaf geen bruikbaar antwoord."""


# ----------------------------------------------------------- savegames

def parse_upload(raw, filename, hero_name=""):
    """
    Lees een geuploade `.lsv` en geef (samenvatting, payload, screenshot).

    De parser leest van een pad, dus het bestand gaat eerst naar een tijdelijk
    bestand. Dat wordt daarna weggegooid: de geparste inhoud slaan we op, het
    bestand zelf niet -- dat is megabytes aan binaire brij die we toch niet
    nog eens lezen.
    """
    digest = hashlib.sha256(raw).hexdigest()
    stats_table = db.get_blob(STATS_KEY)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (Path(filename).name or "save.lsv")
        path.write_bytes(raw)
        try:
            data = bg3_sheet.extract(str(path), stats_table=stats_table)
        except SystemExit as exc:               # de parser roept SystemExit aan
            raise BadSave(str(exc) or "onleesbaar bestand") from exc
        except Exception as exc:
            raise BadSave("%s: %s" % (type(exc).__name__, exc)) from exc

    screenshot = data.pop("_screenshot", None)
    game = data.get("game", {})
    party = data.get("party", [])
    quests = data.get("quests", {})

    # De parser leidt de naam van de hoofdpersoon af uit de mapnaam van de
    # save. Bij een upload is die map er niet, dus wat jij intikt wint.
    hero = (hero_name or "").strip() or game.get("character_name_from_folder") or ""
    game["hero_name"] = hero
    data["game"] = game

    summary = {
        "sha256": digest,
        "filename": Path(filename).name,
        "save_name": game.get("save_name"),
        "hero_name": hero,
        "game_version": game.get("game_version"),
        "difficulty": ", ".join(game.get("difficulty") or []) or None,
        "current_level": game.get("current_level"),
        "play_seconds": _int(game.get("game_time_seconds")),
        "game_id": game.get("game_id"),
        "party_size": len(party),
        "item_count": sum(c.get("item_count") or 0 for c in party),
        "xp_total": max([_int(c.get("xp_total")) or 0 for c in party] or [0]),
        "max_level": max([_int(c.get("level")) or 0 for c in party] or [0]),
        "quests_open": len(quests.get("in_progress") or []),
        "quests_done": len(quests.get("completed") or []),
    }
    return summary, data, screenshot


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# -------------------------------------------------------------- itemstats

def store_stats_export(raw, filename):
    """
    Neem een `bg3_stats.py -o stats.json` export aan.

    Het spel staat niet op de server, dus damage, AC en gewicht kunnen daar
    niet uit de `.pak`-bestanden komen. Dit is de enige route naar die
    gezaghebbende cijfers: één keer exporteren op de PC, één keer uploaden.

    Een volledige export bevat ook de ruwe velden en de `using`-keten; die
    gebruikt alleen de parser zelf. We slaan het uitgedunde formaat op, ook
    als er zonder `--slim` is geëxporteerd.
    """
    try:
        table = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadSave("geen leesbare JSON: %s" % exc) from exc
    if not isinstance(table, dict) or not table:
        raise BadSave("verwacht een JSON-object met interne itemnamen als sleutel")

    if not all(isinstance(entry, dict) and "display" in entry
               for entry in table.values()):
        raise BadSave(
            "dit ziet er niet uit als een itemstats-export. Maak hem met: "
            "uv run bg3_stats.py \"<pad>/Data\" -o stats.json --slim"
        )

    # Uitdunnen met de functie uit de exporteur zelf, zodat beide kanten het
    # over hetzelfde formaat hebben. Een al uitgedunde export overleeft dit
    # ongeschonden.
    slim = bg3_stats.slim(table)
    db.put_blob(STATS_KEY, slim, note="%s, %d entries" % (Path(filename).name,
                                                          len(slim)))
    return len(slim)


# ------------------------------------------------------------------ wiki

def _fetch_table(table):
    """
    Eén Cargo-tabel ophalen, met de uitgangen van een CLI vertaald naar een
    gewone fout.

    `bg3_wiki` is geschreven om vanaf de opdrachtregel te draaien en stopt bij
    een onbereikbare wiki of een gewijzigd schema met `SystemExit`. Dat erft
    van BaseException, niet van Exception, dus een `except Exception` eromheen
    vangt het NIET: de fout schiet dwars door de route heen en de knop lijkt
    stuk zonder dat er iets op het scherm komt. Precies dat gebeurde op
    2026-09-22. Hier wordt het een WikiFailed met de reden erin.
    """
    try:
        return bg3_wiki.fetch_table(table, verbose=False)
    except SystemExit as exc:
        raise WikiFailed(str(exc) or "onbekende fout") from exc
    except urllib.error.HTTPError as exc:
        raise WikiFailed("HTTP %s van bg3.wiki (%s)" % (exc.code, exc.reason)) from exc
    except urllib.error.URLError as exc:
        raise WikiFailed("bg3.wiki niet bereikbaar: %s" % exc.reason) from exc
    except Exception as exc:
        raise WikiFailed("%s: %s" % (type(exc).__name__, exc)) from exc


def refresh_wiki(tables=("weapons", "equipment")):
    """
    Haal de tabellen `weapons` en `equipment` van bg3.wiki en bewaar ze.

    Dit duurt tientallen seconden -- een paar duizend rijen in pagina's van
    500 -- en gebeurt daarom alleen als jij erom vraagt, nooit bij het starten.

    Per tabel, niet in één keer via `bg3_wiki.build_cache`: verandert het
    schema van één tabel, dan houd je de andere en zie je precies welke het
    niet deed. Geeft (aantal rijen, lijst mislukte tabellen) terug en gooit
    alleen als er niets binnenkwam.
    """
    fetched, failed = {}, []
    for table in tables:
        try:
            fetched[table] = _fetch_table(table)
        except WikiFailed as exc:
            failed.append("%s: %s" % (table, exc))

    if not fetched:
        raise WikiFailed("; ".join(failed) or "geen enkele tabel opgehaald")

    cache = {"fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "source": bg3_wiki.API,
             "licence": "CC BY-NC-SA 4.0 of CC BY-SA 4.0",
             "tables": fetched}
    total = sum(len(rows) for rows in fetched.values())
    note = "%d rijen (%s)" % (total, ", ".join(sorted(fetched)))
    if failed:
        note += " -- mislukt: " + "; ".join(failed)
    db.put_blob(WIKI_KEY, cache, note=note)
    return total, failed


def wiki_cache():
    return db.get_blob(WIKI_KEY)


# ------------------------------------------------------------- afgeleiden

def item_rows(payload):
    """
    Alle spullen van de party als vergelijkbare rijen, verrijkt met wat er is.

    `bg3_compare.build_items` doet het koppelen; wij plakken er alleen jouw
    eigen notities en plannen aan vast.
    """
    items, meta = bg3_compare.build_items(payload, wiki_cache())
    notes = db.notes_for("item")
    for item in items:
        note = notes.get(item["id"])
        item["tag"] = note["tag"] if note else ""
        item["note"] = note["body"] if note else ""
        item["label"] = note["label"] if note else ""
    return items, meta


def prettify(name):
    """`TUT_Tutorial_Chest` -> `Tutorial Chest`. Puur cosmetisch."""
    if not name:
        return ""
    body = re.sub(r"^(WPN|ARM|OBJ|CONS|UNI|MAG|LOOT|COL|PUZ|BOOK|TOOL)_", "",
                  str(name))
    return _CAMEL.sub(" ", body.replace("_", " ")).strip() or str(name)


def character_key(character):
    """
    Een sleutel die een notitie over dit personage overleeft bij een nieuwe
    save. `origin` is stabiel voor de companions; de zelfgemaakte hoofdpersoon
    heet altijd `Generic`, en daar is er maar één van in de party.
    """
    return character.get("origin") or "Onbekend"


def character_label(character, hero_name=""):
    origin = character.get("origin")
    if origin in (None, "", "Generic"):
        return hero_name or "Hoofdpersoon"
    return origin


def seconds_to_hm(seconds):
    if not seconds:
        return None
    seconds = int(seconds)
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)
