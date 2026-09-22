#!/usr/bin/env python3
"""
BG3 partyboek -- je savegame lezen zonder het spel te starten.

Upload een `.lsv`, en de app laat de party, de spullen en de questvoortgang
zien op een scherm dat je wel bij de hand hebt. Daarnaast houdt hij vast wat
jij er zelf over weet: wie waar goed in is, welk item je bewaart voor later.
Die notities zitten niet aan een save vast, dus ze overleven elke upload.
"""

import urllib.parse

from fasthtml.common import (
    A, B, Button, Details, Div, Form, H2, H3, Img, Input, Label, Li, NotStr,
    Option, P, Select, Span, Summary, Table, Tbody, Td, Th, Thead,
    Tr, Ul, fast_app,
)
from starlette.datastructures import UploadFile
from starlette.responses import (
    FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response,
)
from starlette.staticfiles import StaticFiles

from . import db, ingest, ui
from .config import (
    APP_PORT, MAX_SAVE_BYTES, MAX_STATS_BYTES, STATIC_DIR, USER_HEADER,
    session_secret,
)
from .ui import bar, empty, kv, note_form, note_readout, num, page, tag

app, rt = fast_app(
    pico=False,
    live=False,
    default_hdrs=False,
    secret_key=session_secret(),
    hdrs=(
        NotStr('<meta charset="utf-8">'),
        NotStr('<meta name="viewport" content="width=device-width, '
               'initial-scale=1, viewport-fit=cover">'),
        NotStr('<meta name="color-scheme" content="light">'),
        NotStr('<meta name="theme-color" content="#000000">'),
        NotStr('<meta name="apple-mobile-web-app-capable" content="yes">'),
        NotStr('<meta name="apple-mobile-web-app-title" content="BG3">'),
        NotStr('<link rel="manifest" href="/manifest.webmanifest">'),
        NotStr('<link rel="icon" href="/static/icon.svg" type="image/svg+xml">'),
        NotStr('<link rel="apple-touch-icon" href="/static/icon-180.png">'),
        NotStr('<link rel="stylesheet" href="/static/app.css">'),
        NotStr('<script src="/static/register-sw.js" defer></script>'),
    ),
)
# fast_app() zet zelf een route `/{fname:path}.{ext:static}` klaar die
# `FileResponse(f"{static_path}/{fname}.{ext}")` teruggeeft -- zonder te
# controleren of het resultaat nog binnen die map ligt, en met de werkmap als
# standaard. Dat is hier de repo-root. Weg ermee, en serveren doet StaticFiles,
# dat het pad wél normaliseert en buiten de map weigert.
app.routes[:] = [r for r in app.routes
                 if getattr(r, "path", "") != "/{fname:path}.{ext:static}"]
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --------------------------------------------------------------- helpers

def who(req):
    """De naam die Authelia doorgeeft. Buiten de server is die er niet."""
    return req.headers.get(USER_HEADER) or req.headers.get("Remote-User") or ""


def flash(sess, text, ok=True):
    sess["flash"] = [text, ok]


def take_flash(sess):
    return sess.pop("flash", None)


def back_to(url, sess=None, text=None, ok=True):
    if text:
        flash(sess, text, ok)
    return RedirectResponse(url or "/", status_code=303)


def active_save(sess, req):
    """
    Welke momentopname kijk je aan. `?save=3` zet hem, daarna onthoudt de
    sessie het, en zonder keuze is het de nieuwste upload.
    """
    chosen = req.query_params.get("save")
    if chosen and chosen.isdigit() and db.save_meta(int(chosen)):
        sess["save_id"] = int(chosen)
    save_id = sess.get("save_id")
    if not save_id or not db.save_meta(save_id):
        save_id = db.latest_save_id()
        sess["save_id"] = save_id
    return save_id


def need_save(sess, req, title, current):
    """Elke pagina begint hetzelfde: is er überhaupt al een save geüpload."""
    save_id = active_save(sess, req)
    if not save_id:
        return None, None, page(
            title,
            empty("Er staat nog geen savegame in.",
                  "Ga naar Overzicht en upload je eerste .lsv-bestand."),
            current=current, user=who(req), flash=take_flash(sess))
    return save_id, db.save_payload(save_id), None


def save_banner(meta):
    """Een regel die bovenaan elke pagina duidelijk maakt wát je aan het lezen bent."""
    bits = [b for b in (meta["hero_name"], meta["save_name"],
                        meta["current_level"],
                        ingest.seconds_to_hm(meta["play_seconds"]),
                        meta["difficulty"]) if b]
    return " · ".join(str(b) for b in bits)


def quote(value):
    return urllib.parse.quote(str(value), safe="")


def cell(value, label, num=False):
    """
    Eén tabelcel, met het kolomlabel erin verstopt.

    Op een telefoon klapt elke rij uit tot een blokje en komt dat label ervoor
    te staan (zie `.stackable` in app.css). Cellen zonder waarde krijgen
    `empty` en verdwijnen daar helemaal: op een smal scherm is een kolom vol
    streepjes alleen maar ruis, terwijl die op een brede tabel juist nodig is
    om de kolommen uit te lijnen.
    """
    blank = value in (None, "", [])
    classes = " ".join(c for c in ("num" if num else "",
                                   "empty" if blank else "") if c)
    return Td("—" if blank else value, cls=classes or None,
              **{"data-l": label})


# --------------------------------------------------------------- overzicht

@app.get("/")
def overview(sess, req):
    save_id = active_save(sess, req)
    upload = Form(
        H3("Savegame uploaden"),
        P("Op Windows staan ze in %LOCALAPPDATA%\\Larian Studios\\Baldur's "
          "Gate 3\\PlayerProfiles\\Public\\Savegames\\Story.", cls="small muted"),
        Div(
            Div(Label("Savebestand (.lsv)", **{"for": "save"}),
                Input(id="save", name="save", type="file", accept=".lsv",
                      required=True),
                cls="field grow"),
            Div(Label("Naam hoofdpersoon", **{"for": "hoofdpersoon"}),
                Input(id="hoofdpersoon", name="hoofdpersoon", type="text",
                      placeholder="staat niet in de save"),
                cls="field grow"),
            Div(Button("Inlezen", type="submit", cls="primary"), cls="field"),
            cls="inline",
        ),
        method="post", action="/upload", enctype="multipart/form-data",
        cls="card",
    )

    if not save_id:
        return page(
            "Overzicht",
            empty("Nog niets ingelezen.",
                  "Upload een .lsv en je party staat er meteen in."),
            upload, current="/", user=who(req), flash=take_flash(sess))

    meta = db.save_meta(save_id)
    payload = db.save_payload(save_id)
    game = payload.get("game", {})
    party = payload.get("party", [])
    notes = db.notes_for("character")
    hero = meta["hero_name"] or ""

    cards = []
    for index, char in enumerate(party):
        key = ingest.character_key(char)
        note = notes.get(key)
        level = char.get("level") or 0
        cards.append(Div(
            H3(A(ingest.character_label(char, hero),
                 href="/personage/%s" % quote(key))),
            kv(("Klasse", " / ".join(x for x in (char.get("class"),
                                                 char.get("subclass")) if x)),
               ("Ras", char.get("race")),
               ("Level", level),
               ("Spullen", char.get("item_count")),
               ("Statussen", len(char.get("statuses") or []) or None)),
            bar(level / 12.0, "level %s van 12" % level),
            note_readout(note) or P("Nog geen notitie.", cls="muted small"),
            cls="card",
        ))

    summary = Div(
        Div(H3("Deze save"),
            kv(("Savenaam", meta["save_name"]),
               ("Hoofdpersoon", hero or "onbekend"),
               ("Waar", meta["current_level"]),
               ("Speeltijd", ingest.seconds_to_hm(meta["play_seconds"])),
               ("Moeilijkheid", meta["difficulty"]),
               ("Versie", meta["game_version"]),
               ("Mods", ", ".join(game.get("mods") or []) or "geen"),
               ("Ingelezen op", ui.stamp(meta["uploaded_at"]))),
            cls="card"),
        Div(H3("Waar je staat"),
            kv(("Party", "%d personages" % (meta["party_size"] or 0)),
               ("Spullen", "%s voorwerpen" % num(meta["item_count"])),
               ("Quests bezig", meta["quests_open"]),
               ("Quests afgerond", meta["quests_done"]),
               ("Hoogste XP", num(meta["xp_total"]))),
            P(A("Alles vergelijken →", href="/party"), cls="small"),
            P(A("Spullen doorzoeken →", href="/spullen"), cls="small"),
            cls="card"),
        Div(H3("Screenshot uit de save"),
            Img(src="/screenshot/%d" % save_id, alt="screenshot", cls="shot",
                loading="lazy")
            if db.save_screenshot(save_id)
            else P("Deze save bevat er geen.", cls="muted"),
            cls="card"),
        cls="grid",
    )

    return page(
        "Overzicht", summary, H2("Party"), Div(*cards, cls="grid"),
        H2("Nieuwe save inlezen"), upload,
        current="/", user=who(req), flash=take_flash(sess),
        subtitle=save_banner(meta))


@app.post("/upload")
async def upload(sess, save: UploadFile, hoofdpersoon: str = ""):
    raw = await save.read()
    if not raw:
        return back_to("/", sess, "Leeg bestand ontvangen.", False)
    if len(raw) > MAX_SAVE_BYTES:
        return back_to("/", sess, "Bestand is groter dan %d MB."
                       % (MAX_SAVE_BYTES // (1024 * 1024)), False)
    try:
        summary, payload, screenshot = ingest.parse_upload(
            raw, save.filename or "save.lsv", hoofdpersoon)
    except ingest.BadSave as exc:
        return back_to("/", sess, "Kon dit niet lezen — %s" % exc, False)

    save_id, created = db.insert_save(summary, payload, screenshot)
    sess["save_id"] = save_id
    if not created:
        return back_to("/", sess, "Deze save stond er al in; ik kijk er nu naar.")
    return back_to("/", sess, "Ingelezen: <b>%s</b> — %d personages, %s spullen."
                   % (summary["save_name"] or summary["filename"],
                      summary["party_size"], num(summary["item_count"])))


@app.get("/screenshot/{save_id}")
def screenshot(save_id: int):
    blob = db.save_screenshot(save_id)
    if not blob:
        return Response(status_code=404)
    kind = "image/webp" if bytes(blob[:4]) == b"RIFF" else "image/png"
    return Response(bytes(blob), media_type=kind,
                    headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------ party

@app.get("/party")
def party(sess, req):
    save_id, payload, missing = need_save(sess, req, "Party", "/party")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    hero = meta["hero_name"] or ""
    members = payload.get("party", [])
    notes = db.notes_for("character")

    rows = [
        ("Ras", lambda c: c.get("race")),
        ("Klasse", lambda c: c.get("class")),
        ("Subklasse", lambda c: c.get("subclass")),
        ("Level", lambda c: c.get("level")),
        ("XP totaal", lambda c: num(c.get("xp_total"))),
        ("Spullen", lambda c: c.get("item_count")),
        ("Statussen", lambda c: len(c.get("statuses") or [])),
        ("Sterk in", lambda c: _note_field(notes, c, "strong")),
        ("Zwak in", lambda c: _note_field(notes, c, "weak")),
        ("Rol", lambda c: _note_field(notes, c, "label")),
    ]
    table = Table(
        Thead(Tr(Th("Kenmerk"),
                 *[Th(A(ingest.character_label(c, hero),
                        href="/personage/%s" % quote(ingest.character_key(c))))
                   for c in members])),
        Tbody(*[Tr(Th(label), *[Td(fn(c) or "—") for c in members])
                for label, fn in rows]),
    )

    others = payload.get("other_playable_characters") or []
    kamp = Details(
        Summary("Speelbare personages buiten de party (%d)" % len(others)),
        Table(
            Thead(Tr(Th("Template"), Th("Waar"), Th("Spullen", cls="num"))),
            Tbody(*[Tr(cell(ingest.prettify(o.get("template_id")), "Template"),
                       cell(o.get("level_name"), "Waar"),
                       cell(o.get("item_count"), "Spullen", num=True))
                    for o in others]),
            cls="stackable",
        ) if others else P("Geen gevonden.", cls="muted"),
        cls="card",
    )

    caveat = Div(
        H3("Wat hier niet staat, en waarom"),
        Ul(*[Li(x) for x in payload.get("not_stored_in_save", [])]),
        P("Die waarden zitten in een deel van de save dat publiek nog niet "
          "ontcijferd is. Ze worden hier dus niet geraden. Wat je er zelf van "
          "weet kun je per personage opschrijven.", cls="small muted"),
        cls="card noprint",
    )

    return page("Party", Div(table, cls="scroll card"), kamp, caveat,
                current="/party", user=who(req), flash=take_flash(sess),
                subtitle=save_banner(meta))


def _quest_note(note):
    """De eerste regel van wat je over deze quest opschreef, als teaser."""
    if not note:
        return None
    if note["label"]:
        return note["label"]
    lines = [l for l in (note["body"] or "").splitlines() if l.strip()]
    return lines[0] if lines else None


def _note_field(notes, char, field):
    note = notes.get(ingest.character_key(char))
    return (note[field] if note else "") or ""


@app.get("/personage/{key}")
def character(sess, req, key: str):
    save_id, payload, missing = need_save(sess, req, "Personage", "/party")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    hero = meta["hero_name"] or ""
    char = next((c for c in payload.get("party", [])
                 if ingest.character_key(c) == key), None)
    if char is None:
        return page("Onbekend personage",
                    empty("Dit personage zit niet in deze save.",
                          "Misschien staat het in een andere momentopname."),
                    current="/party", user=who(req))

    name = ingest.character_label(char, hero)
    groups = char.get("items_by_group") or {}
    item_notes = db.notes_for("item")

    def item_link(stats_name):
        note = item_notes.get(stats_name)
        return Li(A(ingest.prettify(stats_name), href="/spul/%s" % quote(stats_name)),
                  " ", tag(note["tag"], fill=True) if note and note["tag"] else None,
                  " ", Span(note["label"], cls="small muted")
                  if note and note["label"] else None)

    inventory = [Div(H3("%s (%d)" % (group, len(names))),
                     Ul(*[item_link(n) for n in names]), cls="card")
                 for group, names in sorted(groups.items())]

    statuses = char.get("statuses") or []
    facts = Div(
        Div(H3("Uit de save"),
            kv(("Origin", char.get("origin")),
               ("Ras", char.get("race")),
               ("Klasse", char.get("class")),
               ("Subklasse", char.get("subclass")),
               ("Level", char.get("level")),
               ("XP totaal", num(char.get("xp_total"))),
               ("XP dit level", num(char.get("xp_this_level"))),
               ("Waar", char.get("level_name")),
               ("Template", Span(char.get("template_id") or "", cls="mono")),
               ("Spullen", char.get("item_count"))),
            cls="card"),
        Div(H3("Actieve statussen (%d)" % len(statuses)),
            Ul(*[Li(Span(s, cls="mono")) for s in statuses]) if statuses
            else P("Geen.", cls="muted"),
            cls="card"),
        cls="grid",
    )

    return page(
        name, facts,
        note_form("character", key, db.get_note("character", key),
                  back="/personage/%s" % quote(key), with_strengths=True,
                  title="Wat jij over %s weet" % name),
        H2("Spullen (%d)" % (char.get("item_count") or 0)),
        Div(*inventory, cls="grid") if inventory
        else P("Niets gevonden bij dit personage.", cls="muted"),
        current="/party", user=who(req), flash=take_flash(sess),
        subtitle=save_banner(meta))


# ---------------------------------------------------------------- spullen

TEXT_SORTS = {
    "naam": lambda i: (i["name"] or "").lower(),
    "groep": lambda i: (i["group"] or "", (i["name"] or "").lower()),
    "eigenaar": lambda i: (", ".join(i["owners"]), (i["name"] or "").lower()),
    "plan": lambda i: (i["tag"] or "zzz", (i["name"] or "").lower()),
}
NUMERIC_SORTS = {"schade": "avg", "ac": "ac", "gewicht": "weight",
                 "prijs": "price"}
SORTS = tuple(TEXT_SORTS) + tuple(NUMERIC_SORTS)


def sort_items(rows, sort, desc):
    """
    Sorteer de itemlijst, met lege waarden altijd onderaan -- ook als je
    omdraait.

    Daarom draait een getalkolom niet met `reverse=True` maar door het getal
    van teken te wisselen. Met `reverse` zou de vlag "deze heeft geen waarde"
    mee omklappen, en dan staan precies de rijen waar niets van bekend is
    bovenaan, terwijl je juist naar de hoogste schade zocht.
    """
    if sort in NUMERIC_SORTS:
        field = NUMERIC_SORTS[sort]
        sign = -1 if desc else 1
        return sorted(rows, key=lambda i: (i[field] is None,
                                           sign * (i[field] or 0),
                                           (i["name"] or "").lower()))
    key = TEXT_SORTS.get(sort, TEXT_SORTS["groep"])
    return sorted(rows, key=key, reverse=desc)


@app.get("/spullen")
def items(sess, req):
    save_id, payload, missing = need_save(sess, req, "Spullen", "/spullen")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    rows, info = ingest.item_rows(payload)

    q = (req.query_params.get("q") or "").strip()
    owner = req.query_params.get("eigenaar") or ""
    group = req.query_params.get("groep") or ""
    plan = req.query_params.get("plan") or ""
    sort = req.query_params.get("sort") or "groep"
    desc = req.query_params.get("richting") == "af"

    shown = rows
    if q:
        needle = q.lower()
        shown = [i for i in shown
                 if needle in (i["name"] or "").lower()
                 or needle in i["id"].lower()
                 or needle in (i["note"] or "").lower()
                 or needle in (i["label"] or "").lower()]
    if owner:
        shown = [i for i in shown if owner in i["owners"]]
    if group:
        shown = [i for i in shown if i["group"] == group]
    if plan:
        shown = [i for i in shown if (i["tag"] or "") == plan]
    if sort not in SORTS:
        sort = "groep"
    shown = sort_items(shown, sort, desc)

    def header(label, key, numeric=False):
        flip = "af" if (sort == key and not desc) else "op"
        params = dict(req.query_params)
        params.update({"sort": key, "richting": flip})
        arrow = "" if sort != key else (" ▾" if desc else " ▴")
        return Th(A(label + arrow, href="/spullen?" + urllib.parse.urlencode(params)),
                  cls="num" if numeric else None)

    controls = Form(
        Div(
            Div(Label("Zoeken", **{"for": "q"}),
                Input(id="q", name="q", type="search", value=q,
                      placeholder="naam, interne id of je eigen notitie"),
                cls="field grow"),
            Div(Label("Eigenaar", **{"for": "eigenaar"}),
                Select(Option("alle", value=""),
                       *[Option(o, value=o, selected=(o == owner))
                         for o in info["owners"]],
                       id="eigenaar", name="eigenaar"),
                cls="field"),
            Div(Label("Soort", **{"for": "groep"}),
                Select(Option("alle", value=""),
                       *[Option(g, value=g, selected=(g == group))
                         for g in info["groups"]],
                       id="groep", name="groep"),
                cls="field"),
            Div(Label("Plan", **{"for": "plan"}),
                Select(Option("alle", value=""),
                       *[Option(t, value=t, selected=(t == plan))
                         for t in db.TAGS if t],
                       id="plan", name="plan"),
                cls="field"),
            Div(Button("Filteren", type="submit"), cls="field"),
            Div(A("Wissen", href="/spullen", cls="btn"), cls="field"),
            cls="inline",
        ),
        Input(type="hidden", name="sort", value=sort),
        Input(type="hidden", name="richting", value="af" if desc else "op"),
        method="get", action="/spullen", cls="card noprint",
    )

    table = Table(
        Thead(Tr(header("Naam", "naam"), header("Soort", "groep"),
                 header("Eigenaar", "eigenaar"),
                 header("Schade", "schade", True), header("AC", "ac", True),
                 header("Gewicht", "gewicht", True),
                 header("Prijs", "prijs", True), header("Plan", "plan"))),
        Tbody(*[Tr(
            cell(Div(A(i["name"], href="/spul/%s" % quote(i["id"])),
                     " ", tag("wiki ≈", warn=True)
                     if i["match"] == "deelnaam" else None,
                     Div(i["label"], cls="small muted") if i["label"] else None),
                 "Naam"),
            cell(i["group"], "Soort"),
            cell(", ".join(i["owners"]), "Eigenaar"),
            cell(_damage(i), "Schade", num=True),
            cell(ui.num(i["ac"]) if i["ac"] is not None else None, "AC", num=True),
            cell(ui.num(i["weight"], 2) if i["weight"] is not None else None,
                 "Gewicht", num=True),
            cell(ui.num(i["price"]) if i["price"] is not None else None,
                 "Prijs", num=True),
            cell(tag(i["tag"], fill=True) if i["tag"] else None, "Plan"),
        ) for i in shown]),
        cls="stackable",
    )

    sources = P(
        "%d van %d voorwerpen. Gegevens: %d uit de spelbestanden, %d van "
        "bg3.wiki, %d zonder extra gegevens. Een rij met "
        % (len(shown), len(rows), info["with_pak"], info["with_wiki"],
           info["no_data"]),
        tag("wiki ≈", warn=True),
        " is op een deel van de naam gekoppeld — controleer die voordat je "
        "erop afgaat.", cls="small muted")

    return page("Spullen", controls, sources, Div(table, cls="scroll"),
                current="/spullen", user=who(req), flash=take_flash(sess),
                subtitle=save_banner(meta))


def _damage(item):
    if item["avg"] is None:
        return item["damage"]
    return "%s (%s)" % (item["damage"], num(item["avg"], 1))


@app.get("/spul/{name}")
def item_detail(sess, req, name: str):
    save_id, payload, missing = need_save(sess, req, "Voorwerp", "/spullen")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    rows, _ = ingest.item_rows(payload)
    item = next((i for i in rows if i["id"] == name), None)
    if item is None:
        return page("Onbekend voorwerp",
                    empty("Dit voorwerp zit niet in deze save."),
                    current="/spullen", user=who(req))

    facts = Div(
        Div(H3("Cijfers"),
            kv(("Soort", item["group"]),
               ("Categorie", item["category"]),
               ("Zeldzaamheid", item["rarity"]),
               ("Schade", _damage(item)),
               ("Schadetype", item["damage_type"]),
               ("Veelzijdig", item["versatile"]),
               ("Bereik", "%s–%s" % (item["min"], item["max"])
                if item["min"] is not None else None),
               ("Armour class", item["ac"]),
               ("Type wapenrusting", item["armour_type"]),
               ("Slot", item["slot"]),
               ("Handen", item["handedness"]),
               ("Eigenschappen", item["properties"]),
               ("Bekwaamheid", item["proficiency"]),
               ("Gewicht", item["weight"]),
               ("Prijs", item["price"])),
            cls="card"),
        Div(H3("Herkomst"),
            kv(("Interne naam", Span(item["id"], cls="mono")),
               ("In bezit van", ", ".join(item["owners"])),
               ("Bronnen", ", ".join(item["sources"]) or "alleen de save"),
               ("Wiki-koppeling", {"uid": "exact (uid)", "naam": "op naam",
                                   "deelnaam": "op deel van de naam — onzeker"}
                .get(item["match"]))),
            P(item["where"], cls="small") if item["where"] else None,
            cls="card"),
        cls="grid",
    )
    special = Div(H3("Bijzonder"), P(item["special"]), cls="card") \
        if item["special"] else None

    return page(
        item["name"], facts, special,
        note_form("item", name, db.get_note("item", name),
                  back="/spul/%s" % quote(name), with_tag=True,
                  title="Wat jij met dit voorwerp wilt"),
        P(A("← terug naar alle spullen", href="/spullen")),
        current="/spullen", user=who(req), flash=take_flash(sess),
        subtitle=save_banner(meta))


# ----------------------------------------------------------------- quests

@app.get("/quests")
def quests(sess, req):
    save_id, payload, missing = need_save(sess, req, "Quests", "/quests")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    quest_data = payload.get("quests", {})
    notes = db.notes_for("quest")

    def block(title, ids, hint):
        if not ids:
            return Div(H3(title), P(hint, cls="muted"), cls="card")
        return Div(
            H3("%s (%d)" % (title, len(ids))),
            Table(
                Thead(Tr(Th("Quest"), Th("Jouw aantekening"), Th("Interne id"))),
                Tbody(*[Tr(
                    cell(A(ingest.prettify(qid), href="/quest/%s" % quote(qid)),
                         "Quest"),
                    cell(_quest_note(notes.get(qid)), "Aantekening"),
                    cell(Span(qid, cls="mono"), "Id"),
                ) for qid in ids]),
                cls="stackable",
            ),
            cls="card",
        )

    caveat = P(
        "BG3 bewaart alleen de interne id van een quest, niet de titel uit je "
        "journaal. De naam hierboven is die id leesbaarder gemaakt. Wat de "
        "quest werkelijk heet en waar je gebleven was, kun je er zelf bij "
        "zetten.", cls="small muted")

    return page(
        "Quests",
        block("Bezig", quest_data.get("in_progress") or [],
              "Geen lopende quests gevonden."),
        block("Afgerond", quest_data.get("completed") or [],
              "Nog niets afgerond."),
        caveat,
        current="/quests", user=who(req), flash=take_flash(sess),
        subtitle=save_banner(meta))


@app.get("/quest/{qid}")
def quest_detail(sess, req, qid: str):
    save_id, payload, missing = need_save(sess, req, "Quest", "/quests")
    if missing:
        return missing
    meta = db.save_meta(save_id)
    quest_data = payload.get("quests", {})
    state = ("afgerond" if qid in (quest_data.get("completed") or [])
             else "bezig" if qid in (quest_data.get("in_progress") or [])
             else "komt in deze save niet voor")
    return page(
        ingest.prettify(qid),
        Div(kv(("Status", state), ("Interne id", Span(qid, cls="mono"))),
            cls="card"),
        note_form("quest", qid, db.get_note("quest", qid),
                  back="/quest/%s" % quote(qid),
                  title="Wat jij over deze quest weet"),
        P(A("← terug naar alle quests", href="/quests")),
        current="/quests", user=who(req), flash=take_flash(sess),
        subtitle=save_banner(meta))


# --------------------------------------------------------------- notities

@app.post("/notitie/{kind}/{subject}")
def write_note(sess, kind: str, subject: str, label: str = "", body: str = "",
               strong: str = "", weak: str = "", tag: str = "",
               terug: str = ""):
    if kind not in db.KINDS:
        return back_to("/notities", sess, "Onbekende notitiesoort.", False)
    if tag and tag not in db.TAGS:
        tag = ""
    db.save_note(kind, subject, label=label, body=body, strong=strong,
                 weak=weak, tag=tag)
    return back_to(terug or "/notities", sess, "Opgeslagen.")


@app.get("/notities")
def notes_page(sess, req):
    rows = db.all_notes()
    titles = {"character": "Personages", "item": "Voorwerpen",
              "quest": "Quests", "general": "Los"}
    links = {"character": "/personage/%s", "item": "/spul/%s",
             "quest": "/quest/%s", "general": "/notities"}

    blocks = []
    for kind, title in titles.items():
        mine = [r for r in rows if r["kind"] == kind]
        if not mine:
            continue
        blocks.append(Div(
            H3("%s (%d)" % (title, len(mine))),
            *[Div(P(B(A(ingest.prettify(r["subject"]),
                        href=links[kind] % quote(r["subject"])))),
                  note_readout(r),
                  P(Span(ui.stamp(r["updated_at"]), cls="small muted")),
                  style="border-top:1px dotted #bbb;padding-top:8px")
              for r in mine],
            cls="card"))

    if not blocks:
        blocks = [empty("Nog geen notities.",
                        "Open een personage, voorwerp of quest en schrijf op "
                        "wat je wilt onthouden. Notities horen bij het ding, "
                        "niet bij de save, dus ze blijven staan als je een "
                        "nieuwe savegame uploadt.")]

    return page("Mijn notities", *blocks,
                subtitle="Losgekoppeld van de savegames — deze blijven staan.",
                current="/notities", user=who(req), flash=take_flash(sess))


# ------------------------------------------------------------------ saves

@app.get("/saves")
def saves(sess, req):
    active_save(sess, req)
    rows = db.list_saves()
    if not rows:
        return page("Saves", empty("Nog niets ingelezen."),
                    current="/saves", user=who(req), flash=take_flash(sess))

    current = sess.get("save_id")
    table = Table(
        Thead(Tr(Th("Ingelezen"), Th("Save"), Th("Waar"), Th("Speeltijd"),
                 Th("Level", cls="num"), Th("XP", cls="num"),
                 Th("Spullen", cls="num"), Th("Quests"), Th(""))),
        Tbody(*[Tr(
            cell(ui.stamp(r["uploaded_at"]), "Ingelezen"),
            cell(Div(B(r["save_name"] or r["filename"]) if r["id"] == current
                     else (r["save_name"] or r["filename"]),
                     Div(r["hero_name"], cls="small muted")
                     if r["hero_name"] else None), "Save"),
            cell(r["current_level"], "Waar"),
            cell(ingest.seconds_to_hm(r["play_seconds"]), "Speeltijd"),
            cell(r["max_level"], "Level", num=True),
            cell(num(r["xp_total"]), "XP", num=True),
            cell(num(r["item_count"]), "Spullen", num=True),
            cell("%s bezig · %s af" % (r["quests_open"], r["quests_done"]),
                 "Quests"),
            cell(Div(A("Bekijken", href="/?save=%d" % r["id"], cls="btn small")
                     if r["id"] != current else Span("in beeld", cls="tag fill"),
                     " ",
                     Form(Button("Wissen", type="submit", cls="small danger"),
                          method="post",
                          action="/saves/%d/wissen" % r["id"],
                          style="display:inline")), "Actie"),
        ) for r in rows]),
        cls="stackable",
    )

    return page("Saves", Div(_progress(rows), cls="card"),
                Div(table, cls="scroll"),
                P("Elke upload blijft staan als momentopname. Wissen verwijdert "
                  "alleen die ene; je notities raakt het niet.",
                  cls="small muted"),
                current="/saves", user=who(req), flash=take_flash(sess))


def _progress(rows):
    """
    XP-verloop over de momentopnamen. Eén regel SVG, geen bibliotheek: op
    e-ink is een simpele lijn leesbaarder dan welk chartframework ook, en
    offline werkt hij ook.
    """
    points = [(r["uploaded_at"], r["xp_total"] or 0) for r in reversed(rows)]
    if len(points) < 2:
        return P("Na een tweede upload verschijnt hier je XP-verloop.",
                 cls="muted small")
    top = max(v for _, v in points) or 1
    width, height, pad = 640, 120, 8
    step = (width - 2 * pad) / (len(points) - 1)
    coords = " ".join(
        "%.1f,%.1f" % (pad + i * step,
                       height - pad - (v / top) * (height - 2 * pad))
        for i, (_, v) in enumerate(points))
    svg = (
        '<svg class="spark" viewBox="0 0 %d %d" role="img" '
        'aria-label="XP-verloop over de ingelezen saves">'
        '<polyline points="%s" fill="none" stroke="#000" stroke-width="2"/>'
        '%s</svg>'
    ) % (width, height, coords,
         "".join('<circle cx="%s" cy="%s" r="3" fill="#000"/>'
                 % tuple(c.split(",")) for c in coords.split()))
    return Div(H3("XP-verloop"), NotStr(svg),
               P("Oudste upload links, nieuwste rechts. Hoogste punt: %s XP."
                 % num(top), cls="small muted"))


@app.post("/saves/{save_id}/wissen")
def drop_save(sess, save_id: int):
    db.delete_save(save_id)
    if sess.get("save_id") == save_id:
        sess["save_id"] = db.latest_save_id()
    return back_to("/saves", sess, "Momentopname verwijderd.")


@app.get("/party.json")
def download(sess, req):
    """De ruwe, complete uitlezing — zelfde bestand als de CLI maakt."""
    save_id = active_save(sess, req)
    payload = db.save_payload(save_id) if save_id else None
    if not payload:
        return JSONResponse({"error": "geen save geselecteerd"}, status_code=404)
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="party.json"'})


# ------------------------------------------------------------ instellingen

@app.get("/instellingen")
def settings(sess, req):
    wiki = db.blob_info(ingest.WIKI_KEY)
    stats = db.blob_info(ingest.STATS_KEY)

    wiki_card = Div(
        H3("bg3.wiki"),
        P("Leesbare namen, zeldzaamheid, prijzen en vindplaatsen. De server "
          "haalt de tabellen weapons en equipment op en bewaart ze; dat duurt "
          "een halve minuut en gebeurt alleen als je erom vraagt.",
          cls="small muted"),
        kv(("Opgehaald", ui.stamp(wiki["fetched_at"]) if wiki else None),
           ("Inhoud", wiki["note"] if wiki else "nog niets opgehaald")),
        Div(
            Form(Button("Nu ophalen" if not wiki else "Opnieuw ophalen",
                        type="submit", cls="primary"),
                 method="post", action="/instellingen/wiki",
                 style="display:inline"),
            " ",
            Form(Button("Diagnose", type="submit"),
                 method="post", action="/instellingen/wiki/diagnose",
                 style="display:inline"),
            cls="inline"),
        P("Lukt ophalen niet, dan laat Diagnose zien wat bg3.wiki zélf "
          "antwoordt -- bestaat de tabel nog, bestaan de velden nog.",
          cls="small muted"),
        P("Wiki-inhoud staat onder CC BY-NC-SA 4.0 of CC BY-SA 4.0.",
          cls="small muted"),
        cls="card",
    )

    stats_card = Div(
        H3("Itemstats uit de spelbestanden"),
        P("Schade, armour class en gewicht staan in de .pak-bestanden van het "
          "spel, en het spel staat niet op deze server. Exporteer ze één keer "
          "op je PC en upload het resultaat; daarna gebruikt elke nieuwe save "
          "die cijfers.", cls="small muted"),
        P(Span('uv run bg3_stats.py "<pad>/Data" -o stats.json --slim',
               cls="mono")),
        kv(("Geüpload", ui.stamp(stats["fetched_at"]) if stats else None),
           ("Inhoud", stats["note"] if stats else "nog niets geüpload")),
        Form(Div(Div(Input(name="stats", type="file", accept=".json",
                           required=True), cls="field grow"),
                 Div(Button("Uploaden", type="submit", cls="primary"),
                     cls="field"),
                 cls="inline"),
             method="post", action="/instellingen/stats",
             enctype="multipart/form-data"),
        Form(Button("Verwijderen", type="submit", cls="small danger"),
             method="post", action="/instellingen/stats/wissen",
             style="margin-top:8px") if stats else None,
        P("Let op: bestaande momentopnamen worden niet met terugwerkende "
          "kracht verrijkt — lees die save opnieuw in als je de cijfers er "
          "ook bij wilt.", cls="small muted"),
        cls="card",
    )

    about = Div(
        H3("Over deze app"),
        P("Dezelfde parsers als de CLI in deze repo: bg3_lsv, bg3_sheet, "
          "bg3_stats, bg3_compare en bg3_wiki. Wat de CLI kan, kan deze "
          "pagina ook; wat de save niet bevat, blijft leeg."),
        Ul(Li(A("De complete uitlezing als party.json", href="/party.json")),
           Li("Je savebestanden worden niet bewaard — alleen de uitgelezen "
              "inhoud en de screenshot uit de save."),
           Li("Notities horen bij een personage, voorwerp of quest, niet bij "
              "een save, en blijven dus staan.")),
        cls="card",
    )

    return page("Instellingen", Div(wiki_card, stats_card, cls="grid"), about,
                current="/instellingen", user=who(req), flash=take_flash(sess))


@app.post("/instellingen/wiki")
def fetch_wiki(sess):
    try:
        total, failed = ingest.refresh_wiki()
    except ingest.WikiFailed as exc:
        return back_to("/instellingen", sess,
                       "Ophalen bij bg3.wiki mislukt — %s" % exc, False)
    if failed:
        return back_to("/instellingen", sess,
                       "Deels gelukt: %s rijen opgehaald. Niet gelukt: %s"
                       % (num(total), "; ".join(failed)), False)
    return back_to("/instellingen", sess,
                   "Opgehaald: %s rijen van bg3.wiki." % num(total))


@app.post("/instellingen/wiki/diagnose")
def diagnose_wiki(sess, req):
    """
    Laat zien wat bg3.wiki letterlijk terugstuurt.

    Geen redirect met een flashmelding: de uitkomst is een paar regels die je
    wilt kunnen lezen, kopiëren en doorsturen, niet iets dat verdwijnt bij de
    volgende klik.
    """
    rows = ingest.diagnose_wiki()
    table = Table(
        Thead(Tr(Th("Vraag"), Th("Uitkomst"))),
        Tbody(*[Tr(cell(label, "Vraag"),
                   cell(Span(("ok — " if good else "MISLUKT — ") + text,
                             cls="mono"), "Uitkomst"))
                for label, good, text in rows]),
        cls="stackable",
    )
    hint = P(
        "De eerste regel die mislukt wijst de laag aan. Faalt de bovenste, "
        "dan komt de server niet bij bg3.wiki. Werkt die wel maar faalt "
        "\"bestaat de tabel\", dan is de tabel hernoemd of weg. Werkt die "
        "ook en faalt alleen de veldenset, dan zijn de kolommen veranderd.",
        cls="small muted")

    return page("Diagnose bg3.wiki", Div(table, cls="scroll card"), hint,
                P(A("← terug naar instellingen", href="/instellingen")),
                current="/instellingen", user=who(req))


@app.post("/instellingen/stats")
async def upload_stats(sess, stats: UploadFile):
    raw = await stats.read()
    if len(raw) > MAX_STATS_BYTES:
        return back_to("/instellingen", sess, "Bestand is te groot.", False)
    try:
        total = ingest.store_stats_export(raw, stats.filename or "stats.json")
    except ingest.BadSave as exc:
        return back_to("/instellingen", sess, "Kon dit niet lezen — %s" % exc,
                       False)
    return back_to("/instellingen", sess, "Itemstats opgeslagen: %d entries." % total)


@app.post("/instellingen/stats/wissen")
def drop_stats(sess):
    db.drop_blob(ingest.STATS_KEY)
    return back_to("/instellingen", sess, "Itemstats verwijderd.")


# --------------------------------------------------------------------- pwa

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest",
                        media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    """
    Moet vanaf de root geserveerd worden, anders mag hij alleen /static
    beheren en werkt offline lezen niet voor de echte pagina's.
    """
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


@app.get("/offline")
def offline(req):
    return page("Geen verbinding",
                empty("Deze pagina staat niet in de offlinecache.",
                      "Pagina's die je eerder hebt bekeken blijven wel "
                      "leesbaar zonder verbinding."),
                current="/", user="")


@app.get("/gezond")
def health():
    """Voor de deploy: bewijst dat het proces echt antwoordt."""
    return PlainTextResponse("ok")


if __name__ == "__main__":
    # Bewust uvicorn rechtstreeks, niet fasthtml's `serve()`. Die leest de
    # poort uit de omgevingsvariabele `PORT` en alleen als het argument leeg
    # is, terwijl deze server `APP_PORT` gebruikt; en hij zet standaard de
    # herlaadmodus aan, die een bestandswachter als productieproces draait.
    # Beide vallen stil op precies de manier die je niet ziet: een gezonde
    # container op de verkeerde poort, en een 502 zonder traceback.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=APP_PORT, log_level="info",
                proxy_headers=True, forwarded_allow_ips="*")
