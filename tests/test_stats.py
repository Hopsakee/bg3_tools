"""
Itemstats uit de spelbestanden, en wanneer ze zichtbaar worden.

Aanleiding (2026-09-24): een export van 3139 entries werd netjes geüpload en
opgeslagen, en er veranderde niets op de spullenpagina. Reden: de stats werden
alleen meegebakken tijdens het inlezen van een save. Wie zijn eerste save
inleest heeft nog geen export -- die maak je pas als je merkt dat de cijfers
ontbreken -- dus iedereen liep gegarandeerd tegen deze volgorde aan.

De cijfers worden nu bij het tonen opgezocht.
"""

import json

import pytest


EXPORT = {
    "WPN_Handaxe": {"type": "Weapon", "source": "Shared.pak",
                    "display": {"Damage": "1d6", "Damage type": "Slashing",
                                "Weight": "0.9"}},
    "ARM_ChainShirt_Body_Shar": {"type": "Armor", "source": "Shared.pak",
                                 "display": {"Armour class": "13",
                                             "Weight": "9"}},
}


def zonder_stats(db, payload_bron):
    """Een momentopname zoals die eruitziet als er nog geen export was."""
    payload = json.loads(json.dumps(payload_bron))
    payload["item_stats"] = {}
    payload["game"]["hero_name"] = "Didymus"
    db.insert_save({"sha256": "f" * 64, "filename": "later.lsv",
                    "save_name": "Later", "hero_name": "Didymus",
                    "party_size": 2, "item_count": 4}, payload, None)
    return payload


def upload(client, export):
    return client.post("/instellingen/stats",
                       files={"stats": ("stats.json",
                                        json.dumps(export).encode(),
                                        "application/json")})


def test_stats_na_de_save_uploaden_werkt_alsnog(client, app_modules):
    """De gemelde storing, precies in die volgorde."""
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)

    rows, meta = ingest.item_rows(db.save_payload(1))
    assert meta["with_pak"] == 0, "voorwaarde: nog geen cijfers"

    upload(client, EXPORT)

    rows, meta = ingest.item_rows(db.save_payload(1))
    bijl = next(r for r in rows if r["id"] == "WPN_Handaxe")
    hemd = next(r for r in rows if r["id"] == "ARM_ChainShirt_Body_Shar")
    assert bijl["damage"] == "1d6" and bijl["weight"] == 0.9
    assert hemd["ac"] == 13.0
    assert meta["with_pak"] == 2


def test_de_cijfers_staan_ook_op_de_pagina(client, app_modules):
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    upload(client, EXPORT)
    text = client.get("/spul/WPN_Handaxe").text
    assert "1d6" in text
    assert "spelbestanden" in text


def test_een_nieuwere_export_wint(client, app_modules):
    """Zodat een aangevulde export je oude momentopnamen ook verbetert."""
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    upload(client, EXPORT)
    nieuwer = json.loads(json.dumps(EXPORT))
    nieuwer["WPN_Handaxe"]["display"]["Damage"] = "1d8"
    upload(client, nieuwer)
    rows, _ = ingest.item_rows(db.save_payload(1))
    assert next(r for r in rows if r["id"] == "WPN_Handaxe")["damage"] == "1d8"


def test_zonder_export_verandert_er_niets(app_modules):
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    payload = zonder_stats(db, PARTY)
    assert ingest.apply_stats(payload) is payload


def test_de_momentopname_zelf_blijft_ongemoeid(client, app_modules):
    """Overlappen bij het tonen mag de opgeslagen uitlezing niet herschrijven."""
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    upload(client, EXPORT)
    payload = db.save_payload(1)
    ingest.apply_stats(payload)
    assert payload["item_stats"] == {}
    assert db.save_payload(1)["item_stats"] == {}


def test_onbekende_voorwerpen_worden_gemeld(client, app_modules):
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    upload(client, EXPORT)
    ontbreekt = ingest.apply_stats(db.save_payload(1))["item_stats_missing"]
    assert "CONS_Potion_Healing" in ontbreekt
    assert "WPN_Handaxe" not in ontbreekt


@pytest.mark.parametrize("rommel", [
    {"WPN_Handaxe": None},
    {"WPN_Handaxe": "geen dict"},
])
def test_rare_entries_laten_de_pagina_niet_omvallen(app_modules, rommel):
    _, db, ingest = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    db.put_blob(ingest.STATS_KEY, rommel)
    rows, meta = ingest.item_rows(db.save_payload(1))
    assert rows and meta["with_pak"] == 0


def test_download_toont_dezelfde_cijfers_als_de_pagina(client, app_modules):
    _, db, _ = app_modules
    from tests.conftest import PARTY
    zonder_stats(db, PARTY)
    upload(client, EXPORT)
    payload = client.get("/party.json").json()
    assert payload["item_stats"]["WPN_Handaxe"]["fields"]["Damage"] == "1d6"
