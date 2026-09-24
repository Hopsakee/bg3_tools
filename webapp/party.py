"""
De party naast elkaar: wat de save zegt, wat de regels zeggen, wat jij invult.

Drie bronnen door elkaar, en de pagina moet kunnen laten zien welke welke is.
Dit bestand zet ze bij elkaar per personage, zodat main.py alleen nog tekent.
"""

from . import db, ingest  # noqa: F401  (ingest zet het pad naar de parsers)

import bg3_rules  # noqa: E402


def members(payload):
    """Eén samengesteld overzicht per party-lid, in de volgorde van de save."""
    hero = (payload.get("game") or {}).get("hero_name") or ""
    sheets = db.all_sheets()
    out = []
    for char in payload.get("party", []):
        key = ingest.character_key(char)
        entered = sheets.get(key) or dict(db.EMPTY_SHEET)
        classes = char.get("classes") or [
            {"class": char.get("class"), "subclass": char.get("subclass")}]
        extra_classes = [c.get("class") for c in classes[1:] if c.get("class")]
        sheet = bg3_rules.sheet(
            char.get("class"), char.get("level"),
            scores=entered.get("scores"), skills=entered.get("skills", []),
            expertise=entered.get("expertise", []),
            subclass=char.get("subclass"), race=char.get("race"),
            extra_classes=extra_classes, extra_profs=entered.get("extra", []))
        out.append({
            "key": key,
            "label": ingest.character_label(char, hero),
            "char": char,
            "classes": classes,
            "sheet": sheet,
            "entered": entered,
            "has_scores": any(v is not None for v in sheet["scores"].values()),
        })
    return out


def best(values, higher=True):
    """
    De waarde die een ster verdient, of None.

    Alleen als er iets te vergelijken valt: bij één bekende waarde, of als
    iedereen gelijk staat, is een ster ruis.
    """
    known = [v for v in values if v is not None]
    if len(known) < 2 or len(set(known)) == 1:
        return None
    return max(known) if higher else min(known)


def who_can_use(needs, party):
    """Per party-lid: kan hij dit voorwerp gebruiken (True/False/None)."""
    return [(m["label"], m["key"], bg3_rules.can_use(needs, m["sheet"]["proficiencies"]))
            for m in party]
