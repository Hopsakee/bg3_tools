"""De party naast elkaar, het invulblad, en wie welk voorwerp kan gebruiken."""

import json

import pytest


EXPORT = {
    "WPN_Handaxe": {"type": "Weapon", "source": "Shared.pak",
                    "display": {"Damage": "1d6",
                                "Proficiency": "Handaxes;SimpleWeapons"}},
    "WPN_LightCrossbow": {"type": "Weapon", "source": "Shared.pak",
                          "display": {"Damage": "1d8",
                                      "Proficiency": "LightCrossbows;SimpleWeapons"}},
    "ARM_ChainShirt_Body_Shar": {"type": "Armor", "source": "Shared.pak",
                                 "display": {"Armour class": "13",
                                             "Armour type": "ChainShirt"}},
}


def blad(client, key, **velden):
    return client.post("/personage/%s/blad" % key, data=velden)


# --------------------------------------------------------------- de pagina

def test_party_pagina_toont_iedereen_naast_elkaar(client, seeded):
    text = client.get("/party").text
    for kop in ("Vermogens", "Saving throws", "Vaardigheden", "Wapenrusting",
                "Wapens", "Kenmerken", "Jouw notities"):
        assert kop in text, kop
    assert "Didymus" in text and "Shadowheart" in text


def test_zonder_invoer_wijst_de_pagina_je_de_weg(client, seeded):
    text = client.get("/party").text
    assert "Nog in te vullen" in text
    assert "/personage/Shadowheart#blad" in text


def test_regels_staan_er_ook_zonder_invoer(client, seeded):
    """Bekwaamheden volgen uit klasse en ras; daar hoef je niets voor te doen."""
    text = client.get("/party").text
    assert "Spell save DC" in text
    assert "✓" in text


def test_kamp_staat_er_nog(client, seeded):
    assert "buiten de party" in client.get("/party").text


# -------------------------------------------------------------- invullen

def test_blad_opslaan_en_terugzien(client, app_modules, seeded):
    _, db, _ = app_modules
    r = blad(client, "Shadowheart", s_str="13", s_dex="14", s_con="14",
             s_int="10", s_wis="17", s_cha="8",
             **{"k_Insight": "prof", "k_Religion": "exp", "k_Stealth": "",
                "x_HeavyArmor": "1", "x_specifiek": "Longswords, Rapiers",
                "feats": "War Caster"})
    assert r.status_code == 303
    sheet = db.get_sheet("Shadowheart")
    assert sheet["scores"] == {"str": 13, "dex": 14, "con": 14, "int": 10,
                               "wis": 17, "cha": 8}
    assert sheet["skills"] == ["Insight", "Religion"]
    assert sheet["expertise"] == ["Religion"]
    assert sheet["extra"] == ["HeavyArmor", "Longswords", "Rapiers"]
    assert sheet["feats"] == "War Caster"


def test_ingevulde_scores_rekenen_door_op_de_party_pagina(client, seeded):
    blad(client, "Shadowheart", s_wis="17", **{"k_Insight": "prof"})
    text = client.get("/party").text
    assert "17 (+3)" in text
    assert "Wijsheid" in text                 # als sterkste trek
    # Insight: WIS +3, bekwaam +2 (level 3) = +5
    assert "+5" in text


@pytest.mark.parametrize("waarde,melding", [
    ("abc", "moet een getal zijn"),
    ("0", "tussen 1 en 30"),
    ("31", "tussen 1 en 30"),
])
def test_onzin_scores_worden_geweigerd(client, app_modules, seeded, waarde,
                                        melding):
    _, db, _ = app_modules
    blad(client, "Shadowheart", s_str=waarde)
    assert melding in client.get("/personage/Shadowheart").text
    assert db.get_sheet("Shadowheart")["scores"] == {}


def test_leeg_veld_is_geen_fout(client, app_modules, seeded):
    _, db, _ = app_modules
    assert blad(client, "Shadowheart", s_str="", s_wis="16").status_code == 303
    assert db.get_sheet("Shadowheart")["scores"] == {"wis": 16}


def test_blad_overleeft_een_nieuwe_save(client, app_modules, seeded):
    """Aan het personage gehangen, niet aan de momentopname."""
    _, db, _ = app_modules
    blad(client, "Shadowheart", s_wis="17")
    client.post("/saves/%d/wissen" % seeded[1])
    client.post("/saves/%d/wissen" % seeded[0])
    assert db.get_sheet("Shadowheart")["scores"] == {"wis": 17}


def test_extra_bekwaamheid_telt_mee(client, app_modules, seeded):
    """Zet je HeavyArmor aan voor een Cleric, dan kan ze het ook dragen."""
    _, _, _ = app_modules
    blad(client, "Shadowheart", x_HeavyArmor="1")
    text = client.get("/personage/Shadowheart").text
    assert "door jou" in text and "Zwaar" in text


def test_formulier_laat_de_bron_van_bekwaamheden_zien(client, seeded):
    text = client.get("/personage/Shadowheart").text
    assert "Bekwaam in" in text
    assert "klasse" in text and "ras" in text


# ----------------------------------------------------- wie kan wat gebruiken

def met_export(client):
    client.post("/instellingen/stats",
                files={"stats": ("s.json", json.dumps(EXPORT).encode(),
                                 "application/json")})


def test_voorwerppagina_zegt_wie_het_kan_gebruiken(client, seeded):
    met_export(client)
    text = client.get("/spul/WPN_Handaxe").text
    assert "Wie kan dit gebruiken" in text
    assert "Handaxes of Simple Weapons" in text
    # Warlock en Cleric kunnen allebei simple weapons
    assert text.count(">ja<") == 2


def test_wapenrusting_zonder_proficiency_veld(client, seeded):
    """ChainShirt is middel; Warlock kan dat niet, Cleric wel."""
    met_export(client)
    text = client.get("/spul/ARM_ChainShirt_Body_Shar").text
    assert "Middel" in text
    assert text.count(">ja<") == 1 and "nee" in text


def test_zonder_export_zegt_de_pagina_dat_het_onbekend_is(client, seeded):
    text = client.get("/spul/WPN_Handaxe").text
    assert "Onbekend" in text and "stats-export" in text


def test_spullenlijst_heeft_een_kolom_wie_kan_het(client, seeded):
    met_export(client)
    text = client.get("/spullen").text
    assert "Wie kan het" in text
    assert "Didymus, Shadowheart" in text
