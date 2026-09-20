#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["lz4", "zstandard"]
# ///
"""
bg3_compare.py -- interactief vergelijken van de spullen die je zelf hebt.

Bouwt één HTML-pagina met alle items uit je party, met filteren, sorteren en
een vergelijkpaneel waarin je items naast elkaar zet en per rij ziet welke de
beste waarde heeft. Vergelijkbaar met een loadout-vergelijker in Destiny 2,
maar dan voor je BG3-inventaris.

Twee mogelijke gegevensbronnen, los of samen:

  * de spelbestanden zelf (`--stats` bij bg3_sheet.py) — gezaghebbend, want
    dat is precies wat het spel gebruikt, en gekoppeld op interne naam;
  * bg3.wiki via `bg3_wiki.py` — leesbare namen, rarity, prijs, vindplaats en
    beschrijvingen, gekoppeld op uid of op naam.

Elke rij laat zien waar de gegevens vandaan komen en hoe zeker de koppeling
met de wiki is, zodat een benaderende naamkoppeling niet stilletjes als feit
wordt gepresenteerd.
"""

import html
import json
import re

from bg3_stats import damage_range

GROUP_ORDER = ["Wapens", "Wapenrusting", "Unieke voorwerpen", "Drankjes",
               "Perkamentrollen", "Munten en edelstenen",
               "Verbruik en gereedschap", "Overig"]

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def esc(x):
    return html.escape(str("" if x is None else x))


def prettify(stats_name):
    body = re.sub(r"^(WPN|ARM|OBJ|CONS|UNI|MAG|LOOT|COL|PUZ|BOOK|TOOL)_", "",
                  stats_name)
    return _CAMEL.sub(" ", body.replace("_", " ")).strip()


def _number(value):
    """Haal het eerste getal uit een waarde als "1.35" of "13 AC". None als het niet lukt."""
    if value is None:
        return None
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    return float(m.group(0).replace(",", ".")) if m else None


def build_items(data, wiki_cache=None):
    """Zet party.json (plus eventueel een wiki-cache) om in vergelijkbare rijen."""
    item_stats = data.get("item_stats", {})

    owners, groups = {}, {}
    for c in data.get("party", []):
        label = c["origin"] if c.get("origin") not in (None, "Generic") \
            else "Hoofdpersoon"
        for group, names in c.get("items_by_group", {}).items():
            for name in names:
                owners.setdefault(name, []).append(label)
                groups[name] = group

    wiki_rows, wiki_how, wiki_missing = {}, {}, []
    if wiki_cache:
        import bg3_wiki
        found, missing, how = bg3_wiki.match(sorted(owners), wiki_cache)
        wiki_rows, wiki_missing, wiki_how = found, missing, how
        by_uid, by_name = bg3_wiki.index_cache(wiki_cache)
        exact_uids = set(by_uid)

    items = []
    for stats_name in sorted(owners):
        pak = item_stats.get(stats_name, {})
        fields = pak.get("fields", {})
        wiki = wiki_rows.get(stats_name, {})

        # Hoe zeker is de koppeling met de wiki?
        quality = None
        if wiki:
            if wiki_cache and stats_name in exact_uids:
                quality = "uid"
            else:
                import bg3_wiki
                first = bg3_wiki.candidates(stats_name)[:1]
                quality = "naam" if first and \
                    bg3_wiki.normalise(wiki.get("name")) == first[0] else "deelnaam"

        damage = fields.get("Damage") or wiki.get("damage")
        rng = damage_range(damage)
        armour = fields.get("Armour class") or wiki.get("armour_class")

        sources = []
        if fields:
            sources.append("spelbestanden")
        if wiki:
            sources.append("bg3.wiki")

        items.append({
            "id": stats_name,
            "name": wiki.get("name") or prettify(stats_name),
            "group": groups.get(stats_name, "Overig"),
            "owners": sorted(set(owners[stats_name])),
            "damage": damage,
            "damage_type": fields.get("Damage type") or wiki.get("damage_type"),
            "versatile": fields.get("Versatile damage"),
            "avg": round(rng[2], 1) if rng else None,
            "min": rng[0] if rng else None,
            "max": rng[1] if rng else None,
            "ac": _number(armour),
            "armour_type": fields.get("Armour type") or wiki.get("armour_type"),
            "slot": fields.get("Slot"),
            "weight": _number(fields.get("Weight") or wiki.get("weight")),
            "price": _number(wiki.get("price")),
            "rarity": (fields.get("Rarity") or wiki.get("rarity") or "").title()
                      or None,
            "category": wiki.get("category"),
            "handedness": wiki.get("handedness"),
            "properties": fields.get("Properties") or None,
            "special": (wiki.get("special") or "").strip() or None,
            "where": (wiki.get("where_to_find") or "").strip() or None,
            "proficiency": fields.get("Proficiency"),
            "sources": sources,
            "match": quality,
        })

    meta = {
        "save_name": data.get("game", {}).get("save_name"),
        "level": data.get("game", {}).get("current_level"),
        "total": len(items),
        "with_pak": sum(1 for i in items if "spelbestanden" in i["sources"]),
        "with_wiki": sum(1 for i in items if "bg3.wiki" in i["sources"]),
        "no_data": sum(1 for i in items if not i["sources"]),
        "wiki_how": wiki_how,
        "wiki_missing": wiki_missing,
        "owners": sorted({o for i in items for o in i["owners"]}),
        "groups": [g for g in GROUP_ORDER
                   if any(i["group"] == g for i in items)],
    }
    return items, meta


CSS = """
:root{
  --ink:#14101a; --ink-2:#1d1725; --line:#332a40; --field:#251d30;
  --vellum:#efe7d8; --muted:#9a8fa8; --ember:#c2461f; --brass:#b08d3f;
  --good:#5f9e6e;
  --display:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--vellum);
  font-family:var(--display);font-size:15px;line-height:1.5}
.wrap{max-width:1240px;margin:0 auto;padding:30px 22px 80px}
h1{font-size:clamp(25px,4vw,38px);margin:0 0 4px;font-weight:400}
.deck{color:var(--muted);font-family:var(--mono);font-size:11.5px;
  letter-spacing:.06em;text-transform:uppercase;margin:0 0 24px}
h2{font-size:12px;font-family:var(--mono);letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);font-weight:400;
  margin:34px 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}

.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;
  background:var(--ink-2);border:1px solid var(--line);padding:14px 16px;
  margin-bottom:18px}
.control{display:flex;flex-direction:column;gap:4px}
.control label{font-family:var(--mono);font-size:9.5px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted)}
input[type=search],select{background:var(--field);color:var(--vellum);
  border:1px solid var(--line);border-radius:2px;padding:6px 8px;
  font-family:var(--display);font-size:14px;min-width:150px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-family:var(--mono);font-size:10.5px;letter-spacing:.05em;
  border:1px solid var(--line);background:var(--field);color:var(--muted);
  padding:4px 9px;border-radius:2px;cursor:pointer;user-select:none}
.chip[aria-pressed=true]{border-color:var(--brass);color:var(--brass)}
.grow{flex:1}
button{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;
  text-transform:uppercase;background:transparent;color:var(--brass);
  border:1px solid var(--brass);border-radius:2px;padding:6px 11px;
  cursor:pointer}
button:hover{background:var(--brass);color:var(--ink)}
button:disabled{opacity:.4;cursor:default}
button:disabled:hover{background:transparent;color:var(--brass)}

table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;
  vertical-align:top}
th{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);font-weight:400;
  cursor:pointer;white-space:nowrap;position:sticky;top:0;
  background:var(--ink);z-index:2}
th[aria-sort=ascending]::after{content:" ▲";color:var(--brass)}
th[aria-sort=descending]::after{content:" ▼";color:var(--brass)}
tbody tr:hover{background:var(--ink-2)}
td.n{text-align:right;font-family:var(--mono);color:var(--brass);
  white-space:nowrap}
td.c{width:28px;text-align:center}
input[type=checkbox]{accent-color:var(--ember);width:14px;height:14px;
  cursor:pointer}
code{font-family:var(--mono);font-size:10px;color:var(--muted);display:block}
.small{font-size:12px;color:var(--muted)}
.badge{font-family:var(--mono);font-size:8.5px;letter-spacing:.07em;
  text-transform:uppercase;border:1px solid var(--line);color:var(--muted);
  padding:1px 5px;border-radius:2px;margin-left:5px;white-space:nowrap}
.badge.approx{border-color:var(--ember);color:var(--ember)}
.rarity-uncommon{color:#4fa3c7}.rarity-rare{color:#4f7fd1}
.rarity-veryrare{color:#a86fd6}.rarity-legendary{color:#d69a3a}

.panel{border:1px solid var(--brass);background:var(--ink-2);padding:0;
  margin-bottom:22px;overflow-x:auto}
.panel header{display:flex;align-items:center;gap:12px;padding:12px 16px;
  border-bottom:1px solid var(--line)}
.panel h3{margin:0;font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--brass);font-weight:400}
.panel table{font-size:13.5px}
.panel th{position:static;background:var(--ink-2)}
.panel td.best{color:var(--good)}
.panel td.best::after{content:" ★";font-size:10px}
.empty{padding:26px 16px;color:var(--muted);font-family:var(--mono);
  font-size:12px}
.note{border:1px solid var(--line);border-left:3px solid var(--ember);
  background:rgba(194,70,31,.06);padding:13px 16px;margin-bottom:20px;
  font-size:14px}
.note code{display:inline;font-size:12px}
details{border:1px solid var(--line);background:var(--ink-2);padding:12px 16px;
  margin-top:16px}
summary{cursor:pointer;font-family:var(--mono);font-size:11px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
footer{margin-top:40px;color:var(--muted);font-family:var(--mono);
  font-size:11px;line-height:1.7}

@media print{
  body{background:#fff;color:#191423}
  .controls,button,td.c,th.c{display:none}
  table,.panel,.note,details{background:#fff;border-color:#c9c1d2}
  th{background:#fff;color:#191423}
  td.n,.panel td.best{color:#191423}
}
"""

JS = r"""
var ITEMS = window.__ITEMS__;
var state = { q:'', owners:new Set(), groups:new Set(), only:'all',
              sort:'avg', dir:-1, selected:new Set() };

var COLUMNS = [
  {key:'name',   label:'Item',        type:'text'},
  {key:'group',  label:'Categorie',   type:'text'},
  {key:'damage', label:'Schade',      type:'text'},
  {key:'avg',    label:'Gem.',        type:'num'},
  {key:'ac',     label:'AC',          type:'num'},
  {key:'weight', label:'Gewicht',     type:'num'},
  {key:'price',  label:'Prijs',       type:'num'},
  {key:'rarity', label:'Rarity',      type:'text'},
  {key:'owners', label:'Bij',         type:'text'}
];

function rarityClass(r){
  if (!r) return '';
  return 'rarity-' + r.toLowerCase().replace(/[^a-z]/g,'');
}

function visible(){
  var q = state.q.trim().toLowerCase();
  return ITEMS.filter(function(it){
    if (q && (it.name + ' ' + it.id).toLowerCase().indexOf(q) === -1) return false;
    if (state.owners.size && !it.owners.some(function(o){ return state.owners.has(o); }))
      return false;
    if (state.groups.size && !state.groups.has(it.group)) return false;
    if (state.only === 'weapons' && it.avg === null) return false;
    if (state.only === 'armour' && it.ac === null) return false;
    if (state.only === 'stats' && !it.sources.length) return false;
    return true;
  });
}

function compare(a, b){
  var col = COLUMNS.filter(function(c){ return c.key === state.sort; })[0];
  var x = a[state.sort], y = b[state.sort];
  if (col && col.type === 'num'){
    // items zonder waarde horen onderaan, ongeacht de richting
    if (x === null && y === null) return a.name.localeCompare(b.name);
    if (x === null) return 1;
    if (y === null) return -1;
    return (x - y) * state.dir;
  }
  x = Array.isArray(x) ? x.join(', ') : (x || '');
  y = Array.isArray(y) ? y.join(', ') : (y || '');
  return String(x).localeCompare(String(y)) * state.dir;
}

function fmt(value, digits){
  if (value === null || value === undefined) return '—';
  return digits ? value.toFixed(digits) : value;
}

function renderTable(){
  var rows = visible().slice().sort(compare);
  var head = document.getElementById('head');
  head.innerHTML = '<th class="c"></th>' + COLUMNS.map(function(c){
    var sorted = state.sort === c.key
      ? (state.dir === 1 ? 'ascending' : 'descending') : 'none';
    return '<th data-key="' + c.key + '" aria-sort="' + sorted + '">'
      + c.label + '</th>';
  }).join('');

  var body = document.getElementById('body');
  if (!rows.length){
    body.innerHTML = '<tr><td colspan="10" class="empty">'
      + 'Geen items die aan deze filters voldoen.</td></tr>';
  } else {
    body.innerHTML = rows.map(function(it){
      var damage = it.damage || '';
      if (it.versatile) damage += ' / ' + it.versatile;
      if (it.damage_type) damage += ' ' + it.damage_type.toLowerCase();
      var badge = '';
      if (it.match === 'deelnaam')
        badge = '<span class="badge approx" title="Op deelnaam gekoppeld aan de'
          + ' wiki; controleer of dit hetzelfde item is">wiki ≈</span>';
      else if (it.match)
        badge = '<span class="badge" title="Exacte koppeling met de wiki">wiki</span>';
      else if (!it.sources.length)
        badge = '<span class="badge" title="Geen statdefinitie gevonden">geen data</span>';
      return '<tr data-id="' + it.id + '">'
        + '<td class="c"><input type="checkbox" aria-label="Vergelijk '
        + it.name + '"' + (state.selected.has(it.id) ? ' checked' : '') + '></td>'
        + '<td><span class="' + rarityClass(it.rarity) + '">' + it.name
        + '</span>' + badge + '<code>' + it.id + '</code></td>'
        + '<td class="small">' + it.group + '</td>'
        + '<td>' + (damage.trim() || '—') + '</td>'
        + '<td class="n">' + fmt(it.avg, 1) + '</td>'
        + '<td class="n">' + fmt(it.ac) + '</td>'
        + '<td class="n">' + fmt(it.weight) + '</td>'
        + '<td class="n">' + fmt(it.price) + '</td>'
        + '<td class="small">' + (it.rarity || '—') + '</td>'
        + '<td class="small">' + it.owners.join(', ') + '</td>'
        + '</tr>';
    }).join('');
  }
  document.getElementById('count').textContent =
    rows.length + ' van ' + ITEMS.length + ' items';
}

var COMPARE_ROWS = [
  {label:'Categorie',    key:'group',       type:'text'},
  {label:'Schade',       key:'damage',      type:'text'},
  {label:'Schadetype',   key:'damage_type', type:'text'},
  {label:'Tweehandig',   key:'versatile',   type:'text'},
  {label:'Bereik',       key:'_range',      type:'text'},
  {label:'Gemiddeld',    key:'avg',         type:'num', better:'high'},
  {label:'Armour class', key:'ac',          type:'num', better:'high'},
  {label:'Gewicht',      key:'weight',      type:'num', better:'low'},
  {label:'Prijs',        key:'price',       type:'num', better:'low'},
  {label:'Rarity',       key:'rarity',      type:'text'},
  {label:'Eigenschappen',key:'properties',  type:'text'},
  {label:'Proficiency',  key:'proficiency', type:'text'},
  {label:'Speciaal',     key:'special',     type:'text'},
  {label:'Te vinden',    key:'where',       type:'text'},
  {label:'Bij',          key:'owners',      type:'text'},
  {label:'Bron',         key:'sources',     type:'text'}
];

function renderCompare(){
  var chosen = ITEMS.filter(function(it){ return state.selected.has(it.id); });
  var panel = document.getElementById('compare');
  document.getElementById('clear').disabled = !chosen.length;
  if (chosen.length < 2){
    panel.innerHTML = '<header><h3>Vergelijken</h3></header><p class="empty">'
      + 'Vink minstens twee items aan om ze naast elkaar te zetten. '
      + 'De beste waarde per rij krijgt een sterretje.</p>';
    return;
  }
  var html = '<header><h3>Vergelijken — ' + chosen.length
    + ' items</h3></header><table><tr><th></th>'
    + chosen.map(function(it){
        return '<th><span class="' + rarityClass(it.rarity) + '">'
          + it.name + '</span></th>';
      }).join('') + '</tr>';

  COMPARE_ROWS.forEach(function(row){
    var values = chosen.map(function(it){
      if (row.key === '_range')
        return (it.min === null) ? null : it.min + '–' + it.max;
      var v = it[row.key];
      return Array.isArray(v) ? (v.length ? v.join(', ') : null) : v;
    });
    if (values.every(function(v){ return v === null || v === undefined || v === ''; }))
      return;                                   // rij helemaal leeg: overslaan
    var best = null;
    if (row.type === 'num' && row.better){
      var numbers = values.filter(function(v){ return typeof v === 'number'; });
      if (numbers.length > 1)
        best = row.better === 'high' ? Math.max.apply(null, numbers)
                                     : Math.min.apply(null, numbers);
    }
    html += '<tr><th>' + row.label + '</th>' + values.map(function(v){
      var isBest = (best !== null && v === best);
      var cls = (row.type === 'num' ? 'n' : 'small') + (isBest ? ' best' : '');
      var text = (v === null || v === undefined || v === '') ? '—' : v;
      return '<td class="' + cls + '">' + text + '</td>';
    }).join('') + '</tr>';
  });
  panel.innerHTML = html + '</table>';
}

function render(){ renderTable(); renderCompare(); }

function toggleChip(chip, set){
  var value = chip.dataset.value;
  if (set.has(value)) set.delete(value); else set.add(value);
  chip.setAttribute('aria-pressed', set.has(value) ? 'true' : 'false');
  render();
}

function bindChip(chip, set){
  function activate(){ toggleChip(chip, set); }
  chip.addEventListener('click', activate);
  chip.addEventListener('keydown', function(e){
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar'){
      e.preventDefault();
      activate();
    }
  });
}

document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('q').addEventListener('input', function(e){
    state.q = e.target.value; render();
  });
  document.getElementById('only').addEventListener('change', function(e){
    state.only = e.target.value; render();
  });
  document.querySelectorAll('[data-owner]').forEach(function(chip){
    bindChip(chip, state.owners);
  });
  document.querySelectorAll('[data-group]').forEach(function(chip){
    bindChip(chip, state.groups);
  });
  document.getElementById('head').addEventListener('click', function(e){
    var th = e.target.closest('th[data-key]');
    if (!th) return;
    var key = th.dataset.key;
    if (state.sort === key) state.dir = -state.dir;
    else { state.sort = key;
           state.dir = (key === 'name' || key === 'group') ? 1 : -1; }
    render();
  });
  document.getElementById('body').addEventListener('change', function(e){
    var row = e.target.closest('tr[data-id]');
    if (!row) return;
    if (e.target.checked) state.selected.add(row.dataset.id);
    else state.selected.delete(row.dataset.id);
    renderCompare();
  });
  document.getElementById('clear').addEventListener('click', function(){
    state.selected.clear(); render();
  });
  document.getElementById('print').addEventListener('click', function(){
    window.print();
  });
  render();
});
"""


def render(items, meta):
    out = []
    a = out.append
    a("<!doctype html><html lang='nl'><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>Spullen vergelijken — %s</title>" % esc(meta["save_name"]))
    a("<style>%s</style></head><body><div class='wrap'>" % CSS)

    a("<h1>Spullen vergelijken</h1>")
    a("<p class='deck'>%s · %s · %d items</p>"
      % (esc(meta["save_name"]), esc(meta["level"]), meta["total"]))

    # herkomst van de gegevens, eerlijk benoemd
    bits = []
    if meta["with_pak"]:
        bits.append("%d met stats uit de spelbestanden" % meta["with_pak"])
    if meta["with_wiki"]:
        bits.append("%d gekoppeld aan bg3.wiki" % meta["with_wiki"])
    if meta["no_data"]:
        bits.append("%d zonder enige statdefinitie" % meta["no_data"])
    a("<div class='note'>%s." % esc("; ".join(bits) or "Geen statbron gebruikt"))
    if meta["wiki_how"]:
        how = meta["wiki_how"]
        a(" Wiki-koppeling: %d op uid, %d op exacte naam, %d op deelnaam. "
          "Die laatste groep is een gok op basis van naamovereenkomst en staat "
          "in de tabel gemarkeerd met <code>wiki ≈</code> — controleer die "
          "voordat je erop vertrouwt."
          % (how.get("uid", 0), how.get("naam", 0), how.get("deelnaam", 0)))
    if not meta["with_pak"] and not meta["with_wiki"]:
        a(" Geef <code>--stats</code> of <code>--wiki-cache</code> mee om "
          "damage, AC en prijzen te laten zien.")
    a("</div>")

    # bediening
    a("<div class='controls'>")
    a("<div class='control'><label for='q'>Zoeken</label>"
      "<input type='search' id='q' placeholder='naam of interne id'></div>")
    a("<div class='control'><label for='only'>Alleen tonen</label>"
      "<select id='only'>"
      "<option value='all'>alles</option>"
      "<option value='weapons'>items met schade</option>"
      "<option value='armour'>items met armour class</option>"
      "<option value='stats'>items met statgegevens</option>"
      "</select></div>")
    if meta["owners"]:
        a("<div class='control'><label>Van wie</label><div class='chips'>")
        for owner in meta["owners"]:
            a("<span class='chip' role='button' tabindex='0' aria-pressed='false' "
              "data-owner data-value='%s'>%s</span>" % (esc(owner), esc(owner)))
        a("</div></div>")
    if meta["groups"]:
        a("<div class='control'><label>Categorie</label><div class='chips'>")
        for group in meta["groups"]:
            a("<span class='chip' role='button' tabindex='0' aria-pressed='false' "
              "data-group data-value='%s'>%s</span>" % (esc(group), esc(group)))
        a("</div></div>")
    a("<div class='grow'></div>")
    a("<button id='clear' disabled>Selectie wissen</button>")
    a("<button id='print'>Print</button>")
    a("</div>")

    a("<div class='panel' id='compare'></div>")

    a("<h2>Alle items <span id='count' class='small'></span></h2>")
    a("<table><thead><tr id='head'></tr></thead><tbody id='body'></tbody></table>")

    if meta.get("wiki_missing"):
        a("<details><summary>%d items niet op de wiki gevonden</summary>"
          "<p class='small' style='margin:10px 0 0;word-break:break-word'>%s</p>"
          "</details>" % (len(meta["wiki_missing"]),
                          esc(", ".join(meta["wiki_missing"]))))

    a("<footer>Gemiddelde schade is de basiswaarde van het wapen zelf, zonder "
      "ability-modifier, proficiency of enchantment.<br>"
      "Wiki-gegevens komen van bg3.wiki, onder CC BY-NC-SA 4.0 of CC BY-SA 4.0."
      "</footer>")

    a("<script>window.__ITEMS__ = %s;</script>"
      % json.dumps(items, ensure_ascii=False))
    a("<script>%s</script></div></body></html>" % JS)
    return "\n".join(out)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Maak een vergelijkpagina uit een eerder gemaakte party.json.")
    ap.add_argument("party_json")
    ap.add_argument("-o", "--out", default="compare.html")
    ap.add_argument("--wiki-cache", help="cachebestand van bg3_wiki.py")
    args = ap.parse_args()

    with open(args.party_json, encoding="utf-8") as fh:
        data = json.load(fh)
    cache = None
    if args.wiki_cache:
        with open(args.wiki_cache, encoding="utf-8") as fh:
            cache = json.load(fh)
    items, meta = build_items(data, cache)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render(items, meta))
    print("%s (%d items)" % (args.out, len(items)))
