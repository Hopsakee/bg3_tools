"""
De spelregels in bg3_rules.

Hier zit het risico van deze hele feature: als een regel fout staat, zegt de
app met overtuiging dat je Lae'zel geen longsword kunt geven terwijl dat wel
kan. De klassetabellen zijn standaard 5e; de indeling van wapens in simple en
martial is nagelopen tegen de echte spelgegevens. Deze tests leggen vast wat
er staat, zodat een wijziging niet ongemerkt iets omdraait.
"""

import pytest

import bg3_rules as r


# ------------------------------------------------------------- getallen

@pytest.mark.parametrize("level,bonus", [
    (1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (None, 2), ("x", 2)])
def test_proficiency_bonus(level, bonus):
    assert r.proficiency_bonus(level) == bonus


@pytest.mark.parametrize("score,mod", [
    (1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (12, 1), (17, 3), (20, 5),
    (None, None), ("", None), ("abc", None)])
def test_modifier(score, mod):
    assert r.modifier(score) == mod


def test_signed():
    assert (r.signed(3), r.signed(0), r.signed(-1), r.signed(None)) == \
        ("+3", "+0", "-1", "—")


# ---------------------------------------------------------- bekwaamheden

def test_fighter_kan_alles_dragen():
    profs = r.proficiencies("Fighter")
    assert {"LightArmor", "MediumArmor", "HeavyArmor", "Shields",
            "SimpleWeapons", "MartialWeapons"} <= set(profs)


def test_wizard_draagt_geen_pantser():
    profs = r.proficiencies("Wizard")
    assert not set(profs) & set(r.ARMOUR)
    assert "Daggers" in profs and "MartialWeapons" not in profs


def test_bron_wordt_bijgehouden():
    profs = r.proficiencies("Warlock", race="Githyanki")
    assert profs["LightArmor"] == "klasse"        # klasse wint van ras
    assert profs["MediumArmor"] == "ras"
    assert profs["Greatswords"] == "ras"


def test_rasnaam_hoeft_niet_exact():
    """In een save staat 'HalfElf', 'Half-Elf' of 'Half Elf' -- allemaal goed."""
    for spelling in ("HalfElf", "Half-Elf", "half elf"):
        assert "Shields" in r.proficiencies("Wizard", race=spelling)


@pytest.mark.parametrize("subclass,expect", [
    ("LifeDomain", {"HeavyArmor"}),
    ("WarDomain", {"HeavyArmor", "MartialWeapons"}),
    ("TempestDomain", {"HeavyArmor", "MartialWeapons"}),
    ("TrickeryDomain", set()),
])
def test_cleric_domeinen(subclass, expect):
    extra = {n for n, src in r.proficiencies("Cleric", subclass).items()
             if src == "subklasse"}
    assert extra == expect


def test_subklasse_geldt_alleen_voor_de_eigen_klasse():
    """'war' in een Warlock-subklasse mag geen Cleric-War-Domain opleveren."""
    assert "HeavyArmor" not in r.proficiencies("Warlock", "WarlockPatronWar")


def test_bard_valour_variant_spellingen():
    for sub in ("ValourCollege", "CollegeOfValor", "College of Valour"):
        assert "MartialWeapons" in r.proficiencies("Bard", sub)


def test_multiclass_geeft_minder_dan_als_eerste_klasse():
    """Wizard die multiclasst naar Fighter: geen zwaar pantser."""
    profs = r.proficiencies("Wizard", extra_classes=["Fighter"])
    assert "MartialWeapons" in profs and profs["MartialWeapons"] == "multiclass"
    assert "HeavyArmor" not in profs


def test_zelf_toegevoegd():
    profs = r.proficiencies("Wizard", extra=["HeavyArmor", " ", ""])
    assert profs["HeavyArmor"] == "zelf"
    assert "" not in profs and " " not in profs


# ------------------------------------------------------ simple en martial

def test_simple_en_martial_overlappen_niet():
    assert not r.SIMPLE_WEAPONS & r.MARTIAL_WEAPONS


def test_extra_wapens_telt_alleen_wat_niet_al_gedekt_is():
    # Githyanki-Fighter: greatswords komt van het ras, maar Martial dekt het al
    assert r.extra_weapons(r.proficiencies("Fighter", race="Githyanki")) == []
    # Half-Elf Warlock: Spears is simple (al gedekt), de rest is martial
    assert r.extra_weapons(r.proficiencies("Warlock", race="HalfElf")) == \
        ["Glaives", "Halberds", "Pikes"]


# ------------------------------------------------------- wie kan wat

def test_voorwerp_vraagt_een_van_zijn_bekwaamheden():
    needs = r.item_needs({"Proficiency": "Longswords;MartialWeapons"})
    assert needs == {"Longswords", "MartialWeapons"}
    assert r.can_use(needs, r.proficiencies("Fighter")) is True
    assert r.can_use(needs, r.proficiencies("Rogue")) is True   # via Longswords
    assert r.can_use(needs, r.proficiencies("Wizard")) is False


def test_wapenrusting_zonder_proficiency_veld_via_soort():
    """Niet elk stuk wapenrusting in de export heeft Proficiency ingevuld."""
    assert r.item_needs({"Armour type": "Plate"}) == {"HeavyArmor"}
    assert r.item_needs({"Armour type": "Leather"}) == {"LightArmor"}
    assert r.item_needs({"Armour type": "ChainShirt"}) == {"MediumArmor"}


def test_kleding_en_ringen_mag_iedereen():
    assert r.item_needs({"Armour type": "None"}) == set()
    assert r.item_needs({"Armour type": "Cloth"}) == set()
    assert r.can_use(set(), {}) is True


def test_onbekend_blijft_onbekend():
    """Zonder gegevens geen oordeel -- niet 'nee' verzinnen."""
    assert r.item_needs({}) is None
    assert r.item_needs(None) is None
    assert r.can_use(None, r.proficiencies("Fighter")) is None


# ------------------------------------------------------------ kenmerken

def test_extra_attack_pas_op_level_5():
    assert "Extra Attack" not in [n for _, n in r.features("Fighter", 4)]
    assert "Extra Attack" in [n for _, n in r.features("Fighter", 5)]


def test_feat_levels_fighter_krijgt_er_meer():
    fighter = [lvl for lvl, n in r.features("Fighter", 12) if n.startswith("Feat")]
    wizard = [lvl for lvl, n in r.features("Wizard", 12) if n.startswith("Feat")]
    assert fighter == [4, 6, 8, 12] and wizard == [4, 8, 12]


def test_onbekende_klasse_geeft_niets_in_plaats_van_te_crashen():
    assert r.features("Artificer", 5) == [(4, "Feat of +2 op scores")]
    assert r.proficiencies("Artificer") == {}


# --------------------------------------------------------------- het blad

LAEZEL = {"str": 17, "dex": 13, "con": 15, "int": 8, "wis": 12, "cha": 10}


def test_blad_rekent_zoals_het_spel():
    s = r.sheet("Fighter", 5, LAEZEL, skills=["Athletics", "Perception"])
    assert s["prof"] == 3
    assert s["saves"]["str"] == {"proficient": True, "bonus": 6}   # +3 +3
    assert s["saves"]["dex"] == {"proficient": False, "bonus": 1}
    assert s["skills"]["Athletics"]["bonus"] == 6
    assert s["skills"]["Stealth"]["bonus"] == 1                   # niet bekwaam
    assert s["passive_perception"] == 10 + 1 + 3
    assert s["initiative"] == 1
    assert s["strongest"] == "str"
    assert s["hit_die"] == 10
    assert s["spell_dc"] is None                                  # geen caster


def test_expertise_telt_dubbel():
    s = r.sheet("Rogue", 5, {"dex": 16}, skills=["Stealth"],
                expertise=["Stealth"])
    assert s["skills"]["Stealth"]["bonus"] == 3 + 3 * 2
    assert s["skills"]["Stealth"]["expertise"] is True


def test_spell_dc_en_attack():
    s = r.sheet("Wizard", 5, {"int": 16})
    assert s["spell_ability"] == "int"
    assert s["spell_dc"] == 8 + 3 + 3
    assert s["spell_attack"] == 6


def test_zonder_scores_wordt_er_niets_verzonnen():
    s = r.sheet("Fighter", 5, {})
    assert s["strongest"] is None
    assert s["saves"]["str"] == {"proficient": True, "bonus": None}
    assert all(v["bonus"] is None for v in s["skills"].values())
    assert s["passive_perception"] is None
    # maar wat alleen uit de regels volgt is er wel
    assert "HeavyArmor" in s["proficiencies"] and s["hit_die"] == 10


def test_half_ingevulde_scores():
    s = r.sheet("Fighter", 5, {"str": 16})
    assert s["mods"]["str"] == 3 and s["mods"]["dex"] is None
    assert s["strongest"] == "str"
