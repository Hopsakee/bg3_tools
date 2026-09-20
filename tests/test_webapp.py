"""Wat er kapot mag gaan zonder dat iemand het merkt, staat hier in."""

import json

import pytest


# ------------------------------------------------------------ pagina's laden

PAGES = [
    "/", "/party", "/spullen", "/quests", "/notities", "/saves",
    "/instellingen", "/party.json", "/manifest.webmanifest", "/sw.js",
    "/offline", "/gezond", "/static/app.css", "/static/icon-192.png",
    "/personage/Generic", "/personage/Shadowheart",
    "/spul/WPN_Handaxe", "/quest/HAV_Druids_RescueHalsin",
]


@pytest.mark.parametrize("url", PAGES)
def test_pagina_laadt(client, seeded, url):
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("url", ["/", "/party", "/spullen", "/quests", "/saves"])
def test_pagina_zonder_savegames(client, url):
    """Een lege installatie mag geen 500 geven, maar een uitleg."""
    response = client.get(url)
    assert response.status_code == 200
    assert "savegame" in response.text.lower() or "ingelezen" in response.text.lower()


def test_onbekend_personage_en_voorwerp(client, seeded):
    assert client.get("/personage/Bestaatniet").status_code == 200
    assert client.get("/spul/Bestaatniet").status_code == 200


# ------------------------------------------------------------------ saves

def test_nieuwste_save_staat_standaard_in_beeld(client, seeded):
    assert "Tweede save" in client.get("/").text


def test_andere_save_kiezen_blijft_hangen(client, seeded):
    first, _ = seeded
    assert "Eerste save" in client.get("/?save=%d" % first).text
    assert "Eerste save" in client.get("/party").text      # onthouden in de sessie


def test_dezelfde_save_twee_keer_maakt_geen_dubbele(app_modules, seeded):
    _, db, _ = app_modules
    before = len(db.list_saves())
    row = db.save_meta(seeded[0])
    save_id, created = db.insert_save(
        {"sha256": row["sha256"], "filename": "nogmaals.lsv",
         "save_name": "Nogmaals"}, {}, None)
    assert not created and save_id == seeded[0]
    assert len(db.list_saves()) == before


def test_save_wissen_laat_notities_staan(client, app_modules, seeded):
    _, db, _ = app_modules
    db.save_note("character", "Shadowheart", body="blijft staan")
    client.post("/saves/%d/wissen" % seeded[1])
    assert db.save_meta(seeded[1]) is None
    assert db.get_note("character", "Shadowheart")["body"] == "blijft staan"
    assert client.get("/").status_code == 200     # valt terug op de andere save


def test_xp_verloop_verschijnt_pas_bij_twee_saves(client, app_modules, seeded):
    assert "<polyline" in client.get("/saves").text
    client.post("/saves/%d/wissen" % seeded[1])
    text = client.get("/saves").text
    assert "<polyline" not in text
    assert "Na een tweede upload" in text


# --------------------------------------------------------------- notities

def test_notitie_opslaan_en_terugzien(client, seeded):
    client.post("/notitie/character/Shadowheart",
                data={"label": "healer", "strong": "genezen",
                      "weak": "geen AoE", "body": "trickery domain",
                      "terug": "/personage/Shadowheart"})
    for page in ("/notities", "/party", "/personage/Shadowheart"):
        text = client.get(page).text
        assert "genezen" in text, page


def test_notitie_overleeft_een_nieuwe_save(client, app_modules, seeded):
    _, db, _ = app_modules
    db.save_note("item", "WPN_Handaxe", tag="bewaren")
    db.insert_save({"sha256": "c" * 64, "filename": "derde.lsv",
                    "save_name": "Derde save", "hero_name": "Didymus",
                    "party_size": 2, "item_count": 4}, {"party": []}, None)
    assert db.get_note("item", "WPN_Handaxe")["tag"] == "bewaren"


def test_leeg_formulier_wist_de_notitie(client, app_modules, seeded):
    _, db, _ = app_modules
    client.post("/notitie/quest/TUT_Helm_Quest", data={"body": "iets"})
    assert db.get_note("quest", "TUT_Helm_Quest") is not None
    client.post("/notitie/quest/TUT_Helm_Quest", data={"body": "   "})
    assert db.get_note("quest", "TUT_Helm_Quest") is None


def test_deelbewerking_laat_de_rest_staan(client, app_modules, seeded):
    """Het tagkeuzemenu mag je geschreven tekst niet stilletjes wissen."""
    _, db, _ = app_modules
    db.save_note("item", "WPN_Handaxe", body="goed om te gooien", label="reserve")
    db.save_note("item", "WPN_Handaxe", tag="bewaren")
    note = db.get_note("item", "WPN_Handaxe")
    assert note["body"] == "goed om te gooien"
    assert note["label"] == "reserve"
    assert note["tag"] == "bewaren"


def test_onbekende_notitiesoort_wordt_geweigerd(client, app_modules, seeded):
    _, db, _ = app_modules
    assert client.post("/notitie/rommel/x", data={"body": "nee"}).status_code == 303
    with pytest.raises(ValueError):
        db.save_note("rommel", "x", body="nee")


def test_onbekende_tag_wordt_niet_opgeslagen(client, app_modules, seeded):
    _, db, _ = app_modules
    client.post("/notitie/item/WPN_Handaxe",
                data={"tag": "opeten", "body": "iets"})
    assert db.get_note("item", "WPN_Handaxe")["tag"] == ""


# ---------------------------------------------------------------- spullen

def test_filteren_op_eigenaar(client, seeded):
    text = client.get("/spullen?eigenaar=Shadowheart").text
    assert "Potion Healing" in text
    assert "Light Crossbow" not in text


def test_filteren_op_plan(client, app_modules, seeded):
    _, db, _ = app_modules
    db.save_note("item", "WPN_Handaxe", tag="bewaren")
    text = client.get("/spullen?plan=bewaren").text
    assert "Handaxe" in text
    assert "Crossbow" not in text


def test_zoeken_kijkt_ook_in_je_eigen_notitie(client, app_modules, seeded):
    _, db, _ = app_modules
    db.save_note("item", "CONS_Potion_Healing", body="bewaar voor het eindgevecht")
    assert "Potion Healing" in client.get("/spullen?q=eindgevecht").text


def test_sorteren_zet_items_zonder_waarde_onderaan(app_modules, seeded):
    """In beide richtingen, anders duwt één leeg veld de rest uit beeld."""
    main, _, _ = app_modules
    rows = [{"avg": 3.5, "name": "a"}, {"avg": None, "name": "b"},
            {"avg": 7.0, "name": "c"}]
    assert [r["name"] for r in main.sort_items(rows, "schade", False)] == \
        ["a", "c", "b"]
    assert [r["name"] for r in main.sort_items(rows, "schade", True)] == \
        ["c", "a", "b"]


def test_onbekende_sortering_valt_terug(client, seeded):
    assert client.get("/spullen?sort=onzin&richting=af").status_code == 200


def test_onzekere_wikikoppeling_wordt_gemarkeerd(client, app_modules, seeded):
    """Een koppeling op een deel van de naam is een gok en moet dat laten zien."""
    _, db, ingest = app_modules
    db.put_blob(ingest.WIKI_KEY, {"tables": {"weapons": [
        {"uid": "", "name": "Chain Shirt", "rarity": "common", "price": "70"}]}})
    text = client.get("/spullen").text
    assert "wiki" in text and "≈" in text


# ------------------------------------------------------------------ upload

def test_rommel_uploaden_geeft_een_nette_melding(client):
    response = client.post(
        "/upload", files={"save": ("rommel.lsv", b"geen savegame")})
    assert response.status_code == 303
    assert "niet lezen" in client.get("/").text


def test_te_groot_bestand_wordt_geweigerd(client, monkeypatch, app_modules):
    main, _, _ = app_modules
    monkeypatch.setattr(main, "MAX_SAVE_BYTES", 10)
    client.post("/upload", files={"save": ("groot.lsv", b"x" * 100)})
    assert "groter dan" in client.get("/").text


def test_upload_vult_de_samenvatting(app_modules, monkeypatch):
    """De glue rond de parser: wat komt er in de kolommen terecht."""
    _, _, ingest = app_modules
    from tests.conftest import PARTY

    def fake_extract(path, stats_sources=None, stats_table=None):
        data = json.loads(json.dumps(PARTY))
        data["_screenshot"] = b"RIFFfake"
        return data

    monkeypatch.setattr(ingest.bg3_sheet, "extract", fake_extract)
    summary, payload, shot = ingest.parse_upload(b"bytes", "save.lsv", "Karlach")

    assert summary["party_size"] == 2
    assert summary["item_count"] == 4          # 3 + 1 uit items_by_group
    assert summary["xp_total"] == 1200         # de hoogste van de party
    assert summary["max_level"] == 3
    assert summary["quests_open"] == 1 and summary["quests_done"] == 1
    assert summary["difficulty"] == "Balanced"
    assert summary["hero_name"] == "Karlach"   # wat jij intikt wint
    assert payload["game"]["hero_name"] == "Karlach"
    assert shot == b"RIFFfake"
    assert "_screenshot" not in payload        # hoort niet in de JSON-uitvoer


def test_upload_valt_terug_op_de_naam_uit_de_save(app_modules, monkeypatch):
    _, _, ingest = app_modules
    from tests.conftest import PARTY
    monkeypatch.setattr(ingest.bg3_sheet, "extract",
                        lambda *a, **k: json.loads(json.dumps(PARTY)))
    summary, _, _ = ingest.parse_upload(b"bytes", "save.lsv", "   ")
    assert summary["hero_name"] == "Didymus"


def test_onleesbare_save_wordt_een_badsave(app_modules, monkeypatch):
    _, _, ingest = app_modules

    def boom(*args, **kwargs):
        raise SystemExit("SaveInfo.json of Globals.lsf mist.")

    monkeypatch.setattr(ingest.bg3_sheet, "extract", boom)
    with pytest.raises(ingest.BadSave):
        ingest.parse_upload(b"x", "save.lsv")


# -------------------------------------------------------------- itemstats

def test_itemstats_export_wordt_uitgedund(client, app_modules):
    _, db, ingest = app_modules
    full = {"WPN_X": {"type": "Weapon", "source": "Shared.pak",
                      "inherits": "_BaseWeapon",
                      "fields": {"Damage": "1d4", "RootTemplate": "ruis"},
                      "display": {"Damage": "1d4"}}}
    total = ingest.store_stats_export(json.dumps(full).encode(), "stats.json")
    stored = db.get_blob(ingest.STATS_KEY)
    assert total == 1
    assert stored["WPN_X"] == {"type": "Weapon", "source": "Shared.pak",
                               "display": {"Damage": "1d4"}}


def test_verkeerd_json_bestand_wordt_geweigerd(app_modules):
    _, _, ingest = app_modules
    for raw in (b"geen json", b"[]", b'{"WPN_X": {"iets": 1}}'):
        with pytest.raises(ingest.BadSave):
            ingest.store_stats_export(raw, "stats.json")


def test_itemstats_worden_gebruikt_bij_het_inlezen(app_modules, monkeypatch):
    """Een geuploade statstabel moet bij de parser terechtkomen."""
    _, db, ingest = app_modules
    db.put_blob(ingest.STATS_KEY, {"WPN_Handaxe": {"type": "Weapon",
                                                   "source": "s",
                                                   "display": {"Damage": "1d6"}}})
    seen = {}

    def spy(path, stats_sources=None, stats_table=None):
        seen["table"] = stats_table
        from tests.conftest import PARTY
        return json.loads(json.dumps(PARTY))

    monkeypatch.setattr(ingest.bg3_sheet, "extract", spy)
    ingest.parse_upload(b"x", "save.lsv")
    assert "WPN_Handaxe" in seen["table"]


# ------------------------------------------------------------------ overig

def test_statische_bestanden_blijven_binnen_hun_map(client):
    """De ingebouwde fasthtml-route deed hier niet aan; StaticFiles wel."""
    for attempt in ("/static/../main.py", "/static/..%2Fmain.py",
                    "/static/../../etc/passwd"):
        assert client.get(attempt).status_code in (301, 302, 307, 400, 404)


def test_party_json_is_de_volledige_uitlezing(client, seeded):
    payload = client.get("/party.json").json()
    assert payload["party"][0]["origin"] == "Generic"
    assert "_screenshot" not in payload


def test_screenshot_wordt_geserveerd(client, seeded):
    response = client.get("/screenshot/%d" % seeded[1])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert client.get("/screenshot/9999").status_code == 404
