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

* **bg3.wiki** — de server haalt de tabellen zelf op en bewaart ze. Levert
  leesbare namen, zeldzaamheid, prijzen en vindplaatsen. Een koppeling die
  alleen op een deel van de naam lukte, wordt in de lijst gemarkeerd met
  `wiki ≈`; die is een gok.
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

Zwart op wit, harde randen, geen animaties, en filteren en sorteren gebeuren op
de server. Dat is geen soberheid om de soberheid: het primaire scherm is een
Boox e-reader. Daar kost elke pixelverandering een verversing, bestaat hover
niet, en is lichtgrijs onbruikbaar. Eén ding werkt met JavaScript — de service
worker die het offline lezen regelt — en elke pagina doet het ook zonder.

## Hoe het op de server komt

De compose, het Caddy-blok en het deployscript staan in de repo
`hopsakee-server`: `config/bg3/compose.yaml` en `server_setup/deploy-bg3.sh`.
De app zit achter de Authelia-inlog, net als infoflow en netflix.
