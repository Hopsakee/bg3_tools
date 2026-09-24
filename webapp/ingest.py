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
from pathlib import Path

from .config import REPO_DIR
from . import db

# De parsers liggen in de repo-root, naast de map `webapp`.
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

import bg3_compare      # noqa: E402
import bg3_sheet        # noqa: E402
import bg3_stats        # noqa: E402

WIKI_KEY = "wiki"
STATS_KEY = "stats"

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class BadSave(Exception):
    """Het geuploade bestand is geen leesbare BG3-save."""



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

def store_wiki_cache(raw, filename):
    """
    Neem een wiki-cache aan in het formaat dat `bg3_wiki.py` schrijft.

    De server haalt zelf niets op bij bg3.wiki, en dat is een keuze, geen
    tekortkoming. De Cargo-API van die wiki geeft `permissiondenied` aan
    bezoekers zonder account, en robots.txt sluit zowel /w/api.php als de
    Special:-pagina's uit. Er is een tweede ingang die technisch nog werkt;
    daarlangs gaan zou om allebei die borden heen lopen.

    Wat er wél kan: heb jij toestemming, een account met dat recht, of een
    datadump, dan komt het bestand hierlangs binnen en gebruikt de
    spullenlijst het net als voorheen.
    """
    try:
        cache = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadSave("geen leesbare JSON: %s" % exc) from exc
    tables = cache.get("tables") if isinstance(cache, dict) else None
    if not isinstance(tables, dict) or not tables:
        raise BadSave(
            "verwacht een bestand met een 'tables'-sleutel, zoals bg3_wiki.py "
            "dat schrijft")
    if not all(isinstance(rows, list) for rows in tables.values()):
        raise BadSave("elke tabel moet een lijst met rijen zijn")

    total = sum(len(rows) for rows in tables.values())
    db.put_blob(WIKI_KEY, cache,
                note="%s: %d rijen (%s)" % (Path(filename).name, total,
                                            ", ".join(sorted(tables))))
    return total


def wiki_cache():
    return db.get_blob(WIKI_KEY)


# ------------------------------------------------------------- afgeleiden

def apply_stats(payload):
    """
    Leg de huidige itemstats over een momentopname heen.

    Bij het inlezen worden de stats meegebakken in de momentopname. Upload je
    de export pas daarna -- de normale volgorde, want je hebt hem meestal nog
    niet als je je eerste save inleest -- dan blijft alles wat er al in staat
    leeg. Dat was een voetangel waar je wel op móest stappen: uploaden leek te
    lukken, en er veranderde niets.

    Daarom worden ze hier, bij het tonen, opnieuw opgezocht. Een upload werkt
    zo met terugwerkende kracht voor elke momentopname, en een nieuwere export
    verbetert meteen ook de oude.

    De sleutelnaam verandert onderweg: de export noemt het `display`, en dat is
    wat `bg3_sheet.extract` als `fields` wegschrijft. Hier hetzelfde doen, want
    `bg3_compare` leest `fields`.
    """
    table = db.get_blob(STATS_KEY)
    if not table:
        return payload

    wanted = {name
              for char in payload.get("party", [])
              for names in (char.get("items_by_group") or {}).values()
              for name in names}
    found, missing = {}, []
    for name in sorted(wanted):
        entry = table.get(name)
        if not isinstance(entry, dict):
            missing.append(name)
            continue
        found[name] = {"type": entry.get("type"),
                       "source": entry.get("source"),
                       "fields": entry.get("display") or {}}

    merged = dict(payload)
    merged["item_stats"] = found
    merged["item_stats_missing"] = missing
    return merged


def item_rows(payload):
    """
    Alle spullen van de party als vergelijkbare rijen, verrijkt met wat er is.

    `bg3_compare.build_items` doet het koppelen; wij leggen de actuele
    itemstats eroverheen en plakken er jouw eigen notities en plannen aan vast.
    """
    items, meta = bg3_compare.build_items(apply_stats(payload), wiki_cache())
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
