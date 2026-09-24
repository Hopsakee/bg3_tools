# BG3 savegame uitlezen

Leest een Baldur's Gate 3 savegame (`.lsv`) buiten het spel en maakt er een
leesbaar partyoverzicht van.

## Twee manieren om dit te gebruiken

De losse scripts hieronder draaien op je eigen PC en maken HTML-bestanden.
Daarnaast staat er in [`webapp/`](webapp/README.md) een webversie van dezelfde
uitlezing, bedoeld voor `https://bg3.hopsakee.top`: daar upload je een `.lsv`
vanuit de browser, bewaart hij elke upload als momentopname, en kun je er je
eigen notities bij zetten — wie waar goed in is, welk voorwerp je bewaart voor
later. Die notities horen bij het personage of het voorwerp en niet bij een
save, dus ze blijven staan als je de volgende keer een nieuwere savegame
uploadt.

In [`rules-primer/`](rules-primer/README.md) staat los daarvan een statische
Engelstalige cursus over hoe BG3 werkt: de D&D-regels eronder, gevechten,
personages bouwen, uitrusting, verkennen en de systemen die alleen BG3 heeft.
Online staat hij in de
webapp onder `https://bg3.hopsakee.top/regels/`; lokaal kun je ook gewoon
`index.html` openen.

```bash
uv sync
SESSION_SECRET=$(openssl rand -hex 32) uv run python -m webapp.main
```

## Draaien

Geen installatie, geen virtualenv om te beheren en niets in je globale Python.
Elk script draagt zijn eigen afhankelijkheden bij zich in een PEP 723-blok
bovenaan, dus `uv` regelt de omgeving zelf:

```bash
uv run bg3_sheet.py "A Nautiloid in Hell - 1h 34m.lsv" -o uitvoer/
```

De eerste keer haalt `uv` `lz4` en `zstandard` op en zet ze in een eigen
omgeving onder `~/.cache/uv`; daarna start het vrijwel meteen. Je globale
site-packages wordt niet aangeraakt.

De scripts hebben ook een `uv`-shebang, dus na één keer

```bash
chmod +x *.py
```

kun je ze direct aanroepen: `./bg3_sheet.py save.lsv -o uitvoer/`.

Wil je dit in een groter project opnemen, dan werkt de gewone route ook:
`uv init`, `uv add lz4 zstandard`, en dan `uv run`. De inline blokken mag je
dan laten staan — `uv run` gebruikt bij een script met eigen metadata dat blok
en negeert de projectomgeving.

## Wat het oplevert

| Bestand | Inhoud |
| --- | --- |
| `character_sheets.html` | zelfstandige pagina, offline te openen en te printen |
| `compare.html` | interactief je eigen spullen filteren, sorteren en vergelijken |
| `fillable_sheets.html` | invulbaar 5e-sheet per party-lid, voorgevuld uit de save |
| `party.json` | alle uitgelezen gegevens, ruw en compleet |
| `screenshot.webp` | de screenshot die BG3 zelf in de save opslaat |

## Spullen vergelijken

`compare.html` is de vergelijker: zoeken op naam of interne id, filteren op
eigenaar en categorie, sorteren op elke kolom, en items aanvinken om ze naast
elkaar te zetten. In dat paneel krijgt de beste waarde per rij een sterretje —
hoog is beter bij schade en AC, laag bij gewicht en prijs. Items zonder waarde
zakken altijd naar de onderkant, in beide sorteerrichtingen.

Hoe rijker de statbron, hoe nuttiger de pagina. Twee bronnen, los of samen:

```bash
# 1. uit de spelbestanden: gezaghebbend, gekoppeld op interne naam
uv run bg3_sheet.py save.lsv -o uitvoer/ --stats ".../Baldurs Gate 3/Data"

# 2. van bg3.wiki: leesbare namen, rarity, prijzen, vindplaatsen
#    WERKT NIET MEER ZONDER TOESTEMMING -- zie de waarschuwing hieronder
uv run bg3_wiki.py -c bg3wiki_cache.json
uv run bg3_sheet.py save.lsv -o uitvoer/ --wiki-cache bg3wiki_cache.json
```

> **bg3.wiki is dicht voor geautomatiseerde bevraging.** Sinds september 2026
> antwoordt de Cargo-API met `permissiondenied`: "You don't have permission to
> run arbitrary Cargo queries." Er is een tweede ingang die dezelfde gegevens
> zonder account teruggeeft, maar robots.txt sluit zowel `/w/api.php` als de
> `Special:`-pagina's uit, dus die gebruiken we niet. Wil je deze gegevens
> toch, vraag de beheerders om een account met dat recht of om een datadump.
>
> Bron 1 hierboven heeft dit niet nodig en is voor schade, AC en gewicht
> sowieso gezaghebbender: dat is wat het spel zelf gebruikt.

Los te gebruiken op een bestaande `party.json`:

```bash
uv run bg3_compare.py uitvoer/party.json -o compare.html \
  --wiki-cache bg3wiki_cache.json
```

Met `--slim` is de statsexport klein genoeg om naar de webapp te uploaden; daar
staat het spel immers niet:

```bash
uv run bg3_stats.py "<pad>/Data" -o stats.json --slim
```

### Over de wiki-koppeling

bg3.wiki draait op MediaWiki met de Cargo-extensie, en die heeft een
query-endpoint (`action=cargoquery`). `bg3_wiki.py` haalt de tabellen
`weapons` en `equipment` op, in pagina's van 500, en zet ze in een lokale
cache zodat je daarna offline werkt.

De veldnamen komen uit de broncode van de wiki zelf
(`Module:Item table/weapon columns`), maar een schema kan veranderen. Daarom:

```bash
uv run bg3_wiki.py --probe    # laat zien welke velden echt terugkomen
```

Lukt de breedste veldenset niet, dan valt de client automatisch terug op een
smallere in plaats van te crashen.

Het koppelen is het lastige deel: je save kent `ARM_ChainShirt_Body_Shar`, de
wiki kent "Chain Shirt". De koppeling probeert eerst het `uid`-veld (exact),
dan de volledige genormaliseerde naam, en dan steeds kortere deelnamen. Die
laatste categorie is een gok en wordt in `compare.html` gemarkeerd met
`wiki ≈`; controleer die voordat je erop vertrouwt. De verdeling over de drie
methodes staat boven de tabel.

Wiki-inhoud staat onder CC BY-NC-SA 4.0 of CC BY-SA 4.0 — prima voor eigen
gebruik, vermeld de bron als je het verspreidt.

## Invulbaar sheet

`fillable_sheets.html` is een gewone HTML-pagina die je lokaal opent. Wat uit de
save komt staat al ingevuld (koperkleurige rand). Zelf hoef je alleen de zes
ability scores over te typen uit het spel; modifiers, saving throws,
vaardigheden, initiative, passive perception, spell save DC, spell attack en
aanvalsbonussen rekenen zichzelf uit. Hit die, spellcasting ability en welke
saves proficient zijn worden voorgevuld volgens de standaard 5e-klassenregels
en zijn overschrijfbaar.

Opslaan gaat via **Bewaar als JSON** en **Laad JSON** — geen browseropslag, dus
je ingevulde sheets zijn gewone bestanden die je kunt versiebeheren. **Print of
naar PDF** geeft een schone afdruk, één personage per pagina.

De naam van je hoofdpersoon wordt automatisch uit de mapnaam van de save
gehaald (`<Personagenaam>-<id>__<Savenaam>`). Werkt dat niet, geef dan
`--name Didymus` mee.

Los te gebruiken op een eerder gemaakte `party.json`:

```bash
uv run bg3_fillable.py uitvoer/party.json -o sheets.html --name Didymus
```

Met `--dump` worden ook de losse bestanden uit de container weggeschreven naar
`uitvoer/raw/` (`Globals.lsf`, `StorySave.bin`, `meta.lsf`, level caches).

## Itemstats erbij

Een save bevat alleen de interne naam van een item (`WPN_Handaxe`). Damage,
armour class, gewicht en rarity staan in de spelbestanden. Wijs `--stats` naar
je BG3-installatie en die worden erbij gezocht:

```bash
uv run bg3_sheet.py save.lsv -o uitvoer/ \
  --stats "C:/Program Files (x86)/Steam/steamapps/common/Baldurs Gate 3/Data"
```

Dat levert per item een regel met schade of AC, plus twee vergelijkingstabellen
(wapens op gemiddelde schade, wapenrusting op AC). `--stats` accepteert een
`.pak`, een map met `.pak`-bestanden, of een map met al uitgepakte
`Weapon.txt` / `Armor.txt` / `Object.txt`. Meerdere paden mogen; latere
overschrijven eerdere, en `Patch*.pak` wordt automatisch als laatste gelezen.

### Waar staat de Data-map

De betrouwbaarste route, ongeacht besturingssysteem of schijf: in Steam
rechtsklikken op Baldur's Gate 3 → **Beheren** → **Lokale bestanden bekijken**,
en dan de map `Data` in. Bij GOG Galaxy: rechtsklikken → **Manage
installation** → **Show folder**.

Standaardlocaties:

| Systeem | Pad |
| --- | --- |
| Windows | `C:\Program Files (x86)\Steam\steamapps\common\Baldurs Gate 3\Data` |
| Windows, andere schijf | `D:\SteamLibrary\steamapps\common\Baldurs Gate 3\Data` |
| Linux | `~/.steam/steam/steamapps/common/Baldurs Gate 3/Data` |
| Linux, Flatpak-Steam | `~/.var/app/com.valvesoftware.Steam/data/Steam/steamapps/common/Baldurs Gate 3/Data` |
| GOG | `C:\GOG Galaxy\Games\Baldur's Gate 3\Data` |

Let op: de Steam-installatiemap heet `Baldurs Gate 3`, zonder apostrof.

Controleer het pad voordat je verder gaat:

```bash
uv run bg3_stats.py "<jouw pad>/Data" -q WPN_Handaxe
```

Klopt het, dan zie je een paar duizend entries en de gegevens van de handaxe.
De scan pakt alleen `Weapon.txt`, `Armor.txt` en `Object.txt` uit, dus de grote
packages zoals `Textures.pak` worden wel geopend maar niet uitgelezen. Een
onleesbare of meerdelige package wordt met een melding overgeslagen in plaats
van de hele scan af te breken.

Je kunt ook rechtstreeks naar de twee relevante packages wijzen, dat is het
snelst:

```bash
uv run bg3_sheet.py save.lsv -o uitvoer/ \
  --stats "<pad>/Data/Shared.pak" "<pad>/Data/Gustav.pak"
```


Saves staan op Windows in:

```
%LOCALAPPDATA%\Larian Studios\Baldur's Gate 3\PlayerProfiles\Public\Savegames\Story\
```

## Zelf verder graven

`bg3_lsv.py` is los te gebruiken:

```python
from bg3_lsv import read_package, LSF

files = read_package("save.lsv")
g = LSF(files["Globals.lsf"])

print(list(g.regions))                       # top-level regio's
for c in g.find("Character"):                # elke knoop met deze naam
    print(c.path(), c.attrs.get("Level"))
```

`Node` heeft `attrs`, `children`, `child(naam)`, `kids(naam)` en `path()`.
Als CLI drukt `uv run bg3_lsv.py save.lsv` de inhoud van de container af.

Voor los rondkijken in een REPL of notebook heb je een omgeving met de twee
afhankelijkheden nodig, zonder er iets te installeren:

```bash
uv run --with lz4 --with zstandard python
uv run --with lz4 --with zstandard --with ipython ipython
```

## Wat er wel en niet in een savegame staat

Wel: klasse, subklasse, race, level, XP, positie, meegedragen items, actieve
statussen, questvoortgang, moeilijkheid, mods, speltijd.

Niet leesbaar: ability scores, hitpoints, vaardigheidsbonussen, spells en
feats. Die zitten wél in de save, maar in een blob die nog niet ontcijferd is:
`Globals.lsf` heeft een regio `NewAge` met één `ScratchBuffer`-attribuut van
enkele megabytes, met eigen magic `LSMF`. Dat is de geserialiseerde ECS-state.
Het formaat is publiek nog niet opgelost (zie LSLib issue #127 en het project
`clemarescx/bg3d`, dat tot dezelfde conclusie komt). Dit script laat die blob
dus staan en verzint de waarden niet.

Uitlezen kan zo:

```python
blob = LSF(files["Globals.lsf"]).regions["NewAge"].attrs["NewAge"]
print(blob[:4])          # b'LSMF'
```

De naam van je hoofdpersoon staat ook niet als tekst in de save — alleen een
string-handle. Wel is die te achterhalen uit de mapnaam van de save zelf, die
BG3 opbouwt als `<Personagenaam>-<id>__<Savenaam>`.

## Formaten

* Container: LSPK v18 — bestandslijst als los LZ4-block, inhoud met zstd.
* Data: LSF v7 (`LSOF`) — aparte tabellen voor namen, knopen, attributen en
  waarden, elk apart gecomprimeerd (LZ4-frame voor de grote blokken).
* Structuren afgeleid van [LSLib](https://github.com/Norbyte/lslib)
  (`LSFReader.cs`, `LSFCommon.cs`).

Items worden aan personages gekoppeld via positie: inventarisitems delen de
coördinaten van hun eigenaar. Dat is een heuristiek, geen expliciete relatie in
het bestand — bij personages die exact op elkaar staan kan dat vermengen.
