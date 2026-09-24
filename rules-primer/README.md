# BG3 Rules Primer

A short, static course that teaches how Baldur's Gate 3 works, for people who
have never played D&D. Twenty-three lessons in six parts, plus a searchable
glossary:

1. **Core rules**: ability scores, proficiency, the d20 system
2. **Combat**: turns and actions, attacks and AC, spellcasting, where BG3
   departs from tabletop 5e, conditions
3. **Building a character**: races, classes and subclasses, backgrounds and
   skills, levelling, feats and multiclassing
4. **Gear**: weapons and damage types, armour and magic items, potions,
   scrolls and alchemy, inventory and trading
5. **Exploring the world**: dialogue checks, stealth and light, locks, traps
   and crime
6. **BG3's own systems**: companions, approval and camp, Illithid powers,
   difficulty modes

Plain HTML, CSS and JavaScript. No build step, no dependencies, no external
fonts or CDNs. About 130 KB in total.

```
index.html   all content
style.css    styles (dark by default, light-mode toggle)
app.js       navigation, progress tracking, glossary filter, small widgets
```

Reading progress and the theme choice are stored in the browser's
`localStorage`. If storage is blocked the page still works; it just won't
remember.

## Run it locally

Opening `index.html` directly in a browser works. To serve it over HTTP:

```bash
# Python (any 3.x)
python3 -m http.server 8000
# then open http://localhost:8000

# or Caddy
caddy file-server --listen :8000
```

## Deploy to GitHub Pages

**If this folder is its own repository:**

1. Push the folder's contents to the default branch of a GitHub repo.
2. In the repo, go to *Settings → Pages*.
3. Under *Build and deployment*, choose *Deploy from a branch*, select the
   branch (for example `main`) and the folder `/ (root)`, then save.
4. After a minute the site is live at `https://<user>.github.io/<repo>/`.

**If it stays in a subfolder of a larger repo** (as here, in `rules-primer/`):
GitHub Pages can only serve the repo root or `/docs`. Either rename or copy
the folder to `docs/` and pick `/docs` in step 3, or deploy it with a GitHub
Actions workflow that uploads `rules-primer/` as the Pages artifact.

All links are relative, so the site works from any sub-path.

## Other static hosts

Copy the three files to any web root. For nginx, point `root` at the folder;
for Caddy:

```
bg3-primer.example.com {
    root * /srv/rules-primer
    file_server
}
```

## Sources and licensing

The rules are paraphrased from the D&D 5th Edition System Reference Document
(SRD 5.1, CC-BY-4.0, Wizards of the Coast) and the D&D Basic Rules, together
with publicly documented Baldur's Gate 3 mechanics. All text is original
wording; no rulebook text is reproduced. This is an unofficial fan guide,
not affiliated with Larian Studios or Wizards of the Coast. Game values can
change with patches.
