/* Case desk: projector-first, one screen. "Now" and the accounts on the left, activity and the
   call on the right; account detail, coverage, the summary and case settings open in drawers. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, status, chip, evLabel, simTag } = UI;
  UI.shell("desk", { wide: true, context: "Case desk" });
  const root = document.getElementById("desk-root");
  let tab = "activity";
  let accountId = null;

  const COND = { holding: ["holding", "Holding"], violated: ["violated", "Broken"], unknown: ["unknown", "Not stated"], unauthorised: ["unauthorised", "Not approved"], neutral: ["neutral", "Not checked"] };
  const condChip = (c) => { const [k, t] = COND[c.state] || COND.neutral; return chip(k, c.ev === "spoken" && c.state === "unknown" ? "Said on call" : t); };
  const OVERALL = { confirmed: ["holding", "Done"], promised: ["waiting", "Promised"], review: ["review", "To review"], decision: ["review", "Needs family"], waiting: ["progress", "In progress"], handed: ["info", "With Sara"], kept: ["neutral", "Kept"], unconfirmed: ["unknown", "Unconfirmed"], not_theirs: ["neutral", "Not his"], not_started: ["neutral", "Not started"], blocked: ["violated", "Blocked"] };

  /* ---------------- Drawers ---------------- */
  const accountDrawer = UI.drawer({ id: "acct", title: () => { const a = AW.accounts().find((x) => x.id === accountId); return a ? a.name : "Account"; }, render: () => {
    const a = AW.accounts().find((x) => x.id === accountId); if (!a) return "";
    const P = a.profile;
    return `<p class="secondary">${esc(a.label)}<br><span class="small muted">Found in: ${esc(a.origin)}</span></p>
      <dl class="dims">
        <div><dt>Service</dt><dd>${status(a.service)}</dd></div>
        <div><dt>Money</dt><dd>${status(a.money)}${(a.moneyExtra || []).map((m) => " " + status(m)).join("")}</dd></div>
        <div><dt>Documents</dt><dd>${status(a.docs)}</dd></div>
        <div><dt>Next</dt><dd><b>${esc(a.next.owner)}</b>: ${esc(a.next.action)}${a.next.due ? `<br><span class="small muted">By ${esc(a.next.due)}</span>` : ""}</dd></div>
      </dl>
      ${a.plan ? `<div class="drawer__group"><p class="drawer__label">Plan v${a.plan.v}</p><p>${esc(a.plan.action)}</p></div>` : ""}
      ${a.conditions.length ? `<div class="drawer__group"><p class="drawer__label">Conditions</p><ul class="checks" role="list">${a.conditions.map((c) => `<li><span>${esc(c.label)}</span>${condChip(c)}<span class="checks__why">${esc(c.why)}</span></li>`).join("")}</ul></div>` : ""}
      ${a.note ? `<p class="small muted">${esc(a.note)}</p>` : ""}
      ${P ? `<div class="drawer__group"><p class="drawer__label">How ${esc(P.short)} works</p><ul class="facts small" role="list"><li>${icon("mail")}<span>${esc(P.channel)}: ${esc(P.recipient)}</span></li><li>${icon("doc")}<span>${esc(P.docs)}</span></li><li>${icon("clock")}<span>Replies within ${P.windowBd} working days</span></li><li>${icon("check")}<span>Done means: ${esc(P.completion)}</span></li></ul><p class="xsmall muted">Fictional demo provider</p></div>` : `<p class="small muted">No profile for this organisation yet.</p>`}`;
  } });
  const coverageDrawer = UI.drawer({ id: "cov", title: "What we searched", render: () => `
      <div class="drawer__group"><p class="drawer__label">Searched</p><ul class="facts" role="list">${F.coverage.searched.map((x) => `<li>${icon("check")}<span>${esc(x)}</span></li>`).join("")}</ul></div>
      <div class="drawer__group"><p class="drawer__label">Not searched</p><ul class="facts" role="list">${F.coverage.notSearched.map((x) => `<li>${icon("eye-off")}<span>${esc(x)}</span></li>`).join("")}</ul></div>
      <div class="drawer__group"><p class="drawer__label">Where else to look</p><ul class="facts" role="list">${F.coverage.whereElse.map((x) => `<li>${icon("arrow-right")}<span>${esc(x)}</span></li>`).join("")}</ul></div>
      <p class="small muted">The list never closes. New accounts can turn up at any time.</p>` });
  const summaryDrawer = UI.drawer({ id: "sum", title: "Did you finish everything?", render: () => {
    const s = AW.state, sum = AW.summary();
    const caught = s.replies.filter((r) => r.id === "nl_contradictory").length + (s.spoof ? 1 : 0);
    return `<p class="lede" style="font-size:var(--fs-md)">${esc(sum.headline)}</p>
      <ul class="finished__lines" role="list">${sum.lines.map((l) => `<li>${chip(l.tone, l.text)}<small>${esc(l.who)}</small></li>`).join("")}</ul>
      <p class="small muted">${esc(sum.caveat)}</p>
      <div class="metrics">
        <div class="metric"><span class="metric__value">1</span><span class="metric__label">Times the family told us</span></div>
        <div class="metric"><span class="metric__value">${Object.keys(s.sent).length}</span><span class="metric__label">Organisations contacted</span></div>
        <div class="metric"><span class="metric__value">${caught}</span><span class="metric__label">Bad outcomes caught</span></div>
      </div>`;
  } });
  const caseDrawer = UI.drawer({ id: "case", title: "Case settings", render: () => {
    const s = AW.state;
    return `<div class="drawer__group"><p class="drawer__label">People</p><ul class="facts" role="list"><li>${icon("user")}<span><b>Sara Malik</b>, his daughter. Handling the estate (stated). Approves requests.</span></li><li>${icon("user")}<span><b>Amina Malik</b>, his wife. Answers questions; can't approve.</span></li></ul></div>
      <div class="drawer__group"><p class="drawer__label">In the family's words</p><p class="quote--inline">“${esc(F.case.intentQuote)}”</p></div>
      <div class="drawer__group"><p class="drawer__label" id="d-auto">Autopilot</p><div class="segmented" role="group" aria-labelledby="d-auto"><button type="button" data-auto="gentle" aria-pressed="${s.autopilot === "gentle"}">Gentle</button><button type="button" data-auto="steady" aria-pressed="${s.autopilot === "steady"}">Steady</button></div><p class="small muted">${s.autopilot === "gentle" ? "Asks before anything goes out." : "Sends follow-ups and routine notices itself. Still asks for anything that closes, transfers or decides."}</p></div>
      <div class="drawer__group"><p class="drawer__label" id="d-ctl">Pause</p><div class="segmented" role="group" aria-labelledby="d-ctl"><button type="button" data-ctl="active" aria-pressed="${s.control === "active"}">Running</button><button type="button" data-ctl="quiet" aria-pressed="${s.control === "quiet"}">Quiet</button><button type="button" data-ctl="hold" aria-pressed="${s.control === "hold"}">Hold</button><button type="button" data-ctl="stopped" aria-pressed="${s.control === "stopped"}">Stop</button></div><p class="small muted">${{ active: "Everything is running.", quiet: "No messages to the family. Work carries on.", hold: "Nothing goes out to organisations. Still watching for replies.", stopped: "Everything has stopped, including watching for replies." }[s.control]}</p></div>
      <div class="drawer__group"><p class="drawer__label">Security</p><p class="small">${chip("neutral", "Confidential compute: not set up", "status--wrap")}</p></div>
      <div class="drawer__group card card--sim"><p class="drawer__label">Try a failure (demo)</p><div class="btn-row btn-row--stack">
        ${s.monitoring === "ok" ? `<button class="btn btn--sim btn--sm" type="button" data-sim="monitoring-off">Disconnect the mailbox</button>` : `<button class="btn btn--sim btn--sm" type="button" data-sim="monitoring-on">Reconnect the mailbox</button>`}
        <button class="btn btn--sim btn--sm" type="button" data-sim="timeout" ${(s.followups.fl || 0) > 0 && !s.delivery ? "" : "disabled"}>Lose a follow-up mid-send</button>
      </div>${(s.followups.fl || 0) > 0 ? "" : `<p class="xsmall muted">Move the clock 14 days first, so a follow-up exists.</p>`}</div>`;
  } });
  [accountDrawer, coverageDrawer, summaryDrawer, caseDrawer].forEach((d) => d.el.addEventListener("click", onClick));

  /* ---------------- Pieces ---------------- */
  function banners(s) {
    const b = [];
    if (s.monitoring === "interrupted") b.push(`<div class="banner-line banner-line--alert" role="alert">${icon("eye-off")}<span><b>Mailbox disconnected.</b> Replies aren't being read, so nothing can be checked.</span><button class="btn btn--sm" type="button" data-sim="monitoring-on">Reconnect</button></div>`);
    if (s.delivery === "uncertain") b.push(`<div class="banner-line banner-line--warn">${icon("question")}<span><b>A FitLife follow-up may not have sent.</b> Checking the Sent folder before trying again.</span><button class="btn btn--sm" type="button" data-sim="reconcile">Check Sent folder</button></div>`);
    if (s.delivery === "reconciled") b.push(`<div class="banner-line banner-line--good">${icon("check")}<span><b>Found it.</b> The FitLife follow-up went once.</span></div>`);
    if (s.control !== "active") b.push(`<div class="banner-line banner-line--warn">${icon(s.control === "quiet" ? "moon" : s.control === "hold" ? "hand" : "stop")}<span><b>${{ quiet: "Quiet.", hold: "On hold.", stopped: "Stopped." }[s.control]}</b> ${{ quiet: "No messages to the family.", hold: "Nothing goes out to organisations.", stopped: "Everything has stopped." }[s.control]}</span></div>`);
    if (s.spoof) b.push(`<div class="banner-line banner-line--warn">${icon("shield")}<span><b>Held a suspicious email</b> asking for the will. Nothing was sent.</span></div>`);
    return b.join("");
  }

  function nowPanel(s) {
    const c = AW.comparison();
    if (!c) {
      let title, body;
      if (s.intake !== "confirmed") { title = "Waiting for Sara to confirm"; body = `<div class="speech"><p class="speech__who">${icon("mic", "icon--sm")}Sara's voice note ${simTag("Transcribed")}</p><p class="speech__text">“${esc(F.transcripts.sara)}”</p></div>`; }
      else if (s.candidates !== "reviewed") { title = "9 possible accounts found"; body = `<p class="secondary">3 need Sara to say whose they are. <button class="link-btn" type="button" data-open="coverage">What we searched</button></p>`; }
      else if (s.dependency !== "confirmed") { title = "Asking Amina about the 4417 line"; body = `<p class="secondary">${s.dependency === "heard" ? "She's answered. Waiting for her to confirm we understood." : "Nothing changes on the line until she answers."}</p>`; }
      else { title = "Plan v2 is waiting for Sara"; body = `<div class="diff"><div class="diff__row diff__row--old"><span class="diff__v">Before</span><span class="diff__text">Northline 4417: on hold</span></div><div class="diff__row diff__row--new"><span class="diff__v">Now</span><span class="diff__text"><b>Move it to Amina</b>, keeping the number and voicemail, no new contract</span></div><div class="diff__row diff__row--new"><span class="diff__v">Now</span><span class="diff__text"><b>Keep Crescent Bank open</b></span></div></div>`; }
      return `<section class="now" aria-labelledby="now-title"><div class="now__head"><h2 class="now__title" id="now-title">${esc(title)}</h2></div><div class="now__empty">${body}</div></section>`;
    }
    const accepted = s.call.terms.filter((t) => t.status === "accepted").slice(-1)[0];
    const reqConds = accepted ? ["Keep the number", "Keep the voicemail", `${accepted.months} months at $${accepted.price}/month (approved)`] : c.plan.conditions;
    const vIcon = { notdone: "cross", open: "clock", resolved: "check" }[c.verdict.kind];
    const flag = s.nlDecision === "open" ? chip("review", "Sara is deciding") : s.call.terms.some((t) => t.status === "pending") ? chip("review", "Call on hold") : "";
    const quote = c.quote ? `<figure class="quote"><blockquote class="quote__text">${c.quote.segs.map((g) => g.hl ? `<mark class="hl-${g.hl}">${esc(g.t)}</mark>` : esc(g.t)).join("")}</blockquote><figcaption class="quote__source">${evLabel(c.quote.ev)}<span>${esc(AW.fmtTime(c.quote.at))}</span></figcaption></figure>` : `<p class="muted">No reply yet.</p>`;
    return `<section class="now" aria-labelledby="now-title">
      <div class="now__head"><h2 class="now__title" id="now-title">Northline Mobile, line 4417</h2><div class="cluster cluster--tight">${flag}<span class="status status--neutral">Plan v${c.plan.v}</span></div></div>
      <div class="compare-wrap"><div class="compare">
        <div class="compare__col"><h3 class="eyebrow" style="margin-bottom:var(--s-2)">Sara asked for</h3><p class="requested-action">${esc(c.plan.action)}</p><ul class="cond-list" role="list">${reqConds.map((x) => `<li>${icon("dot", "icon--sm")}<span>${esc(x)}</span></li>`).join("")}</ul></div>
        <div class="compare__col"><h3 class="eyebrow" style="margin-bottom:var(--s-2)">Northline said</h3>${quote}</div>
        <div class="compare__col"><h3 class="eyebrow" style="margin-bottom:var(--s-2)">So</h3><p class="verdict verdict--${c.verdict.kind}">${icon(vIcon)}${esc(c.verdict.text)}</p>
          <ul class="checks" role="list">${c.conditions.map((x) => `<li><span>${esc(x.label)}</span>${condChip(x)}</li>`).join("")}</ul></div>
      </div></div>
    </section>`;
  }

  function tiles(s) {
    if (s.intake !== "confirmed") return `<div class="empty"><p>Accounts appear once Sara confirms the summary.</p></div>`;
    return `<div class="tiles">${AW.accounts().map((a) => { const [k, t] = OVERALL[a.bucket] || OVERALL.not_started; return `<button class="tile ${a.focus ? "is-focus" : ""}" type="button" data-account="${a.id}" title="${esc(a.next.owner === "—" ? "Nothing to do" : `Next: ${a.next.owner}, ${a.next.action}`)}"><span class="tile__top"><span class="tile__name">${esc(a.name)}</span>${chip(k, t)}</span><span class="tile__sub">${esc(a.label)}</span></button>`; }).join("")}</div>`;
  }

  function activity(s) {
    return `<ol class="tl" role="list">${s.events.slice().reverse().map((e) => `<li class="t--${esc(e.tone || "none")}"><div><p class="tl__text">${esc(e.text)}</p>${e.quote && e.tone === "provider" ? `<p class="quote--inline small">“${esc(e.quote.length > 120 ? e.quote.slice(0, 117) + "…" : e.quote)}”</p>` : ""}<p class="tl__meta"><span>${esc(AW.fmtTime(e.at))}</span>${e.ev ? evLabel(e.ev) : ""}</p></div></li>`).join("")}</ol>`;
  }

  function callTab(s) {
    const c = s.call;
    if (c.status === "none") return `<p class="muted">No call yet. One starts only if Sara asks for it.</p>`;
    return `<ol class="chat" role="list">${c.turns.map((t) => t.who === "system" ? `<li class="bubble bubble--system ${t.kind === "discarded" ? "bubble--discarded" : ""}"><span class="bubble__text">${esc(t.text)}</span></li>` : `<li class="bubble bubble--${t.who}"><span class="bubble__who">${t.who === "agent" ? "Afterward (AI)" : "Northline"}</span>${esc(t.text)}</li>`).join("")}</ol>
      <p style="margin-top:var(--s-3)"><a href="call.html">Open the call room</a> ${simTag("Simulated call")}</p>`;
  }

  function render() {
    const s = AW.state;
    const proj = document.documentElement.classList.contains("is-projector");
    const unresolved = s.intake === "confirmed" ? AW.accounts().filter((a) => a.bucket === "unconfirmed").length : 0;
    const counts = {}; AW.accounts().forEach((a) => { counts[a.bucket] = (counts[a.bucket] || 0) + 1; });
    const sideScroll = root.querySelector(".side .scroll");
    const y = sideScroll ? sideScroll.scrollTop : 0;
    root.innerHTML = `
      <div class="page-row">
        <div><h1 class="page-title">${esc(F.case.deceased)}</h1><p class="page-sub">Died ${esc(F.case.dateOfDeath)}. Sara is handling the estate (stated).</p></div>
        <div class="toolbar">
          <span class="clock-pill" title="Demo clock. Only moves case time.">${icon("clock")}<span>${esc(AW.fmtTime(s.now))}</span><button class="btn btn--sim btn--sm" type="button" data-clock="14">+14 days</button><button class="btn btn--sim btn--sm" type="button" data-clock="35">+35 days</button></span>
          <button class="btn btn--sm" type="button" data-open="summary">${icon("chat")}Did we finish?</button>
          <button class="btn btn--sm" type="button" data-open="coverage">${icon("eye-off")}Coverage${unresolved ? ` <span class="badge">${unresolved}</span>` : ""}</button>
          <button class="btn btn--sm" type="button" data-open="case">${icon("user")}Case</button>
          <button class="icon-btn" type="button" data-projector aria-pressed="${proj}" title="Projector mode" aria-label="Projector mode">${icon("projector")}</button>
        </div>
      </div>
      ${banners(s)}
      <div class="desk">
        <div class="desk__col">
          ${nowPanel(s)}
          <section class="panel-box tiles-box" aria-labelledby="acc-title">
            <div class="panel-box__head"><h2 class="panel-box__title" id="acc-title">Accounts</h2><span class="small muted">${counts.confirmed || 0} done, ${(counts.waiting || 0) + (counts.promised || 0)} in progress, ${(counts.decision || 0) + (counts.review || 0)} need the family</span></div>
            <div class="panel-box__body scroll">${tiles(s)}</div>
          </section>
        </div>
        <aside class="desk__col side" aria-label="Activity and call">
          <section class="panel-box">
            <div class="panel-box__head"><div class="tablist" role="tablist" aria-label="Side panel" style="flex:1">
              <button type="button" role="tab" id="tab-activity" aria-selected="${tab === "activity"}" aria-controls="side-panel" data-tab="activity">Activity</button>
              <button type="button" role="tab" id="tab-call" aria-selected="${tab === "call"}" aria-controls="side-panel" data-tab="call">Call${s.call.status === "live" ? ` <span class="badge" aria-label="live">•</span>` : ""}</button>
            </div></div>
            <div class="panel-box__body scroll" id="side-panel" role="tabpanel" aria-labelledby="tab-${tab}" tabindex="0">${tab === "activity" ? activity(s) : callTab(s)}</div>
          </section>
        </aside>
      </div>`;
    const ns = root.querySelector(".side .scroll"); if (ns) ns.scrollTop = y;
    accountDrawer.refresh(); summaryDrawer.refresh(); caseDrawer.refresh();
  }

  function onClick(e) {
    const b = e.target.closest("button, [data-open]"); if (!b) return;
    const d = b.dataset;
    if (d.account) { accountId = d.account; accountDrawer.open(); }
    if (d.open === "coverage") coverageDrawer.open();
    if (d.open === "summary") summaryDrawer.open();
    if (d.open === "case") caseDrawer.open();
    if (d.tab) { tab = d.tab; render(); root.querySelector(`[data-tab="${tab}"]`).focus(); }
    if (d.clock) AW.dispatch("clock.advance", { days: Number(d.clock) });
    if (d.auto) AW.dispatch("autopilot.set", { value: d.auto });
    if (d.ctl) { if (d.ctl === "stopped" && !window.confirm("Stop everything, including watching for replies? Sara will be offered an export, then deletion.")) return; AW.dispatch("control.set", { value: d.ctl }); }
    if (d.sim === "monitoring-off") AW.dispatch("monitoring.set", { value: "interrupted" });
    if (d.sim === "monitoring-on") AW.dispatch("monitoring.set", { value: "ok" });
    if (d.sim === "timeout") { AW.dispatch("delivery.timeout"); caseDrawer.close(); }
    if (d.sim === "reconcile") { b.setAttribute("aria-busy", "true"); b.disabled = true; setTimeout(() => AW.dispatch("delivery.reconcile"), 900); }
    if (d.projector != null) {
      const on = document.documentElement.classList.toggle("is-projector");
      try { localStorage.setItem("afterward.projector", on ? "on" : "off"); } catch (err) { /* ignore */ }
      render(); root.querySelector("[data-projector]").focus();
      UI.announce(on ? "Projector mode on." : "Projector mode off.");
    }
  }
  root.addEventListener("click", onClick);

  AW.subscribe(() => {
    const a = document.activeElement, inRoot = a && root.contains(a);
    const key = inRoot && ["clock", "sim", "tab"].find((k) => a.dataset[k] != null);
    const val = key && a.dataset[key];
    render();
    if (key) { const n = root.querySelector(`[data-${key}="${val}"]`); if (n) n.focus(); }
  });
  render();
})();
