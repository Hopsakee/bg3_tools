# De webversie

Dezelfde uitlezing als de scripts hiernaast, maar dan op een adres dat je
onderweg kunt openen: `https://bg3.hopsakee.top`. Bedoeld voor de avond dat je
eindelijk weer speelt en niet eerst twintig minuten door menu's wilt om te
bedenken wie ook alweer wat kon.

## Wat het doet

* Een `.lsv` uploaden vanuit de browser. De server leest hem uit met
  `bg3_sheet.extract` en bewaart de **uitlezing**, niet het bestand.
* Elke upload is een momentopname. Ze komen naast elkaar te staan, met een
  XP-verloop, zodat je kunt zien hoe je party zich ontwikkelt.
* Party, spullen en quests doorbladeren, filteren en sorteren.
* **Je eigen notities** bij personages (sterk in / zwak in / rol), voorwerpen
  (wat wil je ermee: bewaren, verkopen, gebruiken) en quests. Die hangen aan
  het personage of voorwerp, niet aan een save, en blijven dus staan als je een
  nieuwe savegame uploadt. Dit is het deel dat geen enkele bestaande parser
  voor je doet.
* Te installeren op je beginscherm (PWA). Pagina's die je al bekeken hebt,
  blijven zonder verbinding leesbaar.

## De party naast elkaar

De pagina **Party** is het karakterscherm uit het spel, maar dan iedereen
tegelijk: kolommen zijn personages, rijen zijn vermogens, saving throws,
vaardigheden, wapenrusting, wapens en kenmerken. Een ster staat bij de beste
in die rij — zo zie je in één oogopslag wie de kluis moet openen en wie de
Persuasion-check moet doen.

Wat erin staat komt uit drie bronnen, en de pagina zegt welke:

| Bron | Wat |
| --- | --- |
| de save | ras, klasse, subklasse, level |
| de spelregels (`bg3_rules.py`) | bekwaamheden in wapens en wapenrusting, saving throws, hit die, spreukvermogen, kernkenmerken per level |
| jij | ability scores, vaardigheden, expertise, feats, en bekwaamheden uit feats of voorwerpen |

Het laatste rijtje moet je één keer overtypen uit het spel, per personage, op
diens eigen pagina. Daarna rekent alles zichzelf uit — modifiers, saves,
vaardigheidsbonussen, spell save DC, passieve waarneming, sterkste trek — en
het blijft staan als je een nieuwere save uploadt.

**Wie kan wat gebruiken.** Elk wapen en stuk wapenrusting in je stats-export
draagt het veld `Proficiency` van het spel zelf, bijvoorbeeld
`Longswords;MartialWeapons`. De regels gebruiken exact dezelfde namen. Op elke
voorwerppagina en als kolom in de spullenlijst staat daarom per party-lid of
hij het zonder nadelen kan gebruiken.

Hoe zeker de regels zijn: de klassetabellen zijn standaard 5e en die volgt BG3.
De indeling van wapens in simple en martial is nagelopen tegen alle 526 wapens
in een echte export. Rassen en subklassen zijn met redelijke zekerheid
overgenomen; wijkt iets af van wat je in het spel ziet, vink het dan aan bij
"Extra bekwaamheden" van dat personage.

## De regels

Onder `/regels/` (in het menu: *Regels*) serveert de app de statische
regelcursus uit [`rules-primer/`](../rules-primer/README.md): hoe BG3 werkt,
van ability scores tot Illithid-krachten. De app doet er verder niets mee; het
is een map met HTML, CSS en JS die toevallig op dezelfde oorsprong staat, en
dus achter dezelfde login en binnen de service worker.

## Wat het niet doet

Ability scores, hitpoints, vaardigheidsbonussen, spells en feats staan niet in
een savegame — zie de uitleg in de hoofd-`README.md`. Deze app verzint ze niet.
Wat je er zelf van weet, kun je per personage opschrijven; dat is precies
waarvoor het notitieveld er is.

Quests staan er als interne id in, niet met hun journaaltitel. De id wordt
leesbaar gemaakt (`HAV_Druids_RescueHalsin` → `HAV Druids Rescue Halsin`) en je
kunt er je eigen titel en aantekening bij zetten.

## Zelf draaien

```bash
uv sync
SESSION_SECRET=$(openssl rand -hex 32) uv run python -m webapp.main
# http://localhost:8080
```

| Variabele | Doet | Standaard |
| --- | --- | --- |
| `SESSION_SECRET` | sessiesleutel. **Verplicht** — zonder deze weigert de app te starten | — |
| `SESSION_SECRET_FILE` | pad naar een bestand met diezelfde sleutel | — |
| `APP_PORT` | poort | `8080` |
| `BG3_DB_PATH` | het SQLite-bestand | `uitvoer/bg3web.db` |
| `BG3_MAX_SAVE_BYTES` | bovengrens aan een upload | 64 MB |
| `BG3_MAX_STATS_BYTES` | bovengrens aan een itemstats-export | 96 MB |

Tests: `uv run pytest`.

## Itemstats en de wiki

Twee bronnen verrijken de spullenlijst, allebei optioneel, allebei in te
stellen onder **Instellingen**:

* **bg3.wiki** — de app haalt hier **niets** op, met opzet. De wiki heeft de
  Cargo-API gesloten voor bezoekers zonder account (`permissiondenied`), en
  robots.txt sluit zowel `/w/api.php` als de `Special:`-pagina's uit. Er is een
  tweede ingang die technisch nog werkt; daarlangs gaan zou om allebei die
  borden heen lopen.

  Heb je toestemming van de beheerders of een datadump, dan upload je die
  onder Instellingen en gebruikt de spullenlijst hem meteen: leesbare namen,
  zeldzaamheid, prijzen en vindplaatsen. Een koppeling die alleen op een deel
  van de naam lukte, wordt gemarkeerd met `wiki ≈`; die is een gok.
* **De spelbestanden** — daar staan damage, armour class en gewicht in, maar
  het spel staat niet op de server. Exporteer ze één keer op je PC en upload
  het bestand:

  ```bash
  uv run bg3_stats.py "<pad>/Data" -o stats.json --slim
  ```

  Vanaf dan gebruikt elke nieuwe upload die cijfers. Al ingelezen
  momentopnamen worden niet met terugwerkende kracht bijgewerkt — lees zo'n
  save opnieuw in als je de cijfers er ook bij wilt.

## Vorm

XKCD-stijl: handschrift, scheve kaders, zwart op wit. De scheve randen komen
uit één CSS-truc — `border-radius` met acht verschillende waarden, zodat elke
hoek een andere kant op trekt — en niet uit plaatjes, want die zouden op e-ink
alleen maar smurrie geven.

Het lettertype is [xkcd Script](https://github.com/ipython/xkcd-font) van
Randall Munroe, onder CC BY-NC 3.0: vrij voor persoonlijk, niet-commercieel
gebruik zoals dit, mits vermeld. Het staat in `static/` naast zijn licentie, en
wordt vanaf de eigen server geserveerd — de CSP laat `font-src 'self'` toe en
verder niets.

Wat daaronder hetzelfde bleef, en waarom: zwart op wit, geen animaties, geen
hover-afhankelijke informatie, en filteren en sorteren op de server. Het
primaire scherm is een Boox e-reader. Daar kost elke pixelverandering een
verversing, bestaat hover niet, en is lichtgrijs onbruikbaar. Handschrift leest
daar wel iets lastiger dan een schreefloze, dus de basisgrootte is opgeschroefd
en de lijnen zijn dikker dan je normaal zou nemen; op Boox-formaat en op een
telefoon nagekeken. Eén ding werkt met JavaScript — de service worker die het
offline lezen regelt — en elke pagina doet het ook zonder.

## Hoe het op de server komt

De compose, het Caddy-blok en het deployscript staan in de repo
`hopsakee-server`: `config/bg3/compose.yaml` en `server_setup/deploy-bg3.sh`.
De app zit achter de Authelia-inlog, net als infoflow en netflix.
