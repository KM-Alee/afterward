/* Family view: phone-first web version of the cards Sara and Amina receive in chat.
   One screen: the card that needs you, and a dock for history, questions and pausing.
   Every card has at most three choices, matching WhatsApp's button limit. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, evLabel, simTag } = UI;
  UI.shell("family", { context: "Family", fitAlways: true });

  const phone = document.getElementById("phone");
  const ctx = document.getElementById("family-context");
  let persona = UI.param("as") === "amina" ? "amina" : "sara";
  let typing = false;
  let page = 0;
  let lastCard = null;
  const opened = new Set();

  const PEOPLE = {
    sara: { name: "Sara Malik", initial: "S", role: "Handling the estate (stated)" },
    amina: { name: "Amina Malik", initial: "A", role: "Household member" },
  };

  const meta = (c, extra) => `<p class="fcard__meta"><span>${esc(AW.fmtTime(c.at))}</span><span title="Also sent in Telegram">${icon("chat", "icon--sm")}<span class="visually-hidden">Also sent in Telegram</span></span>${extra || ""}</p>`;
  const btn = (label, action, opts) => {
    opts = opts || {};
    const data = Object.entries(opts.data || {}).map(([k, v]) => `data-${k}="${esc(v)}"`).join(" ");
    return `<button class="btn ${opts.primary ? "btn--primary" : ""} ${opts.cls || ""}" type="button" data-act="${action}" ${data} ${opts.disabled ? "disabled" : ""}>${opts.icon ? icon(opts.icon) : ""}<span>${esc(label)}${opts.desc ? `<span class="option-desc">${esc(opts.desc)}</span>` : ""}</span></button>`;
  };
  const row = (ic, text) => `<li>${icon(ic)}<span>${text}</span></li>`;

  /* ---------------- Cards ---------------- */
  const R = {
    intake(c) {
      return `${meta(c)}<h3 class="fcard__title">I'm so sorry, Sara. Is this right?</h3>
        <div class="fcard__body">
          <ul class="facts" role="list">
            ${row("user", "<b>Yusuf Malik</b> died on 3 March 2026")}
            ${row("doc", "You're handling the estate <span class='muted'>(as you told me)</span>")}
            ${row("check", "<b>Keep</b> Mum's phone and Dad's voicemail")}
            ${row("cross", "<b>Stop</b> bills nobody needs")}
          </ul>
          <details class="details small"><summary>${icon("chevron-down")}Your voice note</summary><p class="speech__text" style="margin-top:var(--s-2)">“${esc(F.transcripts.sara)}”</p><p class="xsmall muted">Transcribed ${simTag()}</p></details>
        </div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("That's right", "intake.confirm", { primary: true })}${btn("Fix something", "intake.fix")}</div>` : ""}`;
    },
    candidates(c, s) {
      const ask = F.accounts.filter((a) => a.ownership === "unconfirmed");
      const asked = ask.map((a) => {
        const own = s.ownership[a.id];
        const said = { yusuf: "His", other: "Not his", unsure: "Not sure", joint: "Joint with Amina" }[own];
        return `<div class="who-row"><p><b>${esc(a.name)}</b> <span class="muted small">${esc(a.service)}</span></p>
          ${said ? `<p>${chip(own === "unsure" ? "unknown" : "holding", said)}</p>` : `<div class="btn-row btn-row--inline" role="group" aria-label="Whose is ${esc(a.name)} ${esc(a.service)}?">${btn("Dad's", "ownership", { cls: "btn--sm", data: { id: a.id, v: "yusuf" } })}${btn("Someone else's", "ownership", { cls: "btn--sm", data: { id: a.id, v: "other" } })}${btn("Not sure", "ownership", { cls: "btn--sm", data: { id: a.id, v: "unsure" } })}</div>`}</div>`;
      }).join("");
      return `${meta(c)}<h3 class="fcard__title">I found 9 possible accounts</h3>
        <div class="fcard__body">
          <p>Six look like Dad's. Whose are these three?</p>
          <div>${asked}</div>
          <p class="fcard__note">${icon("info", "icon--sm")} Paper post and cash payments won't show up here. Bank statements are the best place to find more.</p>
        </div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("Continue", "candidates.continue", { primary: true })}</div>` : ""}`;
    },
    dependency_notice(c) {
      return `${meta(c)}<h3 class="fcard__title">I've asked Amina one question</h3><div class="fcard__body"><p>Does anyone still use the 4417 line? Nothing changes until she answers.</p></div>`;
    },
    dependency_question(c) {
      const open = c.status === "open";
      return `${meta(c)}<h3 class="fcard__title">Amina, does anyone still use the 4417 number?</h3>
        <div class="fcard__body"><p>It's Yusuf's Northline line. Does it get codes for other accounts, or hold anything you'd want to keep?</p>
        ${open && typing ? `<div class="field"><label class="label" for="amina-text">Your answer</label><textarea class="textarea" id="amina-text">${esc(F.transcripts.amina)}</textarea></div>` : ""}
        </div>
        ${open ? `<div class="fcard__actions btn-row">${typing ? btn("Send", "amina.type", { primary: true, icon: "send" }) + btn("Cancel", "amina.cancel") : btn("Send a voice note", "amina.voice", { primary: true, icon: "mic" }) + btn("Type instead", "amina.typing", { icon: "keyboard" })}</div>` : ""}`;
    },
    dependency_reading(c, s) {
      const a = s.aminaAnswer || { via: "voice", text: F.transcripts.amina };
      return `${meta(c)}<h3 class="fcard__title">Here's what I understood</h3>
        <div class="fcard__body">
          <ul class="facts" role="list">
            ${row("phone", "You use the 4417 number")}
            ${row("lock", "Crescent Bank sends your codes to it")}
            ${row("speaker", "Yusuf's voice is on the voicemail")}
          </ul>
          <details class="details small"><summary>${icon("chevron-down")}What you said</summary><p class="speech__text" style="margin-top:var(--s-2)">“${esc(a.text)}”</p>${a.via === "voice" ? `<p class="xsmall muted">Transcribed ${simTag()}</p>` : ""}</details>
        </div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("That's right", "amina.confirm", { primary: true })}${btn("Fix something", "amina.fix")}</div>` : ""}`;
    },
    amina_thanks(c) {
      return `${meta(c)}<h3 class="fcard__title">Thank you, Amina</h3><div class="fcard__body"><p>Your number and his voicemail are protected. Sara approves the next step.</p></div>`;
    },
    crescent_joint(c, s) {
      return `${meta(c)}<h3 class="fcard__title">Is the Crescent Bank account joint with you?</h3><div class="fcard__body"><p>Only if you know. Nothing happens to it without you both.</p></div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("Yes", "crescent", { data: { v: "yes" } })}${btn("No, only his", "crescent", { data: { v: "no" } })}${btn("Not sure", "crescent", { data: { v: "unsure" } })}</div>` : `<p class="fcard__outcome">${chip("info", { yes: "Joint", no: "Only his", unsure: "Not sure" }[s.crescentJoint])}</p>`}`;
    },
    plan_changed(c, s) {
      return `${meta(c)}<h3 class="fcard__title">Amina's answer changed the plan</h3>
        <div class="fcard__body">
          <div class="diff">
            <div class="diff__row diff__row--old"><span class="diff__v">Before</span><span class="diff__text">Northline 4417: on hold</span></div>
            <div class="diff__row diff__row--new"><span class="diff__v">Now</span><span class="diff__text"><b>Move it to Amina</b>, keeping the number and voicemail, with no new contract</span></div>
            <div class="diff__row diff__row--new"><span class="diff__v">Now</span><span class="diff__text"><b>Keep Crescent Bank open.</b> It may be joint.</span></div>
          </div></div>
        ${!s.planReviewed ? `<div class="fcard__actions btn-row">${btn("Review the Northline request", "plan.reviewed", { primary: true })}<a class="btn" href="desk.html">See the full plan</a></div>` : ""}`;
    },
    approval(c, s) {
      const st = s.approvals.nl, P = F.providers.northline;
      const open = st === "open" || st === "notnow";
      return `<div class="approval ${st === "approved" ? "approval--approved" : ""}" id="approval-nl">
        <div class="approval__head"><h3 class="fcard__title">Send this to Northline?</h3><span class="approval__binding" title="This approval only applies to this exact version of the plan">Plan v2</span></div>
        <div class="approval__body"><ul class="facts" role="list">
          ${row("arrow-right", "<b>Move line 4417 to Amina Malik</b>")}
          ${row("check", "Only if they keep the number and voicemail, with no new contract")}
          ${row("mail", `To ${esc(P.recipient)} <small>From Northline's published contacts</small>`)}
          ${row("photo", "Shares a <b>photo</b> of the death certificate. Nothing else.")}
          ${row("info", "Yusuf's Northline login may stop working")}
          ${row("hand", "If they can't do all of it, I'll stop and ask you")}
        </ul></div>
        <div class="approval__foot">
          ${open ? `<div class="btn-row">${btn("Approve", "approve", { primary: true, data: { id: "nl" } })}${btn("Change", "approval.change", { data: { id: "nl" } })}${st === "notnow" ? "" : btn("Not now", "approval.notnow", { data: { id: "nl" } })}</div>${st === "notnow" ? `<p class="fcard__outcome">${chip("neutral", "Not sent yet")}</p>` : ""}${s.control === "hold" ? `<p class="fcard__note">${icon("hand", "icon--sm")} On hold: this sends when you resume.</p>` : ""}`
          : `<p class="fcard__outcome">${chip("holding", "Approved")}${simTag("Sent (simulated)")}</p>`}
        </div></div>`;
    },
    routine(c, s) {
      const items = [["cp", "citypower", "Close the electricity", "After a final meter reading"], ["sb", "streambox", "Cancel the subscription", "His watch history goes"], ["fl", "fitlife", "Cancel the membership", "Shares a photo of the certificate"]];
      return `${meta(c)}<h3 class="fcard__title">Three more to approve</h3>
        <div class="fcard__body"><p class="small muted">One at a time, because each has consequences.</p>
        <div>${items.map(([k, pid, req, note]) => { const P = F.providers[pid], st = s.approvals[k]; return `<div class="who-row">
          <p><b>${esc(P.name)}</b>: ${esc(req)}<br><span class="small muted">${esc(note)}. To ${esc(P.recipient)}</span></p>
          ${st === "approved" ? `<p>${chip("holding", "Approved")} ${simTag("Sent (simulated)")}</p>` : `<div class="btn-row btn-row--inline">${btn("Approve", "approve", { primary: true, cls: "btn--sm", data: { id: k } })}${st === "notnow" ? chip("neutral", "Not now") : btn("Not now", "approval.notnow", { cls: "btn--sm", data: { id: k } })}</div>`}
        </div>`; }).join("")}</div></div>`;
    },
    not_done(c) {
      const open = c.status === "open";
      return `${meta(c)}<h3 class="fcard__title">Northline says it's done. It isn't.</h3>
        <div class="fcard__body">
          <figure class="quote"><blockquote class="quote__text">Request complete. <mark class="hl-holding">Line transferred to Mrs Malik</mark> on a <mark class="hl-violated">new 24-month plan</mark>. <mark class="hl-violated">Voicemail will be reset</mark> during migration.</blockquote><figcaption class="quote__source">${evLabel("writing")}</figcaption></figure>
          <ul class="checks" role="list">
            <li><span>Moved to Amina</span>${chip("holding", "Yes")}</li>
            <li><span>Voicemail kept</span>${chip("violated", "No, it'll be reset")}</li>
            <li><span>No new contract</span>${chip("unauthorised", "24-month plan added")}</li>
            <li><span>Number kept</span>${chip("unknown", "Not mentioned")}</li>
          </ul>
        </div>
        ${open ? `<div class="fcard__actions btn-row btn-row--stack decision-btns">
          ${btn("Ask them to fix it", "decide", { primary: true, data: { v: "ask" }, desc: "Keep the voicemail, no contract" })}
          ${btn("Call them for me", "decide", { data: { v: "call" }, desc: "I'll check with you before agreeing to anything" })}
          ${btn("Accept anyway", "decide", { data: { v: "accept" }, desc: "The voicemail is reset and the 24-month plan stays" })}
        </div>` : ""}`;
    },
    call_started(c) {
      return `${meta(c)}<h3 class="fcard__title">I'm calling Northline</h3><div class="fcard__body"><p>If they offer anything new, I'll ask you first. <a href="call.html">Listen in</a></p><p>${simTag("Simulated call")}</p></div>`;
    },
    terms(c, s) {
      const t = s.call.terms.find((x) => x.id === c.data.terms);
      const open = c.status === "open", isVoid = c.status === "void";
      return `${meta(c, open ? chip("review", "Call on hold") : "")}
        <h3 class="fcard__title">Northline's offer: ${t.months} months at $${t.price} a month</h3>
        <div class="fcard__body">
          ${open && s.call.terms.some((x) => x.status === "void" && x.id !== t.id) ? (() => { const old = s.call.terms.filter((x) => x.status === "void" && x.id !== t.id).slice(-1)[0]; return `<div class="banner banner--warning" role="note">${icon("warning")}<p class="banner__title">This changed. Here's why.</p><p class="banner__body">Northline withdrew the $${old.price} offer before I accepted it, so your earlier yes no longer counts. Nothing was agreed.</p></div>`; })() : ""}
          ${isVoid ? `<div class="banner banner--warning" role="note">${icon("warning")}<p class="banner__title">This changed. Here's why.</p><p class="banner__body">Northline changed the offer before I accepted. This approval no longer applies, and nothing was agreed.</p></div>` : ""}
          <p>They'll keep the number and voicemail, but only with a new contract in Amina's name.</p>
          <p><span class="quote--inline small">“${esc(t.quote)}”</span> ${evLabel("spoken")}</p>
        </div>
        ${open ? `<div class="fcard__actions btn-row btn-row--stack decision-btns">
          ${btn(`Accept ${t.months} months at $${t.price}`, "terms", { primary: true, data: { t: t.id, v: "approve" }, desc: "If they change anything, I'll ask again" })}
          ${btn("Decline", "terms", { data: { t: t.id, v: "decline" }, desc: "I'll ask for no contract" })}
          ${btn("Not now", "terms", { data: { t: t.id, v: "later" }, desc: "The call stays on hold" })}
        </div>` : isVoid ? `<div class="fcard__actions btn-row"><button class="btn" type="button" disabled>Accept ${t.months} months at $${t.price}</button></div>` : ""}`;
    },
    accepted(c, s) {
      const t = s.call.terms.find((x) => x.id === c.data.terms);
      return `${meta(c)}<h3 class="fcard__title">Accepted on the call</h3><div class="fcard__body"><p>${t.months} months at $${t.price} a month, keeping the number and voicemail. It's not done until Northline puts it in writing.</p></div>`;
    },
    written(c) {
      return `${meta(c)}<h3 class="fcard__title">Northline confirmed it in writing</h3><div class="fcard__body"><figure class="quote"><blockquote class="quote__text"><mark class="hl-holding">Transferred to Amina Malik.</mark> <mark class="hl-holding">The number and the existing voicemail have been kept.</mark> 12 months at $35 per month.</blockquote><figcaption class="quote__source">${evLabel("writing")}</figcaption></figure></div>`;
    },
    voicemail_backup(c) {
      return `${meta(c)}<h3 class="fcard__title">Do you have your own copy of the voicemail?</h3><div class="fcard__body"><p>Then it can't be lost in a future change.</p></div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("Yes, I have a copy", "backup", { data: { v: "yes" } })}${btn("Not yet", "backup", { data: { v: "notyet" } })}</div>` : ""}`;
    },
    certified(c) {
      return `${meta(c)}<h3 class="fcard__title">Northline wants a certified copy</h3><div class="fcard__body"><p>We only have a photo of the certificate, and I won't pass a photo off as certified. Could you post one to them?</p></div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("I'll post it", "certified")}</div>` : ""}`;
    },
    spoof(c) {
      return `${meta(c)}<h3 class="fcard__title">I ignored a suspicious email</h3><div class="fcard__body"><p>Someone posing as Northline asked for the will and bank details from <span class="ref">${esc(c.data.from)}</span>. I didn't reply or send anything.</p></div>${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("Okay", "spoof")}</div>` : ""}`;
    },
    bill(c) {
      return `${meta(c)}<h3 class="fcard__title">City Power's final bill: $61.40</h3><div class="fcard__body"><p>It's for February, before the account closed, so it looks fair. I haven't disputed it, and I never pay bills for you.</p></div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("I'll pay it", "bill", { data: { v: "reviewed" } })}${btn("Ask them to explain", "bill", { data: { v: "asked" } })}</div>` : ""}`;
    },
    refund(c) {
      return `${meta(c)}<h3 class="fcard__title">A $42 refund is on its way</h3><div class="fcard__body"><p>City Power says it's been issued. I'll keep this open until it shows up on a statement.</p></div>
        ${c.status === "open" ? `<div class="fcard__actions btn-row">${btn("I've seen it", "refund", { icon: "photo", desc: "Share the statement (simulated)" })}${btn("Remind me later", "refund.later")}</div>` : ""}`;
    },
    monitoring(c, s) {
      return `${meta(c)}<h3 class="fcard__title">I can't read new replies right now</h3><div class="fcard__body"><p>Access to the family mailbox has expired. Nothing will be checked or marked done until it's back.</p></div>
        ${s.monitoring === "interrupted" ? `<div class="fcard__actions btn-row">${btn("Reconnect", "reconnect", { primary: true })}</div>` : ""}`;
    },
    finished(c) {
      const sum = c.data.summary;
      return `${meta(c)}<h3 class="fcard__title">${esc(sum.headline)}</h3><div class="fcard__body">${summaryHtml(sum)}</div>`;
    },
  };
  const summaryHtml = (sum) => `<ul class="finished__lines" role="list">${sum.lines.map((l) => `<li>${chip(l.tone, l.text)}<small>${esc(l.who)}</small></li>`).join("")}</ul><p class="fcard__note">${esc(sum.caveat)}</p>`;

  /* One-line summaries for finished cards. */
  function line(c, s) {
    const t = c.kind === "terms" || c.kind === "accepted" ? s.call.terms.find((x) => x.id === c.data.terms) : null;
    return ({
      intake: ["check", "You confirmed the summary"],
      candidates: ["check", "9 possible accounts found"],
      dependency_notice: ["chat", "Asked Amina about the 4417 line"],
      dependency_question: ["check", "You answered about the 4417 line"],
      dependency_reading: ["check", "You confirmed what we understood"],
      amina_thanks: ["chat", "Sara has your answer"],
      crescent_joint: ["check", "You answered about Crescent Bank"],
      plan_changed: ["doc", "Plan updated after Amina's answer"],
      approval: ["send", "Northline request approved and sent"],
      routine: ["send", "Three more requests approved"],
      not_done: ["cross", { ask: "Northline wasn't done. You asked them to fix it", call: "Northline wasn't done. You asked for a call", accept: "Northline wasn't done. You accepted anyway" }[c.status]],
      call_started: ["phone", "Called Northline"],
      terms: t ? (c.status === "void" ? ["slash", `$${t.price} offer changed before it was accepted`] : c.status === "approved" ? ["check", `You accepted $${t.price} a month`] : ["cross", "You declined the offer"]) : ["dot", "Offer"],
      accepted: ["phone", "Accepted on the call. Waiting for it in writing"],
      written: ["mail", "Northline confirmed it in writing"],
      voicemail_backup: ["check", c.status === "yes" ? "You have a copy of the voicemail" : "Voicemail copy: not yet"],
      certified: ["doc", "You'll post a certified copy"],
      spoof: ["shield", "Ignored a suspicious email"],
      bill: ["money", c.status === "reviewed" ? "You'll pay City Power's $61.40" : "Asked City Power about the bill"],
      refund: ["money", "$42 refund received"],
      monitoring: ["retry", "Mailbox reconnected"],
      finished: ["chat", "You asked: did we finish everything?"],
    })[c.kind] || ["dot", c.kind];
  }

  function isActive(c, s) {
    if (c.status !== "open") return false;
    if (c.kind === "plan_changed") return !s.planReviewed;
    if (c.kind === "approval") return ["open", "notnow"].includes(s.approvals.nl);
    if (c.kind === "routine") return ["cp", "sb", "fl"].some((k) => s.approvals[k] !== "approved");
    return true;
  }
  const cardHtml = (c, s, active) => {
    const inner = R[c.kind] ? R[c.kind](c, s) : "";
    if (c.kind === "approval") return `<article data-card="${c.id}" aria-label="Approval: Northline request">${inner}</article>`;
    return `<article class="fcard ${c.status === "void" ? "fcard--void" : active ? "fcard--active" : ""}" data-card="${c.id}">${inner}</article>`;
  };
  const earlierCards = (s) => s.cards.filter((c) => c.to === persona && !isActive(c, s)).reverse();

  /* ---------------- Sheets ---------------- */
  const earlierSheet = UI.drawer({ id: "earlier", side: "bottom", title: "Earlier", render: () => {
    const s = AW.state, rest = earlierCards(s);
    if (!rest.length) return `<p class="muted">Nothing yet.</p>`;
    return `<ul class="earlier" role="list">${rest.map((c) => { const [ic, txt] = line(c, s); return `<li><details ${opened.has(c.id) ? "open" : ""} data-row="${c.id}"><summary><span class="earlier__icon">${icon(ic)}</span><span class="earlier__text">${esc(txt)}</span><span class="earlier__time">${esc(AW.fmtDay(c.closedAt != null ? c.closedAt : c.at))}</span></summary><div class="earlier__card">${cardHtml(c, s, false)}</div></details></li>`; }).join("")}</ul>`;
  } });
  const askSheet = UI.drawer({ id: "ask", side: "bottom", title: "Did you finish everything?", render: () => {
    const s = AW.state;
    if (s.intake !== "confirmed") return `<p>Not yet. Confirm the summary first and I'll get started.</p>`;
    const sum = AW.summary();
    return `<p class="lede" style="font-size:var(--fs-base)">${esc(sum.headline)}</p>${summaryHtml(sum)}`;
  } });
  const pauseSheet = UI.drawer({ id: "pause", side: "bottom", title: "Pause or stop", render: () => {
    const s = AW.state;
    return `<div class="btn-row btn-row--stack decision-btns">
      ${btn(s.control === "quiet" ? "Turn quiet off" : "Quiet until tomorrow", "control", { data: { v: s.control === "quiet" ? "active" : "quiet" }, icon: "moon", desc: "No messages to you. Work carries on." })}
      ${btn(s.control === "hold" ? "Resume" : "Hold", "control", { data: { v: s.control === "hold" ? "active" : "hold" }, icon: "hand", desc: "Nothing goes out to organisations." })}
      ${btn(s.control === "stopped" ? "Restart" : "Stop everything", "control", { data: { v: s.control === "stopped" ? "active" : "stopped" }, icon: "stop", cls: s.control === "stopped" ? "" : "btn--danger", desc: "Including monitoring. You can export, then delete." })}
    </div>
    <p class="small muted">Feeling overwhelmed? <a href="https://findahelpline.com" rel="noopener">Find someone to talk to</a>. The admin can wait.</p>`;
  } });
  [earlierSheet, askSheet, pauseSheet].forEach((d) => d.el.addEventListener("click", (e) => { const b = e.target.closest("[data-act]"); if (b && !b.disabled && act[b.dataset.act]) act[b.dataset.act](b); }));
  earlierSheet.el.addEventListener("toggle", (e) => { const d = e.target; if (d.matches && d.matches("[data-row]")) { if (d.open) opened.add(d.dataset.row); else opened.delete(d.dataset.row); } }, true);

  /* ---------------- Render ---------------- */
  function render() {
    const s = AW.state, P = PEOPLE[persona];
    const URGENT = ["monitoring", "terms", "spoof"];
    const active = s.cards.filter((c) => c.to === persona && isActive(c, s)).sort((x, y) => (URGENT.includes(y.kind) ? 1 : 0) - (URGENT.includes(x.kind) ? 1 : 0));
    const rest = earlierCards(s);
    if (page >= active.length) page = Math.max(0, active.length - 1);
    const cur = active[page];

    const banners = [];
    if (persona === "sara" && s.monitoring === "interrupted") banners.push(`<div class="banner banner--interrupted">${icon("eye-off")}<p class="banner__title">Mailbox disconnected</p><p class="banner__body">Replies aren't being read until it's back.</p><div class="banner__actions">${btn("Reconnect", "reconnect", { cls: "btn--sm" })}</div></div>`);
    if (persona === "sara" && s.control !== "active") banners.push(`<div class="banner banner--hold">${icon(s.control === "quiet" ? "moon" : s.control === "hold" ? "hand" : "stop")}<p class="banner__title">${{ quiet: "Quiet until tomorrow", hold: "On hold", stopped: "Stopped" }[s.control]}</p></div>`);
    if (persona === "sara" && s.call.status === "live" && !(cur && cur.kind === "terms")) banners.push(`<div class="banner">${icon("phone")}<p class="banner__title">On a call with Northline</p><p class="banner__body"><a href="call.html">Listen in</a></p></div>`);

    phone.innerHTML = `
      <div class="persona"><span class="avatar avatar--${persona}" aria-hidden="true">${P.initial}</span><div><h1 class="persona__name" id="persona-name">${esc(P.name)}</h1><p class="persona__role">${esc(P.role)}</p></div>
        <button class="btn btn--sm persona-switch" type="button" data-persona="${persona === "sara" ? "amina" : "sara"}">View as ${persona === "sara" ? "Amina" : "Sara"}</button></div>
      ${banners.join("")}
      <section class="needs" aria-labelledby="needs-you" id="active">
        <div class="needs__head"><h2 class="h4" id="needs-you">${active.length ? "Needs you" : "Nothing needs you"}</h2>${active.length > 1 ? `<span class="pager"><button class="icon-btn" type="button" data-page="-1" aria-label="Previous" ${page === 0 ? "disabled" : ""}>${icon("arrow-left")}</button><span aria-live="polite">${page + 1} of ${active.length}</span><button class="icon-btn" type="button" data-page="1" aria-label="Next" ${page === active.length - 1 ? "disabled" : ""}>${icon("arrow-right")}</button></span>` : ""}</div>
        ${cur ? `<div class="needs__card ${lastCard !== null && lastCard !== cur.id ? "settle" : ""}">${cardHtml(cur, s, true)}</div>` : `<div class="calm"><svg class="empty__art" viewBox="0 0 96 56" aria-hidden="true"><path d="M8 48H88" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M34 48A14 14 0 0 1 62 48" fill="currentColor"/><path d="M24 40A24 24 0 0 1 72 40" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg><p>${persona === "amina" ? "I'll only message you when there's something only you can answer." : "I'm working in the background. I'll tell you when something needs you."}</p></div>`}
      </section>
      <nav class="dock" aria-label="More">
        <button type="button" data-sheet="earlier">${icon("clock")}Earlier${rest.length ? `<span class="badge" aria-label="${rest.length} items">${rest.length}</span>` : ""}</button>
        <button type="button" data-sheet="ask" ${persona === "amina" ? "disabled" : ""}>${icon("chat")}Where are we?</button>
        <button type="button" data-sheet="pause" ${persona === "amina" ? "disabled" : ""}>${icon("pause")}Pause</button>
      </nav>`;

    ctx.innerHTML = `<section class="card card--sim stack stack-sm" aria-labelledby="persona-switch">
        <h2 class="h4" id="persona-switch">View as</h2>
        <div class="segmented" role="group" aria-labelledby="persona-switch">
          <button type="button" data-persona="sara" aria-pressed="${persona === "sara"}">Sara</button>
          <button type="button" data-persona="amina" aria-pressed="${persona === "amina"}">Amina</button>
        </div>
        <p class="small secondary">The same cards arrive in Telegram or WhatsApp. This is the web version.</p>
      </section>`;
    lastCard = cur ? cur.id : "";
    earlierSheet.refresh(); askSheet.refresh(); pauseSheet.refresh();
  }

  /* ---------------- Events ---------------- */
  const act = {
    "intake.confirm": () => AW.dispatch("intake.confirm"),
    "intake.fix": () => AW.dispatch("intake.fix"),
    "ownership": (b) => AW.dispatch("ownership.set", { id: b.dataset.id, value: b.dataset.v }),
    "candidates.continue": () => AW.dispatch("candidates.continue"),
    "amina.voice": (b) => { b.setAttribute("aria-busy", "true"); b.disabled = true; b.querySelector("span").firstChild.textContent = "Listening…"; setTimeout(() => AW.dispatch("amina.voice"), 900); },
    "amina.typing": () => { typing = true; render(); const t = document.getElementById("amina-text"); if (t) t.focus(); },
    "amina.cancel": () => { typing = false; render(); },
    "amina.type": () => { const t = document.getElementById("amina-text"); typing = false; AW.dispatch("amina.type", { text: t ? t.value : "" }); },
    "amina.confirm": () => AW.dispatch("amina.confirm"),
    "amina.fix": () => AW.dispatch("amina.fix"),
    "crescent": (b) => AW.dispatch("crescent.joint", { value: b.dataset.v }),
    "plan.reviewed": () => AW.dispatch("plan.reviewed"),
    "approve": (b) => AW.dispatch("approve", { id: b.dataset.id }),
    "approval.notnow": (b) => AW.dispatch("approval.notnow", { id: b.dataset.id }),
    "approval.change": (b) => AW.dispatch("approval.change", { id: b.dataset.id }),
    "decide": (b) => AW.dispatch("decide", { choice: b.dataset.v }),
    "terms": (b) => AW.dispatch("terms.decide", { terms: b.dataset.t, choice: b.dataset.v }),
    "backup": (b) => AW.dispatch("voicemail.backup", { value: b.dataset.v }),
    "certified": () => AW.dispatch("certified.ack"),
    "spoof": () => AW.dispatch("spoof.ack"),
    "bill": (b) => AW.dispatch("bill.decide", { value: b.dataset.v }),
    "refund": (b) => { b.setAttribute("aria-busy", "true"); b.disabled = true; setTimeout(() => AW.dispatch("refund.received"), 700); },
    "refund.later": () => UI.announce("Okay, I'll ask again later.", { toast: true }),
    "reconnect": () => AW.dispatch("monitoring.set", { value: "ok" }),
    "control": (b) => { if (b.dataset.v === "stopped" && !window.confirm("Stop everything, including monitoring? You'll be offered an export, then deletion.")) return; AW.dispatch("control.set", { value: b.dataset.v }); },
  };
  UI.on(phone, "[data-act]", "click", (e, b) => { if (b.disabled) return; const f = act[b.dataset.act]; if (f) f(b); });
  UI.on(phone, "[data-sheet]", "click", (e, b) => {
    const key = b.dataset.sheet;
    const refocus = () => { const n = phone.querySelector(`[data-sheet="${key}"]`); if (n) n.focus(); };
    [earlierSheet, askSheet, pauseSheet].forEach((d) => { d.el.addEventListener("close", refocus, { once: true }); });
    if (b.dataset.sheet === "earlier") earlierSheet.open();
    if (b.dataset.sheet === "ask") { if (AW.state.intake === "confirmed") AW.dispatch("finished.ask"); askSheet.open(); }
    if (b.dataset.sheet === "pause") pauseSheet.open();
  });
  UI.on(phone, "[data-page]", "click", (e, b) => { page += Number(b.dataset.page); render(); const n = phone.querySelector(`[data-page="${b.dataset.page}"]:not([disabled])`); if (n) n.focus(); else UI.focusFirst(phone.querySelector(".needs__card")); });
  UI.on(document.body, "[data-persona]", "click", (e, b) => {
    persona = b.dataset.persona; typing = false; page = 0;
    const u = new URL(location.href); u.searchParams.set("as", persona); history.replaceState(null, "", u);
    render(); const n = document.querySelector(`[data-persona="${persona}"]`) || document.querySelector("[data-persona]"); if (n) n.focus();
    UI.announce(`Viewing as ${PEOPLE[persona].name}.`);
  });

  // After an action, focus moves to the next decision so keyboard users keep their place.
  AW.subscribe((s, local) => {
    const inSheet = document.activeElement && document.activeElement.closest(".drawer");
    const before = document.activeElement && document.activeElement.closest("[data-card]");
    const beforeId = before && before.dataset.card;
    render();
    if (!local || inSheet) return;
    const still = beforeId && phone.querySelector(`[data-card="${beforeId}"] button:not([disabled])`);
    if (still) { still.focus(); return; }
    const next = phone.querySelector(".needs__card button:not([disabled])");
    if (next) next.focus();
  });
  render();
})();
