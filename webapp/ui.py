"""Gedeelde bouwstenen: de paginarand, tabellen, notitieformulieren."""

from fasthtml.common import (
    A, B, Button, Div, Dd, Dl, Dt, Footer, Form, H1, H3, Header, I, Input,
    Label, Nav, NotStr, Option, P, Select, Span, Textarea, Title,
)

from . import db

# Een mannetje van streepjes, met een d20 in de hand. Inline en niet als
# bestand, want het is dertig tekens en het hoort bij de rand van de pagina.
# stroke-linecap rond, want xkcd-lijnen zijn met een stift getrokken.
STICK = NotStr(
    '<svg class="stick" width="26" height="34" viewBox="0 0 26 34" '
    'aria-hidden="true" fill="none" stroke="#000" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="11" cy="6" r="5"/>'
    '<path d="M11 11v11"/>'
    '<path d="M11 14l-6 5M11 14l7 3"/>'
    '<path d="M11 22l-5 10M11 22l5 10"/>'
    '<path d="M18 17l3-2 3 2-1 3.5h-4z"/>'   # d20 in de opgestoken hand
    '</svg>'
)

NAV = [
    ("/", "Overzicht"),
    ("/party", "Party"),
    ("/spullen", "Spullen"),
    ("/quests", "Quests"),
    ("/notities", "Notities"),
    ("/saves", "Saves"),
    ("/instellingen", "Instellingen"),
]


def page(title, *content, current="/", user=None, flash=None, subtitle=None):
    """De hele pagina. Eén plek voor de rand, zodat elke route kort blijft."""
    head = Header(
        Div(
            Div(STICK, B("BG3"), Span("partyboek", cls="muted"),
                Span(user or "", cls="who"), cls="brand"),
            Nav(*[A(label, href=href,
                    **({"aria-current": "page"} if href == current else {}))
                  for href, label in NAV]),
            cls="wrap",
        ),
        cls="top",
    )
    body = [H1(title)]
    if subtitle:
        body.append(P(subtitle, cls="deck"))
    if flash:
        text, ok = flash
        body.append(P(NotStr(text), cls="flash" if ok else "flash bad"))
    body.extend(content)
    body.append(Footer(
        P("Alles op deze pagina komt uit je eigen savegames en je eigen "
          "notities. Wat niet in een save staat, verzint deze app niet.",
          cls="small muted"),
    ))
    return Title("%s — BG3 partyboek" % title), head, Div(*body, cls="wrap")


# ------------------------------------------------------------- kleinigheden

def stamp(iso):
    """`2026-09-20T17:50:45+00:00` -> `2026-09-20 17:50`. Seconden en tijdzone
    zijn ruis in een regel die alleen zegt: dit heb je toen opgeschreven."""
    return (iso or "")[:16].replace("T", " ")


def kv(*pairs):
    """Een definitielijst, lege waarden overgeslagen."""
    items = []
    for label, value in pairs:
        if value in (None, "", []):
            continue
        items.extend([Dt(label), Dd(value)])
    return Dl(*items, cls="kv") if items else P("—", cls="muted")


def tag(text, fill=False, warn=False):
    cls = "tag" + (" fill" if fill else "") + (" warn" if warn else "")
    return Span(text, cls=cls)


def bar(fraction, label=None):
    """Een balkje van 0..1. Puur zwart-wit, want e-ink kent geen kleurverloop."""
    pct = max(0.0, min(1.0, float(fraction or 0))) * 100
    return Div(Div(I(style="width:%.1f%%" % pct), cls="bar"),
               Span(label, cls="small muted") if label else None)


def num(value, digits=0):
    if value in (None, ""):
        return "—"
    try:
        return ("{:,.%df}" % digits).format(float(value)).replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def empty(text, hint=None):
    return Div(P(text), P(hint, cls="muted small") if hint else None, cls="card")


# ----------------------------------------------------------- notitieformulier

def note_form(kind, subject, note, *, action=None, back=None,
              with_strengths=False, with_tag=False, title="Mijn notitie"):
    """
    Het formulier waarmee je je eigen kennis vastlegt.

    Bewust een gewoon POST-formulier zonder JavaScript: op e-ink is een
    volledige paginaverversing eerlijker dan een halve die je niet ziet
    gebeuren, en zonder netwerk werkt geen enkele slimmigheid toch.
    """
    get = (lambda field: (note[field] if note else "") or "")
    fields = [
        Div(Label("Korte aanduiding", **{"for": "label"}),
            Input(id="label", name="label", type="text", value=get("label"),
                  placeholder="bijv. tank / bewaar voor act 3"),
            cls="field"),
    ]
    if with_tag:
        fields.append(Div(
            Label("Wat wil je ermee", **{"for": "tag"}),
            Select(*[Option(opt or "— geen plan —", value=opt,
                            selected=(opt == get("tag"))) for opt in db.TAGS],
                   id="tag", name="tag"),
            cls="field"))
    if with_strengths:
        fields.extend([
            Div(Label("Sterk in", **{"for": "strong"}),
                Textarea(get("strong"), id="strong", name="strong",
                         placeholder="waar zet je dit personage voor in"),
                cls="field"),
            Div(Label("Zwak in", **{"for": "weak"}),
                Textarea(get("weak"), id="weak", name="weak",
                         placeholder="waar moet je op letten"),
                cls="field"),
        ])
    fields.append(Div(Label("Notitie", **{"for": "body"}),
                      Textarea(get("body"), id="body", name="body"),
                      cls="field"))

    return Form(
        H3(title),
        *fields,
        Div(Button("Opslaan", type="submit", cls="primary"),
            Span("Laatst bijgewerkt: %s" % stamp(note["updated_at"]),
                 cls="small muted") if note else None,
            cls="inline", style="margin-top:12px"),
        Input(type="hidden", name="terug", value=back or ""),
        method="post",
        action=action or "/notitie/%s/%s" % (kind, subject),
        cls="card",
    )


def note_readout(note):
    """Wat je eerder opschreef, compact, voor op een overzichtspagina."""
    if not note:
        return None
    bits = []
    if note["label"]:
        bits.append(P(B(note["label"])))
    if note["strong"]:
        bits.append(P(Span("Sterk: ", cls="muted"), note["strong"]))
    if note["weak"]:
        bits.append(P(Span("Zwak: ", cls="muted"), note["weak"]))
    if note["body"]:
        bits.extend(P(line) for line in note["body"].splitlines() if line.strip())
    if note["tag"]:
        bits.append(P(tag(note["tag"], fill=True)))
    return Div(*bits, cls="stack") if bits else None
