/* Guided tour: a spotlight, a narration card, and real showcase steps that animate in.
 * State: sessionStorage for the UI position, Postgres (showcase snapshot) for the rest.
 * Targets are [data-tour="..."] elements. Every effect shown is a real database change. */
(function () {
  "use strict";

  var KEY = "afterward.tour";
  var reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var cfg = null;
  var idx = 0;
  var active = false;
  var ui = null;
  var target = null;
  var raf = 0;
  var recog = null;

  // ---------- small helpers ----------
  function readSession() {
    try { return JSON.parse(sessionStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; }
  }
  function writeSession(patch) {
    var cur = readSession();
    Object.keys(patch).forEach(function (k) { if (patch[k] === null) delete cur[k]; else cur[k] = patch[k]; });
    try { sessionStorage.setItem(KEY, JSON.stringify(cur)); } catch (e) { /* ignore */ }
  }
  function api(path, body) {
    var opts = { credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body !== undefined) {
      opts.method = "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    });
  }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function path(u) { return String(u || "").replace(/\/+$/, "") || "/"; }
  function stop() { return cfg.stops[idx]; }
  function saveState() {
    writeSession({ active: active, index: idx });
    return api("/api/showcase/tour/state", { active: active, index: idx });
  }

  // ---------- loading ----------
  function loadConfig() {
    return api("/api/showcase/tour").then(function (res) {
      if (!res.ok || !res.data.stops) return false;
      cfg = res.data;
      return true;
    });
  }

  function start() {
    loadConfig().then(function (ok) {
      if (!ok) { window.alert("Sign in with the demo passcode first."); return; }
      active = true;
      idx = 0;
      writeSession({ justRan: null });
      saveState();
      show(0);
    });
  }

  function resume() {
    var s = readSession();
    if (!s.active) return false;
    loadConfig().then(function (ok) {
      if (!ok) { writeSession({ active: null }); return; }
      active = true;
      idx = Math.max(0, Math.min(Number(s.index) || 0, cfg.stops.length - 1));
      show(idx, true);
    });
    return true;
  }

  function exit() {
    active = false;
    writeSession({ active: null, justRan: null });
    api("/api/showcase/tour/state", { active: false });
    stopListening();
    teardown();
  }

  // ---------- shell ----------
  function build() {
    if (ui) return;
    var root = el("div", "tour");
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-label", "Guided tour");
    var spot = el("div", "tour-spot");
    spot.setAttribute("aria-hidden", "true");
    var card = el("section", "tour-card");
    card.setAttribute("aria-live", "polite");
    var head = el("div", "tour-card__head");
    var count = el("span", "tour-count");
    var tag = el("span", "tour-tag");
    head.appendChild(count);
    head.appendChild(tag);
    var title = el("h2", "tour-title");
    var text = el("p", "tour-text");
    var body = el("div", "tour-body");
    var dots = el("div", "tour-dots");
    dots.setAttribute("aria-hidden", "true");
    var actions = el("div", "tour-actions");
    var back = el("button", "tour-btn tour-btn--ghost", "Back");
    back.type = "button";
    var run = el("button", "tour-btn tour-btn--run", "Run it");
    run.type = "button";
    var next = el("button", "tour-btn tour-btn--next", "Next");
    next.type = "button";
    var quit = el("button", "tour-exit", "Exit");
    quit.type = "button";
    quit.setAttribute("aria-label", "Exit the tour");
    actions.appendChild(back);
    actions.appendChild(run);
    actions.appendChild(next);
    card.appendChild(quit);
    card.appendChild(head);
    card.appendChild(title);
    card.appendChild(text);
    card.appendChild(body);
    card.appendChild(dots);
    card.appendChild(actions);
    root.appendChild(spot);
    root.appendChild(card);
    document.body.appendChild(root);
    ui = { root: root, spot: spot, card: card, count: count, tag: tag, title: title, text: text, body: body, dots: dots, back: back, run: run, next: next, quit: quit };
    back.addEventListener("click", function () { go(idx - 1); });
    next.addEventListener("click", function () { advance(); });
    quit.addEventListener("click", exit);
    run.addEventListener("click", function () { doRun(); });
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true);
    document.addEventListener("keydown", onKey);
    document.documentElement.classList.add("tour-on");
  }

  function teardown() {
    if (!ui) return;
    window.removeEventListener("resize", schedule);
    window.removeEventListener("scroll", schedule, true);
    document.removeEventListener("keydown", onKey);
    ui.root.classList.add("is-leaving");
    var root = ui.root;
    ui = null;
    target = null;
    document.documentElement.classList.remove("tour-on");
    window.setTimeout(function () { if (root.parentNode) root.parentNode.removeChild(root); }, reduce ? 0 : 220);
  }

  function onKey(e) {
    if (!active || !ui) return;
    var t = e.target;
    var typing = t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT" || t.isContentEditable);
    if (e.key === "Escape") { e.preventDefault(); exit(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "ArrowRight") { e.preventDefault(); advance(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(idx - 1); }
  }

  // ---------- navigation ----------
  function go(i) {
    if (i < 0 || i >= cfg.stops.length) return;
    stopListening();
    idx = i;
    saveState();
    show(i);
  }

  function advance() {
    var s = stop();
    if (idx >= cfg.stops.length - 1) { exit(); return; }
    // A run-stop that was skipped still runs, so the next page has something to show.
    if (s.run && s.run !== "reset" && !cfg.done[s.run]) {
      setBusy(true, "Running it…");
      api("/api/showcase/run-to", { step: s.run }).then(function (res) {
        setBusy(false);
        if (!res.ok) { message((res.data && res.data.error) || "That step could not run.", true); return; }
        if (res.data.step) cfg.done[res.data.step] = res.data;
        go(idx + 1);
      });
      return;
    }
    if (s.run === "reset" && !cfg.started) { doRun(true); return; }
    go(idx + 1);
  }

  function show(i, resumed) {
    var s = cfg.stops[i];
    if (path(location.pathname) !== path(s.url)) {
      writeSession({ active: true, index: i });
      location.href = s.url;
      return;
    }
    build();
    render(s, i, resumed);
  }

  // ---------- rendering a stop ----------
  function render(s, i, resumed) {
    var total = cfg.stops.length;
    ui.card.classList.remove("is-in");
    ui.count.textContent = (i + 1) + " / " + total;
    ui.title.textContent = s.title;
    ui.text.textContent = s.text;
    ui.body.textContent = "";
    ui.tag.textContent = "";
    ui.tag.className = "tour-tag";
    ui.back.disabled = i === 0;
    ui.next.textContent = i === total - 1 ? "Finish" : "Next";
    ui.run.hidden = !s.run;
    ui.run.disabled = false;
    ui.run.textContent = s.run_label || "Run it";
    renderDots(i, total);

    var done = s.run ? cfg.done[s.run] : null;
    var just = readSession().justRan === s.id;
    if (s.run && s.run !== "reset" && done) {
      ui.run.hidden = true;
      showResult(s, done, just && !reduce);
    } else if (s.run === "reset" && just) {
      ui.run.hidden = true;
      var ok = el("p", "tour-result tour-pop", "Clean case seeded. Nothing has run yet.");
      ui.body.appendChild(ok);
    }
    if (s.live) renderLive(s);
    if (just) writeSession({ justRan: null });

    target = s.target ? document.querySelector('[data-tour="' + s.target + '"]') : null;
    if (target) {
      // Tall targets sit at the top so the card at the bottom does not cover them.
      var tall = target.getBoundingClientRect().height > window.innerHeight * 0.38;
      target.style.scrollMarginTop = "76px";
      target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: tall ? "start" : "center" });
    }
    window.setTimeout(function () {
      if (!ui) return;
      place(true);
      ui.card.classList.add("is-in");
      if (just && !reduce) reveal(target);
      if (just && reduce) target && target.classList.add("tour-flash-static");
    }, resumed ? 80 : (reduce ? 0 : 320));
    window.setTimeout(place, reduce ? 0 : 700);
  }

  function renderDots(i, total) {
    ui.dots.textContent = "";
    for (var n = 0; n < total; n++) {
      var d = el("i", n === i ? "is-now" : (n < i ? "is-past" : ""));
      ui.dots.appendChild(d);
    }
  }

  function schedule() {
    if (raf) return;
    raf = window.requestAnimationFrame(function () { raf = 0; place(false); });
  }

  // Place the spotlight around the target and park the card at the side with more room.
  function place(first) {
    if (!ui) return;
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var spot = ui.spot;
    if (!target || !document.body.contains(target)) {
      spot.classList.add("tour-spot--none");
      ui.card.classList.add("tour-card--center");
      ui.card.classList.remove("tour-card--left", "tour-card--top");
      return;
    }
    ui.card.classList.remove("tour-card--center");
    var r = target.getBoundingClientRect();
    var pad = 10;
    var top = Math.max(6, r.top - pad);
    var left = Math.max(6, r.left - pad);
    var width = Math.min(vw - 12, r.width + pad * 2);
    var height = Math.min(vh - 12, r.height + pad * 2);
    spot.classList.remove("tour-spot--none");
    if (first) spot.classList.add("no-anim");
    spot.style.top = top + "px";
    spot.style.left = left + "px";
    spot.style.width = width + "px";
    spot.style.height = height + "px";
    if (first) { void spot.offsetWidth; spot.classList.remove("no-anim"); }
    dock(r, vw, vh);
  }

  // Dock the card in the viewport corner that hides the least of the highlighted target.
  function dock(r, vw, vh) {
    var card = ui.card, m = 20, narrow = vw <= 760;
    var cw = narrow ? vw - 2 * 16 : Math.min(26 * 16, vw - 40), ch = Math.min(card.offsetHeight || 260, vh - 2 * m);
    var corners = narrow ? [[false, false], [false, true]] : [[false, false], [true, false], [false, true], [true, true]];
    var best = null, bestArea = Infinity;
    corners.forEach(function (c) {
      var left = narrow ? 16 : (c[0] ? m : vw - m - cw), top = c[1] ? m : vh - m - ch;
      var ox = Math.max(0, Math.min(left + cw, r.right) - Math.max(left, r.left));
      var oy = Math.max(0, Math.min(top + ch, r.bottom) - Math.max(top, r.top));
      var area = ox * oy;
      if (area < bestArea - 1) { bestArea = area; best = c; }
    });
    best = best || corners[0];
    card.classList.toggle("tour-card--left", !narrow && best[0]);
    card.classList.toggle("tour-card--top", best[1]);
  }

  function setBusy(on, label) {
    if (!ui) return;
    ui.card.classList.toggle("is-busy", on);
    ui.run.disabled = on;
    ui.next.disabled = on;
    ui.back.disabled = on || idx === 0;
    if (on && label) message(label, false, true);
  }

  function message(text, isError, quiet) {
    if (!ui) return;
    var old = ui.body.querySelector(".tour-msg");
    if (old) old.parentNode.removeChild(old);
    var p = el("p", "tour-msg" + (isError ? " is-error" : "") + (quiet ? " is-quiet" : ""), text);
    p.setAttribute("role", isError ? "alert" : "status");
    ui.body.insertBefore(p, ui.body.firstChild);
  }

  // ---------- run it ----------
  function doRun(thenNext) {
    var s = stop();
    if (!s.run) return;
    setBusy(true, s.run === "reset" ? "Resetting…" : "Running the real step…");
    var req = s.run === "reset" ? api("/api/showcase/reset", {}) : api("/api/showcase/run-to", { step: s.run });
    req.then(function (res) {
      setBusy(false);
      if (!res.ok) { message((res.data && res.data.error) || "That step could not run.", true); return; }
      if (thenNext) { go(idx + 1); return; }
      writeSession({ justRan: s.id, active: true, index: idx });
      location.reload();
    });
  }

  function showResult(s, done, animate) {
    var box = el("div", "tour-result" + (animate ? " tour-pop" : ""));
    var check = el("span", "tour-result__mark", "Done");
    var head = el("p", "tour-result__head");
    head.appendChild(check);
    head.appendChild(countText(done.headline || "", animate));
    box.appendChild(head);
    if (s.show === "details" && done.details && done.details.length) {
      var list = el("ul", "tour-list");
      done.details.slice(0, 4).forEach(function (line, n) {
        var li = el("li", "", line);
        li.style.setProperty("--i", String(n));
        list.appendChild(li);
      });
      box.appendChild(list);
    }
    var sim = (done.simulated || [])[0];
    if (sim) box.appendChild(el("p", "tour-sim", "Simulated: " + sim));
    ui.body.appendChild(box);
  }

  // Numbers in a headline count up from zero (skipped under reduced motion).
  function countText(text, animate) {
    var span = el("span", "tour-headline");
    var parts = String(text).split(/(\b\d{1,3}\b)/);
    parts.forEach(function (part) {
      if (/^\d{1,3}$/.test(part)) {
        var n = el("b", "tour-num", animate ? "0" : part);
        span.appendChild(n);
        if (animate) countUp(n, Number(part));
      } else {
        span.appendChild(document.createTextNode(part));
      }
    });
    return span;
  }
  function countUp(node, to) {
    if (to <= 0) { node.textContent = String(to); return; }
    var t0 = null;
    function tick(ts) {
      if (t0 === null) t0 = ts;
      var p = Math.min(1, (ts - t0) / 900);
      node.textContent = String(Math.round(to * (1 - Math.pow(1 - p, 3))));
      if (p < 1) window.requestAnimationFrame(tick);
    }
    window.setTimeout(function () { window.requestAnimationFrame(tick); }, 250);
  }

  // New rows pop in one after another and the target flashes once.
  function reveal(node) {
    if (!node) return;
    node.classList.add("tour-flash");
    window.setTimeout(function () { node.classList.remove("tour-flash"); }, 1800);
    var items = node.querySelectorAll("li, .tile, .cand, .fcard, article, .chip, .status");
    var limit = Math.min(items.length, 40);
    for (var n = 0; n < limit; n++) {
      items[n].style.setProperty("--tour-i", String(n));
      items[n].classList.add("tour-pop-in");
    }
    window.setTimeout(function () {
      for (var m = 0; m < limit; m++) items[m].classList.remove("tour-pop-in");
    }, 1800 + limit * 40);
  }

  // ---------- live moments: the presenter plays the role ----------
  function sourceTag(label) {
    var live = label === "Live model";
    ui.tag.textContent = label;
    ui.tag.className = "tour-tag " + (live ? "tour-tag--live" : "tour-tag--rec");
    ui.tag.title = live ? "The real model read these words" : "A recorded model output is shown, not a live reading";
  }

  function renderLive(s) {
    var saved = cfg.state && cfg.state.live ? cfg.state.live[s.live] : null;
    if (saved) {
      sourceTag(saved.source || "Recorded model output");
      showLiveResult(s, saved, false);
      return;
    }
    var box = el("div", "tour-live");
    var area = el("textarea", "tour-input");
    area.rows = 3;
    area.placeholder = s.placeholder || "Type here";
    area.setAttribute("aria-label", s.placeholder || "What you would say");
    area.maxLength = 1500;
    var row = el("div", "tour-live__row");
    var hint = el("button", "tour-chipbtn", "Use suggested line");
    hint.type = "button";
    hint.addEventListener("click", function () { area.value = s.hint || ""; area.focus(); });
    var mic = el("button", "tour-chipbtn tour-mic", "Speak");
    mic.type = "button";
    var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) {
      mic.hidden = true;
    } else {
      mic.addEventListener("click", function () { toggleMic(Rec, area, mic); });
    }
    var send = el("button", "tour-btn tour-btn--run", "Send");
    send.type = "button";
    row.appendChild(hint);
    row.appendChild(mic);
    row.appendChild(send);
    box.appendChild(area);
    box.appendChild(row);
    var modelNote = cfg.model === "Live model" ? "A live model will read this." : "No model key here: a recorded reading will be shown, labelled as such.";
    var note = el("p", "tour-sim", (Rec ? "Speak or type. " : "Typing only here. ") + modelNote);
    box.appendChild(note);
    ui.body.appendChild(box);
    send.addEventListener("click", function () { submitLive(s, area, send); });
    area.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submitLive(s, area, send); }
    });
    window.setTimeout(function () { try { area.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }, 400);
  }

  function toggleMic(Rec, area, btn) {
    if (recog) { stopListening(); return; }
    try {
      recog = new Rec();
      recog.lang = "en-US";
      recog.interimResults = true;
      recog.continuous = true;
      var base = area.value ? area.value.replace(/\s*$/, " ") : "";
      recog.onresult = function (ev) {
        var said = "";
        for (var n = 0; n < ev.results.length; n++) said += ev.results[n][0].transcript;
        area.value = base + said;
      };
      recog.onend = function () { recog = null; btn.classList.remove("is-on"); btn.textContent = "Speak"; };
      recog.onerror = function () { recog = null; btn.classList.remove("is-on"); btn.textContent = "Speak"; };
      recog.start();
      btn.classList.add("is-on");
      btn.textContent = "Listening… tap to stop";
    } catch (e) { recog = null; }
  }
  function stopListening() {
    if (recog) { try { recog.stop(); } catch (e) { /* ignore */ } recog = null; }
  }

  function submitLive(s, area, send) {
    var text = (area.value || "").trim();
    if (!text) { message("Say or type something first.", true); return; }
    stopListening();
    var page = s.live === "reply" ? document.getElementById("reply-text") : null;
    if (page) page.value = text; // the provider console shows what the presenter wrote
    send.disabled = true;
    area.disabled = true;
    ui.card.classList.add("is-busy");
    message("The model is reading it…", false, true);
    api("/api/showcase/live/" + s.live, { text: text }).then(function (res) {
      if (!ui) return;
      ui.card.classList.remove("is-busy");
      if (!res.ok) {
        send.disabled = false;
        area.disabled = false;
        message((res.data && res.data.error) || "That did not work. Try again.", true);
        return;
      }
      cfg.state.live = cfg.state.live || {};
      cfg.state.live[s.live] = res.data;
      cfg.done[liveStep(s.live)] = { step: liveStep(s.live), headline: res.data.headline };
      ui.body.textContent = "";
      sourceTag(res.data.source);
      showLiveResult(s, res.data, true);
    });
  }
  function liveStep(kind) { return kind === "intake" ? "intent" : kind; }

  function showLiveResult(s, data, animate) {
    var box = el("div", "tour-result" + (animate ? " tour-pop" : ""));
    if (data.note) box.appendChild(el("p", "tour-sim", data.note));
    if (s.live === "intake") intakeCard(box, data);
    else if (s.live === "dependency") dependencyCard(box, data);
    else replyCard(box, data);
    ui.body.appendChild(box);
    stagger(box);
  }

  function stagger(box) {
    var rows = box.querySelectorAll(".tour-row, .tour-diff__col li");
    for (var n = 0; n < rows.length; n++) rows[n].style.setProperty("--i", String(n));
  }

  function quoteLine(parent, label, item) {
    if (!item) return;
    var row = el("div", "tour-row");
    row.appendChild(el("span", "tour-row__k", label));
    var v = el("span", "tour-row__v");
    v.appendChild(el("b", "", item.value));
    if (item.quote) v.appendChild(el("q", "", item.quote));
    row.appendChild(v);
    parent.appendChild(row);
  }

  function intakeCard(box, data) {
    var c = data.card || {};
    box.appendChild(el("p", "tour-said", "“" + (data.text || "") + "”"));
    quoteLine(box, "Who", c.deceased);
    if (c.died) quoteLine(box, "Died", c.died);
    else if (c.date_kept_on_file) box.appendChild(rowText("Died", "Not stated in her words; the date on file is kept"));
    quoteLine(box, "Her role", c.role);
    (c.keep || []).forEach(function (q) { quoteLine(box, "Keep", q); });
    (c.stop || []).forEach(function (q) { quoteLine(box, "Stop", q); });
    (c.protect || []).forEach(function (q) { quoteLine(box, "Protect", q); });
    var drop = el("p", "tour-drop");
    drop.appendChild(countText(String(c.dropped || 0) + " claims dropped for lacking a quote", true));
    box.appendChild(drop);
  }

  function rowText(k, v) {
    var row = el("div", "tour-row");
    row.appendChild(el("span", "tour-row__k", k));
    row.appendChild(el("span", "tour-row__v", v));
    return row;
  }

  var COND = { number_kept: "Number kept", voicemail_preserved: "Voicemail kept", document_required: "Keep the document" };

  function dependencyCard(box, data) {
    var c = data.card || {};
    box.appendChild(el("p", "tour-said", "“" + (c.quote || "") + "”"));
    var diff = el("div", "tour-diff");
    var a = el("div", "tour-diff__col");
    a.appendChild(el("h3", "", "Plan v" + ((c.before || {}).version || 1)));
    var al = el("ul", "");
    al.appendChild(el("li", "tour-cond tour-cond--none", "Transfer, no conditions"));
    a.appendChild(al);
    var arrow = el("span", "tour-diff__arrow", "→");
    arrow.setAttribute("aria-hidden", "true");
    var b = el("div", "tour-diff__col tour-diff__col--new");
    b.appendChild(el("h3", "", "Plan v" + ((c.after || {}).version || 2)));
    var bl = el("ul", "");
    ((c.after || {}).conditions || []).forEach(function (k) {
      bl.appendChild(el("li", "tour-cond tour-cond--new", "+ " + (COND[k] || k.replace(/_/g, " "))));
    });
    b.appendChild(bl);
    diff.appendChild(a);
    diff.appendChild(arrow);
    diff.appendChild(b);
    box.appendChild(diff);
    if (c.linked) box.appendChild(el("p", "tour-sim", "Linked by code: " + c.linked + " depends on this number. Sara must approve v" + ((c.after || {}).version || 2) + "."));
  }

  var STATE_CLASS = { "Holding": "ok", "Broken": "bad", "Not approved": "bad", "Not stated": "warn" };

  function replyCard(box, data) {
    var c = data.card || {};
    box.appendChild(el("p", "tour-said", "“" + (data.text || "") + "”"));
    (c.rows || []).forEach(function (r) {
      var row = el("div", "tour-row tour-row--check");
      row.appendChild(el("span", "tour-row__k", r.label));
      var v = el("span", "tour-row__v");
      v.appendChild(el("span", "tour-state tour-state--" + (STATE_CLASS[r.state] || "warn"), r.state));
      if (r.quote) v.appendChild(el("q", "", r.quote));
      row.appendChild(v);
      box.appendChild(row);
    });
    var bad = c.kind !== "resolved";
    box.appendChild(el("p", "tour-verdict " + (bad ? "is-bad" : "is-good"), c.verdict || ""));
  }

  // ---------- entry points ----------
  function wireStarters() {
    document.querySelectorAll("[data-tour-start]").forEach(function (b) {
      b.addEventListener("click", function (e) { e.preventDefault(); start(); });
    });
  }

  // On the landing page, a signed-in visitor gets a quiet "Start the guided tour" pill.
  function offerOnLanding() {
    if (document.body.getAttribute("data-page") !== "index") return;
    api("/api/showcase/tour").then(function (res) {
      if (!res.ok || active) return;
      var b = el("button", "tour-pill", "Start the guided tour");
      b.type = "button";
      b.addEventListener("click", function () { b.remove(); start(); });
      document.body.appendChild(b);
    });
  }

  function init() {
    wireStarters();
    if (!resume()) offerOnLanding();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
