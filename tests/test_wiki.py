"""
De knop "Nu ophalen" bij bg3.wiki.

Geschreven na 2026-09-22, toen die knop niets deed. `bg3_wiki` is een
CLI-module en stopt bij een onbereikbare wiki met `SystemExit`; dat erft van
BaseException, dus het `except Exception` in de route ving het niet en de fout
schoot dwars door de request heen. Geen melding, geen pagina, niets.

De wiki zelf wordt hier niet benaderd -- `_request` is vervangen door een stub
die teruggeeft wat de Cargo-API teruggeeft. Wat hier getest wordt is dus onze
kant: vertalen, opslaan, en netjes melden wat er misging.
"""

import urllib.error

import pytest


def cargo_stub(rows_per_table, fail=()):
    """
    Bootst de Cargo-API na.

    probe() vraagt eerst één rij op om te zien welke velden bestaan; daarna
    paginaert fetch_table() met limit=500. De stub geeft de gevraagde velden
    terug en stopt zodra de tabel op is.
    """
    def _request(params, timeout=30):
        table = params["tables"]
        if table in fail:
            raise urllib.error.URLError("Connection refused")
        fields = params["fields"].split(",")
        limit = int(params["limit"])
        offset = int(params.get("offset", 0))
        total = rows_per_table.get(table, 0)
        rows = []
        for i in range(offset, min(offset + limit, total)):
            rows.append({"title": {f: "%s-%s-%d" % (table, f, i) for f in fields}})
        return {"cargoquery": rows}
    return _request


@pytest.fixture
def wiki(app_modules, monkeypatch):
    _, _, ingest = app_modules

    def install(rows_per_table, fail=()):
        monkeypatch.setattr(ingest.bg3_wiki, "_request",
                            cargo_stub(rows_per_table, fail))
        monkeypatch.setattr(ingest.bg3_wiki.time, "sleep", lambda *_: None)
    return install


# ------------------------------------------------------------- het gelukt-pad

def test_ophalen_bewaart_de_tabellen(app_modules, wiki):
    _, db, ingest = app_modules
    wiki({"weapons": 3, "equipment": 2})
    total, failed = ingest.refresh_wiki()
    assert total == 5 and failed == []
    cache = db.get_blob(ingest.WIKI_KEY)
    assert sorted(cache["tables"]) == ["equipment", "weapons"]
    assert len(cache["tables"]["weapons"]) == 3
    assert cache["source"] == ingest.bg3_wiki.API


def test_paginering_haalt_alles_op(app_modules, wiki):
    """Meer dan één pagina van 500; anders mis je stilzwijgend de rest."""
    _, db, ingest = app_modules
    wiki({"weapons": 1200, "equipment": 0})
    total, failed = ingest.refresh_wiki()
    assert total == 1200 and failed == []


def test_knop_meldt_succes(client, wiki, app_modules):
    wiki({"weapons": 3, "equipment": 2})
    assert client.post("/instellingen/wiki").status_code == 303
    text = client.get("/instellingen").text
    assert "Opgehaald" in text and "5" in text


# --------------------------------------------------------------- het faal-pad

def test_onbereikbare_wiki_geeft_een_melding_geen_crash(client, wiki):
    """
    De storing zelf: probe() gooit SystemExit, die door `except Exception`
    heen glipt. De route hoort een nette melding te geven.
    """
    wiki({"weapons": 3, "equipment": 2}, fail=("weapons", "equipment"))
    response = client.post("/instellingen/wiki")
    assert response.status_code == 303
    assert "mislukt" in client.get("/instellingen").text.lower()


def test_systemexit_wordt_een_gewone_fout(app_modules, wiki):
    _, _, ingest = app_modules
    wiki({}, fail=("weapons", "equipment"))
    with pytest.raises(ingest.WikiFailed) as caught:
        ingest.refresh_wiki()
    assert "weapons" in str(caught.value)


def test_een_kapotte_tabel_verpest_de_andere_niet(app_modules, wiki):
    """Verandert het schema van één tabel, dan houd je de rest."""
    _, db, ingest = app_modules
    wiki({"weapons": 4, "equipment": 0}, fail=("equipment",))
    total, failed = ingest.refresh_wiki()
    assert total == 4
    assert len(failed) == 1 and "equipment" in failed[0]
    assert list(db.get_blob(ingest.WIKI_KEY)["tables"]) == ["weapons"]
    assert "mislukt" in db.blob_info(ingest.WIKI_KEY)["note"]


def test_deels_gelukt_wordt_ook_als_deels_gemeld(client, wiki):
    wiki({"weapons": 4, "equipment": 0}, fail=("equipment",))
    client.post("/instellingen/wiki")
    assert "Deels gelukt" in client.get("/instellingen").text


def test_niet_json_of_ander_ongeluk_blijft_binnen_de_route(app_modules, monkeypatch):
    _, _, ingest = app_modules

    def boom(*a, **k):
        raise ValueError("geen JSON")

    monkeypatch.setattr(ingest.bg3_wiki, "_request", boom)
    with pytest.raises(ingest.WikiFailed) as caught:
        ingest.refresh_wiki()
    assert "ValueError" in str(caught.value)


# ------------------------------------------------- en wordt het ook gebruikt

def test_opgehaalde_wiki_verrijkt_de_spullenlijst(client, app_modules, seeded):
    """Zonder dit is het ophalen een knop die alleen een database vult."""
    _, db, ingest = app_modules
    db.put_blob(ingest.WIKI_KEY, {"tables": {"weapons": [
        {"uid": "WPN_Handaxe", "name": "Handaxe", "rarity": "common",
         "price": "15", "damage": "1d6"}]}})
    text = client.get("/spul/WPN_Handaxe").text
    assert "Handaxe" in text
    assert "bg3.wiki" in text


# --------------------------------------------------------------- diagnose

def test_diagnose_wijst_de_kapotte_laag_aan(app_modules, monkeypatch, client):
    """
    Het echte geval van 2026-09-22: de wiki antwoordt, maar Cargo zegt dat de
    tabel niet bestaat. Diagnose hoort dat letterlijk te laten zien.
    """
    _, _, ingest = app_modules

    def antwoord(params, timeout=30):
        if params.get("action") == "query":
            return {"query": {"general": {"sitename": "bg3.wiki"}}}
        if params.get("action") == "cargotables":
            return {"error": {"code": "unknown_action", "info": "Onbekende actie"}}
        return {"error": {"code": "invalidtable",
                          "info": "Error: no such table: %s" % params["tables"]}}

    monkeypatch.setattr(ingest.bg3_wiki, "_request", antwoord)
    rows = ingest.diagnose_wiki()
    labels = {label: (good, text) for label, good, text in rows}

    api = [v for k, v in labels.items() if "API bereikbaar" in k][0]
    assert api[0] is True, "de API zelf werkt en moet als ok gelden"
    tabel = [v for k, v in labels.items() if "tabel weapons" in k][0]
    assert tabel[0] is False and "no such table" in tabel[1]

    body = client.post("/instellingen/wiki/diagnose").text
    assert "no such table" in body
    assert "MISLUKT" in body and "ok" in body


def test_diagnose_overleeft_een_onbereikbare_wiki(app_modules, monkeypatch, client):
    _, _, ingest = app_modules

    def dood(*a, **k):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(ingest.bg3_wiki, "_request", dood)
    rows = ingest.diagnose_wiki()
    assert rows and all(good is False for _, good, _ in rows)
    assert client.post("/instellingen/wiki/diagnose").status_code == 200


def test_foutmelding_van_de_wiki_komt_in_de_melding_terecht(app_modules, monkeypatch):
    """
    probe() gooide de tekst van de wiki weg; die stond alleen in de
    verbose-uitvoer. Juist daar staat of de tabel of het veld het probleem is.
    """
    _, _, ingest = app_modules

    def afgewezen(params, timeout=30):
        return {"error": {"code": "invalidtable",
                          "info": "Error: no such table: weapons"}}

    monkeypatch.setattr(ingest.bg3_wiki, "_request", afgewezen)
    with pytest.raises(ingest.WikiFailed) as caught:
        ingest.refresh_wiki(tables=("weapons",))
    assert "no such table" in str(caught.value)
