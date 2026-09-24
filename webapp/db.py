"""
SQLite. Een bestand op de datavolume van de server, verder niets.

Twee soorten gegevens, en het verschil ertussen is het hele punt van de app:

* **Uit de save**, in `saves`. Per upload een momentopname, onveranderlijk.
  Een nieuwe save vervangt de oude niet maar komt ernaast, zodat je kunt zien
  hoe de party zich ontwikkelt.
* **Van jezelf**, in `notes`. Losgekoppeld van welke save dan ook, want een
  notitie over Shadowheart gaat over Shadowheart en niet over die ene zondag.
  Daarom hangen notities aan een stabiele sleutel (origin, interne itemnaam,
  quest-id) en overleven ze elke nieuwe upload.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    id            INTEGER PRIMARY KEY,
    sha256        TEXT    NOT NULL UNIQUE,
    filename      TEXT    NOT NULL,
    uploaded_at   TEXT    NOT NULL,
    save_name     TEXT,
    hero_name     TEXT,
    game_version  TEXT,
    difficulty    TEXT,
    current_level TEXT,
    play_seconds  INTEGER,
    game_id       TEXT,
    party_size    INTEGER,
    item_count    INTEGER,
    xp_total      INTEGER,
    max_level     INTEGER,
    quests_open   INTEGER,
    quests_done   INTEGER,
    payload       TEXT    NOT NULL,
    screenshot    BLOB
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    subject    TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL DEFAULT '',
    strong     TEXT NOT NULL DEFAULT '',
    weak       TEXT NOT NULL DEFAULT '',
    tag        TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE (kind, subject)
);

CREATE TABLE IF NOT EXISTS blobs (
    key        TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL
);

-- Wat alleen jij weet en niet leesbaar in de save staat: ability scores,
-- gekozen vaardigheden, expertise, extra bekwaamheden uit feats of items.
-- Aan het personage gehangen, net als notities, zodat het een nieuwe save
-- overleeft. Eén JSON-blok per personage: de vorm verandert vaker dan een
-- tabelschema prettig vindt.
CREATE TABLE IF NOT EXISTS sheets (
    character  TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS notes_kind ON notes (kind);
CREATE INDEX IF NOT EXISTS saves_uploaded ON saves (uploaded_at DESC);
"""

KINDS = ("character", "item", "quest", "general")

# Wat wil je met dit ding. Bewust kort: een lijstje dat je in een half
# seconde overziet terwijl het spel op pauze staat.
TAGS = ("", "gebruiken", "bewaren", "verkopen", "weggeven", "uitzoeken")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_conn = None


def conn():
    """
    Eén verbinding voor het hele proces. WAL zodat een lezende pagina niet
    wacht op een schrijvende, en `check_same_thread=False` omdat uvicorn
    requests over een threadpool verdeelt.
    """
    global _conn
    if _conn is None:
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


# ------------------------------------------------------------------ saves

SAVE_COLUMNS = (
    "id, sha256, filename, uploaded_at, save_name, hero_name, game_version, "
    "difficulty, current_level, play_seconds, game_id, party_size, "
    "item_count, xp_total, max_level, quests_open, quests_done"
)


def insert_save(summary, payload, screenshot):
    """Sla een momentopname op. Dezelfde save twee keer uploaden doet niets."""
    fields = dict(summary)
    fields["payload"] = json.dumps(payload, ensure_ascii=False)
    fields["screenshot"] = screenshot
    fields.setdefault("uploaded_at", now())
    names = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn().execute(
        "INSERT OR IGNORE INTO saves (%s) VALUES (%s)" % (names, marks),
        list(fields.values()),
    )
    conn().commit()
    if cur.lastrowid and cur.rowcount:
        return cur.lastrowid, True
    row = conn().execute("SELECT id FROM saves WHERE sha256 = ?",
                         (fields["sha256"],)).fetchone()
    return (row["id"] if row else None), False


def list_saves():
    return conn().execute(
        "SELECT %s FROM saves ORDER BY uploaded_at DESC, id DESC" % SAVE_COLUMNS
    ).fetchall()


def save_meta(save_id):
    return conn().execute(
        "SELECT %s FROM saves WHERE id = ?" % SAVE_COLUMNS, (save_id,)
    ).fetchone()


def latest_save_id():
    row = conn().execute(
        "SELECT id FROM saves ORDER BY uploaded_at DESC, id DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def save_payload(save_id):
    row = conn().execute("SELECT payload FROM saves WHERE id = ?",
                         (save_id,)).fetchone()
    return json.loads(row["payload"]) if row else None


def save_screenshot(save_id):
    row = conn().execute("SELECT screenshot FROM saves WHERE id = ?",
                         (save_id,)).fetchone()
    return row["screenshot"] if row else None


def delete_save(save_id):
    conn().execute("DELETE FROM saves WHERE id = ?", (save_id,))
    conn().commit()


def rename_save(save_id, hero_name):
    conn().execute("UPDATE saves SET hero_name = ? WHERE id = ?",
                   (hero_name, save_id))
    conn().commit()


# ----------------------------------------------------------------- notes

def get_note(kind, subject):
    return conn().execute(
        "SELECT * FROM notes WHERE kind = ? AND subject = ?", (kind, subject)
    ).fetchone()


def notes_for(kind):
    """Alle notities van één soort, als dict op subject -- scheelt N queries."""
    rows = conn().execute("SELECT * FROM notes WHERE kind = ?", (kind,)).fetchall()
    return {row["subject"]: row for row in rows}


def all_notes():
    return conn().execute(
        "SELECT * FROM notes WHERE label <> '' OR body <> '' OR strong <> '' "
        "OR weak <> '' OR tag <> '' ORDER BY kind, subject"
    ).fetchall()


def save_note(kind, subject, **fields):
    """
    Schrijf een notitie. Alleen de meegegeven velden veranderen, zodat het
    tagknopje in de itemlijst niet stilletjes je tekst leegmaakt.

    Een notitie die helemaal leeg is achtergelaten wordt verwijderd; anders
    vult de lijst 'mijn notities' zich met lege regels van pagina's die je
    alleen maar hebt opengeklapt.
    """
    if kind not in KINDS:
        raise ValueError("onbekende notitiesoort: %s" % kind)
    row = get_note(kind, subject)
    merged = {k: (row[k] if row else "") for k in
              ("label", "body", "strong", "weak", "tag")}
    merged.update({k: (v or "") for k, v in fields.items() if k in merged})

    if not any(v.strip() for v in merged.values()):
        if row:
            conn().execute("DELETE FROM notes WHERE id = ?", (row["id"],))
            conn().commit()
        return None

    conn().execute(
        """INSERT INTO notes (kind, subject, label, body, strong, weak, tag,
                              updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (kind, subject) DO UPDATE SET
               label = excluded.label, body = excluded.body,
               strong = excluded.strong, weak = excluded.weak,
               tag = excluded.tag, updated_at = excluded.updated_at""",
        (kind, subject, merged["label"], merged["body"], merged["strong"],
         merged["weak"], merged["tag"], now()),
    )
    conn().commit()
    return get_note(kind, subject)


# ----------------------------------------------------------------- blobs

def put_blob(key, payload, note=""):
    conn().execute(
        """INSERT INTO blobs (key, fetched_at, note, payload) VALUES (?,?,?,?)
           ON CONFLICT (key) DO UPDATE SET fetched_at = excluded.fetched_at,
               note = excluded.note, payload = excluded.payload""",
        (key, now(), note, json.dumps(payload, ensure_ascii=False)),
    )
    conn().commit()


def get_blob(key):
    row = conn().execute("SELECT * FROM blobs WHERE key = ?", (key,)).fetchone()
    return json.loads(row["payload"]) if row else None


def blob_info(key):
    return conn().execute(
        "SELECT key, fetched_at, note, length(payload) AS size "
        "FROM blobs WHERE key = ?", (key,)
    ).fetchone()


def drop_blob(key):
    conn().execute("DELETE FROM blobs WHERE key = ?", (key,))
    conn().commit()


# ---------------------------------------------------------------- sheets

EMPTY_SHEET = {"scores": {}, "skills": [], "expertise": [], "extra": [],
               "feats": ""}


def get_sheet(character):
    row = conn().execute("SELECT data, updated_at FROM sheets WHERE character = ?",
                         (character,)).fetchone()
    if not row:
        return dict(EMPTY_SHEET, updated_at=None)
    data = dict(EMPTY_SHEET)
    data.update(json.loads(row["data"]))
    data["updated_at"] = row["updated_at"]
    return data


def all_sheets():
    rows = conn().execute("SELECT character, data FROM sheets").fetchall()
    out = {}
    for row in rows:
        data = dict(EMPTY_SHEET)
        data.update(json.loads(row["data"]))
        out[row["character"]] = data
    return out


def save_sheet(character, data):
    clean = {k: data.get(k, EMPTY_SHEET[k]) for k in EMPTY_SHEET}
    conn().execute(
        """INSERT INTO sheets (character, data, updated_at) VALUES (?, ?, ?)
           ON CONFLICT (character) DO UPDATE SET data = excluded.data,
               updated_at = excluded.updated_at""",
        (character, json.dumps(clean, ensure_ascii=False), now()),
    )
    conn().commit()
