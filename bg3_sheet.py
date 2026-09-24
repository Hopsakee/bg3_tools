#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["lz4", "zstandard"]
# ///
"""
bg3_sheet.py -- maakt een leesbaar overzicht van je BG3-party uit een savegame.

Gebruik:
    python3 bg3_sheet.py "A Nautiloid in Hell - 1h 34m.lsv" -o uitvoer/

Met itemstats erbij (damage, armour class, gewicht) uit de spelbestanden:
    python3 bg3_sheet.py save.lsv -o uitvoer/ \
        --stats "C:/Program Files (x86)/Steam/steamapps/common/Baldurs Gate 3/Data"

Levert op:
    party.json            alle uitgelezen gegevens, ruw en compleet
    character_sheets.html zelfstandige pagina, offline te openen of te printen
    screenshot.webp       de screenshot die BG3 zelf in de save opslaat

Wat er WEL in een BG3-savegame staat: klasse, subklasse, race, level, XP,
positie, meegedragen items, actieve statussen, questvoortgang, moeilijkheid.
Wat er NIET in staat: ability scores, hitpoints, vaardigheidsbonussen,
spells, feats en de zelfgekozen naam van je hoofdpersoon. Die worden door de
engine tijdens het laden opnieuw opgebouwd uit de spelgegevens en staan niet
in het savebestand. Dit script verzint ze dus niet.
"""

import argparse
import base64
import html
import json
import os
import re
import sys

from bg3_lsv import LSF, read_package
from bg3_compare import build_items, render as render_compare
from bg3_fillable import render as render_fillable
from bg3_stats import damage_range, load_stats

# --------------------------------------------------------------- items

ITEM_GROUPS = [
    ("Wapens",              r"^WPN_"),
    ("Wapenrusting",        r"^ARM_"),
    ("Drankjes",            r"^(OBJ|CONS)_.*Potion"),
    ("Perkamentrollen",     r"^(OBJ|CONS)_.*Scroll"),
    ("Munten en edelstenen", r"^OBJ_(Gold|Silver|Copper|Malachite|Onyx|Pearl|Amber|Ruby|Sapphire|Diamond|Topaz|Amethyst)"),
    ("Unieke voorwerpen",   r"^(UNI|MAG)_"),
    ("Verbruik en gereedschap", r"^(CONS|OBJ)_"),
]

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def item_group(stats_name):
    for label, pattern in ITEM_GROUPS:
        if re.search(pattern, stats_name):
            return label
    return "Overig"


def prettify(stats_name):
    """WPN_LightCrossbow -> Light Crossbow. Alleen cosmetisch; ruwe id blijft bewaard."""
    body = re.sub(r"^(WPN|ARM|OBJ|CONS|UNI|MAG|LOOT|COL|PUZ|BOOK|TOOL)_", "", stats_name)
    body = body.replace("_", " ")
    return _CAMEL.sub(" ", body).strip()


def seconds_to_hm(seconds):
    seconds = int(seconds)
    return "%dh %02dm" % (seconds // 3600, (seconds % 3600) // 60)


def character_name_from_path(lsv_path):
    """BG3 noemt savemappen <Personagenaam>-<id>__<Savenaam>. Haal de naam eruit."""
    folder = os.path.basename(os.path.dirname(os.path.abspath(lsv_path)))
    m = re.match(r"^(.+?)-\d+__", folder)
    return m.group(1) if m else None


# --------------------------------------------------------------- extractie

def extract(lsv_path, stats_sources=None, stats_table=None):
    """
    Lees een savegame uit.

    `stats_sources` wijst naar de spelbestanden en wordt dan ter plekke
    ingelezen. `stats_table` is dezelfde tabel, maar al ingelezen -- dat is wat
    de webapp gebruikt, want op de server staat het spel niet geinstalleerd en
    komt die tabel uit een eerder geexporteerd JSON-bestand.
    """
    files = read_package(lsv_path)

    if "SaveInfo.json" not in files or "Globals.lsf" not in files:
        raise SystemExit("Dit lijkt geen BG3-savegame: SaveInfo.json of Globals.lsf mist.")

    save_info = json.loads(files["SaveInfo.json"])
    globals_lsf = LSF(files["Globals.lsf"])
    meta = LSF(files["meta.lsf"]).regions["MetaData"].child("MetaData") \
        if "meta.lsf" in files else None

    screenshot = next((blob for name, blob in files.items()
                       if name.lower().endswith((".webp", ".png"))), None)

    # -- spelbestand-brede gegevens
    game = {
        "save_name": save_info.get("Save Name"),
        "game_version": save_info.get("Game Version"),
        "platform": save_info.get("Platform"),
        "difficulty": save_info.get("Difficulty", []),
        "current_level": save_info.get("Current Level"),
        "source_file": os.path.basename(lsv_path),
        "character_name_from_folder": character_name_from_path(lsv_path),
    }
    if meta is not None:
        game["game_time_seconds"] = meta.attrs.get("TimeStamp")
        game["game_id"] = meta.attrs.get("GameID")
        game["modded"] = meta.attrs.get("Modded")
        game["has_unofficial_mods"] = meta.attrs.get("HasUnofficialMods")
        mods = meta.child("ModuleSettings")
        if mods is not None and mods.child("Mods") is not None:
            game["mods"] = [m.attrs.get("Name")
                            for m in mods.child("Mods").kids("ModuleShortDesc")]

    # -- alle personages uit Globals, geïndexeerd op positie
    characters = globals_lsf.find("Character")
    by_position = {}
    for c in characters:
        translate = c.attrs.get("Translate")
        if translate:
            by_position[tuple(round(x, 2) for x in translate)] = c

    # items horen bij de positie van hun eigenaar (inventaris erft de positie)
    items_by_position = {}
    for item in globals_lsf.find("Item"):
        translate = item.attrs.get("Translate")
        stats = item.attrs.get("Stats")
        if not translate or not stats:
            continue
        items_by_position.setdefault(
            tuple(round(x, 2) for x in translate), []
        ).append(stats)

    # -- actieve party uit SaveInfo, verrijkt met Globals
    party = []
    for entry in save_info.get("Active Party", {}).get("Characters", []):
        pos = tuple(round(x, 2) for x in entry.get("Position", []))
        node = by_position.get(pos)
        classes = entry.get("Classes", [{}])[0]

        statuses = []
        if node is not None:
            manager = node.child("StatusManager")
            if manager is not None:
                statuses = sorted({s.attrs.get("ID")
                                   for s in manager.kids("STATUS")
                                   if s.attrs.get("ID")})

        raw_items = sorted(items_by_position.get(pos, []))
        grouped = {}
        for stats in raw_items:
            grouped.setdefault(item_group(stats), []).append(stats)

        party.append({
            "origin": entry.get("Origin"),
            "race": entry.get("Race"),
            "class": classes.get("Main"),
            "subclass": classes.get("Sub") or None,
            # Alle klassen, niet alleen de eerste: bij multiclassen bepaalt de
            # eerste de bekwaamheden, en geven de latere er een deel bij.
            "classes": [{"class": c.get("Main"), "subclass": c.get("Sub") or None}
                        for c in entry.get("Classes", []) if c.get("Main")],
            "level": entry.get("Level"),
            "xp_total": entry.get("Experience Points (Total)"),
            "xp_this_level": entry.get("Experience Points (Current level)"),
            "position": list(pos),
            "level_name": node.attrs.get("Level") if node else None,
            "template_id": node.attrs.get("CurrentTemplate") if node else None,
            "statuses": statuses,
            "item_count": len(raw_items),
            "items_by_group": grouped,
            "matched_in_globals": node is not None,
        })

    # -- overige speelbare personages (nog niet in party, wel in de wereld)
    party_positions = {tuple(c["position"]) for c in party}
    recruitable = []
    for c in characters:
        if c.child("PlayerData") is None:
            continue
        translate = c.attrs.get("Translate")
        if not translate:
            continue
        pos = tuple(round(x, 2) for x in translate)
        if pos in party_positions:
            continue
        recruitable.append({
            "template_id": c.attrs.get("CurrentTemplate"),
            "level_name": c.attrs.get("Level"),
            "position": list(pos),
            "item_count": len(items_by_position.get(pos, [])),
        })
    recruitable.sort(key=lambda r: (r["level_name"] or "", r["template_id"] or ""))

    # -- quests
    journal = globals_lsf.regions.get("Journal")
    quests = {"completed": [], "in_progress": [], "game_time_seconds": None}
    if journal is not None:
        quests["game_time_seconds"] = journal.attrs.get("CurrentGameTime")
        categories = journal.child("QuestCategories")
        done = set()
        if categories is not None:
            for q in categories.kids("QuestCategory"):
                if q.attrs.get("CategoryID") == "CompletedQuests":
                    done.add(q.attrs.get("QuestID"))
        quests["completed"] = sorted(done)
        outer = journal.child("Quests")
        seen = set()
        if outer is not None:
            for inner in outer.children:
                for p in inner.kids("QuestsProgress"):
                    key = p.attrs.get("MapKey")
                    if key and key not in done:
                        seen.add(key)
        quests["in_progress"] = sorted(seen)

    # -- itemstats uit de spelbestanden, als die zijn meegegeven
    item_stats, comparison, missing = {}, {}, []
    if stats_sources or stats_table:
        all_stats = stats_table if stats_table else load_stats(stats_sources)
        wanted = {name for c in party for names in c["items_by_group"].values()
                  for name in names}
        for name in sorted(wanted):
            entry = all_stats.get(name)
            if entry is None:
                missing.append(name)
                continue
            item_stats[name] = {
                "type": entry["type"],
                "source": entry["source"],
                "fields": entry["display"],
            }

        # vergelijkingstabellen: wapens op gemiddelde schade, wapenrusting op AC
        owner_of = {}
        for c in party:
            label = c["origin"] if c["origin"] != "Generic" else "Hoofdpersoon"
            for names in c["items_by_group"].values():
                for name in names:
                    owner_of.setdefault(name, []).append(label)

        weapons, armour = [], []
        for name, entry in item_stats.items():
            fields = entry["fields"]
            owners = sorted(set(owner_of.get(name, [])))
            if entry["type"] == "Weapon":
                rng = damage_range(fields.get("Damage"))
                weapons.append({
                    "name": name,
                    "pretty": prettify(name),
                    "owners": owners,
                    "damage": fields.get("Damage"),
                    "damage_type": fields.get("Damage type"),
                    "versatile": fields.get("Versatile damage"),
                    "range": list(rng) if rng else None,
                    "properties": fields.get("Properties"),
                    "proficiency": fields.get("Proficiency"),
                    "weight": fields.get("Weight"),
                })
            elif entry["type"] == "Armor":
                armour.append({
                    "name": name,
                    "pretty": prettify(name),
                    "owners": owners,
                    "armour_class": fields.get("Armour class"),
                    "armour_type": fields.get("Armour type"),
                    "ac_ability": fields.get("AC ability"),
                    "ac_ability_cap": fields.get("AC ability cap"),
                    "slot": fields.get("Slot"),
                    "weight": fields.get("Weight"),
                })
        weapons.sort(key=lambda w: (-(w["range"][2] if w["range"] else -1),
                                    w["pretty"]))
        armour.sort(key=lambda a: (-float(a["armour_class"] or 0), a["pretty"]))
        comparison = {"weapons": weapons, "armour": armour}

    return {
        "game": game,
        "party": party,
        "item_stats": item_stats,
        "item_stats_missing": missing,
        "comparison": comparison,
        "other_playable_characters": recruitable,
        "quests": quests,
        "not_stored_in_save": [
            "Ability scores (Strength t/m Charisma)",
            "Hitpoints, armour class en snelheid",
            "Vaardigheids- en saving-throw-bonussen",
            "Bekende spells en spell slots",
            "Feats, passives en gekozen progressie-opties",
            "Aantallen per itemstapel, bijvoorbeeld hoeveel goud",
        ],
        "provenance": [
            ("Savenaam, versie, platform, moeilijkheid", "SaveInfo.json"),
            ("Klasse, subklasse, race, level, XP, positie", "SaveInfo.json > Active Party"),
            ("Speltijd, GameID, mods", "meta.lsf > MetaData"),
            ("Personages en hun runtime-toestand", "Globals.lsf > Characters"),
            ("Meegedragen items (gekoppeld op positie)", "Globals.lsf > Items"),
            ("Actieve statussen", "Globals.lsf > Characters > StatusManager"),
            ("Questvoortgang", "Globals.lsf > Journal"),
            ("Screenshot", "<savenaam>.WebP"),
            ("Damage, armour class, gewicht, rarity",
             "spelbestanden: Weapon.txt / Armor.txt / Object.txt in de .pak"),
        ],
        "_screenshot": screenshot,
    }


# --------------------------------------------------------------- html

CSS = """
:root{
  --ink:#14101a; --ink-2:#1d1725; --line:#332a40;
  --vellum:#efe7d8; --muted:#9a8fa8;
  --ember:#c2461f; --brass:#b08d3f;
  --display:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--vellum);
  font-family:var(--display);font-size:16px;line-height:1.55}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px 80px}
a{color:var(--brass)}

.hero{position:relative;margin-bottom:48px}
.hero img{width:100%;height:340px;object-fit:cover;display:block;
  filter:saturate(.85) contrast(1.05)}
.hero::after{content:"";position:absolute;inset:0;
  background:linear-gradient(to bottom,rgba(20,16,26,.15) 0%,rgba(20,16,26,.55) 45%,var(--ink) 100%)}
.hero-text{position:absolute;bottom:0;left:0;right:0;z-index:1;
  max-width:1000px;margin:0 auto;padding:0 24px 28px}
h1{font-size:clamp(30px,5vw,52px);line-height:1.05;margin:0 0 6px;
  font-weight:400;letter-spacing:-.01em}
.deck{color:var(--muted);font-family:var(--mono);font-size:12.5px;
  letter-spacing:.06em;text-transform:uppercase}

.tag{display:inline-block;font-family:var(--mono);font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--brass);
  border:1px solid var(--brass);border-radius:2px;padding:2px 7px;
  opacity:.85}
h2{font-size:13px;font-family:var(--mono);letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);font-weight:400;
  margin:56px 0 18px;padding-bottom:9px;border-bottom:1px solid var(--line)}

.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line)}
.fact{background:var(--ink-2);padding:13px 15px}
.fact dt{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);margin:0 0 4px}
.fact dd{margin:0;font-size:18px}

.sheet{border:1px solid var(--line);background:var(--ink-2);
  margin-bottom:28px;break-inside:avoid}
.sheet-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:14px;
  padding:20px 22px;border-bottom:1px solid var(--line);
  background:linear-gradient(90deg,rgba(194,70,31,.10),transparent 55%)}
.sheet-head .who{font-size:27px;line-height:1.1}
.sheet-head .lvl{font-family:var(--mono);font-size:12px;color:var(--brass);
  letter-spacing:.08em}
.sheet-body{display:grid;grid-template-columns:minmax(220px,1fr) 1.55fr}
@media(max-width:720px){.sheet-body{grid-template-columns:1fr}}
.col{padding:20px 22px}
.col+.col{border-left:1px solid var(--line)}
@media(max-width:720px){.col+.col{border-left:0;border-top:1px solid var(--line)}}

.rows{margin:0}
.rows div{display:flex;justify-content:space-between;gap:16px;
  padding:6px 0;border-bottom:1px dotted var(--line);font-size:14.5px}
.rows span:first-child{color:var(--muted);font-family:var(--mono);
  font-size:11px;letter-spacing:.06em;text-transform:uppercase;
  padding-top:3px}
.rows span:last-child{text-align:right}

.group{margin-bottom:16px}
.group h4{margin:0 0 5px;font-family:var(--mono);font-size:10.5px;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ember);
  font-weight:400}
.group ul{list-style:none;margin:0;padding:0;
  columns:2;column-gap:22px}
@media(max-width:560px){.group ul{columns:1}}
.group li{font-size:14px;padding:1px 0;break-inside:avoid}
.group li code{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  display:block;line-height:1.3}
.group li .stat{display:block;font-size:12px;color:var(--brass);line-height:1.35}
td.small{font-size:12px;color:var(--muted)}
code.dim{font-family:var(--mono);font-size:10.5px;color:var(--muted)}
p.small{font-family:var(--mono);font-size:11.5px;color:var(--muted);
  line-height:1.6;word-break:break-word;margin:0}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.chip{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;
  border:1px solid var(--line);background:#231b2d;color:var(--vellum);
  padding:3px 8px;border-radius:2px}

.gap{border:1px solid var(--ember);border-left-width:3px;
  background:rgba(194,70,31,.07);padding:20px 22px}
.gap ul{margin:10px 0 0;padding-left:20px}
.gap li{font-size:14.5px;padding:2px 0;color:var(--vellum)}
.gap p{margin:0;color:var(--muted);font-size:14.5px}

table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);
  vertical-align:top}
th{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);font-weight:400}
td.src{font-family:var(--mono);font-size:11.5px;color:var(--brass)}
details{border:1px solid var(--line);background:var(--ink-2);padding:14px 18px}
summary{cursor:pointer;font-family:var(--mono);font-size:11.5px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
details[open] summary{margin-bottom:14px}
footer{margin-top:56px;color:var(--muted);font-size:12.5px;
  font-family:var(--mono);line-height:1.7}

@media print{
  body{background:#fff;color:#191423}
  .hero{display:none}
  .sheet,.facts,.fact,details{background:#fff;border-color:#c9c1d2}
  .col+.col{border-color:#c9c1d2}
  h1{color:#191423}
  .gap{background:#fff}
}
"""


def esc(x):
    return html.escape(str(x if x is not None else "—"))


def item_summary(data, stats_name):
    """Korte regel achter een item: schade of AC, plus gewicht. Leeg zonder stats."""
    entry = data.get("item_stats", {}).get(stats_name)
    if not entry:
        return ""
    f = entry["fields"]
    bits = []
    if f.get("Damage"):
        damage = f["Damage"]
        if f.get("Versatile damage"):
            damage += " / %s tweehandig" % f["Versatile damage"]
        if f.get("Damage type"):
            damage += " %s" % f["Damage type"].lower()
        bits.append(damage)
    if f.get("Armour class"):
        ac = "AC %s" % f["Armour class"]
        if f.get("AC ability"):
            cap = f.get("AC ability cap")
            ac += " + %s%s" % (f["AC ability"][:3].lower(),
                               " (max %s)" % cap if cap else "")
        bits.append(ac)
    if f.get("Weight"):
        bits.append("%s kg" % f["Weight"])
    if f.get("Rarity") and f["Rarity"].lower() not in ("common", ""):
        bits.append(f["Rarity"].lower())
    return " · ".join(bits)


def render(data):
    game, party = data["game"], data["party"]
    out = []
    a = out.append

    a("<!doctype html><html lang='nl'><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>%s — partyoverzicht</title>" % esc(game["save_name"]))
    a("<style>%s</style></head><body>" % CSS)

    # hero
    a("<div class='hero'>")
    if data.get("_screenshot"):
        b64 = base64.b64encode(data["_screenshot"]).decode()
        a("<img src='data:image/webp;base64,%s' alt='Screenshot uit de savegame'>" % b64)
    a("<div class='hero-text'><h1>%s</h1>" % esc(game["save_name"]))
    a("<p class='deck'>%s &nbsp;·&nbsp; BG3 %s &nbsp;·&nbsp; %s</p></div></div>"
      % (esc(game["current_level"]), esc(game["game_version"]), esc(game["platform"])))

    a("<div class='wrap'>")

    # spelgegevens
    a("<h2>Savegame</h2><dl class='facts'>")
    facts = [
        ("Bestand", game["source_file"]),
        ("Moeilijkheid", " · ".join(game.get("difficulty") or []) or None),
        ("Speltijd (klok in het spel)",
         seconds_to_hm(game["game_time_seconds"]) if game.get("game_time_seconds") else None),
        ("Mods", ", ".join(game.get("mods") or []) or None),
        ("Party", "%d personages" % len(party)),
    ]
    for label, value in facts:
        a("<div class='fact'><dt>%s</dt><dd>%s</dd></div>" % (esc(label), esc(value)))
    a("</dl>")

    # personages
    a("<h2>Personages <span class='tag'>SaveInfo.json + Globals.lsf</span></h2>")
    for c in party:
        who = c["origin"] if c["origin"] and c["origin"] != "Generic" \
            else "Hoofdpersoon (eigen personage)"
        klass = c["class"] or "?"
        if c["subclass"]:
            klass += " — " + re.sub(r"(?<=[a-z])(?=[A-Z])", " ", c["subclass"])

        a("<article class='sheet'><div class='sheet-head'>")
        a("<div class='who'>%s</div>" % esc(who))
        a("<div class='lvl'>Level %s %s</div></div>" % (esc(c["level"]), esc(klass)))
        a("<div class='sheet-body'><div class='col'><div class='rows'>")
        rows = [
            ("Race", re.sub(r"_", " ", c["race"] or "")),
            ("Klasse", klass),
            ("Level", c["level"]),
            ("XP", c["xp_total"]),
            ("Gebied", c["level_name"]),
            ("Items bij zich", c["item_count"]),
        ]
        for label, value in rows:
            a("<div><span>%s</span><span>%s</span></div>" % (esc(label), esc(value)))
        a("</div>")
        if c["statuses"]:
            a("<h4 style='margin:18px 0 0;font-family:var(--mono);font-size:10.5px;"
              "letter-spacing:.1em;text-transform:uppercase;color:var(--ember);"
              "font-weight:400'>Actieve statussen</h4><div class='chips'>")
            for s in c["statuses"]:
                a("<span class='chip'>%s</span>" % esc(s))
            a("</div>")
        a("</div><div class='col'>")
        if c["items_by_group"]:
            for group in [g for g, _ in ITEM_GROUPS] + ["Overig"]:
                entries = c["items_by_group"].get(group)
                if not entries:
                    continue
                a("<div class='group'><h4>%s</h4><ul>" % esc(group))
                for stats in entries:
                    a("<li>%s" % esc(prettify(stats)))
                    summary = item_summary(data, stats)
                    if summary:
                        a("<span class='stat'>%s</span>" % esc(summary))
                    a("<code>%s</code></li>" % esc(stats))
                a("</ul></div>")
        else:
            a("<p class='deck'>Geen items gevonden op deze positie.</p>")
        a("</div></div></article>")

    # vergelijken
    comparison = data.get("comparison") or {}
    if comparison.get("weapons"):
        a("<h2>Wapens vergelijken <span class='tag'>Weapon.txt</span></h2>")
        a("<table><tr><th>Wapen</th><th>Schade</th><th>Bereik</th><th>Gem.</th>"
          "<th>Eigenschappen</th><th>Bij</th></tr>")
        for w in comparison["weapons"]:
            damage = w["damage"] or "—"
            if w["versatile"]:
                damage += " / %s" % w["versatile"]
            if w["damage_type"]:
                damage += " %s" % w["damage_type"].lower()
            rng = "%d–%d" % (w["range"][0], w["range"][1]) if w["range"] else "—"
            avg = ("%.1f" % w["range"][2]) if w["range"] else "—"
            props = (w["properties"] or "").replace(";", " · ")
            a("<tr><td>%s<br><code class='dim'>%s</code></td><td>%s</td>"
              "<td>%s</td><td>%s</td><td class='small'>%s</td>"
              "<td class='small'>%s</td></tr>"
              % (esc(w["pretty"]), esc(w["name"]), esc(damage), rng, avg,
                 esc(props), esc(", ".join(w["owners"]))))
        a("</table><p class='deck' style='margin-top:10px'>Gemiddelde is de "
          "basisschade van het wapen zelf, zonder ability-modifier of "
          "proficiency — die staan niet in de save.</p>")

    if comparison.get("armour"):
        a("<h2>Wapenrusting vergelijken <span class='tag'>Armor.txt</span></h2>")
        a("<table><tr><th>Stuk</th><th>AC</th><th>Type</th><th>Slot</th>"
          "<th>Gewicht</th><th>Bij</th></tr>")
        for s in comparison["armour"]:
            ac = s["armour_class"] or "—"
            if s["ac_ability"]:
                ac += " + %s" % s["ac_ability"][:3].lower()
                if s["ac_ability_cap"]:
                    ac += " (max %s)" % s["ac_ability_cap"]
            a("<tr><td>%s<br><code class='dim'>%s</code></td><td>%s</td>"
              "<td class='small'>%s</td><td class='small'>%s</td>"
              "<td class='small'>%s</td><td class='small'>%s</td></tr>"
              % (esc(s["pretty"]), esc(s["name"]), esc(ac), esc(s["armour_type"]),
                 esc(s["slot"]), esc(s["weight"]), esc(", ".join(s["owners"]))))
        a("</table>")

    if data.get("item_stats_missing"):
        a("<details style='margin-top:20px'><summary>%d items zonder statdefinitie"
          "</summary><p class='small'>%s</p><p class='deck' style='margin-top:10px'>"
          "Meestal wereldobjecten en questitems die niet in Weapon.txt, Armor.txt "
          "of Object.txt staan.</p></details>"
          % (len(data["item_stats_missing"]),
             esc(", ".join(data["item_stats_missing"]))))

    # wat er niet uit te lezen is
    a("<h2>Niet uit te lezen uit dit savebestand</h2><div class='gap'>")
    a("<p>Deze gegevens <em>zitten</em> wel in de save, maar in een stuk dat nog "
      "niet te ontcijferen is: <code>Globals.lsf</code> bevat een regio "
      "<code>NewAge</code> met één blob van enkele megabytes en eigen magic "
      "<code>LSMF</code> — de geserialiseerde ECS-state. Dat formaat is publiek "
      "niet opgelost, dus dit overzicht laat de waarden leeg in plaats van ze "
      "te verzinnen. Vul ze desgewenst zelf in via het invulbare sheet.</p><ul>")
    for line in data["not_stored_in_save"]:
        a("<li>%s</li>" % esc(line))
    a("</ul><p style='margin-top:14px'>De zelfgekozen naam van je hoofdpersoon "
      "staat er ook niet als tekst in, alleen als string-handle. Die is wél te "
      "achterhalen uit de mapnaam van de save, die BG3 opbouwt als "
      "<code>&lt;Personagenaam&gt;-&lt;id&gt;__&lt;Savenaam&gt;</code>.</p></div>")

    # quests
    q = data["quests"]
    if q["completed"] or q["in_progress"]:
        a("<h2>Questvoortgang <span class='tag'>Globals.lsf › Journal</span></h2>")
        a("<table><tr><th>Quest</th><th>Status</th></tr>")
        for name in q["in_progress"]:
            a("<tr><td>%s</td><td class='src'>bezig</td></tr>" % esc(name))
        for name in q["completed"]:
            a("<tr><td>%s</td><td class='src'>afgerond</td></tr>" % esc(name))
        a("</table>")

    # overige speelbare personages
    others = data["other_playable_characters"]
    if others:
        a("<h2>Overige speelbare personages in de wereld</h2>")
        a("<details><summary>%d personages met spelersgegevens, nog niet in de party"
          "</summary><table><tr><th>Template-id</th><th>Gebied</th>"
          "<th>Items</th></tr>" % len(others))
        for o in others:
            a("<tr><td class='src'>%s</td><td>%s</td><td>%s</td></tr>"
              % (esc(o["template_id"]), esc(o["level_name"]), esc(o["item_count"])))
        a("</table><p class='deck' style='margin-top:12px'>Namen staan hier niet bij: "
          "in het savebestand is alleen het template-id opgeslagen.</p></details>")

    # herkomst
    a("<h2>Waar komt elk gegeven vandaan</h2>")
    a("<table><tr><th>Gegeven</th><th>Bron in de savegame</th></tr>")
    for what, where in data["provenance"]:
        a("<tr><td>%s</td><td class='src'>%s</td></tr>" % (esc(what), esc(where)))
    a("</table>")

    a("<footer>Uitgelezen met bg3_sheet.py — het spel is hiervoor niet gestart.<br>"
      "Formaten: LSPK v18-container, LSF v7-knopen. De koppeling tussen items en "
      "personages loopt via positie: inventarisitems delen de coördinaten van hun "
      "eigenaar.</footer>")
    a("</div></body></html>")
    return "\n".join(out)


# --------------------------------------------------------------- cli

def main():
    ap = argparse.ArgumentParser(description="Maak een partyoverzicht uit een BG3-savegame.")
    ap.add_argument("lsv", help="pad naar het .lsv-savebestand")
    ap.add_argument("-o", "--out", default=".", help="uitvoermap (standaard: huidige map)")
    ap.add_argument("--dump", action="store_true",
                    help="pak ook alle losse bestanden uit de container uit")
    ap.add_argument("--name", help="naam van je hoofdpersoon, als die niet uit "
                                   "de mapnaam van de save te halen is")
    ap.add_argument("--wiki-cache", metavar="PAD",
                    help="cachebestand van bg3_wiki.py; voegt leesbare namen, "
                         "rarity, prijzen en vindplaatsen toe")
    ap.add_argument("--stats", nargs="+", metavar="PAD",
                    help="Data-map van BG3, losse .pak, of map met uitgepakte "
                         "Weapon.txt/Armor.txt/Object.txt; voegt damage, "
                         "armour class en gewicht toe")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    data = extract(args.lsv, stats_sources=args.stats)
    screenshot = data.pop("_screenshot", None)

    json_path = os.path.join(args.out, "party.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    data["_screenshot"] = screenshot
    html_path = os.path.join(args.out, "character_sheets.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render(data))

    fillable_path = os.path.join(args.out, "fillable_sheets.html")
    name_hint = args.name or data["game"].get("character_name_from_folder")
    with open(fillable_path, "w", encoding="utf-8") as fh:
        fh.write(render_fillable(data, name_hint))

    wiki_cache = None
    if args.wiki_cache:
        with open(args.wiki_cache, encoding="utf-8") as fh:
            wiki_cache = json.load(fh)
    items, item_meta = build_items(data, wiki_cache)
    compare_path = os.path.join(args.out, "compare.html")
    with open(compare_path, "w", encoding="utf-8") as fh:
        fh.write(render_compare(items, item_meta))

    written = [json_path, html_path, fillable_path, compare_path]
    if screenshot:
        shot_path = os.path.join(args.out, "screenshot.webp")
        with open(shot_path, "wb") as fh:
            fh.write(screenshot)
        written.append(shot_path)

    if args.dump:
        raw_dir = os.path.join(args.out, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        for name, blob in read_package(args.lsv).items():
            path = os.path.join(raw_dir, name.replace("/", "_"))
            with open(path, "wb") as fh:
                fh.write(blob)
            written.append(path)

    for path in written:
        print(path)
    print("\n%d personages in de party, %d items totaal."
          % (len(data["party"]), sum(c["item_count"] for c in data["party"])),
          file=sys.stderr)


if __name__ == "__main__":
    main()
