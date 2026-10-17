/* Autoplay: a hands-free 2-minute run of the guided tour, for screen recording.
 * Real steps run through the same showcase endpoints; live moments are typed in, then sent.
 * Voice: server TTS when a key is configured, else the browser voice, else timed captions.
 * Keys: p pause, s skip, h hide controls, Esc exit. State survives page changes in sessionStorage. */
(function () {
  "use strict";
  var KEY = "afterward.autoplay";
  var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var cfg = null, st = null, ui = null, paused = false, hidden = false, gen = 0, audio = null;
  var cache = {};

  function read() { try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function write() { try { if (st) sessionStorage.setItem(KEY, JSON.stringify(st)); else sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ } }
  function api(path, body) {
    var o = { credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body !== undefined) { o.method = "POST"; o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
    return fetch(path, o).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
    });
  }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
  function path(u) { return String(u || "").replace(/\/+$/, "") || "/"; }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, reduce ? Math.min(ms, 60) : ms); }); }
  // Waits while unpaused; resolves false if this stop was superseded (skip/exit).
  function wait(ms, g) {
    return new Promise(function (resolve) {
      var left = ms;
      (function tick() {
        if (g !== gen) { resolve(false); return; }
        if (!paused) left -= 100;
        if (left <= 0) resolve(true); else setTimeout(tick, 100);
      })();
    });
  }

  // Silent boxes: what the full product does at each stop (shown, not spoken).
  var CAPS = {
    welcome: ["Families talk to it in Telegram: voice notes, photos, buttons", "Works for months: follow-ups, final bills, refunds", "Every step is a real database row you can audit"],
    intake: ["Real voice notes are transcribed, then read by the model", "Any fact without a quote from the family is dropped", "One summary card to confirm; nothing is sent before that"],
    discover: ["Connect a household inbox, or his own mailbox with stated authority", "Headers first; a message is read only when the family ticks it", "Photos of bills and bank statements add accounts too"],
    confirm: ["Nothing is planned until the family says an account is his", "Not his / Shared or not sure are recorded and audited", "Legal, tax and government bodies are hand-back only"],
    dependency: ["Asks what could be lost: shared use, login codes, memories", "The answer becomes enforced conditions, not notes", "Linked accounts stay protected until the link is resolved"],
    send: ["Approval is bound to the exact plan version", "Sent through Gmail to approved addresses only", "A durable job runner follows up and reconciles uncertain sends"],
    provider: ["Replies are polled from the inbox automatically", "Unapproved or spoofed senders are held, never read by the model", "The model reads the reply; code checks it against the plan"],
    caught: ["“Done” needs evidence plus every condition holding", "Unapproved contracts and broken conditions are flagged", "The family decides the next step with one tap"],
    call: ["Live voice agent over WebRTC; you talk, it answers", "It can note an offer but has no way to accept one", "Only a server-built, family-approved sentence is ever spoken as acceptance"],
    clock: ["Real follow-ups fire on schedule, months later if needed", "The family is asked before anything is sent again", "Money is tracked as promised vs evidenced"],
    handback: ["Probate, tax, benefits and certified copies are prepared, not filed", "A phone photo is never treated as a certified copy", "The family marks a hand-back step done; it stays 'stated' until evidenced"],
    finish: ["Honest answer: what is done with evidence, what is open", "No 'we found everything' claim, ever", "Coverage shows what was and was not searched"]
  };
  var FAST = "Fast-forward demo: lines are typed for you and weeks are skipped to save time. Every step runs the real system.";

  // ---------- shell ----------
  function build() {
    if (ui) return;
    var root = el("div", "ap");
    var spot = el("div", "ap-spot");
    var tag = el("div", "ap-tag");
    var cap = el("div", "ap-cap");
    var capText = el("p", "ap-cap__text");
    cap.appendChild(capText);
    var live = el("div", "ap-live");
    var liveMeta = el("div", "ap-live__meta");
    var liveBox = el("p", "ap-live__box");
    var liveOut = el("p", "ap-live__out");
    live.appendChild(liveMeta); live.appendChild(liveBox); live.appendChild(liveOut);
    var bar = el("div", "ap-bar");
    var prog = el("div", "ap-prog"); var fill = el("i"); prog.appendChild(fill);
    var bPause = el("button", "", "Pause"), bSkip = el("button", "", "Skip"), bExit = el("button", "", "Exit");
    [bPause, bSkip, bExit].forEach(function (b) { b.type = "button"; bar.appendChild(b); });
    var card = el("div", "ap-card"); card.hidden = true;
    var know = el("aside", "ap-know");
    var fast = el("div", "ap-fast", FAST);
    root.appendChild(spot); root.appendChild(tag); root.appendChild(live); root.appendChild(cap);
    root.appendChild(prog); root.appendChild(bar); root.appendChild(card);
    root.appendChild(know); root.appendChild(fast);
    document.body.appendChild(root);
    ui = { root: root, spot: spot, tag: tag, cap: cap, capText: capText, live: live, liveMeta: liveMeta, liveBox: liveBox, liveOut: liveOut, bar: bar, fill: fill, card: card, bPause: bPause, know: know };
    bPause.onclick = togglePause;
    bSkip.onclick = skip;
    bExit.onclick = exit;
    document.addEventListener("keydown", function (e) {
      if (!st) return;
      var t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (e.key === "h" || e.key === "H") { hidden = !hidden; ui.bar.classList.toggle("is-hidden", hidden); ui.fill.parentNode.classList.toggle("is-hidden", hidden); }
      else if (e.key === "p" || e.key === "P") togglePause();
      else if (e.key === "s" || e.key === "S") skip();
      else if (e.key === "Escape") exit();
    });
    window.addEventListener("resize", function () { if (ui && ui.cur) place(ui.cur); });
  }
  function togglePause() {
    paused = !paused;
    ui.bPause.textContent = paused ? "Resume" : "Pause";
    if (audio) { if (paused) audio.pause(); else audio.play().catch(function () {}); }
    try { if (window.speechSynthesis) { if (paused) speechSynthesis.pause(); else speechSynthesis.resume(); } } catch (e) { /* ignore */ }
  }
  function stopVoice() {
    if (audio) { try { audio.pause(); } catch (e) { /* ignore */ } audio = null; }
    try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { /* ignore */ }
  }
  function skip() { gen++; stopVoice(); next(); }
  function exit() {
    gen++; stopVoice(); st = null; write();
    if (ui) { ui.root.remove(); ui = null; }
  }

  // ---------- spotlight ----------
  function place(node) {
    ui.cur = node;
    if (!node) { ui.spot.className = "ap-spot ap-spot--none"; ui.spot.removeAttribute("style"); return; }
    var r = node.getBoundingClientRect(), pad = 10;
    ui.spot.className = "ap-spot";
    ui.spot.style.top = Math.max(4, r.top - pad) + "px";
    ui.spot.style.left = Math.max(4, r.left - pad) + "px";
    ui.spot.style.width = Math.min(window.innerWidth - 8, r.width + pad * 2) + "px";
    ui.spot.style.height = Math.min(window.innerHeight * 0.62, r.height + pad * 2) + "px";
  }
  function focusTarget(name) {
    var node = name ? document.querySelector('[data-tour="' + name + '"]') : null;
    // A button that opens a panel ("Did we finish?"): open it and show the panel itself.
    var opens = node && node.getAttribute("data-open");
    var panel = opens ? document.getElementById(opens) : null;
    if (panel) {
      // Non-modal, so the demo's captions stay above it (a modal dialog would cover them).
      if (!panel.open) {
        try {
          panel.show();
          panel.style.cssText += ";position:fixed;inset:0 0 0 auto;margin:0;z-index:8999;";
        } catch (e) { node.click(); }
      }
      return sleep(reduce ? 0 : 700).then(function () {
        var body = panel.querySelector(".drawer__body") || panel;
        place(body);
      });
    }
    if (node) {
      node.style.scrollMarginTop = "90px";
      node.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      node.classList.remove("ap-zoom"); void node.offsetWidth; node.classList.add("ap-zoom");
    }
    return sleep(reduce ? 0 : 650).then(function () { place(node); });
  }

  // ---------- voice and captions ----------
  function words(text) { return text.split(/\s+/).length; }
  function fetchAudio(text) {
    if (cache[text] !== undefined) return Promise.resolve(cache[text]);
    return fetch("/api/showcase/narrate", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: text }) })
      .then(function (r) { if (!r.ok) throw new Error("no voice"); return r.blob(); })
      .then(function (b) { cache[text] = URL.createObjectURL(b); return cache[text]; })
      .catch(function () { cache[text] = null; return null; });
  }
  function caption(text, g) {
    ui.cap.classList.remove("is-in"); ui.capText.textContent = "";
    var w = text.split(" "), i = 0, per = Math.max(95, Math.min(240, (words(text) * 300) / Math.max(1, w.length)));
    void ui.cap.offsetWidth; ui.cap.classList.add("is-in");
    (function add() {
      if (g !== gen || i >= w.length) return;
      var s = el("span", "ap-w", (i ? " " : "") + w[i++]); ui.capText.appendChild(s);
      setTimeout(add, reduce ? 0 : per * 0.8);
    })();
  }
  // Speaks `text`; resolves when it ends (or after a safe cap), false if superseded.
  function speak(text, g) {
    var capMs = Math.max(2000, words(text) * 290 + 900);
    return fetchAudio(text).then(function (url) {
      if (g !== gen) return false;
      if (url) {
        return new Promise(function (resolve) {
          var a = new Audio(url); a.playbackRate = 1.45; audio = a; var done = false;
          function fin(ok) { if (!done) { done = true; resolve(ok); } }
          a.onended = function () { fin(true); };
          a.onerror = function () { audio = null; browserVoice(text, g, capMs).then(fin); };
          a.play().catch(function () { audio = null; browserVoice(text, g, capMs).then(fin); });
          wait(capMs + 1500, g).then(fin);
        });
      }
      return browserVoice(text, g, capMs);
    });
  }
  function browserVoice(text, g, capMs) {
    return new Promise(function (resolve) {
      var done = false;
      function fin() { if (!done) { done = true; resolve(g === gen); } }
      try {
        if (window.speechSynthesis && window.SpeechSynthesisUtterance) {
          var u = new SpeechSynthesisUtterance(text);
          u.lang = "en-US"; u.rate = 1.5;
          var v = (speechSynthesis.getVoices() || []).filter(function (x) { return /^en/i.test(x.lang); })[0];
          if (v) u.voice = v;
          u.onend = fin; u.onerror = fin;
          speechSynthesis.speak(u);
        }
      } catch (e) { /* captions only */ }
      wait(capMs, g).then(fin);
    });
  }

  // ---------- typing a live moment ----------
  function typeInto(text, g) {
    return new Promise(function (resolve) {
      var i = 0;
      (function step() {
        if (g !== gen) { resolve(false); return; }
        if (paused) { setTimeout(step, 100); return; }
        i = reduce ? text.length : i + 1;
        ui.liveBox.textContent = text.slice(0, i);
        var page = document.getElementById("reply-text");
        if (page) page.value = text.slice(0, i);
        if (i < text.length) setTimeout(step, 9); else resolve(true);
      })();
    });
  }
  function liveMoment(s, g) {
    var role = { intake: "Sara", dependency: "Amina", reply: "Northline" }[s.live] || "";
    ui.live.classList.add("is-in");
    ui.liveMeta.textContent = "You are " + role + " (typed for you)";
    ui.liveOut.textContent = ""; ui.liveBox.textContent = "";
    return typeInto(s.hint, g).then(function (ok) {
      if (!ok) return false;
      ui.liveOut.textContent = "Sending to the real engine…";
      return api("/api/showcase/live/" + s.live, { text: s.hint }).then(function (res) {
        if (g !== gen) return false;
        if (!res.ok) { ui.liveOut.textContent = (res.data && res.data.error) || "That moment did not run."; return true; }
        var src = res.data.source || "Recorded model output";
        ui.liveOut.textContent = "";
        ui.liveOut.appendChild(el("b", "ap-src " + (src === "Live model" ? "is-live" : "is-rec"), src));
        ui.liveOut.appendChild(document.createTextNode("  " + (res.data.headline || "")));
        st.live = st.live || {}; st.live[s.id] = true; write();
        return true;
      });
    });
  }

  // ---------- the run ----------
  function card(title, sub, small) {
    ui.card.hidden = false; ui.card.classList.remove("is-in");
    ui.card.textContent = "";
    ui.card.appendChild(el("h1", "", title)); ui.card.appendChild(el("p", "", sub));
    if (small) ui.card.appendChild(el("small", "", small));
    void ui.card.offsetWidth; ui.card.classList.add("is-in");
  }
  function progress() { ui.fill.style.width = Math.round(((st.idx + 0.5) / cfg.stops.length) * 100) + "%"; }

  function runStop() {
    var g = ++gen, s = cfg.stops[st.idx], ap = s.autoplay || { say: s.text, dwell: 8 };
    build(); progress();
    ui.card.hidden = true; ui.live.classList.remove("is-in"); ui.liveBox.textContent = ""; ui.liveOut.textContent = "";
    ui.tag.textContent = (st.idx + 1) + " / " + cfg.stops.length + "  " + s.title;
    ui.tag.classList.remove("is-in"); void ui.tag.offsetWidth; ui.tag.classList.add("is-in");
    var items = CAPS[s.id] || [];
    ui.know.innerHTML = "";
    if (items.length) {
      ui.know.appendChild(el("p", "ap-know__h", "In the full product"));
      var ul = el("ul");
      items.forEach(function (t) { ul.appendChild(el("li", "", t)); });
      ui.know.appendChild(ul);
    }
    ui.know.classList.remove("is-in"); void ui.know.offsetWidth; if (items.length) ui.know.classList.add("is-in");
    var t0 = Date.now();
    if (!st.idx && !st.titled) {
      st.titled = true; write();
      card("Afterward — tell it once", "Paperwork after a death, handled honestly.", "Fictional demo. Browser demo, not a phone call.");
      return sleep(1400).then(function () { if (g === gen) { ui.card.hidden = true; return body(); } });
    }
    return body();

    function body() {
      if (g !== gen) return;
      return focusTarget(s.target).then(function () {
        if (g !== gen) return;
        var pre = Promise.resolve();
        if (s.run && s.run !== "reset" && !(st.ran || {})[s.id]) {
          // The real step ran before we arrived on this page (see next()); nothing to do here.
        }
        var voice = speak(ap.say, g);
        caption(ap.say, g);
        var work = s.live && !(st.live || {})[s.id] ? liveMoment(s, g) : Promise.resolve(true);
        return Promise.all([pre, voice, work]).then(function () {
          if (g !== gen) return;
          var spent = Date.now() - t0;
          return wait(Math.max(300, ap.dwell * 1000 - spent), g);
        }).then(function (ok) { if (ok) next(); });
      });
    }
  }

  // Runs the real step for stop i (before navigating to its page), then goes there.
  function prepare(i) {
    var s = cfg.stops[i];
    if (s.live || !s.run || s.run === "reset") return Promise.resolve();
    return api("/api/showcase/run-to", { step: s.run }).then(function () {});
  }
  function next() {
    if (!st) return;
    var i = st.idx + 1;
    if (i >= cfg.stops.length) return finish();
    gen++;
    // A live stop's earlier steps must exist first (e.g. discover/confirm before the Amina moment).
    var s = cfg.stops[i], need = { dependency: "confirm", reply: "send" }[s.live], pre = need ? api("/api/showcase/run-to", { step: need }) : Promise.resolve();
    Promise.resolve(pre).then(function () { return prepare(i); }).then(function () {
      st.idx = i; write();
      if (path(location.pathname) !== path(s.url)) { location.href = s.url; return; }
      runStop();
    });
  }
  function finish() {
    var g = ++gen;
    ui.live.classList.remove("is-in"); ui.cap.classList.remove("is-in"); ui.tag.classList.remove("is-in"); place(null);
    ui.fill.style.width = "100%";
    card("Afterward", "It tells the truth about what is done. AI proposes, code decides, the family approves.", "Fictional demo. Simulated parts are labelled.");
    var line = "Afterward. Tell it once, and it tells you the truth about what is done.";
    speak(line, g).then(function () { return wait(1800, g); }).then(function (ok) { if (ok) { exit(); } });
  }

  function begin() {
    api("/api/showcase/tour").then(function (res) {
      if (!res.ok || !res.data.stops) { window.alert("Sign in with the demo passcode first."); return; }
      cfg = res.data;
      try { sessionStorage.removeItem("afterward.tour"); } catch (e) { /* ignore */ }
      build();
      card("Afterward — tell it once", "Resetting the demo case…", "Fictional demo. Simulated parts are labelled.");
      api("/api/showcase/reset", {}).then(function () {
        st = { idx: 0, titled: false, live: {} }; write();
        var s = cfg.stops[0];
        if (path(location.pathname) !== path(s.url)) { location.href = s.url; return; }
        runStop();
      });
    });
  }
  function resume() {
    st = read();
    if (!st) return;
    api("/api/showcase/tour").then(function (res) {
      if (!res.ok || !res.data.stops) { st = null; write(); return; }
      cfg = res.data;
      var s = cfg.stops[st.idx];
      if (!s) { st = null; write(); return; }
      if (path(location.pathname) !== path(s.url)) { location.href = s.url; return; }
      runStop();
    });
  }

  function init() {
    document.querySelectorAll("[data-autoplay-start]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); begin(); });
    });
    if (read()) { resume(); return; }
    if (path(location.pathname) === "/showcase" && /[?&]autoplay=1/.test(location.search)) {
      try { history.replaceState(null, "", "/showcase"); } catch (e) { /* ignore */ }
      begin();
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
