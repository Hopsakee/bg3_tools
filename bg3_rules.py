"""
bg3_rules.py -- de spelregels die volgen uit klasse, ras en level.

Een savegame zegt welke klasse, subklasse, ras en level een personage heeft.
Wat hij niet leesbaar bevat -- ability scores, gekozen vaardigheden, feats --
staat in het nog niet ontcijferde deel van de save (zie README). Maar een groot
deel van wat je in het spel naast elkaar wilt zien volgt niet uit keuzes, maar
uit regels: een Fighter kan zware wapenrusting dragen, een Wizard niet; een
Githyanki kan met een greatsword overweg. Dat staat hier.

De namen van de bekwaamheden zijn exact die van het spel zelf: `MartialWeapons`,
`Longswords`, `LightArmor`, `Shields`. Dezelfde namen staan in het veld
`Proficiency` van elk wapen en elk stuk wapenrusting in de export van
`bg3_stats.py`. Daardoor is "kan dit personage dit wapen gebruiken" een
doorsnede van twee verzamelingen, zonder vertaalslag ertussen.

Zekerheid, eerlijk gezegd:

  * klassen      -- hoog. Standaard 5e, en BG3 volgt die hierin.
  * rassen       -- redelijk. BG3 wijkt hier en daar af van 5e; de tabel
                    hieronder volgt BG3 waar ik het verschil ken.
  * subklassen   -- redelijk, en alleen de bekende gevallen (Clerics met een
                    zwaar-pantserdomein, Bards van Valour en Swords).

Elke bekwaamheid draagt daarom zijn bron mee, zodat je in de app ziet waaróm
iemand iets kan en het zelf kunt aanvullen of corrigeren.
"""

import re

# ----------------------------------------------------------- basis, 5e

ABILITIES = [
    ("str", "Strength"), ("dex", "Dexterity"), ("con", "Constitution"),
    ("int", "Intelligence"), ("wis", "Wisdom"), ("cha", "Charisma"),
]
ABILITY_KEYS = [key for key, _ in ABILITIES]
ABILITY_NL = {"str": "Kracht", "dex": "Behendigheid", "con": "Gestel",
              "int": "Intelligentie", "wis": "Wijsheid", "cha": "Charisma"}

SKILLS = [
    ("Acrobatics", "dex"), ("Animal Handling", "wis"), ("Arcana", "int"),
    ("Athletics", "str"), ("Deception", "cha"), ("History", "int"),
    ("Insight", "wis"), ("Intimidation", "cha"), ("Investigation", "int"),
    ("Medicine", "wis"), ("Nature", "int"), ("Perception", "wis"),
    ("Performance", "cha"), ("Persuasion", "cha"), ("Religion", "int"),
    ("Sleight of Hand", "dex"), ("Stealth", "dex"), ("Survival", "wis"),
]
SKILL_NAMES = [name for name, _ in SKILLS]

HIT_DIE = {
    "Barbarian": 12, "Fighter": 10, "Paladin": 10, "Ranger": 10,
    "Bard": 8, "Cleric": 8, "Druid": 8, "Monk": 8, "Rogue": 8, "Warlock": 8,
    "Sorcerer": 6, "Wizard": 6,
}

SAVE_PROFICIENCIES = {
    "Barbarian": ("str", "con"), "Bard": ("dex", "cha"),
    "Cleric": ("wis", "cha"), "Druid": ("int", "wis"),
    "Fighter": ("str", "con"), "Monk": ("str", "dex"),
    "Paladin": ("wis", "cha"), "Ranger": ("str", "dex"),
    "Rogue": ("dex", "int"), "Sorcerer": ("con", "cha"),
    "Warlock": ("wis", "cha"), "Wizard": ("int", "wis"),
}

SPELL_ABILITY = {
    "Bard": "cha", "Cleric": "wis", "Druid": "wis", "Paladin": "cha",
    "Ranger": "wis", "Sorcerer": "cha", "Warlock": "cha", "Wizard": "int",
}

# -------------------------------------------------- wapens en wapenrusting

ARMOUR = ["LightArmor", "MediumArmor", "HeavyArmor", "Shields"]
ARMOUR_NL = {"LightArmor": "Licht", "MediumArmor": "Middel",
             "HeavyArmor": "Zwaar", "Shields": "Schilden"}

# Welk wapen onder welke groep valt. Nagelopen tegen het veld `Weapon group`
# van alle 526 wapens in een echte export uit het spel (september 2026): de
# indeling is exact die van 5e. Shortswords en Scimitars staan daar een paar
# keer als simple bij losse, afwijkende voorwerpen, maar ruim 20 keer zo vaak
# als martial.
SIMPLE_WEAPONS = {
    "Clubs", "Daggers", "Darts", "Greatclubs", "Handaxes", "Javelins",
    "LightCrossbows", "LightHammers", "Maces", "Quarterstaffs", "Shortbows",
    "Sickles", "Slings", "Spears",
}
MARTIAL_WEAPONS = {
    "Battleaxes", "Flails", "Glaives", "Greataxes", "Greatswords", "Halberds",
    "HandCrossbows", "HeavyCrossbows", "Longbows", "Longswords", "Mauls",
    "Morningstars", "Pikes", "Rapiers", "Scimitars", "Shortswords",
    "Tridents", "Warhammers", "Warpicks",
}


def extra_weapons(profs):
    """
    Losse wapenbekwaamheden die niet al gedekt zijn door Simple of Martial.

    Een Githyanki Fighter kan met greatswords overweg, maar dat zegt niets:
    hij kan het al als Fighter. Dit geeft alleen wat er écht bij komt.
    """
    profs = set(profs)
    covered = set()
    if "SimpleWeapons" in profs:
        covered |= SIMPLE_WEAPONS
    if "MartialWeapons" in profs:
        covered |= MARTIAL_WEAPONS
    return sorted(p for p in profs
                  if (p in SIMPLE_WEAPONS or p in MARTIAL_WEAPONS)
                  and p not in covered)


# De eerste klasse bepaalt alles hieronder.
CLASS_PROFICIENCIES = {
    "Barbarian": {"LightArmor", "MediumArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Bard":      {"LightArmor", "SimpleWeapons", "HandCrossbows",
                  "Longswords", "Rapiers", "Shortswords", "MusicalInstrument"},
    "Cleric":    {"LightArmor", "MediumArmor", "Shields", "SimpleWeapons"},
    "Druid":     {"LightArmor", "MediumArmor", "Shields", "Clubs", "Daggers",
                  "Darts", "Javelins", "Maces", "Quarterstaffs", "Scimitars",
                  "Sickles", "Slings", "Spears"},
    "Fighter":   {"LightArmor", "MediumArmor", "HeavyArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Monk":      {"SimpleWeapons", "Shortswords"},
    "Paladin":   {"LightArmor", "MediumArmor", "HeavyArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Ranger":    {"LightArmor", "MediumArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Rogue":     {"LightArmor", "SimpleWeapons", "HandCrossbows",
                  "Longswords", "Rapiers", "Shortswords"},
    "Sorcerer":  {"Daggers", "Darts", "Slings", "Quarterstaffs",
                  "LightCrossbows"},
    "Warlock":   {"LightArmor", "SimpleWeapons"},
    "Wizard":    {"Daggers", "Darts", "Slings", "Quarterstaffs",
                  "LightCrossbows"},
}

# Wat een tweede of latere klasse erbij geeft. Minder dan als eerste klasse:
# zo werkt multiclassen in 5e en in BG3.
MULTICLASS_PROFICIENCIES = {
    "Barbarian": {"Shields", "SimpleWeapons", "MartialWeapons"},
    "Bard":      {"LightArmor", "MusicalInstrument"},
    "Cleric":    {"LightArmor", "MediumArmor", "Shields"},
    "Druid":     {"LightArmor", "MediumArmor", "Shields"},
    "Fighter":   {"LightArmor", "MediumArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Monk":      {"SimpleWeapons", "Shortswords"},
    "Paladin":   {"LightArmor", "MediumArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Ranger":    {"LightArmor", "MediumArmor", "Shields",
                  "SimpleWeapons", "MartialWeapons"},
    "Rogue":     {"LightArmor"},
    "Sorcerer":  set(),
    "Warlock":   {"LightArmor", "SimpleWeapons"},
    "Wizard":    set(),
}

_CIVIL_MILITIA = {"Spears", "Pikes", "Halberds", "Glaives",
                  "LightArmor", "Shields"}

# Op genormaliseerde rasnaam. Staat een ras er niet in, dan geeft het niets.
RACE_PROFICIENCIES = {
    "human":      _CIVIL_MILITIA,
    "halfelf":    _CIVIL_MILITIA,
    "elf":        {"Longswords", "Shortswords", "Longbows", "Shortbows"},
    "highelf":    {"Longswords", "Shortswords", "Longbows", "Shortbows"},
    "woodelf":    {"Longswords", "Shortswords", "Longbows", "Shortbows"},
    "drow":       {"Rapiers", "Shortswords", "HandCrossbows"},
    "dwarf":      {"Battleaxes", "Handaxes", "LightHammers", "Warhammers"},
    "golddwarf":  {"Battleaxes", "Handaxes", "LightHammers", "Warhammers"},
    "shielddwarf": {"Battleaxes", "Handaxes", "LightHammers", "Warhammers",
                    "LightArmor", "MediumArmor"},
    "duergar":    {"Battleaxes", "Handaxes", "LightHammers", "Warhammers"},
    "githyanki":  {"Greatswords", "Longswords", "Shortswords",
                   "LightArmor", "MediumArmor"},
}

# (klasse, trefwoord in de subklasse) -> extra bekwaamheden. Op trefwoord en
# niet op exacte naam, want de interne subklassenamen in een save zijn niet
# overal eenduidig ("ValourCollege", "CollegeOfValor", ...).
SUBCLASS_PROFICIENCIES = [
    ("Cleric", "life",    {"HeavyArmor"}),
    ("Cleric", "nature",  {"HeavyArmor"}),
    ("Cleric", "tempest", {"HeavyArmor", "MartialWeapons"}),
    ("Cleric", "war",     {"HeavyArmor", "MartialWeapons"}),
    ("Bard",   "valo",    {"MediumArmor", "Shields", "MartialWeapons"}),
    ("Bard",   "sword",   {"MediumArmor", "Scimitars"}),
]

# Wapenrustingsoort -> welke bekwaamheid je nodig hebt. Voor items waar het
# veld Proficiency ontbreekt maar Armour type wel bekend is.
ARMOUR_TYPE_NEEDS = {
    "Padded": "LightArmor", "Leather": "LightArmor",
    "StuddedLeather": "LightArmor",
    "Hide": "MediumArmor", "ChainShirt": "MediumArmor",
    "ScaleMail": "MediumArmor", "BreastPlate": "MediumArmor",
    "HalfPlate": "MediumArmor",
    "RingMail": "HeavyArmor", "ChainMail": "HeavyArmor",
    "Splint": "HeavyArmor", "Plate": "HeavyArmor",
}

# ------------------------------------------------------- kernkenmerken

# De kenmerken waar je een beslissing op neemt: wie slaat twee keer, wie kan
# een tweede actie nemen, wie verstopt zich. Bewust niet volledig -- een lange
# lijst verbergt wat ertoe doet, en wat ik niet zeker weet laat ik weg.
CLASS_FEATURES = {
    "Barbarian": {1: ["Rage", "Unarmoured Defence"],
                  2: ["Reckless Attack", "Danger Sense"],
                  5: ["Extra Attack", "Fast Movement"],
                  7: ["Feral Instinct"], 9: ["Brutal Critical"],
                  11: ["Relentless Rage"]},
    "Bard":      {1: ["Spellcasting", "Bardic Inspiration"],
                  2: ["Jack of All Trades", "Song of Rest"],
                  3: ["Expertise"], 5: ["Font of Inspiration"],
                  6: ["Countercharm"], 10: ["Magical Secrets", "Expertise"]},
    "Cleric":    {1: ["Spellcasting", "Divine Domain"],
                  2: ["Channel Divinity"], 5: ["Destroy Undead"],
                  10: ["Divine Intervention"]},
    "Druid":     {1: ["Spellcasting"], 2: ["Wild Shape", "Druid Circle"]},
    "Fighter":   {1: ["Fighting Style", "Second Wind"], 2: ["Action Surge"],
                  3: ["Martial Archetype"], 5: ["Extra Attack"],
                  9: ["Indomitable"], 11: ["Extra Attack (2)"]},
    "Monk":      {1: ["Martial Arts", "Unarmoured Defence"],
                  2: ["Ki", "Unarmoured Movement"], 3: ["Deflect Missiles"],
                  5: ["Extra Attack", "Stunning Strike"],
                  7: ["Evasion"]},
    "Paladin":   {1: ["Divine Sense", "Lay on Hands"],
                  2: ["Fighting Style", "Divine Smite", "Spellcasting"],
                  3: ["Channel Oath"], 5: ["Extra Attack"],
                  6: ["Aura of Protection"], 11: ["Improved Divine Smite"]},
    "Ranger":    {1: ["Favoured Enemy", "Natural Explorer"],
                  2: ["Fighting Style", "Spellcasting"],
                  5: ["Extra Attack"]},
    "Rogue":     {1: ["Expertise", "Sneak Attack"], 2: ["Cunning Action"],
                  5: ["Uncanny Dodge"], 6: ["Expertise"], 7: ["Evasion"],
                  11: ["Reliable Talent"]},
    "Sorcerer":  {1: ["Spellcasting", "Sorcerous Origin"],
                  2: ["Sorcery Points"], 3: ["Metamagic"]},
    "Warlock":   {1: ["Otherworldly Patron", "Pact Magic"],
                  2: ["Eldritch Invocations"], 3: ["Pact Boon"],
                  11: ["Mystic Arcanum"]},
    "Wizard":    {1: ["Spellcasting", "Arcane Recovery"],
                  2: ["Arcane Tradition"]},
}

# Wanneer je een feat of +2 op je scores krijgt. BG3 gaat tot level 12.
FEAT_LEVELS = {"Fighter": (4, 6, 8, 12), "Rogue": (4, 8, 10, 12)}
DEFAULT_FEAT_LEVELS = (4, 8, 12)


# ------------------------------------------------------------ functies

def normalise(text):
    return re.sub(r"[^a-z]", "", (text or "").lower())


def proficiency_bonus(level):
    """+2 tot en met 4, +3 tot en met 8, +4 daarna. BG3 stopt bij 12."""
    try:
        level = int(level)
    except (TypeError, ValueError):
        return 2
    return 2 + max(0, (max(level, 1) - 1) // 4)


def modifier(score):
    """10-11 is +0, 12-13 is +1, 8-9 is -1. Geen score, geen modifier."""
    if score in (None, ""):
        return None
    try:
        return (int(score) - 10) // 2
    except (TypeError, ValueError):
        return None


def signed(value):
    return "—" if value is None else ("+%d" % value if value >= 0 else "%d" % value)


def proficiencies(klass, subclass=None, race=None, extra_classes=(), extra=()):
    """
    Alle bekwaamheden van één personage, elk met zijn bron.

    Geeft {naam: bron} terug. Eerste bron wint, in deze volgorde: klasse,
    subklasse, ras, latere klassen, jezelf -- zodat je ziet waar iets
    oorspronkelijk vandaan komt als het van meer kanten komt.
    """
    found = {}

    def add(names, source):
        for name in names:
            found.setdefault(name, source)

    add(CLASS_PROFICIENCIES.get(klass, ()), "klasse")
    sub = normalise(subclass)
    for owner, keyword, names in SUBCLASS_PROFICIENCIES:
        if owner == klass and keyword in sub:
            add(names, "subklasse")
    add(RACE_PROFICIENCIES.get(normalise(race), ()), "ras")
    for other in extra_classes:
        if other and other != klass:
            add(MULTICLASS_PROFICIENCIES.get(other, ()), "multiclass")
    add((e.strip() for e in extra if e and e.strip()), "zelf")
    return found


def item_needs(display, item_type=None):
    """
    Welke bekwaamheid een voorwerp vraagt, uit zijn eigen gegevens.

    Geeft een verzameling terug waarvan je er ÉÉN nodig hebt ("Longswords" of
    "MartialWeapons" volstaat voor een longsword), of een lege verzameling als
    iedereen het mag dragen, of None als het niet te zeggen is.
    """
    display = display or {}
    tokens = {t for t in (display.get("Proficiency") or "").split(";") if t}
    if tokens:
        return tokens
    armour_type = display.get("Armour type")
    if armour_type in ARMOUR_TYPE_NEEDS:
        return {ARMOUR_TYPE_NEEDS[armour_type]}
    if armour_type in ("None", "Cloth") or item_type == "Object":
        return set()
    return None


def can_use(needs, profs):
    """True / False, of None als de bekwaamheid van het voorwerp onbekend is."""
    if needs is None:
        return None
    if not needs:
        return True
    return bool(needs & set(profs))


def features(klass, level):
    """Kernkenmerken tot en met dit level, op volgorde."""
    try:
        level = int(level)
    except (TypeError, ValueError):
        return []
    out = []
    for at, names in sorted(CLASS_FEATURES.get(klass, {}).items()):
        if at <= level:
            out.extend((at, name) for name in names)
    feat_at = FEAT_LEVELS.get(klass, DEFAULT_FEAT_LEVELS)
    out.extend((at, "Feat of +2 op scores") for at in feat_at if at <= level)
    return sorted(out)


def sheet(klass, level, scores=None, skills=(), expertise=(), subclass=None,
          race=None, extra_classes=(), extra_profs=()):
    """
    Alles wat je in het spel op het karakterscherm ziet, voor zover het uit
    regels en jouw invoer volgt.

    `scores` mag leeg of onvolledig zijn: wat ervan afhangt blijft dan leeg
    in plaats van dat er iets verzonnen wordt.
    """
    scores = {k: (scores or {}).get(k) for k in ABILITY_KEYS}
    mods = {k: modifier(v) for k, v in scores.items()}
    prof = proficiency_bonus(level)
    save_profs = set(SAVE_PROFICIENCIES.get(klass, ()))
    skills, expertise = set(skills), set(expertise)

    saves = {}
    for key in ABILITY_KEYS:
        m = mods[key]
        saves[key] = {"proficient": key in save_profs,
                      "bonus": None if m is None else
                      m + (prof if key in save_profs else 0)}

    skill_rows = {}
    for name, key in SKILLS:
        m = mods[key]
        mult = 2 if name in expertise else 1 if name in skills else 0
        skill_rows[name] = {"ability": key, "proficient": mult >= 1,
                            "expertise": mult == 2,
                            "bonus": None if m is None else m + prof * mult}

    spell = SPELL_ABILITY.get(klass)
    spell_mod = mods.get(spell) if spell else None
    perception = skill_rows["Perception"]["bonus"]

    known = [(scores[k], k) for k in ABILITY_KEYS if scores[k] is not None]
    strongest = max(known)[1] if known else None

    return {
        "scores": scores, "mods": mods, "prof": prof,
        "saves": saves, "skills": skill_rows,
        "hit_die": HIT_DIE.get(klass),
        "spell_ability": spell,
        "spell_dc": None if spell_mod is None else 8 + prof + spell_mod,
        "spell_attack": None if spell_mod is None else prof + spell_mod,
        "initiative": mods["dex"],
        "passive_perception": None if perception is None else 10 + perception,
        "strongest": strongest,
        "proficiencies": proficiencies(klass, subclass, race, extra_classes,
                                       extra_profs),
        "features": features(klass, level),
    }
