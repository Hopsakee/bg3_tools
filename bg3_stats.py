#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["lz4", "zstandard"]
# ///
"""
bg3_stats.py -- leest de statdefinities van items uit de spelbestanden.

Een savegame bevat alleen de interne naam van een item, bijvoorbeeld
"WPN_Handaxe". De echte waarden (damage, armour class, gewicht, rarity) staan
in de spelgegevens, niet in de save. Die staan in tekstbestanden als
Weapon.txt, Armor.txt en Object.txt, binnen de .pak-bestanden van het spel:

    <Steam>/steamapps/common/Baldurs Gate 3/Data/Shared.pak
    <Steam>/steamapps/common/Baldurs Gate 3/Data/Gustav.pak

Bronnen die dit script accepteert:
  * een .pak-bestand
  * een map met .pak-bestanden (bijvoorbeeld de hele Data-map)
  * een map met al uitgepakte .txt-bestanden (bijvoorbeeld via LSLib)
  * een los .txt-bestand

Formaat van de statbestanden:

    new entry "WPN_Longsword"
    type "Weapon"
    using "_BaseWeapon"
    data "Damage" "1d8"
    data "Damage Type" "Slashing"

Met `using` erft een entry alle velden van zijn ouder; dit script lost die
keten op. Sleutels worden genormaliseerd, zodat "Damage Type" en "DamageType"
hetzelfde veld zijn.
"""

import os
import re
import zipfile

from bg3_lsv import read_package

# Bestanden die itemstats bevatten. Andere statbestanden (Character.txt,
# Spell*.txt, Status*.txt, Passive.txt) worden overgeslagen.
ITEM_STAT_FILES = ("Weapon.txt", "Armor.txt", "Object.txt")

_ENTRY = re.compile(r'^\s*new entry\s+"([^"]*)"')
_TYPE = re.compile(r'^\s*type\s+"([^"]*)"')
_USING = re.compile(r'^\s*using\s+"([^"]*)"')
_DATA = re.compile(r'^\s*data\s+"([^"]*)"\s+"(.*)"\s*$')


def normalise_key(key):
    """"Damage Type" en "DamageType" worden hetzelfde veld."""
    return key.replace(" ", "").replace("_", "").lower()


# Veldnamen zoals we ze willen tonen, gekoppeld aan hun genormaliseerde sleutel
FIELDS = {
    "damage": "Damage",
    "damagetype": "Damage type",
    "versatiledamage": "Versatile damage",
    "weaponproperties": "Properties",
    "weapongroup": "Weapon group",
    "proficiencygroup": "Proficiency",
    "armorclass": "Armour class",
    "armortype": "Armour type",
    "armorclassability": "AC ability",
    "abilitymodifiercap": "AC ability cap",
    "slot": "Slot",
    "weight": "Weight",
    "valuelevel": "Value level",
    "rarity": "Rarity",
    "unique": "Unique",
    "boosts": "Boosts",
    "defaultboosts": "Default boosts",
    "passivesonequip": "Passives on equip",
    "statusonequip": "Status on equip",
    "boostsonequipmainhand": "Boosts (main hand)",
    "itemgroup": "Item group",
    "roottemplate": "Root template",
}


def parse_stats_text(text):
    """Parseer één statbestand. Geeft {entrynaam: {'_type','_using', velden}}."""
    entries = {}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        m = _ENTRY.match(line)
        if m:
            current = {"_name": m.group(1), "_type": None, "_using": None,
                       "fields": {}}
            entries[m.group(1)] = current
            continue
        if current is None:
            continue
        m = _TYPE.match(line)
        if m:
            current["_type"] = m.group(1)
            continue
        m = _USING.match(line)
        if m:
            current["_using"] = m.group(1)
            continue
        m = _DATA.match(line)
        if m:
            key, value = normalise_key(m.group(1)), m.group(2)
            if value != "":
                current["fields"][key] = value
    return entries


def _decode(blob):
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return blob.decode(encoding)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", "replace")


def _wanted_stat_file(name):
    return os.path.basename(name) in ITEM_STAT_FILES


def _collect_sources(path, verbose=True):
    """Geeft een lijst (herkomst, tekst) terug voor alles onder dit pad."""
    out = []
    if os.path.isfile(path):
        if path.lower().endswith((".pak", ".lsv")):
            try:
                files = read_package(path, want=_wanted_stat_file)
            except Exception as exc:
                # Eén onleesbare of meerdelige package mag de rest niet ophouden
                if verbose:
                    print("  overgeslagen: %s (%s)"
                          % (os.path.basename(path), exc))
                return out
            for name, blob in files.items():
                out.append(("%s!%s" % (os.path.basename(path), name),
                            _decode(blob)))
        elif path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if os.path.basename(name) in ITEM_STAT_FILES:
                        out.append((name, _decode(zf.read(name))))
        elif path.lower().endswith(".txt"):
            with open(path, "rb") as fh:
                out.append((os.path.basename(path), _decode(fh.read())))
        return out

    if not os.path.isdir(path):
        raise SystemExit("Bron bestaat niet: %s" % path)

    paks, texts = [], []
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            if name.lower().endswith(".pak"):
                paks.append(full)
            elif name in ITEM_STAT_FILES:
                texts.append(full)

    # Patch-paks overschrijven de basis-paks, dus die moeten als laatste
    def pak_order(p):
        base = os.path.basename(p)
        return (1 if base.lower().startswith("patch") else 0, base.lower())

    for pak in sorted(paks, key=pak_order):
        out.extend(_collect_sources(pak, verbose))
    for txt in sorted(texts):
        out.extend(_collect_sources(txt, verbose))
    return out


def load_stats(sources, verbose=True):
    """Laad en combineer alle bronnen. Later gelezen entries overschrijven eerdere."""
    raw, origins = {}, {}
    for source in sources:
        for origin, text in _collect_sources(source, verbose):
            parsed = parse_stats_text(text)
            for name, entry in parsed.items():
                if name in raw:
                    # Latere definitie vult aan en overschrijft per veld
                    raw[name]["fields"].update(entry["fields"])
                    raw[name]["_type"] = entry["_type"] or raw[name]["_type"]
                    raw[name]["_using"] = entry["_using"] or raw[name]["_using"]
                else:
                    raw[name] = entry
                origins[name] = origin

    resolved = {}

    def resolve(name, seen=None):
        """Los de `using`-keten op: ouder eerst, kind overschrijft."""
        if name in resolved:
            return resolved[name]
        entry = raw.get(name)
        if entry is None:
            return {}
        seen = seen or set()
        if name in seen:            # bescherming tegen kringverwijzingen
            return dict(entry["fields"])
        seen.add(name)
        fields = {}
        if entry["_using"]:
            fields.update(resolve(entry["_using"], seen))
        fields.update(entry["fields"])
        resolved[name] = fields
        return fields

    out = {}
    for name, entry in raw.items():
        fields = dict(resolve(name))
        entry_type = entry["_type"]
        if entry_type is None and entry["_using"] in raw:
            entry_type = raw[entry["_using"]]["_type"]
        out[name] = {
            "type": entry_type,
            "inherits": entry["_using"],
            "source": origins.get(name),
            "fields": fields,
            "display": {FIELDS[k]: v for k, v in fields.items() if k in FIELDS},
        }
    return out


def damage_range(dice):
    """"1d8" of "2d6+1" -> (min, max, gemiddeld). None als het niet te lezen is."""
    if not dice:
        return None
    total_min = total_max = 0
    found = False
    for sign, count, size in re.findall(r"([+-]?)\s*(\d*)d(\d+)", dice):
        found = True
        n = int(count or 1)
        s = int(size)
        lo, hi = n, n * s
        if sign == "-":
            total_min -= hi
            total_max -= lo
        else:
            total_min += lo
            total_max += hi
    # losse bonussen, bijvoorbeeld de +1 in 2d6+1
    for sign, number in re.findall(r"([+-])\s*(\d+)(?!\s*d)", dice):
        found = True
        value = int(number) * (-1 if sign == "-" else 1)
        total_min += value
        total_max += value
    if not found:
        return None
    return (total_min, total_max, (total_min + total_max) / 2)


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Lees itemstats uit de spelbestanden van BG3.")
    ap.add_argument("sources", nargs="+",
                    help=".pak-bestand, Data-map, of map met uitgepakte .txt")
    ap.add_argument("-o", "--out", help="schrijf alles naar dit JSON-bestand")
    ap.add_argument("-q", "--query", nargs="*", default=[],
                    help="toon alleen deze entries, bijvoorbeeld WPN_Handaxe")
    args = ap.parse_args()

    stats = load_stats(args.sources)
    print("%d entries gelezen." % len(stats))

    for name in args.query:
        entry = stats.get(name)
        if entry is None:
            print("\n%s: niet gevonden" % name)
            continue
        print("\n%s (%s, uit %s)" % (name, entry["type"], entry["source"]))
        for label, value in sorted(entry["display"].items()):
            print("   %-20s %s" % (label, value))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(stats, fh, indent=1, ensure_ascii=False)
        print("\n-> %s" % args.out)
