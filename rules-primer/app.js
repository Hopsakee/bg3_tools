// BG3 Rules Primer: navigation, progress, theme, and the small interactive bits.
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // localStorage can throw (private mode, blocked storage); the page must work without it.
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) {} }
  };

  /* ── theme ───────────────────────────── */
  var root = document.documentElement;
  $("#themeToggle").addEventListener("click", function () {
    var next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    store.set("bg3-theme", next);
  });

  /* ── mobile nav ──────────────────────── */
  var toggle = $("#navToggle"), scrim = $("#scrim");
  function setNav(open) {
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    scrim.hidden = !open;
  }
  toggle.addEventListener("click", function () { setNav(!document.body.classList.contains("nav-open")); });
  scrim.addEventListener("click", function () { setNav(false); });
  $$("#toc a").forEach(function (a) { a.addEventListener("click", function () { setNav(false); }); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setNav(false); });

  /* ── progress (read lessons) ─────────── */
  var KEY = "bg3-progress";
  var lessons = $$(".lesson").map(function (s) { return s.id; });
  var done = {};
  try { (JSON.parse(store.get(KEY)) || []).forEach(function (id) { done[id] = true; }); } catch (e) {}

  function renderProgress() {
    var n = 0;
    lessons.forEach(function (id) {
      var isDone = !!done[id];
      if (isDone) n++;
      var link = $('#toc a[data-sec="' + id + '"]');
      if (link) link.classList.toggle("is-done", isDone);
      var btn = $('[data-done="' + id + '"]');
      if (btn) {
        btn.classList.toggle("is-done", isDone);
        btn.textContent = isDone ? "Read" : "Mark as read";
        btn.setAttribute("aria-pressed", String(isDone));
      }
    });
    $$(".toc-part").forEach(function (part) {
      var ids = $$("a[data-sec]", part).map(function (l) { return l.dataset.sec; });
      var got = ids.filter(function (id) { return done[id]; }).length;
      var el = $(".part-count", part);
      el.textContent = got + "/" + ids.length;
      el.classList.toggle("is-complete", got === ids.length);
    });
    $("#progressText").textContent = n + " / " + lessons.length;
    $("#progressFill").style.width = (100 * n / lessons.length) + "%";
  }
  function save() { store.set(KEY, JSON.stringify(Object.keys(done))); }

  $$("[data-done]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.dataset.done;
      if (done[id]) delete done[id]; else done[id] = true;
      save(); renderProgress();
    });
  });
  $("#resetProgress").addEventListener("click", function () {
    done = {}; store.del(KEY); renderProgress();
  });
  renderProgress();

  /* ── "you are here" ──────────────────── */
  var links = {};
  $$("#toc a").forEach(function (a) { links[a.dataset.sec] = a; });
  var lastCurrent = null;
  function setCurrent(id) {
    if (id === lastCurrent) return;
    lastCurrent = id;
    Object.keys(links).forEach(function (k) {
      links[k].classList.toggle("is-current", k === id);
      if (k === id) links[k].setAttribute("aria-current", "location"); else links[k].removeAttribute("aria-current");
    });
    // Keep the part holding the current lesson open, and its link in view in the sidebar.
    var cur = links[id];
    if (cur) {
      var part = cur.closest("details");
      if (part && !part.open) part.open = true;
      var sb = $("#sidebar"), r = cur.getBoundingClientRect(), sr = sb.getBoundingClientRect();
      if (r.top < sr.top || r.bottom > sr.bottom) sb.scrollTop += r.top - sr.top - sr.height / 3;
    }
  }
  // The current lesson is the last one whose top has scrolled past a line near the top of the viewport.
  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () {
      ticking = false;
      var line = window.innerHeight * 0.3, current = lessons[0];
      for (var i = 0; i < lessons.length; i++) {
        if (document.getElementById(lessons[i]).getBoundingClientRect().top <= line) current = lessons[i];
      }
      // At the very bottom, the last lesson is current even if it is short.
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) current = lessons[lessons.length - 1];
      setCurrent(current);
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();

  /* ── modifier calculator ─────────────── */
  var scoreIn = $("#scoreInput");
  function fmt(n) { return (n >= 0 ? "+" : "−") + Math.abs(n); }
  function updateMod() {
    var s = +scoreIn.value;
    $("#scoreOut").textContent = s;
    $("#modOut").textContent = fmt(Math.floor((s - 10) / 2));
  }
  scoreIn.addEventListener("input", updateMod);
  updateMod();

  /* ── advantage roller ────────────────── */
  function d20() { return 1 + Math.floor(Math.random() * 20); }
  function dieHtml(v, keep) {
    var cls = "die" + (keep ? " keep" : "") + (keep && v === 20 ? " nat20" : "") + (keep && v === 1 ? " nat1" : "");
    return '<span class="' + cls + '">' + v + "</span>";
  }
  $$("#advRoller [data-mode]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var mode = btn.dataset.mode, out = $("#advOut"), a = d20(), html, kept;
      if (mode === "normal") {
        kept = a; html = dieHtml(a, true);
      } else {
        var b = d20();
        kept = mode === "adv" ? Math.max(a, b) : Math.min(a, b);
        var first = a === kept; // if both are equal, highlight the first
        html = dieHtml(a, first) + dieHtml(b, !first);
      }
      var note = kept === 20 ? " Natural 20!" : kept === 1 ? " Natural 1." : "";
      out.innerHTML = html + " → keep <strong>" + kept + "</strong>." + note;
    });
  });

  /* ── tabs ────────────────────────────── */
  $$("[data-tabs]").forEach(function (group) {
    var tabs = $$('[role="tab"]', group);
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t); });
      t.addEventListener("keydown", function (e) {
        var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : null;
        if (j === null) return;
        e.preventDefault();
        select(tabs[(j + tabs.length) % tabs.length], true);
      });
    });
  });

  /* ── class filter ────────────────────── */
  var chips = $$(".class-filter .chip");
  chips.forEach(function (chip) {
    chip.setAttribute("aria-pressed", String(chip.classList.contains("is-on")));
    chip.addEventListener("click", function () {
      var role = chip.dataset.role;
      chips.forEach(function (c) {
        var on = c === chip;
        c.classList.toggle("is-on", on);
        c.setAttribute("aria-pressed", String(on));
      });
      $$("#classGrid .class-card").forEach(function (card) {
        card.hidden = role !== "all" && card.dataset.roles.split(" ").indexOf(role) === -1;
      });
    });
  });

  /* ── glossary search ─────────────────── */
  var entries = $$("#glossList > div").map(function (el) {
    var dt = $("dt", el), dd = $("dd", el);
    return { el: el, dt: dt, dd: dd, term: dt.textContent, def: dd.textContent, keys: (el.dataset.keys || "").toLowerCase() };
  });
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function highlight(text, q) {
    if (!q) return esc(text);
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>" + esc(text.slice(i + q.length));
  }
  var search = $("#glossSearch");
  function filter() {
    var q = search.value.trim().toLowerCase(), shown = 0;
    entries.forEach(function (e) {
      var hit = !q || e.term.toLowerCase().indexOf(q) >= 0 || e.def.toLowerCase().indexOf(q) >= 0 || e.keys.indexOf(q) >= 0;
      e.el.hidden = !hit;
      if (hit) shown++;
      e.dt.innerHTML = highlight(e.term, q);
      e.dd.innerHTML = highlight(e.def, q);
    });
    $("#glossEmpty").hidden = shown > 0;
    $("#glossCount").textContent = q ? shown + " of " + entries.length : entries.length + " terms";
  }
  search.addEventListener("input", filter);
  filter();
})();
