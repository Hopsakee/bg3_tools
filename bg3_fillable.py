#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
bg3_fillable.py -- maakt een invulbaar D&D-5e-sheet per party-lid.

Alles wat uit de savegame komt staat al ingevuld: naam, race, klasse,
subklasse, level, XP en de meegedragen items (met damage en AC als je
--stats hebt gebruikt). Alles wat niet uit de save te lezen is, staat leeg
maar rekent zichzelf door zodra je het invult:

  * ability scores -> modifiers, saving throws, vaardigheden, initiative
  * level          -> proficiency bonus
  * klasse         -> hit die, spellcasting ability, saving-throw-proficiencies
  * spellcasting   -> spell save DC en spell attack bonus

Voorgevulde regelgebonden waarden (hit die, welke saves proficient zijn)
komen uit de standaard 5e-klassenregels en zijn allemaal aanpasbaar.

Opslaan gaat via "Bewaar als JSON" en "Laad JSON": geen browseropslag, dus je
houdt je ingevulde sheets zelf in de hand en kunt ze in versiebeheer zetten.
"""

import html
import json

# --------------------------------------------------------------- 5e-regels

ABILITIES = [
    ("str", "Strength"), ("dex", "Dexterity"), ("con", "Constitution"),
    ("int", "Intelligence"), ("wis", "Wisdom"), ("cha", "Charisma"),
]

SKILLS = [
    ("Acrobatics", "dex"), ("Animal Handling", "wis"), ("Arcana", "int"),
    ("Athletics", "str"), ("Deception", "cha"), ("History", "int"),
    ("Insight", "wis"), ("Intimidation", "cha"), ("Investigation", "int"),
    ("Medicine", "wis"), ("Nature", "int"), ("Perception", "wis"),
    ("Performance", "cha"), ("Persuasion", "cha"), ("Religion", "int"),
    ("Sleight of Hand", "dex"), ("Stealth", "dex"), ("Survival", "wis"),
]

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


def esc(x):
    return html.escape(str("" if x is None else x))


CSS = """
:root{
  --ink:#14101a; --ink-2:#1d1725; --line:#332a40; --field:#251d30;
  --vellum:#efe7d8; --muted:#9a8fa8; --ember:#c2461f; --brass:#b08d3f;
  --display:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--vellum);
  font-family:var(--display);font-size:15px;line-height:1.5}
.wrap{max-width:1040px;margin:0 auto;padding:32px 24px 90px}
h1{font-size:clamp(26px,4vw,40px);margin:0 0 4px;font-weight:400;
  letter-spacing:-.01em}
.deck{color:var(--muted);font-family:var(--mono);font-size:12px;
  letter-spacing:.06em;text-transform:uppercase;margin:0 0 28px}
h2{font-size:12.5px;font-family:var(--mono);letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);font-weight:400;
  margin:0 0 16px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h3{font-size:11px;font-family:var(--mono);letter-spacing:.12em;
  text-transform:uppercase;color:var(--ember);font-weight:400;margin:0 0 8px}

.bar{position:sticky;top:0;z-index:5;background:rgba(20,16,26,.94);
  border-bottom:1px solid var(--line);padding:10px 24px;
  display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  backdrop-filter:blur(6px)}
.bar .spacer{flex:1}
button{font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;background:transparent;color:var(--brass);
  border:1px solid var(--brass);border-radius:2px;padding:6px 12px;
  cursor:pointer}
button:hover{background:var(--brass);color:var(--ink)}
button:focus-visible,input:focus-visible,textarea:focus-visible{
  outline:2px solid var(--ember);outline-offset:1px}

.sheet{border:1px solid var(--line);background:var(--ink-2);
  margin-bottom:34px;break-inside:avoid}
.sheet>header{padding:18px 22px;border-bottom:1px solid var(--line);
  background:linear-gradient(90deg,rgba(194,70,31,.10),transparent 55%)}
.ident{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:12px}
.body{display:grid;grid-template-columns:200px 1fr;gap:0}
@media(max-width:820px){.body{grid-template-columns:1fr}}
.pane{padding:20px 22px}
.pane+.pane{border-left:1px solid var(--line)}
@media(max-width:820px){.pane+.pane{border-left:0;border-top:1px solid var(--line)}}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:26px}
@media(max-width:680px){.cols{grid-template-columns:1fr}}

label{display:block;font-family:var(--mono);font-size:9.5px;
  letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  margin-bottom:3px}
input[type=text],input[type=number],textarea,select{
  width:100%;background:var(--field);color:var(--vellum);
  border:1px solid var(--line);border-radius:2px;padding:6px 8px;
  font-family:var(--display);font-size:15px}
input.prefilled{border-color:#4a3a24}
textarea{font-size:14px;line-height:1.5;resize:vertical;min-height:90px}
input[type=checkbox]{accent-color:var(--ember);width:14px;height:14px;
  margin:0;cursor:pointer}

.ability{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.ability label{margin:0;flex:1}
.ability input{width:56px;text-align:center;font-size:17px}
.ability output{width:38px;text-align:center;font-family:var(--mono);
  font-size:15px;color:var(--brass)}

table{width:100%;border-collapse:collapse}
td,th{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;
  font-size:14px}
th{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);font-weight:400}
td.n{text-align:right;font-family:var(--mono);color:var(--brass);width:44px}
td.c{width:26px}
td.ab{font-family:var(--mono);font-size:10px;color:var(--muted);width:34px;
  text-transform:uppercase}

.derived{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));
  gap:1px;background:var(--line);border:1px solid var(--line);margin-bottom:20px}
.derived div{background:var(--field);padding:9px 10px;text-align:center}
.derived span{display:block;font-family:var(--mono);font-size:9px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.derived output{font-size:20px;font-family:var(--mono);color:var(--vellum)}

.hint{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  margin:6px 0 0;line-height:1.5}
ul.gear{list-style:none;margin:0;padding:0;columns:2;column-gap:22px}
@media(max-width:600px){ul.gear{columns:1}}
ul.gear li{font-size:13.5px;padding:1px 0;break-inside:avoid}
ul.gear code{display:block;font-family:var(--mono);font-size:10px;
  color:var(--muted)}
ul.gear .stat{display:block;font-size:11.5px;color:var(--brass)}
.note{border:1px solid var(--ember);border-left-width:3px;
  background:rgba(194,70,31,.07);padding:14px 18px;margin-bottom:30px;
  font-size:14px}
.note code{font-family:var(--mono);font-size:12px}

@media print{
  body{background:#fff;color:#191423}
  .bar,.hint{display:none}
  .sheet,.pane,.derived div,input,textarea,select{background:#fff!important;
    color:#191423!important;border-color:#c9c1d2!important}
  .sheet{break-after:page}
  .derived output,td.n{color:#191423!important}
}
"""

JS = """
function mod(score){
  var v = parseInt(score, 10);
  if (isNaN(v)) return null;
  return Math.floor((v - 10) / 2);
}
function sign(n){ return n === null ? '—' : (n >= 0 ? '+' + n : '' + n); }
function profBonus(level){
  var l = parseInt(level, 10);
  if (isNaN(l) || l < 1) return 2;
  return 2 + Math.floor((Math.min(l, 20) - 1) / 4);
}

function recalc(sheet){
  var level = sheet.querySelector('[data-f=level]').value;
  var pb = profBonus(level);
  sheet.querySelector('[data-o=prof]').textContent = sign(pb);

  var mods = {};
  sheet.querySelectorAll('[data-ability]').forEach(function(input){
    var key = input.dataset.ability;
    var m = mod(input.value);
    mods[key] = m;
    sheet.querySelector('[data-omod=' + key + ']').textContent = sign(m);
  });

  // saving throws
  sheet.querySelectorAll('[data-save]').forEach(function(row){
    var key = row.dataset.save;
    var prof = row.querySelector('input[type=checkbox]').checked;
    var m = mods[key];
    row.querySelector('output').textContent =
      m === null ? '—' : sign(m + (prof ? pb : 0));
  });

  // skills
  sheet.querySelectorAll('[data-skill]').forEach(function(row){
    var key = row.dataset.ab;
    var boxes = row.querySelectorAll('input[type=checkbox]');
    var prof = boxes[0].checked, expertise = boxes[1].checked;
    var m = mods[key];
    var bonus = prof ? pb : 0;
    if (expertise) bonus = pb * 2;
    row.querySelector('output').textContent =
      m === null ? '—' : sign(m + bonus);
    if (key === 'wis' && row.dataset.skill === 'Perception'){
      var pp = sheet.querySelector('[data-o=passive]');
      if (pp) pp.textContent = m === null ? '—' : (10 + m + bonus);
    }
  });

  // initiative volgt dex
  sheet.querySelector('[data-o=init]').textContent = sign(mods.dex);

  // suggestie voor maximale HP op level 1
  var die = parseInt(sheet.querySelector('[data-f=hitdie]').value, 10);
  var hpHint = sheet.querySelector('[data-o=hphint]');
  if (hpHint){
    hpHint.textContent = (isNaN(die) || mods.con === null) ? '—'
      : (die + mods.con) + ' op level 1';
  }

  // spell save DC en spell attack
  var sel = sheet.querySelector('[data-f=spellability]');
  var key = sel ? sel.value : '';
  var dc = sheet.querySelector('[data-o=dc]');
  var atk = sheet.querySelector('[data-o=spellatk]');
  if (dc && atk){
    if (!key || mods[key] === null){
      dc.textContent = '—'; atk.textContent = '—';
    } else {
      dc.textContent = 8 + pb + mods[key];
      atk.textContent = sign(pb + mods[key]);
    }
  }

  // aanvalsbonussen per wapen
  sheet.querySelectorAll('[data-attack]').forEach(function(row){
    var abil = row.querySelector('select').value;
    var prof = row.querySelector('input[type=checkbox]').checked;
    var m = mods[abil];
    row.querySelector('output').textContent =
      m === null ? '—' : sign(m + (prof ? pb : 0));
  });
}

function recalcAll(){
  document.querySelectorAll('.sheet').forEach(recalc);
}

function collect(){
  var out = {};
  document.querySelectorAll('.sheet').forEach(function(sheet){
    var data = {};
    sheet.querySelectorAll('input, textarea, select').forEach(function(el){
      if (!el.name) return;
      data[el.name] = (el.type === 'checkbox') ? el.checked : el.value;
    });
    out[sheet.dataset.key] = data;
  });
  return out;
}

function saveJson(){
  var blob = new Blob([JSON.stringify(collect(), null, 2)],
                      {type: 'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'character_sheets.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

function loadJson(file){
  var reader = new FileReader();
  reader.onload = function(){
    var data;
    try { data = JSON.parse(reader.result); }
    catch (err) {
      alert('Dit bestand is geen geldige JSON.');
      return;
    }
    document.querySelectorAll('.sheet').forEach(function(sheet){
      var values = data[sheet.dataset.key];
      if (!values) return;
      sheet.querySelectorAll('input, textarea, select').forEach(function(el){
        if (!el.name || !(el.name in values)) return;
        if (el.type === 'checkbox') el.checked = !!values[el.name];
        else el.value = values[el.name];
      });
    });
    recalcAll();
  };
  reader.readAsText(file);
}

document.addEventListener('input', recalcAll);
document.addEventListener('change', recalcAll);
document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('save').addEventListener('click', saveJson);
  document.getElementById('print').addEventListener('click', function(){
    window.print();
  });
  var picker = document.getElementById('file');
  document.getElementById('load').addEventListener('click', function(){
    picker.click();
  });
  picker.addEventListener('change', function(){
    if (picker.files[0]) loadJson(picker.files[0]);
  });
  recalcAll();
});
"""


def _field(name, label, value="", kind="text", prefilled=False, extra=""):
    cls = " class='prefilled'" if prefilled else ""
    return ("<div><label>%s</label><input type='%s' name='%s' value='%s'%s%s>"
            "</div>" % (esc(label), kind, esc(name), esc(value), cls, extra))


def render(data, name_hint=None):
    party = data.get("party", [])
    item_stats = data.get("item_stats", {})
    out = []
    a = out.append

    a("<!doctype html><html lang='nl'><head><meta charset='utf-8'>")
    a("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    a("<title>Invulbare character sheets — %s</title>"
      % esc(data.get("game", {}).get("save_name")))
    a("<style>%s</style></head><body>" % CSS)

    a("<div class='bar'><button id='save'>Bewaar als JSON</button>"
      "<button id='load'>Laad JSON</button>"
      "<input type='file' id='file' accept='.json' hidden>"
      "<span class='spacer'></span><button id='print'>Print of naar PDF</button>"
      "</div><div class='wrap'>")

    a("<h1>Invulbare character sheets</h1>")
    a("<p class='deck'>%s · level %s · %s</p>"
      % (esc(data.get("game", {}).get("save_name")),
         esc(party[0]["level"] if party else "?"),
         esc(data.get("game", {}).get("current_level"))))

    a("<div class='note'>Velden met een <strong>koperkleurige rand</strong> komen "
      "uit de savegame. De rest vul je zelf in — de zes ability scores zijn de "
      "enige die je echt moet overtypen uit het spel; modifiers, saving throws, "
      "vaardigheden, initiative, spell save DC en aanvalsbonussen rekenen zich "
      "daarna zelf uit. Hit die en de proficiente saves zijn voorgevuld volgens "
      "de standaard 5e-klassenregels en overschrijfbaar. Opslaan gaat via "
      "<code>Bewaar als JSON</code>; die kun je later weer inladen.</div>")

    for index, c in enumerate(party):
        klass = c["class"] or ""
        subclass = c["subclass"] or ""
        if c["origin"] and c["origin"] != "Generic":
            name = c["origin"]
        else:
            name = name_hint or ""
        key = "char%d" % index
        p = lambda field: "%s_%s" % (key, field)   # unieke veldnamen per sheet

        a("<article class='sheet' data-key='%s'><header><div class='ident'>" % key)
        a(_field(p("name"), "Naam", name, prefilled=bool(name)))
        a(_field(p("class"), "Klasse", klass, prefilled=bool(klass)))
        a(_field(p("subclass"), "Subklasse", subclass, prefilled=bool(subclass)))
        a(_field(p("race"), "Race", (c["race"] or "").replace("_", " "),
                 prefilled=bool(c["race"])))
        a("<div><label>Level</label><input type='number' min='1' max='12' "
          "class='prefilled' name='%s' data-f='level' value='%s'></div>"
          % (esc(p("level")), esc(c["level"])))
        a(_field(p("xp"), "XP", c["xp_total"], kind="number",
                 prefilled=c["xp_total"] is not None))
        a(_field(p("background"), "Background"))
        a("</div></header><div class='body'>")

        # ---- linkerkolom: ability scores
        a("<div class='pane'><h3>Ability scores</h3>")
        for abbr, label in ABILITIES:
            a("<div class='ability'><label for='%s'>%s</label>"
              "<input id='%s' type='number' min='1' max='30' name='%s' "
              "data-ability='%s' placeholder='—'>"
              "<output data-omod='%s'>—</output></div>"
              % (esc(p(abbr)), esc(label), esc(p(abbr)), esc(p(abbr)), abbr, abbr))
        a("<p class='hint'>Deze zes staan in het spel op het characterscherm. "
          "De rest volgt hieruit.</p>")

        a("<h3 style='margin-top:22px'>Saving throws</h3><table>")
        proficient = SAVE_PROFICIENCIES.get(klass, ())
        for abbr, label in ABILITIES:
            checked = " checked" if abbr in proficient else ""
            a("<tr data-save='%s'><td class='c'><input type='checkbox' "
              "name='%s'%s></td><td>%s</td><td class='n'><output>—</output></td>"
              "</tr>" % (abbr, esc(p("save_" + abbr)), checked, esc(label)))
        a("</table>")
        if klass in SAVE_PROFICIENCIES:
            a("<p class='hint'>Aangevinkt volgens de 5e-regels voor %s.</p>"
              % esc(klass))
        a("</div>")

        # ---- rechterkolom
        a("<div class='pane'>")
        a("<div class='derived'>"
          "<div><span>Proficiency</span><output data-o='prof'>+2</output></div>"
          "<div><span>Initiative</span><output data-o='init'>—</output></div>"
          "<div><span>Passive perception</span>"
          "<output data-o='passive'>—</output></div>"
          "<div><span>Spell save DC</span><output data-o='dc'>—</output></div>"
          "<div><span>Spell attack</span><output data-o='spellatk'>—</output>"
          "</div></div>")

        a("<div class='cols'><div>")
        a("<h3>Vaardigheden</h3><table><tr><th>P</th><th>E</th><th></th>"
          "<th>Vaardigheid</th><th></th></tr>")
        for skill, abbr in SKILLS:
            a("<tr data-skill='%s' data-ab='%s'>"
              "<td class='c'><input type='checkbox' name='%s'></td>"
              "<td class='c'><input type='checkbox' name='%s'></td>"
              "<td class='ab'>%s</td><td>%s</td>"
              "<td class='n'><output>—</output></td></tr>"
              % (esc(skill), abbr,
                 esc(p("skill_" + skill.replace(" ", ""))),
                 esc(p("exp_" + skill.replace(" ", ""))),
                 abbr, esc(skill)))
        a("</table><p class='hint'>P is proficient, E is expertise "
          "(dubbele proficiency bonus).</p>")
        a("</div><div>")

        # gevecht
        a("<h3>Gevecht</h3><div class='ident'>")
        a(_field(p("ac"), "Armour class", kind="number"))
        a(_field(p("hp_max"), "HP maximum", kind="number"))
        a(_field(p("hp_current"), "HP nu", kind="number"))
        a(_field(p("speed"), "Snelheid", "9 m"))
        die = HIT_DIE.get(klass, "")
        a("<div><label>Hit die (d…)</label><input type='number' name='%s' "
          "data-f='hitdie' value='%s'%s></div>"
          % (esc(p("hitdie")), esc(die), " class='prefilled'" if die else ""))
        a("<div><label>Spellcasting ability</label><select name='%s' "
          "data-f='spellability'><option value=''>geen</option>"
          % esc(p("spellability")))
        default_spell = SPELL_ABILITY.get(klass, "")
        for abbr, label in ABILITIES:
            sel = " selected" if abbr == default_spell else ""
            a("<option value='%s'%s>%s</option>" % (abbr, sel, esc(label)))
        a("</select></div></div>")
        a("<p class='hint'>Suggestie voor HP-maximum: "
          "<output data-o='hphint'>—</output>. Armour class hangt af van wat je "
          "aan hebt; welke stukken je bij je hebt staat onderaan.</p>")

        # aanvallen, voorgevuld met de wapens uit de save
        weapons = []
        for group, names in c["items_by_group"].items():
            for stats_name in names:
                if item_stats.get(stats_name, {}).get("type") == "Weapon" \
                        or stats_name.startswith("WPN_"):
                    weapons.append(stats_name)
        weapons = sorted(set(weapons))
        a("<h3 style='margin-top:22px'>Aanvallen</h3><table>"
          "<tr><th>Wapen</th><th>Schade</th><th>Mod</th><th>P</th>"
          "<th>Bonus</th></tr>")
        for i, stats_name in enumerate(weapons or [""]):
            fields = item_stats.get(stats_name, {}).get("fields", {})
            damage = fields.get("Damage", "")
            if damage and fields.get("Damage type"):
                damage += " " + fields["Damage type"].lower()
            pretty = stats_name.split("_", 1)[-1] if stats_name else ""
            ranged = "Ranged" in (fields.get("Properties") or "") \
                or any(w in stats_name for w in ("Bow", "Crossbow"))
            a("<tr data-attack='1'>"
              "<td><input type='text' name='%s' value='%s'%s></td>"
              "<td><input type='text' name='%s' value='%s'%s></td>"
              "<td><select name='%s'>" % (
                  esc(p("atk_name_%d" % i)), esc(pretty),
                  " class='prefilled'" if pretty else "",
                  esc(p("atk_dmg_%d" % i)), esc(damage),
                  " class='prefilled'" if damage else "",
                  esc(p("atk_ab_%d" % i))))
            for abbr, label in (("str", "Str"), ("dex", "Dex")):
                sel = " selected" if (abbr == "dex") == ranged else ""
                a("<option value='%s'%s>%s</option>" % (abbr, sel, label))
            a("</select></td><td class='c'><input type='checkbox' name='%s' "
              "checked></td><td class='n'><output>—</output></td></tr>"
              % esc(p("atk_prof_%d" % i)))
        for i in range(len(weapons), len(weapons) + 2):
            a("<tr data-attack='1'>"
              "<td><input type='text' name='%s'></td>"
              "<td><input type='text' name='%s'></td>"
              "<td><select name='%s'><option value='str'>Str</option>"
              "<option value='dex'>Dex</option></select></td>"
              "<td class='c'><input type='checkbox' name='%s'></td>"
              "<td class='n'><output>—</output></td></tr>"
              % (esc(p("atk_name_%d" % i)), esc(p("atk_dmg_%d" % i)),
                 esc(p("atk_ab_%d" % i)), esc(p("atk_prof_%d" % i))))
        a("</table>")
        a("</div></div>")

        # spells, features, uitrusting
        a("<div class='cols' style='margin-top:24px'><div>"
          "<h3>Spells en cantrips</h3><textarea name='%s' rows='7' "
          "placeholder='Bijvoorbeeld: Guidance, Sacred Flame, Bless, "
          "Command'></textarea></div><div>"
          "<h3>Features, passives en feats</h3><textarea name='%s' rows='7' "
          "placeholder='Bijvoorbeeld: Favoured Enemy, Natural Explorer, "
          "Darkvision'></textarea></div></div>"
          % (esc(p("spells")), esc(p("features"))))

        if c["items_by_group"]:
            a("<h3 style='margin-top:24px'>Uit de savegame: %d items bij zich</h3>"
              "<ul class='gear'>" % c["item_count"])
            for group in sorted(c["items_by_group"]):
                for stats_name in c["items_by_group"][group]:
                    fields = item_stats.get(stats_name, {}).get("fields", {})
                    bits = []
                    if fields.get("Damage"):
                        bits.append(fields["Damage"])
                    if fields.get("Armour class"):
                        bits.append("AC %s" % fields["Armour class"])
                    if fields.get("Weight"):
                        bits.append("%s kg" % fields["Weight"])
                    a("<li>%s" % esc(stats_name.split("_", 1)[-1]))
                    if bits:
                        a("<span class='stat'>%s</span>" % esc(" · ".join(bits)))
                    a("<code>%s</code></li>" % esc(stats_name))
            a("</ul>")

        a("<h3 style='margin-top:24px'>Aantekeningen</h3>"
          "<textarea name='%s' rows='4'></textarea>" % esc(p("notes")))
        a("</div></div></article>")

    a("</div><script>%s</script></body></html>" % JS)
    return "\n".join(out)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(
        description="Maak invulbare sheets uit een eerder gemaakte party.json.")
    ap.add_argument("party_json")
    ap.add_argument("-o", "--out", default="fillable_sheets.html")
    ap.add_argument("--name", help="naam van je hoofdpersoon")
    args = ap.parse_args()

    with open(args.party_json, encoding="utf-8") as fh:
        data = json.load(fh)
    hint = args.name or data.get("game", {}).get("character_name_from_folder")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(render(data, hint))
    print(args.out)
