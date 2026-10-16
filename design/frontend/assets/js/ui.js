/* Afterward shared UI helpers for the prototype: escaping, icons, status chips, the site
   header, the prototype bar, the Story guide dialog, theme and announcements. */
(function () {
  "use strict";
  const SPRITE = "assets/icons/sprite.svg";

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls) => `<svg class="icon ${cls || ""}" aria-hidden="true" focusable="false"><use href="${SPRITE}#i-${name}"></use></svg>`;
  const status = (st, extra) => `<span class="status status--${st.kind} ${extra || ""}">${icon(st.icon || (window.AW && AW.ICON[st.kind]) || "dot")}${esc(st.text)}</span>`;
  const chip = (kind, text, extra) => status({ kind, text, icon: window.AW ? AW.ICON[kind] : "dot" }, extra);
  const EVL = { writing: ["ev--writing", "Provider confirmed in writing", "mail"], family: ["ev--family", "Family confirmed", "user"], statement: ["ev--statement", "Observed on a statement", "money"], unverified: ["ev--unverified", "Unverified", "question"], spoken: ["ev--spoken", "Said on a call, not in writing", "phone"], sim: ["sim-tag", "Simulated", "ring"] };
  const evLabel = (k) => { const e = EVL[k]; if (!e) return ""; return k === "sim" ? `<span class="sim-tag">${icon("ring", "icon--sm")}Simulated</span>` : `<span class="ev ${e[0]}">${icon(e[2], "icon--sm")}${e[1]}</span>`; };
  const simTag = (text) => `<span class="sim-tag">${icon("ring", "icon--sm")}${esc(text || "Simulated")}</span>`;
  const compactMark = () => `<svg class="brand__compact" viewBox="0 0 32 32" aria-hidden="true"><path d="M5.66 17.24A11 11 0 0 1 26.34 17.24" fill="none" stroke="var(--c-ink)" stroke-width="3" stroke-linecap="round"/><path d="M9.5 21A6.5 6.5 0 0 1 22.5 21Z" fill="var(--c-dawn)"/><path d="M4 21H28" stroke="var(--c-ink)" stroke-width="3" stroke-linecap="round"/></svg>`;
  // Full lockup drawn with live tokens so it follows light/dark automatically.
  function lockup(cls) {
    return `<svg class="${cls || "brand__lockup"}" viewBox="0 0 633.45 94" role="img" aria-label="Afterward"><use href="assets/brand/afterward-lockup-tokens.svg#lockup"></use></svg>`;
  }

  const PAGES = [
    { id: "index", href: "index.html", label: "Start", icon: "horizon" },
    { id: "desk", href: "desk.html", label: "Case desk", icon: "desk" },
    { id: "family", href: "family.html", label: "Family", icon: "users" },
    { id: "call", href: "call.html", label: "Call room", icon: "phone" },
    { id: "provider", href: "provider.html", label: "Provider console", icon: "building" },
    { id: "proofs", href: "proofs.html", label: "Proofs", icon: "flask" },
    { id: "style", href: "style.html", label: "Style guide", icon: "palette" },
  ];

  /* ---------- Theme ---------- */
  const THEME_KEY = "afterward.theme";
  function getTheme() { try { return localStorage.getItem(THEME_KEY) || "auto"; } catch (e) { return "auto"; } }
  function setTheme(t) { try { localStorage.setItem(THEME_KEY, t); } catch (e) { /* ignore */ } applyTheme(); }
  function applyTheme() { const t = getTheme(); if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t); }
  applyTheme();

  /* ---------- Announcements ---------- */
  let live;
  function announce(text, opts) {
    if (!text) return;
    if (!live) { live = document.createElement("div"); live.className = "visually-hidden"; live.setAttribute("aria-live", "polite"); live.id = "aw-live"; document.body.appendChild(live); }
    live.textContent = "";
    setTimeout(() => { live.textContent = text; }, 30);
    if (!opts || opts.toast !== false) toast(text);
  }
  function toast(text) {
    let wrap = document.querySelector(".toasts");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "toasts"; wrap.setAttribute("aria-hidden", "true"); document.body.appendChild(wrap); }
    const t = document.createElement("div");
    t.className = "toast";
    t.innerHTML = `${icon("check")}<span>${esc(text)}</span>`;
    wrap.appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }

  /* ---------- Shell: prototype bar and header ---------- */
  function shell(pageId, opts) {
    opts = opts || {};
    const skip = document.createElement("a");
    skip.className = "skip-link"; skip.href = "#main"; skip.textContent = "Skip to content";
    document.body.prepend(skip);

    const bar = document.createElement("div");
    bar.className = "protobar"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Prototype controls");
    skip.after(bar);

    const header = document.createElement("header");
    header.className = "site-header";
    header.innerHTML = `<div class="wrap ${opts.wide ? "wrap--wide" : ""} site-header__inner">
      <a class="brand" href="index.html" aria-label="Afterward, start page">${lockup()}</a>
      ${opts.context ? `<span class="brand__context">${esc(opts.context)}</span>` : ""}
      <button class="btn btn--quiet btn--sm nav__toggle" type="button" aria-expanded="false" aria-controls="site-nav">${icon("chevron-down")}Menu</button>
      <nav class="nav" id="site-nav" aria-label="Surfaces">${PAGES.map((p) => `<a href="${p.href}" ${p.id === pageId ? 'aria-current="page"' : ""}>${icon(p.icon)}${p.label}</a>`).join("")}</nav>
    </div>`;
    bar.after(header);
    const toggle = header.querySelector(".nav__toggle"), nav = header.querySelector(".nav");
    toggle.addEventListener("click", () => { const open = toggle.getAttribute("aria-expanded") !== "true"; toggle.setAttribute("aria-expanded", String(open)); nav.dataset.open = String(open); });

    renderBar(bar, opts);
    if (window.AW) AW.subscribe((s, local) => { renderBar(bar, opts); if (local && s.announce) announce(s.announce); });
    buildStoryDialog();
  }

  function renderBar(bar, opts) {
    const cur = window.AW ? AW.currentStep() : null;
    const theme = getTheme();
    bar.innerHTML = `<div class="wrap ${opts.wide ? "wrap--wide" : ""} protobar__inner">
      <span class="protobar__label">${icon("ring")}Prototype</span>
      <span class="protobar__note">Fictional family · local mock state · nothing is sent</span>
      <span class="protobar__spacer"></span>
      ${cur ? `<span class="protobar__step">Next in the story: <b>${cur.n}. ${esc(cur.title)}</b> <a href="${cur.href}">${esc(cur.where)}</a></span>` : window.AW ? `<span class="protobar__step"><b>Core story complete.</b> Side scenarios are in the guide.</span>` : ""}
      <button class="btn btn--sim btn--sm" type="button" data-open-story>${icon("horizon")}Story guide</button>
      <div class="segmented" role="group" aria-label="Colour theme">
        ${["auto", "light", "dark"].map((t) => `<button type="button" data-theme-set="${t}" aria-pressed="${theme === t}" title="${t[0].toUpperCase() + t.slice(1)} theme">${icon(t === "auto" ? "contrast" : t === "light" ? "sun" : "moon")}<span class="visually-hidden-sm">${t[0].toUpperCase() + t.slice(1)}</span></button>`).join("")}
      </div>
    </div>`;
    bar.querySelector("[data-open-story]").addEventListener("click", openStory);
    bar.querySelectorAll("[data-theme-set]").forEach((b) => b.addEventListener("click", () => { setTheme(b.dataset.themeSet); renderBar(bar, opts); }));
  }

  /* ---------- Story guide ---------- */
  let dialog;
  function buildStoryDialog() {
    if (!window.AW || dialog) return;
    dialog = document.createElement("dialog");
    dialog.className = "dialog";
    dialog.setAttribute("aria-labelledby", "story-title");
    document.body.appendChild(dialog);
    dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  }
  function storyBody() {
    const s = AW.state, cur = AW.currentStep();
    const steps = AW.STEPS.map((x) => {
      const done = x.done(s), isCur = cur && cur.n === x.n;
      return `<li class="step ${done ? "is-done" : ""} ${isCur ? "is-current" : ""}">
        <span class="step__marker" aria-hidden="true">${done ? icon("check", "icon--sm") : x.n}</span>
        <span class="step__title">${esc(x.title)}<span class="visually-hidden">${done ? " (done)" : isCur ? " (next)" : ""}</span></span>
        <span class="step__where">${esc(x.where)}</span>
        <button class="btn btn--sm" type="button" data-setup="core:${x.n}">Set up and open</button>
      </li>`;
    }).join("");
    const side = AW.SIDE.map((x) => `<li class="step"><span class="step__marker" aria-hidden="true">${icon("dot", "icon--sm")}</span>
        <span class="step__title">${esc(x.title)}</span><span class="step__where">${esc(x.where)}</span>
        <button class="btn btn--sm" type="button" data-setup="side:${x.id}">Set up and open</button></li>`).join("");
    return `<div class="dialog__head"><h2 class="h3" id="story-title">Story guide</h2><button class="btn btn--quiet btn--sm" type="button" data-close>${icon("close")}Close</button></div>
      <div class="dialog__body stack">
        <p class="secondary small">"Set up and open" replays the mock state to just before that moment and opens the right page. Use the pages normally from there. Everything happens in this browser only.</p>
        <div class="horizon">Core story</div>
        <ol class="steps" role="list">${steps}</ol>
        <div class="horizon">Side scenarios</div>
        <ul class="steps" role="list">${side}</ul>
        <div class="cluster cluster--between"><button class="btn btn--danger btn--sm" type="button" data-setup="reset">${icon("retry")}Reset to the start</button><span class="xsmall muted">${AW.logLength} mock actions recorded</span></div>
      </div>`;
  }
  function openStory() {
    buildStoryDialog();
    dialog.innerHTML = storyBody();
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.querySelectorAll("[data-setup]").forEach((b) => b.addEventListener("click", () => {
      const v = b.dataset.setup;
      if (v === "reset") { AW.reset([]); dialog.close(); announce("Prototype reset to the start of the story."); return; }
      const [kind, id] = v.split(":");
      const item = kind === "core" ? AW.STEPS.find((x) => String(x.n) === id) : AW.SIDE.find((x) => x.id === id);
      AW.reset(item.setup);
      const target = new URL(item.href, location.href);
      if (target.pathname === location.pathname && target.search === location.search) { dialog.close(); announce(`Set up: ${item.title}`); if (target.hash) location.hash = target.hash; return; }
      location.href = item.href;
    }));
    dialog.showModal();
  }

  /* ---------- Small helpers ---------- */
  function on(root, sel, evt, fn) { root.addEventListener(evt, (e) => { const t = e.target.closest(sel); if (t && root.contains(t)) fn(e, t); }); }
  function param(name) { return new URLSearchParams(location.search).get(name); }
  function focusFirst(el) { if (!el) return; const f = el.querySelector("button:not([disabled]), a[href], input, textarea, select"); if (f) f.focus({ preventScroll: false }); }

  window.UI = { esc, icon, status, chip, evLabel, simTag, compactMark, lockup, shell, announce, toast, openStory, on, param, focusFirst, setTheme, getTheme };
})();
