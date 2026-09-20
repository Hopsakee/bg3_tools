"""Een webapp met een verse database per test, en een nagebouwde savegame.

De echte parser wordt hier niet gedraaid: die heeft een binaire `.lsv` nodig en
is al gedekt door zijn eigen CLI. Wat hier getest wordt is alles eromheen --
opslaan, terugvinden, filteren, notities, en de vraag of een pagina überhaupt
rendert zonder te struikelen over een leeg veld.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PARTY = {
    "game": {
        "save_name": "A Nautiloid in Hell", "game_version": "4.1.1.111",
        "platform": "Steam", "difficulty": ["Balanced"],
        "current_level": "TUT_Avernus_C", "source_file": "save.lsv",
        "character_name_from_folder": "Didymus", "game_time_seconds": 5678,
        "game_id": "abc-123", "modded": False, "mods": ["GustavDev"],
    },
    "party": [
        {"origin": "Generic", "race": "HalfElf", "class": "Warlock",
         "subclass": "TheFiend", "level": 3, "xp_total": 1200,
         "xp_this_level": 100, "position": [1.0, 2.0, 3.0],
         "level_name": "TUT_Avernus_C", "template_id": "S_Player_Hero",
         "statuses": ["MAG_BURNING"], "item_count": 3,
         "items_by_group": {"Wapens": ["WPN_Handaxe", "WPN_LightCrossbow"],
                            "Wapenrusting": ["ARM_ChainShirt_Body_Shar"]},
         "matched_in_globals": True},
        {"origin": "Shadowheart", "race": "HalfElf", "class": "Cleric",
         "subclass": "TrickeryDomain", "level": 3, "xp_total": 1100,
         "xp_this_level": 50, "position": [4.0, 2.0, 3.0],
         "level_name": "TUT_Avernus_C", "template_id": "S_GLO_Shadowheart",
         "statuses": [], "item_count": 1,
         "items_by_group": {"Drankjes": ["CONS_Potion_Healing"]},
         "matched_in_globals": True},
    ],
    "item_stats": {
        "WPN_Handaxe": {"type": "Weapon", "source": "Shared.pak",
                        "fields": {"Damage": "1d6", "Damage type": "Slashing",
                                   "Weight": "0.9", "Rarity": "common"}},
    },
    "item_stats_missing": ["CONS_Potion_Healing"],
    "comparison": {},
    "other_playable_characters": [
        {"template_id": "S_GLO_Astarion", "level_name": "TUT_Avernus_C",
         "position": [9.0, 1.0, 1.0], "item_count": 4}],
    "quests": {"completed": ["TUT_Helm_Quest"],
               "in_progress": ["HAV_Druids_RescueHalsin"],
               "game_time_seconds": 5678},
    "not_stored_in_save": ["Ability scores (Strength t/m Charisma)"],
    "provenance": [("Savenaam", "SaveInfo.json")],
}


@pytest.fixture
def app_modules(tmp_path, monkeypatch):
    """Importeer de app vers, met een eigen database en sessiesleutel."""
    monkeypatch.setenv("SESSION_SECRET", "test")
    monkeypatch.setenv("BG3_DB_PATH", str(tmp_path / "test.db"))
    for name in list(sys.modules):
        if name.startswith("webapp"):
            del sys.modules[name]
    from webapp import db, ingest, main
    return main, db, ingest


@pytest.fixture
def client(app_modules):
    from starlette.testclient import TestClient
    main, _, _ = app_modules
    return TestClient(main.app, follow_redirects=False)


@pytest.fixture
def seeded(app_modules):
    """Twee momentopnamen in de database, de tweede is de nieuwste."""
    _, db, _ = app_modules

    def add(name, sha, xp):
        payload = json.loads(json.dumps(PARTY))
        payload["game"]["save_name"] = name
        payload["game"]["hero_name"] = "Didymus"
        return db.insert_save({
            "sha256": sha, "filename": name + ".lsv", "save_name": name,
            "hero_name": "Didymus", "game_version": "4.1.1.111",
            "difficulty": "Balanced", "current_level": "TUT_Avernus_C",
            "play_seconds": 5678, "game_id": "abc-123", "party_size": 2,
            "item_count": 4, "xp_total": xp, "max_level": 3,
            "quests_open": 1, "quests_done": 1,
        }, payload, b"RIFF0000WEBPfake")[0]

    return add("Eerste save", "a" * 64, 1200), add("Tweede save", "b" * 64, 2400)
