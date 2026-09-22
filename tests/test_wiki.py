"""
Wikigegevens: alleen wat jij aanlevert.

De app haalt met opzet niets op bij bg3.wiki. Die wiki heeft de Cargo-API
gesloten voor bezoekers zonder account ("You don't have permission to run
arbitrary Cargo queries"), en robots.txt sluit zowel /w/api.php als de
Special:-pagina's uit. Er is een tweede ingang die technisch nog werkt, maar
daarlangs gaan zou om allebei die borden heen lopen.

Wat blijft: heb jij een cache -- van de beheerders, of zelf gemaakt met
toestemming -- dan kun je die uploaden, en gebruikt de spullenlijst hem.
"""

import json

import pytest


CACHE = {
    "fetched": "2026-09-22T05:00:00Z",
    "source": "https://bg3.wiki/w/api.php",
    "licence": "CC BY-NC-SA 4.0 of CC BY-SA 4.0",
    "tables": {
        "weapons": [
            {"uid": "WPN_Handaxe", "name": "Handaxe", "rarity": "common",
             "price": "15", "damage": "1d6", "damage_type": "Slashing",
             "weight": "0.9", "where_to_find": "Overal in act 1"},
        ],
        "equipment": [
            {"uid": "ARM_ChainShirt_Body_Shar", "name": "Chain Shirt",
             "rarity": "common", "price": "70", "armour_class": "13"},
        ],
    },
}


def upload(client, payload, name="wiki.json"):
    body = payload if isinstance(payload, bytes) else \
        json.dumps(payload).encode("utf-8")
    return client.post("/instellingen/wiki",
                       files={"wiki": (name, body, "application/json")})


# ------------------------------------------------------ de app haalt niets op

def test_de_app_haalt_zelf_niets_op(app_modules):
    """
    Geen enkele functie in de app mag bg3.wiki benaderen. Deze test is de
    grens: hij valt om zodra iemand het ophalen terugzet.

    Via de AST en niet via de tekst van het bestand, anders slaat hij aan op
    de uitleg erboven waarin api.php gewoon genoemd wordt.
    """
    import ast

    _, _, ingest = app_modules
    assert not hasattr(ingest, "refresh_wiki")
    assert not hasattr(ingest, "diagnose_wiki")

    boom = ast.parse(ingest.Path(ingest.__file__).read_text(encoding="utf-8"))
    geimporteerd, aangeroepen = set(), set()
    for node in ast.walk(boom):
        if isinstance(node, ast.Import):
            geimporteerd.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            geimporteerd.add(node.module.split(".")[0])
        elif isinstance(node, ast.Attribute):
            aangeroepen.add(node.attr)

    assert "urllib" not in geimporteerd, "de app hoort geen netwerkcode te hebben"
    assert "bg3_wiki" not in geimporteerd
    assert "urlopen" not in aangeroepen


def test_instellingen_legt_uit_waarom(client):
    text = client.get("/instellingen").text
    assert "robots.txt" in text
    assert "permissiondenied" in text


# ---------------------------------------------------------------- uploaden

def test_cache_uploaden_en_terugzien(client, app_modules):
    _, db, ingest = app_modules
    assert upload(client, CACHE).status_code == 303
    stored = db.get_blob(ingest.WIKI_KEY)
    assert sorted(stored["tables"]) == ["equipment", "weapons"]
    info = db.blob_info(ingest.WIKI_KEY)
    assert "2 rijen" in info["note"]
    assert "Wiki-cache opgeslagen" in client.get("/instellingen").text


def test_geuploade_cache_verrijkt_de_spullenlijst(client, app_modules, seeded):
    """Zonder dit is uploaden een knop die alleen een database vult."""
    _, _, _ = app_modules
    upload(client, CACHE)
    text = client.get("/spul/WPN_Handaxe").text
    assert "Handaxe" in text
    assert "bg3.wiki" in text          # bron wordt vermeld
    assert "Overal in act 1" in text   # vindplaats komt mee


def test_cache_verwijderen(client, app_modules):
    _, db, ingest = app_modules
    upload(client, CACHE)
    assert client.post("/instellingen/wiki/wissen").status_code == 303
    assert db.get_blob(ingest.WIKI_KEY) is None


@pytest.mark.parametrize("payload,waarom", [
    (b"geen json", "onleesbaar"),
    (b"[]", "een lijst in plaats van een object"),
    ({"iets": "anders"}, "geen tables-sleutel"),
    ({"tables": {}}, "lege tables"),
    ({"tables": {"weapons": "geen lijst"}}, "tabel is geen lijst"),
])
def test_onbruikbaar_bestand_wordt_geweigerd(app_modules, payload, waarom):
    _, _, ingest = app_modules
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    with pytest.raises(ingest.BadSave):
        ingest.store_wiki_cache(raw, "wiki.json")


def test_geweigerd_bestand_geeft_een_nette_melding(client):
    assert upload(client, b"geen json").status_code == 303
    assert "niet lezen" in client.get("/instellingen").text
