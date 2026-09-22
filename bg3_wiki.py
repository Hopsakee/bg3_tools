#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
bg3_wiki.py -- haalt itemgegevens van bg3.wiki via de Cargo-API.

bg3.wiki draait op MediaWiki met de Cargo-extensie. Die heeft een
query-endpoint:

    https://bg3.wiki/w/api.php?action=cargoquery&tables=weapons
        &fields=name,damage,damage_type&limit=500&format=json

De veldnamen hieronder komen uit de wiki-broncode zelf
(Module:Item table/weapon columns), niet uit aannames. Toch kan het schema
veranderen, daarom:

  * `probe()` vraagt eerst een enkele rij op en meldt welke velden er
    werkelijk terugkomen;
  * mislukt een query op een onbekend veld, dan valt de client terug op een
    kleinere veldenset in plaats van te crashen;
  * alles wordt gecachet in een JSON-bestand, zodat je daarna offline werkt en
    de wiki niet onnodig belast.

Let op: de inhoud van bg3.wiki staat onder CC BY-NC-SA 4.0 of CC BY-SA 4.0.
Prima voor eigen gebruik; ga je het verspreiden, vermeld dan de bron.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://bg3.wiki/w/api.php"
USER_AGENT = "bg3-sheet/1.0 (persoonlijk hulpmiddel; leest eigen savegame)"

# Velden die in de wiki-broncode voorkomen. Per tabel van breed naar smal:
# lukt de eerste set niet, dan wordt de volgende geprobeerd.
FIELD_SETS = {
    "weapons": [
        ["uid", "name", "rarity", "weight", "price", "damage", "damage_type",
         "extra_damage", "extra_damage_type", "category", "handedness",
         "finesse", "light", "reach", "thrown", "enchantment",
         "weapon_passives", "special", "where_to_find"],
        ["name", "rarity", "weight", "price", "damage", "damage_type",
         "category", "handedness", "finesse", "light", "reach", "thrown",
         "special"],
        ["name", "rarity", "weight", "price", "damage", "damage_type"],
        ["name", "rarity"],
    ],
    "equipment": [
        ["uid", "name", "rarity", "weight", "price", "type", "armour_class",
         "armour_type", "enchantment", "special", "where_to_find"],
        ["name", "rarity", "weight", "price", "type", "armour_class",
         "armour_type", "special"],
        ["name", "rarity", "weight", "price", "type"],
        ["name", "rarity"],
    ],
}


def _request(params, timeout=30):
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def probe(table, verbose=True):
    """Vraag één rij op en geef terug welke velden de wiki teruggeeft."""
    rejected = []
    for fields in FIELD_SETS.get(table, []):
        params = {"action": "cargoquery", "tables": table,
                  "fields": ",".join(fields), "limit": 1, "format": "json"}
        try:
            payload = _request(params)
        except urllib.error.URLError as exc:
            raise SystemExit("Kan bg3.wiki niet bereiken: %s" % exc)
        if "error" in payload:
            info = (payload["error"].get("info") or "").strip()
            rejected.append("%d velden -> %s" % (len(fields), info[:200]))
            if verbose:
                print("  veldenset van %d afgewezen: %s"
                      % (len(fields), info[:120]))
            continue
        rows = payload.get("cargoquery", [])
        got = sorted(rows[0]["title"].keys()) if rows else []
        if verbose:
            print("  tabel %-10s werkt met %d velden; teruggekregen: %s"
                  % (table, len(fields), ", ".join(got) or "(geen rijen)"))
        return fields, got
    # De melding van de wiki zelf is het enige wat hier verder helpt: hij zegt
    # of de tabel niet bestaat of welk veld onbekend is. Die stond alleen in de
    # verbose-uitvoer en ging dus verloren zodra dit vanuit iets anders dan de
    # opdrachtregel draaide -- precies het geval waarin je hem nodig hebt.
    raise SystemExit(
        "Geen enkele veldenset werkt voor tabel %r. Het schema is "
        "vermoedelijk gewijzigd. De wiki antwoordde: %s"
        % (table, " | ".join(rejected) or "(geen foutmelding meegegeven)"))


def fetch_table(table, fields=None, page_size=500, pause=0.4, verbose=True):
    """Haal een hele Cargo-tabel op, in pagina's."""
    if fields is None:
        fields, _ = probe(table, verbose=verbose)
    rows, offset = [], 0
    while True:
        params = {"action": "cargoquery", "tables": table,
                  "fields": ",".join(fields), "limit": page_size,
                  "offset": offset, "format": "json"}
        payload = _request(params)
        if "error" in payload:
            raise SystemExit("Cargo-fout: %s" % payload["error"].get("info"))
        batch = [entry["title"] for entry in payload.get("cargoquery", [])]
        rows.extend(batch)
        if verbose:
            print("  %s: %d rijen" % (table, len(rows)), end="\r", flush=True)
        if len(batch) < page_size:
            break
        offset += page_size
        time.sleep(pause)          # wees aardig voor een fan-wiki
    if verbose:
        print("  %s: %d rijen" % (table, len(rows)))
    return rows


def build_cache(path, tables=("weapons", "equipment"), verbose=True):
    """Haal de tabellen op en schrijf ze naar een cachebestand."""
    cache = {"fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "source": API, "licence": "CC BY-NC-SA 4.0 of CC BY-SA 4.0",
             "tables": {}}
    for table in tables:
        if verbose:
            print("Tabel %s:" % table)
        cache["tables"][table] = fetch_table(table, verbose=verbose)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=1, ensure_ascii=False)
    return cache


def load_cache(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------- koppelen aan de save

PREFIXES = ("WPN_", "ARM_", "OBJ_", "UNI_", "MAG_", "CONS_", "LOOT_",
            "BOOK_", "TOOL_")


def normalise(text):
    """"WPN_Handaxe" en "Handaxe" moeten dezelfde sleutel opleveren."""
    if not text:
        return ""
    body = text
    for prefix in PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    return "".join(ch for ch in body.lower() if ch.isalnum())


def candidates(stats_name):
    """
    Kandidaatsleutels voor één interne naam, van specifiek naar algemeen.

    "ARM_ChainShirt_Body_Shar" levert chainshirtbodyshar, chainshirtbody en
    chainshirt op, zodat slot- en variantachtervoegsels de koppeling niet
    kapotmaken. Wel eerst de langste proberen, anders koppelt een variant
    ten onrechte aan het basisitem.
    """
    body = stats_name
    for prefix in PREFIXES:
        if body.startswith(prefix):
            body = body[len(prefix):]
            break
    tokens = [t for t in body.split("_") if t]
    keys = []
    for count in range(len(tokens), 0, -1):
        key = normalise("".join(tokens[:count]))
        if key and key not in keys:
            keys.append(key)
    return keys


def index_cache(cache):
    """Bouw twee zoekindexen: op uid (exact) en op genormaliseerde naam."""
    by_uid, by_name = {}, {}
    for table, rows in cache.get("tables", {}).items():
        for row in rows:
            row = dict(row)
            row["_table"] = table
            uid = (row.get("uid") or "").strip()
            if uid:
                by_uid[uid] = row
            key = normalise(row.get("name"))
            if key and key not in by_name:
                by_name[key] = row
    return by_uid, by_name


def match(stats_names, cache):
    """
    Koppel de interne namen uit de save aan wiki-rijen.

    Geeft (gevonden, niet_gevonden, hoe) terug. `hoe` telt per methode hoeveel
    er zo gevonden zijn, zodat je kunt zien of de uid-koppeling werkt of dat
    alles op naam moest.
    """
    by_uid, by_name = index_cache(cache)
    found, missing, how = {}, [], {"uid": 0, "naam": 0, "deelnaam": 0}
    for stats_name in stats_names:
        row = by_uid.get(stats_name)
        if row is not None:
            how["uid"] += 1
        else:
            keys = candidates(stats_name)
            row = None
            for index, key in enumerate(keys):
                row = by_name.get(key)
                if row is not None:
                    how["naam" if index == 0 else "deelnaam"] += 1
                    break
        if row is None:
            missing.append(stats_name)
        else:
            found[stats_name] = row
    return found, missing, how


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Haal itemdata van bg3.wiki.")
    ap.add_argument("-c", "--cache", default="bg3wiki_cache.json",
                    help="pad naar het cachebestand")
    ap.add_argument("--probe", action="store_true",
                    help="alleen kijken welke velden de wiki teruggeeft")
    ap.add_argument("--refresh", action="store_true",
                    help="cache opnieuw opbouwen, ook als hij al bestaat")
    args = ap.parse_args()

    if args.probe:
        for table in ("weapons", "equipment"):
            probe(table)
        raise SystemExit(0)

    if os.path.exists(args.cache) and not args.refresh:
        cache = load_cache(args.cache)
        total = sum(len(rows) for rows in cache["tables"].values())
        print("Cache bestaat al: %s (%d rijen, opgehaald %s). "
              "Gebruik --refresh om te vernieuwen."
              % (args.cache, total, cache.get("fetched")))
    else:
        cache = build_cache(args.cache)
        print("-> %s" % args.cache)
