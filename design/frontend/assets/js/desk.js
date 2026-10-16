/* Case desk: projector-first view of the case. Renders from the shared mock store. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, status, chip, evLabel, simTag } = UI;
  UI.shell("desk", { wide: true, context: "Case desk" });

  const spine = document.getElementById("spine");
  const main = document.getElementById("desk-main");
  const side = document.getElementById("desk-side");
  let showAllEvents = false;

  const COND = {
    holding: ["holding", "Holding"], violated: ["violated", "Violated"], unknown: ["unknown", "Not stated"],
    unauthorised: ["unauthorised", "Unauthorised change"], neutral: ["neutral", "Not checked yet"],
  };
  const condChip = (c) => { const [k, t] = COND[c.state] || COND.neutral; return chip(k, c.ev === "spoken" && c.state === "unknown" ? "Said on call only" : t); };

  /* ---------------- Spine ---------------- */
  function renderSpine(s) {
    const amina = s.dependency !== "none";
    const ctl = { active: "Everything is running normally.", quiet: "Quiet: no messages to the family for 24 hours. Monitoring and approved routine work continue.", hold: "Hold: nothing goes out to organisations. Monitoring continues.", stopped: "Stopped: everything has stopped, including monitoring." }[s.control];
    const auto = s.autopilot === "gentle" ? "Gentle: reads and classifies replies automatically; asks before every outbound action." : "Steady: also sends follow-ups and identical routine notices; still asks for closures, transfers and decisions.";
    const fuCount = Object.values(s.followups).reduce((a, b) => a + b, 0);
    spine.innerHTML = `
      <section class="spine__case stack stack-sm">
        <p class="eyebrow">Case ${esc(F.case.ref)} · demo case</p>
        <h1 class="h1">${esc(F.case.deceased)}</h1>
        <p class="spine__died">Died ${esc(F.case.dateOfDeath)}</p>
      </section>
      <section class="stack stack-sm" aria-labelledby="sp-people">
        <h2 class="eyebrow" id="sp-people">People</h2>
        <ul class="spine__people" role="list">
          <li><span class="avatar avatar--sara" aria-hidden="true">S</span><span><b>Sara Malik</b> · case owner</span><small>His daughter; handling the estate (stated)</small></li>
          <li><span class="avatar avatar--amina" aria-hidden="true">A</span><span><b>Amina Malik</b> · household</span><small>${amina ? "His wife; joined by invite link. Answers questions, can't approve." : "His wife. Not joined yet."}</small></li>
        </ul>
      </section>
      <section class="stack stack-sm" aria-labelledby="sp-intent">
        <h2 class="eyebrow" id="sp-intent">In the family's words</h2>
        <blockquote class="spine__intent">“${esc(F.case.intentQuote)}”</blockquote>
        <dl class="intent-lists">
          <div><dt>Keep</dt><dd>${esc(F.case.intent.keep.join(" · "))}</dd></div>
          <div><dt>Stop</dt><dd>${esc(F.case.intent.stop.join(" · "))}</dd></div>
          <div><dt>Protect</dt><dd>${esc(F.case.intent.protect.join(" · "))}</dd></div>
        </dl>
      </section>
      <section class="stack stack-sm" aria-labelledby="sp-auto">
        <h2 class="eyebrow" id="sp-auto">Autopilot</h2>
        <div class="segmented" role="group" aria-labelledby="sp-auto">
          <button type="button" data-auto="gentle" aria-pressed="${s.autopilot === "gentle"}">Gentle</button>
          <button type="button" data-auto="steady" aria-pressed="${s.autopilot === "steady"}">Steady</button>
        </div>
        <p class="control-note">${esc(auto)}</p>
      </section>
      <section class="stack stack-sm" aria-labelledby="sp-ctl">
        <h2 class="eyebrow" id="sp-ctl">Case control</h2>
        <div class="segmented" role="group" aria-labelledby="sp-ctl">
          <button type="button" data-ctl="active" aria-pressed="${s.control === "active"}">Running</button>
          <button type="button" data-ctl="quiet" aria-pressed="${s.control === "quiet"}">${icon("moon")}Quiet</button>
          <button type="button" data-ctl="hold" aria-pressed="${s.control === "hold"}">${icon("hand")}Hold</button>
          <button type="button" data-ctl="stopped" aria-pressed="${s.control === "stopped"}">${icon("stop")}Stop</button>
        </div>
        <p class="control-note">${esc(ctl)}</p>
      </section>
      <section class="clock stack stack-sm" id="clock" aria-labelledby="sp-clock" tabindex="-1">
        <h2 class="clock__label" id="sp-clock">${icon("clock")}Demo case clock · simulated</h2>
        <p class="clock__now">${esc(AW.fmtTime(s.now))}</p>
        <div class="btn-row btn-row--inline">
          <button class="btn btn--sim btn--sm" type="button" data-clock="14">${icon("fast-forward")}+14 days</button>
          <button class="btn btn--sim btn--sm" type="button" data-clock="35">${icon("fast-forward")}+35 days</button>
        </div>
        <p class="control-note">Moves case time only. Jobs whose time has come run, with the usual checks. Follow-ups sent so far: ${fuCount}.</p>
      </section>
      <section class="stack stack-sm" aria-labelledby="sp-health">
        <h2 class="eyebrow" id="sp-health">Health</h2>
        <p>${s.monitoring === "ok" ? chip("holding", "Mailbox monitoring on") : chip("violated", "Monitoring interrupted")}</p>
        <p class="control-note">Last check: ${s.monitoring === "ok" ? "under a minute ago" : "failed: access expired"} <span class="sim-tag">Simulated</span></p>
        <p>${chip("neutral", "Confidential compute: not attempted")}</p>
        <p class="control-note">The prototype has no deployment. When attested, the desk shows it here with its boundary: it covers our compute and storage, not the AI provider, chat platforms or recipients.</p>
      </section>
      <section class="shortcut stack stack-sm" aria-labelledby="sp-sim">
        <h2 class="clock__label" id="sp-sim">${icon("ring")}Prototype scenarios</h2>
        <div class="btn-row btn-row--stack">
          ${s.monitoring === "ok" ? `<button class="btn btn--sim btn--sm" type="button" data-sim="monitoring-off">Interrupt mailbox monitoring</button>` : `<button class="btn btn--sim btn--sm" type="button" data-sim="monitoring-on">Reconnect mailbox (simulated)</button>`}
          <button class="btn btn--sim btn--sm" type="button" data-sim="timeout" ${(s.followups.fl || 0) > 0 && !s.delivery ? "" : "disabled"}>Time out FitLife follow-up send</button>
        </div>
        <p class="control-note">${(s.followups.fl || 0) > 0 ? "" : "The send timeout needs a FitLife follow-up first: use +14 days after the requests are approved."}</p>
      </section>`;
  }

  /* ---------------- Main column ---------------- */
  function banners(s) {
    const out = [];
    if (s.monitoring === "interrupted") out.push(`<div class="banner banner--interrupted" role="alert">${icon("eye-off")}<p class="banner__title">Monitoring interrupted</p><p class="banner__body">Access to the family mailbox expired. Replies from organisations are not being read, so nothing can be checked or marked done until it's reconnected. Sara has been told.</p><div class="banner__actions"><button class="btn btn--sm" type="button" data-sim="monitoring-on">${icon("retry")}Reconnect (simulated)</button></div></div>`);
    if (s.delivery === "uncertain") out.push(`<div class="banner banner--uncertain">${icon("question")}<p class="banner__title">Delivery uncertain: FitLife follow-up 1</p><p class="banner__body">The send timed out after the request left, so it may or may not have been sent. Afterward won't retry blindly. It searches the Sent folder for the reference <span class="ref">AW-1042-FL1-F1</span> first.</p><div class="banner__actions"><button class="btn btn--sm" type="button" data-sim="reconcile">${icon("retry")}Run the Sent-folder check (simulated)</button></div></div>`);
    if (s.delivery === "reconciled") out.push(`<div class="banner banner--success">${icon("check")}<p class="banner__title">Reconciled: FitLife follow-up 1 was sent once</p><p class="banner__body">Found in the Sent folder by its reference. Marked sent; not resent.</p></div>`);
    if (s.control === "hold") out.push(`<div class="banner banner--hold">${icon("hand")}<p class="banner__title">Case on hold</p><p class="banner__body">No requests, follow-ups or replies go out to organisations. Monitoring continues, so nothing is missed.</p></div>`);
    if (s.control === "quiet") out.push(`<div class="banner">${icon("moon")}<p class="banner__title">Quiet for 24 hours</p><p class="banner__body">No messages to the family. Monitoring and approved routine work continue.</p></div>`);
    if (s.control === "stopped") out.push(`<div class="banner banner--error">${icon("stop")}<p class="banner__title">Case stopped</p><p class="banner__body">Everything has stopped, including monitoring. Export and delete are offered to Sara. (Prototype: choose Running to resume.)</p></div>`);
    if (s.spoof) out.push(`<div class="banner banner--warning">${icon("shield")}<p class="banner__title">Held: email from an unapproved address</p><p class="banner__body"><span class="ref">records@northline-support.example</span> isn't on Northline's approved list. Its request for the full will was treated as evidence, not instructions. No reply, no documents.</p></div>`);
    return out.length ? `<div class="banners">${out.join("")}</div>` : "";
  }

  function nowPanel(s) {
    const cmp = AW.comparison();
    if (cmp) return comparePanel(s, cmp);
    let title, body, eyebrow = "Now";
    if (s.intake !== "confirmed") {
      title = "Waiting for Sara to confirm the summary";
      body = `<div class="speech"><p class="speech__who">${icon("mic", "icon--sm")}Sara's voice note · transcribed ${simTag()}</p><p class="speech__text">“${esc(F.transcripts.sara)}”</p></div>
        <p class="secondary">Afterward read one voice note into a case summary. Nothing happens until Sara confirms it.</p>`;
    } else if (s.candidates !== "reviewed") {
      title = "9 possible accounts; 3 need ownership confirmed";
      body = `<p class="secondary">Found in 6 forwarded emails and 4 photos. Paper post, other email addresses and cash payments haven't been searched. <a href="#coverage">See coverage</a>.</p>`;
    } else if (s.dependency !== "confirmed") {
      title = "Asking Amina what could disappear";
      body = `<p class="lede">“Does anyone still use the Northline line ending 4417, or does it get codes for any other account?”</p>
        <p class="secondary">${s.dependency === "heard" ? "Amina has answered. Waiting for her to confirm what Afterward understood." : "No change can be made to the line until this is answered."}</p>`;
    } else {
      eyebrow = "Now · waiting for Sara";
      title = "Plan v2 is ready for approval";
      body = `<div class="diff">
        <div class="diff__row diff__row--old"><span class="diff__v">v1</span><span class="diff__text">Northline 4417: hold and check with the household first</span></div>
        <div class="diff__row diff__row--new"><span class="diff__v">v2</span><span class="diff__text"><b>Transfer to Amina</b>, only if the number and voicemail are kept and there's no new contract. Otherwise hold and ask.</span></div>
        <div class="diff__row diff__row--old"><span class="diff__v">v1</span><span class="diff__text">Crescent Bank 0932: notify (ownership unconfirmed)</span></div>
        <div class="diff__row diff__row--new"><span class="diff__v">v2</span><span class="diff__text"><b>Don't close.</b> It may be a joint account Amina relies on; it's linked to the 4417 line.</span></div>
      </div>
      <p class="secondary">Changed by code from Amina's answer, using the dependency rules table. Approval is bound to plan v2.</p>`;
    }
    return `<section class="now" aria-labelledby="now-title"><div class="now__head"><div><p class="eyebrow">${eyebrow}</p><h2 class="now__title" id="now-title">${esc(title)}</h2></div></div><div class="compare__col stack">${body}</div></section>`;
  }

  function quoteHtml(q) {
    return `<figure class="quote"><blockquote class="quote__text">${q.segs.map((g) => g.hl ? `<mark class="hl-${g.hl}">${esc(g.t)}</mark>` : esc(g.t)).join("")}</blockquote>
      <figcaption class="quote__source">${q.ev === "writing" ? `<span class="verified">${icon("check", "icon--sm")}Quote found in the message</span>` : ""}${evLabel(q.ev)}<span>${esc(q.source)}</span><span>${esc(AW.fmtTime(q.at))}</span></figcaption></figure>`;
  }

  function comparePanel(s, c) {
    const d = c.account, v = c.plan.v, accepted = s.call.terms.filter((t) => t.status === "accepted").slice(-1)[0];
    const reqConds = accepted ? ["Keep the number", "Keep the voicemail", `Contract: ${accepted.months} months at $${accepted.price}/month (approved on the call)`] : c.plan.conditions;
    const vIcon = { notdone: "cross", open: "clock", resolved: "check" }[c.verdict.kind];
    const decision = s.nlDecision === "open" ? chip("review", "Decision sent to Sara") : s.call.terms.some((t) => t.status === "pending") ? chip("review", "Call paused: Sara is deciding") : "";
    return `<section class="now" aria-labelledby="now-title">
      <div class="now__head">
        <div><p class="eyebrow">Now</p><h2 class="now__title" id="now-title">Northline Mobile · line ending 4417</h2></div>
        <div class="cluster cluster--tight">${decision}<span class="status status--neutral">${icon("doc")}Plan v${v}</span></div>
      </div>
      <div class="compare">
        <div class="compare__col">
          <div class="compare__label"><span class="num-badge" aria-hidden="true">1</span><h3 class="eyebrow">Requested</h3></div>
          <p class="requested-action">${esc(c.plan.action)}</p>
          <ul class="cond-list" role="list">${reqConds.map((x) => `<li>${icon("dot", "icon--sm")}<span>${esc(x)}</span></li>`).join("")}</ul>
          <p class="xsmall muted" style="margin-top:var(--s-3)">Approved by Sara · plan v${v}${accepted ? ` · terms ${accepted.id}` : ""} · sent to ${esc(F.providers.northline.recipient)}</p>
        </div>
        <div class="compare__col">
          <div class="compare__label"><span class="num-badge" aria-hidden="true">2</span><h3 class="eyebrow">Northline says</h3></div>
          ${c.quote ? quoteHtml(c.quote) : `<div class="empty" style="padding:var(--s-4) 0">${icon("mail", "icon--lg")}<p>No reply yet.</p></div>`}
        </div>
        <div class="compare__col">
          <div class="compare__label"><span class="num-badge" aria-hidden="true">3</span><h3 class="eyebrow">Afterward concludes</h3></div>
          <p class="verdict verdict--${c.verdict.kind}">${icon(vIcon)}${esc(c.verdict.text)}</p>
          <p class="small secondary" style="margin-top:var(--s-2)">${esc(c.verdict.sub)}</p>
          <ul class="checks" role="list">
            <li><span>Requested action</span>${status(c.action)}</li>
            ${c.conditions.map((x) => `<li><span>${esc(x.label)}</span>${condChip(x)}<span class="checks__why">${esc(x.why)}</span></li>`).join("")}
          </ul>
        </div>
      </div>
      <div class="now__foot"><span><b>Next:</b> ${esc(d.next.owner)} · ${esc(d.next.action)}${d.next.due ? ` · due ${esc(d.next.due)}` : ""}</span><span>Done means completion evidence plus every condition holding.</span></div>
    </section>`;
  }

  function ledger(s) {
    if (s.intake !== "confirmed") return `<section class="desk-section" aria-labelledby="led-title"><h2 class="section-title" id="led-title">Accounts</h2><div class="empty"><svg class="empty__art" viewBox="0 0 96 56" aria-hidden="true"><path d="M8 48H88" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M34 48A14 14 0 0 1 62 48" fill="currentColor"/><path d="M24 40A24 24 0 0 1 72 40" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg><p class="empty__title">No accounts yet</p><p>Candidate accounts appear once Sara confirms the summary.</p></div></section>`;
    const rows = AW.accounts().map((a) => `<tr class="${a.focus ? "is-focus" : ""}">
        <td><span class="acct__name">${esc(a.name)}</span><br><span class="small">${esc(a.label)}</span><br><span class="acct__ref">${esc(a.ref)} · ${esc(a.origin)}${a.profile ? "" : " · no declared profile"}</span>${a.plan ? `<br><span class="xsmall muted">Plan v${a.plan.v}: ${esc(a.plan.action)}</span>` : ""}</td>
        <td><span class="dim-label">Service</span>${status(a.service)}</td>
        <td><span class="dim-label">Money</span>${status(a.money)}</td>
        <td><span class="dim-label">Documents</span>${status(a.docs)}</td>
        <td><span class="dim-label">Next step</span><span class="next"><span class="next__owner">${esc(a.next.owner)}</span><span>${esc(a.next.action)}</span>${a.next.due ? `<span class="xsmall muted">Due ${esc(a.next.due)}</span>` : ""}</span></td>
        <td><span class="dim-label">Conditions</span>${a.conditions.length ? `<span class="cluster cluster--tight">${a.conditions.map((c) => `<span title="${esc(c.label)}">${condChip(c)}</span>`).join("")}</span>` : `<span class="muted small">None</span>`}</td>
      </tr>`).join("");
    return `<section class="desk-section desk-section--ledger" aria-labelledby="led-title">
      <div class="panel__head"><h2 class="section-title" id="led-title">Accounts</h2><span class="small muted">Four dimensions per account. "Done" needs all of them resolved.</span></div>
      <table class="ledger"><caption class="visually-hidden">Accounts with service, money, documents, next step and conditions</caption>
        <thead><tr><th scope="col">Account</th><th scope="col">Service</th><th scope="col">Money</th><th scope="col">Documents</th><th scope="col">Next step</th><th scope="col">Conditions</th></tr></thead>
        <tbody>${rows}</tbody></table></section>`;
  }

  function coverage(s) {
    if (s.intake !== "confirmed") return "";
    const unresolved = AW.accounts().filter((a) => a.bucket === "unconfirmed").length;
    return `<section class="desk-section" id="coverage" aria-labelledby="cov-title" tabindex="-1">
      <div class="panel__head"><h2 class="section-title" id="cov-title">Coverage</h2>${chip("unknown", `${unresolved} candidate${unresolved === 1 ? "" : "s"} unresolved`)}</div>
      <div class="coverage">
        <div><h3 class="h4">${icon("check")}Searched</h3><ul>${F.coverage.searched.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div><h3 class="h4">${icon("eye-off")}Not searched</h3><ul>${F.coverage.notSearched.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        <div><h3 class="h4">${icon("arrow-right")}Where else to look</h3><ul>${F.coverage.whereElse.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      </div>
      <p class="small muted" style="margin-top:var(--s-4)">There is no "complete" button. The list stays open and new candidates can arrive at any time.</p>
    </section>`;
  }

  function finished(s) {
    const sum = AW.summary();
    const stated = 1;
    const orgs = Object.keys(s.sent).length;
    const interventions = s.events.filter((e) => e.actor === "Sara" || e.actor === "Amina").length;
    const caught = s.replies.filter((r) => r.id === "nl_contradictory").length + (s.spoof ? 1 : 0);
    return `<section class="desk-section" aria-labelledby="fin-title">
      <div class="panel__head"><h2 class="section-title" id="fin-title">Did you finish everything?</h2><span class="small muted">Generated by code from the four status dimensions</span></div>
      <p class="lede" style="margin-bottom:var(--s-3)">${esc(sum.headline)}</p>
      <ul class="finished__lines" role="list">${sum.lines.map((l) => `<li>${chip(l.tone, l.text)}<small>${esc(l.who)}</small></li>`).join("")}</ul>
      <p class="small muted" style="margin-top:var(--s-3)">${esc(sum.caveat)}</p>
      <hr>
      <div class="metrics">
        <div class="metric"><span class="metric__value">${stated}</span><span class="metric__label">Times the family stated the death</span></div>
        <div class="metric"><span class="metric__value">${orgs}</span><span class="metric__label">Organisations contacted (simulated)</span></div>
        <div class="metric"><span class="metric__value">${interventions}</span><span class="metric__label">Family interventions</span></div>
        <div class="metric"><span class="metric__value">${caught}</span><span class="metric__label">Wrong or unsafe outcomes caught</span></div>
      </div>
    </section>`;
  }

  /* ---------------- Side column ---------------- */
  function timeline(s) {
    const list = s.events.slice().reverse();
    const shown = showAllEvents ? list : list.slice(0, 10);
    return `<section class="desk-section" aria-labelledby="tl-title">
      <div class="panel__head"><h2 class="section-title" id="tl-title">Timeline</h2><span class="xsmall muted">Case time, newest first</span></div>
      <ol class="timeline" role="list">${shown.map((e) => `<li class="t--${esc(e.tone || "none")}">
        <p class="timeline__time">${esc(AW.fmtTime(e.at))} · ${esc(e.actor || "Afterward")}</p>
        <p class="timeline__text">${esc(e.text)}</p>
        ${e.quote ? `<p class="quote--inline small">“${esc(e.quote.length > 160 ? e.quote.slice(0, 157) + "…" : e.quote)}”</p>` : ""}
        ${e.ev ? `<div class="timeline__meta">${evLabel(e.ev)}</div>` : ""}
      </li>`).join("")}</ol>
      ${list.length > 10 ? `<button class="btn btn--quiet btn--sm" type="button" data-toggle-events>${showAllEvents ? "Show the latest 10" : `Show all ${list.length} events`}</button>` : ""}
    </section>`;
  }

  function callPanel(s) {
    const c = s.call;
    if (c.status === "none") return `<section class="desk-section" aria-labelledby="call-title"><h2 class="section-title" id="call-title">Call</h2><p class="small muted" style="margin-top:var(--s-2)">No call yet. A simulated provider call starts only when Sara chooses "Call them for me".</p></section>`;
    const turns = c.turns.slice(-6).map(turnHtml).join("");
    const max = Math.max(...c.latency.map((l) => l.total), 1);
    const colors = ["var(--c-ink-3)", "var(--c-dusk)", "var(--c-dawn)", "var(--c-moss)", "var(--c-plum)", "var(--c-ochre)"];
    const lat = c.latency.slice(-5).map((l) => `<tr><td>Turn ${l.turn}</td><td><div class="latency-bar" style="width:${Math.round((l.total / max) * 100)}%">${Object.values(l.stages).map((v, i) => `<span style="width:${(v / l.total) * 100}%;background:${colors[i]}"></span>`).join("")}</div></td><td>${l.total} ms</td></tr>`).join("");
    return `<section class="desk-section" aria-labelledby="call-title">
      <div class="panel__head"><h2 class="section-title" id="call-title">Call</h2>${simTag("Simulated provider call")}</div>
      <ol class="transcript" role="list">${turns}</ol>
      <p style="margin-top:var(--s-3)"><a href="call.html">Open the call room</a></p>
      ${c.latency.length ? `<hr><table class="latency"><caption class="cluster cluster--tight"><span class="h4">Per-turn timing</span>${simTag("Simulated timing, not a measurement")}</caption><thead><tr><th scope="col">Turn</th><th scope="col">Stages</th><th scope="col">Total</th></tr></thead><tbody>${lat}</tbody></table>
      <p class="xsmall muted" style="margin-top:var(--s-2)">Stages: upload, transcription, reasoning, validation, first speech byte, playback start. The deployed desk reports measured values only.</p>` : ""}
    </section>`;
  }
  function turnHtml(t) {
    if (t.who === "system") return `<li class="turn turn--system turn--${esc(t.kind)}"><p class="turn__text">${t.kind === "discarded" ? icon("slash", "icon--sm") + " " : ""}${esc(t.text)}</p></li>`;
    const who = t.who === "agent" ? `<span class="avatar avatar--agent" aria-hidden="true">${UI.compactMark().replace('class="brand__compact"', 'class="brand__compact" style="width:18px;height:18px"').replaceAll("var(--c-ink)", "var(--c-on-ink)")}</span>` : `<span class="avatar avatar--rep" aria-hidden="true">N</span>`;
    return `<li class="turn turn--${t.who}">${who}<div><p class="turn__who">${t.who === "agent" ? "Afterward (AI)" : "Northline rep"}${t.kind === "template" ? " · server template" : ""}${t.via === "typed" ? " · typed" : ""}</p><p class="turn__text">${esc(t.text)}</p></div></li>`;
  }

  /* ---------------- Render and events ---------------- */
  function render() {
    const s = AW.state;
    renderSpine(s);
    const proj = document.documentElement.classList.contains("is-projector");
    main.innerHTML = `
      <div class="desk-toolbar">
        <p class="small muted">Case time ${esc(AW.fmtTime(s.now))} · updates live from other tabs</p>
        <button class="btn btn--sm" type="button" data-projector aria-pressed="${proj}">${icon("projector")}Projector mode${proj ? ": on" : ""}</button>
      </div>
      ${banners(s)}
      ${nowPanel(s)}
      ${ledger(s)}
      ${coverage(s)}
      ${finished(s)}`;
    side.innerHTML = timeline(s) + callPanel(s);
  }

  function confirmStop() {
    const d = document.createElement("dialog");
    d.className = "dialog"; d.setAttribute("aria-labelledby", "stop-title");
    d.innerHTML = `<div class="dialog__head"><h2 class="h3" id="stop-title">Stop the whole case?</h2></div><div class="dialog__body stack"><p>Everything stops, including monitoring, so replies won't be read. Sara is offered an export, then deletion of Afterward's copies. Organisations keep what they already received.</p><div class="btn-row"><button class="btn btn--danger" type="button" value="stop">${icon("stop")}Stop the case</button><button class="btn" type="button" value="cancel">Keep it running</button></div></div>`;
    document.body.appendChild(d);
    d.addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; if (b.value === "stop") AW.dispatch("control.set", { value: "stopped" }); d.close(); });
    d.addEventListener("close", () => d.remove());
    d.showModal();
  }

  const root = document.body;
  UI.on(root, "[data-auto]", "click", (e, b) => AW.dispatch("autopilot.set", { value: b.dataset.auto }));
  UI.on(root, "[data-ctl]", "click", (e, b) => { if (b.dataset.ctl === "stopped") confirmStop(); else AW.dispatch("control.set", { value: b.dataset.ctl }); });
  UI.on(root, "[data-clock]", "click", (e, b) => AW.dispatch("clock.advance", { days: Number(b.dataset.clock) }));
  UI.on(root, "[data-sim]", "click", (e, b) => {
    const v = b.dataset.sim;
    if (v === "monitoring-off") AW.dispatch("monitoring.set", { value: "interrupted" });
    if (v === "monitoring-on") AW.dispatch("monitoring.set", { value: "ok" });
    if (v === "timeout") AW.dispatch("delivery.timeout");
    if (v === "reconcile") { b.setAttribute("aria-busy", "true"); b.disabled = true; setTimeout(() => AW.dispatch("delivery.reconcile"), 900); }
  });
  UI.on(root, "[data-toggle-events]", "click", () => { showAllEvents = !showAllEvents; render(); });
  UI.on(root, "[data-projector]", "click", () => {
    const on = document.documentElement.classList.toggle("is-projector");
    try { localStorage.setItem("afterward.projector", on ? "on" : "off"); } catch (e) { /* ignore */ }
    render();
    document.querySelector("[data-projector]").focus();
    UI.announce(on ? "Projector mode on." : "Projector mode off.", { toast: false });
  });

  // Re-render keeps focus on the control that was used, so keyboard users don't lose their place.
  AW.subscribe(() => {
    const a = document.activeElement;
    const key = a && (a.dataset.ctl || a.dataset.auto || a.dataset.clock || a.dataset.sim);
    const attr = a && ["ctl", "auto", "clock", "sim"].find((k) => a.dataset[k] != null);
    render();
    if (key && attr) { const n = document.querySelector(`[data-${attr}="${key}"]`); if (n) n.focus(); }
  });

  let first = true;
  try { first = !sessionStorage.getItem("afterward.desk.loaded"); sessionStorage.setItem("afterward.desk.loaded", "1"); } catch (e) { first = false; }
  setTimeout(() => { render(); if (location.hash) { const t = document.querySelector(location.hash); if (t) { t.scrollIntoView(); t.focus({ preventScroll: true }); } } }, first ? 600 : 0);
})();
