/* Family view: phone-first web version of the cards Sara and Amina receive in chat.
   Every card has at most three choices, matching WhatsApp's button limit. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, status, chip, evLabel, simTag } = UI;
  UI.shell("family", { context: "Family view" });

  const phone = document.getElementById("phone");
  const ctx = document.getElementById("family-context");
  let persona = UI.param("as") === "amina" ? "amina" : "sara";
  let typing = false;      // Amina's typed-answer form is open
  let showControls = false;
  let candOpen = true;

  const PEOPLE = {
    sara: { name: "Sara Malik", initial: "S", role: "Case owner · his daughter; handling the estate (stated)" },
    amina: { name: "Amina Malik", initial: "A", role: "Household member · his wife; joined by invite link" },
  };

  const from = (c, extra) => `<p class="fcard__meta"><span class="fcard__from">${UI.compactMark()}Afterward</span><span>${esc(AW.fmtTime(c.at))}</span><span>${icon("chat", "icon--sm")} Also sent in Telegram</span>${extra || ""}</p>`;
  const btn = (label, action, opts) => {
    opts = opts || {};
    const data = Object.entries(opts.data || {}).map(([k, v]) => `data-${k}="${esc(v)}"`).join(" ");
    return `<button class="btn ${opts.primary ? "btn--primary" : ""} ${opts.cls || ""}" type="button" data-act="${action}" ${data} ${opts.disabled ? "disabled" : ""}>${opts.icon ? icon(opts.icon) : ""}<span>${esc(label)}${opts.desc ? `<span class="option-desc">${esc(opts.desc)}</span>` : ""}</span></button>`;
  };
  const outcome = (c, text, kind) => `<p class="fcard__outcome">${chip(kind || "holding", text)}<span>${esc(AW.fmtTime(c.closedAt != null ? c.closedAt : c.at))}</span></p>`;
  const holdNote = (s) => s.control === "hold" ? `<p class="fcard__note">${icon("hand", "icon--sm")} The case is on hold. Your answer is recorded; nothing goes out to organisations until you resume.</p>` : "";

  /* ---------------- Card renderers ---------------- */
  const R = {
    intake(c, s) {
      const open = c.status === "open";
      return `${from(c)}<h3 class="fcard__title">I'm so sorry, Sara.</h3>
        <div class="fcard__body">
          <p>I'll handle the emails and follow-ups so you don't have to explain this again. Here's what I understood from your voice note:</p>
          <div class="speech"><p class="speech__who">${icon("mic", "icon--sm")}Your voice note · transcribed ${simTag()}</p><p class="speech__text">“${esc(F.transcripts.sara)}”</p></div>
          <dl class="deflist">
            <dt>Who died</dt><dd>Yusuf Malik, on 3 March 2026</dd>
            <dt>You</dt><dd>His daughter, handling the estate <span class="muted">(as you've told me)</span></dd>
            <dt>Keep</dt><dd>Mum's phone · Dad's voicemail</dd>
            <dt>Stop</dt><dd>Bills nobody needs</dd>
          </dl>
        </div>
        ${open ? `<div class="fcard__actions btn-row">${btn("That's right", "intake.confirm", { primary: true })}${btn("Fix something", "intake.fix")}</div>` : outcome(c, "You confirmed this")}`;
    },
    candidates(c, s) {
      const open = c.status === "open";
      const list = F.accounts.map((a) => {
        const own = s.ownership[a.id] || a.ownership;
        const ask = ["unconfirmed", "unsure"].includes(own) && a.ownership === "unconfirmed";
        const lab = { confirmed: chip("holding", "His"), yusuf: chip("holding", "His (you said)"), other: chip("neutral", "Not his (you said)"), unsure: chip("unknown", "Not sure yet"), unconfirmed: chip("unknown", "Whose is this?"), joint: chip("info", "Joint with Amina (stated)") }[own];
        return `<li class="cand"><span><span class="cand__name">${esc(a.name)}</span> · ${esc(a.service)}</span>${lab || ""}
          <span class="cand__meta"><span>${icon(a.origin.startsWith("Photo") ? "photo" : "mail", "icon--sm")} ${esc(a.origin)}</span>${a.note ? `<span>${esc(a.note)}</span>` : ""}</span>
          ${ask && own === "unconfirmed" ? `<span class="cand__ask" role="group" aria-label="Whose is ${esc(a.name)} ${esc(a.service)}?">${btn("Yusuf's", "ownership", { cls: "btn--sm", data: { id: a.id, v: "yusuf" } })}${btn("Someone else's", "ownership", { cls: "btn--sm", data: { id: a.id, v: "other" } })}${btn("Not sure", "ownership", { cls: "btn--sm", data: { id: a.id, v: "unsure" } })}</span>` : ""}
        </li>`;
      }).join("");
      return `${from(c)}<h3 class="fcard__title">I found 9 possible accounts</h3>
        <div class="fcard__body">
          <p>From the 6 emails and 4 photos you sent. <b>3 need you to say whose they are.</b> You can answer now or later.</p>
          <details class="details" ${candOpen ? "open" : ""} data-cands><summary>${icon("chevron-down")}See all 9</summary><ul class="cands" role="list">${list}</ul></details>
          <div class="banner">${icon("info")}<p class="banner__title">This list isn't complete, and I won't pretend it is</p><p class="banner__body">Paper-only accounts, other email addresses and cash payments won't show up here. Bank statements are the best place to look for more.</p></div>
        </div>
        ${open ? `<div class="fcard__actions btn-row">${btn("Continue", "candidates.continue", { primary: true, desc: "The list stays open for new accounts" })}</div>` : outcome(c, "Reviewed. The list stays open", "info")}`;
    },
    dependency_notice(c) {
      return `${from(c)}<h3 class="fcard__title">I've asked Amina one question</h3><div class="fcard__body"><p>Before anything changes with Northline Mobile, I've asked her whether anyone still uses the line ending 4417. I'll tell you what she says. Nothing changes until then.</p></div>`;
    },
    dependency_question(c, s) {
      const open = c.status === "open";
      return `${from(c)}<h3 class="fcard__title">Amina, one question before anything changes</h3>
        <div class="fcard__body"><p class="lede">With Northline Mobile, the line ending 4417: does anyone still use this number, or does it get codes for any other account? Is there anything on it you'd want to keep?</p><p class="fcard__note">A voice note is fine. Take your time.</p>
        ${open && typing ? `<div class="field"><label class="label" for="amina-text">Your answer</label><textarea class="textarea" id="amina-text">${esc(F.transcripts.amina)}</textarea><span class="hint">Prefilled with the demo answer. Change it if you like; the prototype reads it the same way.</span></div>` : ""}
        </div>
        ${open ? `<div class="fcard__actions btn-row">${typing ? btn("Send answer", "amina.type", { primary: true, icon: "send" }) + btn("Cancel", "amina.cancel") : btn("Send a voice note", "amina.voice", { primary: true, icon: "mic", desc: "Simulated: nothing is recorded" }) + btn("Type an answer", "amina.typing", { icon: "keyboard" })}</div>` : outcome(c, "Answered")}`;
    },
    dependency_reading(c, s) {
      const open = c.status === "open", a = s.aminaAnswer || { via: "voice", text: F.transcripts.amina };
      return `${from(c)}<h3 class="fcard__title">Here's what I understood</h3>
        <div class="fcard__body">
          <div class="speech"><p class="speech__who">${icon(a.via === "voice" ? "mic" : "keyboard", "icon--sm")}Your ${a.via === "voice" ? "voice note · transcribed" : "message"} ${a.via === "voice" ? simTag() : ""}</p><p class="speech__text">“${esc(a.text)}”</p></div>
          <ul class="cond-list" role="list">
            <li>${chip("info", "Shared service")}<span>You use the 4417 number</span></li>
            <li>${chip("info", "Access")}<span>Crescent Bank sends your login codes to it</span></li>
            <li>${chip("info", "Memory")}<span>Yusuf's voice is on the voicemail</span></li>
          </ul>
        </div>
        ${open ? `<div class="fcard__actions btn-row">${btn("That's right", "amina.confirm", { primary: true })}${btn("Fix something", "amina.fix")}</div>` : outcome(c, "You confirmed this")}`;
    },
    amina_thanks(c) {
      return `${from(c)}<h3 class="fcard__title">Thank you, Amina</h3><div class="fcard__body"><p>Nothing will happen to your number or the voicemail without those protections. Sara approves requests for this case, so I've passed this on to her.</p><p class="fcard__note">${icon("info", "icon--sm")} As a household member you can answer questions and suggest changes. Approvals are Sara's.</p></div>`;
    },
    crescent_joint(c, s) {
      const open = c.status === "open";
      const said = { yes: "Joint with you", no: "Only his", unsure: "Not sure yet" }[s.crescentJoint];
      return `${from(c)}<h3 class="fcard__title">One more, only if you know</h3><div class="fcard__body"><p>Is the Crescent Bank account ending 0932 a joint account with you? I won't contact the bank about it either way until you and Sara agree.</p></div>
        ${open ? `<div class="fcard__actions btn-row">${btn("Yes, it's joint", "crescent", { data: { v: "yes" } })}${btn("No, only his", "crescent", { data: { v: "no" } })}${btn("I'm not sure", "crescent", { data: { v: "unsure" } })}</div>` : outcome(c, `You said: ${said}`, "info")}`;
    },
    plan_changed(c, s) {
      return `${from(c)}<h3 class="fcard__title">Amina's answer changed the plan</h3>
        <div class="fcard__body"><p>Amina still uses the 4417 line, and Crescent Bank sends her codes to it. Here's what changed:</p>
          <div class="diff">
            <div class="diff__row diff__row--old"><span class="diff__v">v1</span><span class="diff__text">Northline 4417: hold and check with the household first</span></div>
            <div class="diff__row diff__row--new"><span class="diff__v">v2</span><span class="diff__text"><b>Transfer to Amina</b>, only if the number and the voicemail are kept and there's no new contract. If they can't, I'll hold and ask you.</span></div>
            <div class="diff__row diff__row--old"><span class="diff__v">v1</span><span class="diff__text">Crescent Bank 0932: notify the bank</span></div>
            <div class="diff__row diff__row--new"><span class="diff__v">v2</span><span class="diff__text"><b>Don't close.</b> It may be a joint account Amina relies on.</span></div>
          </div></div>
        ${!s.planReviewed ? `<div class="fcard__actions btn-row">${btn("Review the Northline request", "plan.reviewed", { primary: true })}<a class="btn" href="desk.html">See the full plan</a></div>` : ""}`;
    },
    approval(c, s) {
      const st = s.approvals.nl, P = F.providers.northline;
      const open = st === "open" || st === "notnow";
      return `<div class="approval ${st === "approved" ? "approval--approved" : ""}" id="approval-nl">
        <div class="approval__head"><div><p class="eyebrow">Approval needed · one request</p><h3 class="fcard__title">Transfer the 4417 line to Amina</h3></div><span class="approval__binding">plan v2 · #${esc(c.data.hash)}</span></div>
        <div class="approval__body"><dl class="deflist">
          <dt>To</dt><dd>Northline Mobile, bereavement team<br><span class="ref">${esc(P.recipient)}</span> <span class="xsmall muted">from Northline's declared profile</span></dd>
          <dt>Account</dt><dd>Mobile line ending 4417</dd>
          <dt>Request</dt><dd><b>Transfer to Amina Malik</b></dd>
          <dt>Conditions</dt><dd><ul class="cond-list" role="list"><li>${icon("check", "icon--sm")}Keep the number</li><li>${icon("check", "icon--sm")}Keep the voicemail</li><li>${icon("check", "icon--sm")}No new contract</li></ul></dd>
          <dt>Documents</dt><dd>Death certificate (<b>photo</b>). Northline's profile accepts a photo. Nothing else is shared.</dd>
          <dt>Consequence</dt><dd>Northline will change the account holder. Yusuf's online Northline login may stop working.</dd>
          <dt>If a condition can't be met</dt><dd>Hold and ask you</dd>
        </dl></div>
        <div class="approval__foot">
          ${open ? `<div class="btn-row">${btn("Approve", "approve", { primary: true, data: { id: "nl" } })}${btn("Change", "approval.change", { data: { id: "nl" } })}${st === "notnow" ? "" : btn("Not now", "approval.notnow", { data: { id: "nl" } })}</div>
            <p class="fcard__note" style="margin-top:var(--s-2)">Approving sends one email to the address above. In this prototype nothing is sent.</p>${st === "notnow" ? `<p class="fcard__outcome">${chip("neutral", "Not now: nothing sent")}</p>` : ""}${holdNote(s)}`
          : `<p class="fcard__outcome">${chip("holding", "Approved")}<span>${esc(AW.fmtTime(c.closedAt))}</span>${simTag("Sent (simulated)")}</p>`}
        </div></div>`;
    },
    routine(c, s) {
      const items = [["cp", "citypower", "Close the electricity account", "14 Orchard Row · CP-77120", "None", "The supply ends after a final meter read. Amina should confirm she has her own account if she needs power at the house.", "Close"], ["sb", "streambox", "Cancel the subscription", "SB-88213", "None", "Access to his watch history ends.", "Cancel"], ["fl", "fitlife", "Cancel the membership", "FL-5531", "Death certificate (photo)", "Membership ends; no further payments.", "Cancel"]];
      return `${from(c)}<h3 class="fcard__title">3 more requests are ready</h3>
        <div class="fcard__body"><p>Each one is approved separately, because closing or cancelling has consequences.</p>
        ${items.map(([k, pid, req, ref, docs, cons]) => { const P = F.providers[pid], st = s.approvals[k]; return `<div class="card card--flat" style="padding:var(--s-4)">
          <p class="h4">${esc(P.name)}: ${esc(req)}</p>
          <dl class="deflist small" style="margin-top:var(--s-2)"><dt>To</dt><dd><span class="ref">${esc(P.recipient)}</span></dd><dt>Account</dt><dd>${esc(ref)}</dd><dt>Documents</dt><dd>${esc(docs)}</dd><dt>Consequence</dt><dd>${esc(cons)}</dd></dl>
          ${st === "approved" ? `<p class="fcard__outcome">${chip("holding", "Approved")}${simTag("Sent (simulated)")}</p>` : `<div class="btn-row" style="margin-top:var(--s-3)">${btn("Approve", "approve", { primary: true, cls: "btn--sm", data: { id: k } })}${st === "notnow" ? `<span class="status status--neutral">${icon("dash")}Not now</span>` : btn("Not now", "approval.notnow", { cls: "btn--sm", data: { id: k } })}</div>`}
        </div>`; }).join("")}</div>`;
    },
    not_done(c, s) {
      const open = c.status === "open";
      const label = { ask: "You chose: ask them to correct it", call: "You chose: call them", accept: "You chose: accept anyway" }[c.status];
      return `${from(c, `<span class="status status--violated">${icon("cross")}Not done</span>`)}<h3 class="fcard__title">Northline says it's complete, but it isn't what you approved</h3>
        <div class="fcard__body">
          <figure class="quote"><blockquote class="quote__text">Request complete. <mark class="hl-holding">Line transferred to Mrs Malik</mark> on a <mark class="hl-violated">new 24-month plan</mark>. <mark class="hl-violated">Voicemail will be reset</mark> during migration.</blockquote><figcaption class="quote__source"><span class="verified">${icon("check", "icon--sm")}Quote found in their email</span>${evLabel("writing")}</figcaption></figure>
          <ul class="checks" role="list">
            <li><span>Transfer to Amina</span>${chip("holding", "Done")}</li>
            <li><span>Keep the number</span>${chip("unknown", "Not stated")}</li>
            <li><span>Keep the voicemail</span>${chip("violated", "Will be reset")}</li>
            <li><span>No new contract</span>${chip("unauthorised", "24-month plan added")}</li>
          </ul>
          <p><b>I haven't marked this done.</b> What would you like me to do?</p>
        </div>
        ${open ? `<div class="fcard__actions btn-row btn-row--stack decision-btns">
          ${btn("Ask them to keep the voicemail, no contract", "decide", { primary: true, data: { v: "ask" }, desc: "I'll email a correction quoting what's outstanding" })}
          ${btn("Call them for me", "decide", { data: { v: "call" }, desc: "Simulated call. I'll pause and ask you before agreeing to anything new" })}
          ${btn("Accept anyway", "decide", { data: { v: "accept" }, desc: "Keeps the 24-month plan and lets the voicemail reset" })}
        </div>` : outcome(c, label, "info")}`;
    },
    call_started(c) {
      return `${from(c)}<h3 class="fcard__title">I'm calling Northline now</h3><div class="fcard__body"><p>I'll say I'm an AI acting for your family. If they offer anything that isn't in your plan, I'll pause the call and ask you first.</p><p class="fcard__note">${simTag("Simulated provider call")} Browser call room, not a phone call. <a href="call.html">Open the call room</a></p></div>`;
    },
    terms(c, s) {
      const t = s.call.terms.find((x) => x.id === c.data.terms);
      const open = c.status === "open";
      const isVoid = c.status === "void";
      return `<div class="fcard__inner">${from(c, isVoid ? `<span class="status status--neutral">${icon("slash")}No longer applies</span>` : open ? `<span class="status status--review">${icon("pause")}Call on hold</span>` : "")}
        <h3 class="fcard__title">Northline offers new terms on the call</h3>
        <div class="fcard__body">
          ${isVoid ? `<div class="banner banner--warning" role="note">${icon("warning")}<p class="banner__title">This changed. Here's why.</p><p class="banner__body">Northline changed the terms at ${esc(AW.fmtTime(c.closedAt))}, before I accepted. Your approval for these terms no longer applies. Nothing was agreed${t.status === "void" && s.call.terms.some((x) => x.id !== t.id) ? "; the new offer is above" : ""}.</p></div>` : ""}
          <p>They'll keep the number and the voicemail, but only on a <b>${t.months}-month contract at $${t.price} a month</b>, in Amina's name. That's a new contract you haven't approved.</p>
          <dl class="deflist small"><dt>They said</dt><dd><span class="quote--inline">“${esc(t.quote)}”</span> ${evLabel("spoken")}</dd><dt>Bound to</dt><dd><span class="ref">terms ${esc(t.id)} · #${esc(t.hash)}</span></dd><dt>If they change anything</dt><dd>This approval stops applying, and I ask you again</dd></dl>
        </div>
        ${open ? `<div class="fcard__actions btn-row btn-row--stack decision-btns">
          ${btn(`Accept ${t.months} months at $${t.price}`, "terms", { primary: true, data: { t: t.id, v: "approve" }, desc: "I'll accept on the call using exactly these terms" })}
          ${btn("Decline", "terms", { data: { t: t.id, v: "decline" }, desc: "I'll ask whether the transfer can go ahead without a contract" })}
          ${btn("Not now", "terms", { data: { t: t.id, v: "later" }, desc: "The call stays on hold" })}
        </div>` : isVoid ? `<div class="fcard__actions btn-row"><button class="btn" type="button" disabled>Accept ${t.months} months at $${t.price}</button></div>` : outcome(c, c.status === "approved" ? (t.status === "accepted" ? "Approved and accepted on the call" : "Approved: acceptance ready") : "Declined", c.status === "approved" ? "holding" : "neutral")}</div>`;
    },
    accepted(c, s) {
      const t = s.call.terms.find((x) => x.id === c.data.terms);
      return `${from(c)}<h3 class="fcard__title">I accepted on the call, using exactly your terms</h3><div class="fcard__body"><p>Transfer to Amina, keeping the number and the voicemail, on a ${t.months}-month contract at $${t.price} a month.</p><p>${chip("waiting", "Not done yet")} It's only done when Northline confirms it in writing. I've asked them to.</p></div>`;
    },
    written(c) {
      return `${from(c, `<span class="status status--holding">${icon("check")}Resolved</span>`)}<h3 class="fcard__title">Northline confirmed everything in writing</h3><div class="fcard__body"><figure class="quote"><blockquote class="quote__text"><mark class="hl-holding">The line ending 4417 has been transferred to Amina Malik.</mark> <mark class="hl-holding">The number and the existing voicemail have been kept.</mark> The new plan is 12 months at $35 per month, as agreed on the call.</blockquote><figcaption class="quote__source">${evLabel("writing")}</figcaption></figure></div>`;
    },
    voicemail_backup(c) {
      const open = c.status === "open";
      return `${from(c)}<h3 class="fcard__title">Do you have your own copy of the voicemail?</h3><div class="fcard__body"><p>Northline says the greeting is kept. A copy of your own means it can't be lost in a future change.</p></div>
        ${open ? `<div class="fcard__actions btn-row">${btn("Yes, I have a copy", "backup", { data: { v: "yes" } })}${btn("Not yet", "backup", { data: { v: "notyet" } })}</div>` : outcome(c, c.status === "yes" ? "Family confirmed backup" : "Not yet: I'll ask again next week", c.status === "yes" ? "holding" : "neutral")}`;
    },
    certified(c) {
      const open = c.status === "open";
      return `${from(c, chip("violated", "Requirement unmet"))}<h3 class="fcard__title">Northline wants a certified copy</h3><div class="fcard__body"><p>You've shared a <b>photo</b> of the death certificate. I won't send a photo as if it were a certified copy.</p><p>Next step: post a certified copy to Northline's bereavement team. The address is in their profile.</p></div>
        ${open ? `<div class="fcard__actions btn-row">${btn("I'll post it", "certified")}</div>` : outcome(c, "You'll post it", "info")}`;
    },
    spoof(c) {
      const open = c.status === "open";
      return `${from(c, chip("violated", "Held"))}<h3 class="fcard__title">An email I didn't trust</h3><div class="fcard__body"><p>An email claiming to be Northline came from <span class="ref">${esc(c.data.from)}</span>, which isn't on Northline's approved list. It asks for the full will and bank details.</p><p><b>I haven't replied or sent anything, and I won't.</b> Emails can't add new people to send things to.</p></div>${open ? `<div class="fcard__actions btn-row">${btn("Understood", "spoof")}</div>` : ""}`;
    },
    bill(c) {
      const open = c.status === "open";
      return `${from(c, chip("review", "Needs review"))}<h3 class="fcard__title">City Power sent a final bill</h3><div class="fcard__body"><p><b>$61.40</b>, dated 2 April, for electricity used <b>1 to 28 February</b>, before the account closed on 31 March.</p><p>That looks like a valid final charge, so I haven't disputed it. I never pay bills for you.</p></div>
        ${open ? `<div class="fcard__actions btn-row">${btn("It's fine, I'll pay it", "bill", { data: { v: "reviewed" } })}${btn("Ask City Power to explain", "bill", { data: { v: "asked" } })}</div>` : outcome(c, c.status === "reviewed" ? "You'll pay it" : "Asked City Power", "info")}`;
    },
    refund(c) {
      const open = c.status === "open";
      return `${from(c, chip("waiting", "Issued, awaiting receipt"))}<h3 class="fcard__title">City Power says it issued a $42.00 refund</h3><div class="fcard__body"><p>I'll keep this open until it shows up on a statement. "Issued" isn't the same as received.</p></div>
        ${open ? `<div class="fcard__actions btn-row">${btn("Share a statement", "refund", { icon: "photo", desc: "Simulated upload" })}${btn("Remind me later", "refund.later")}</div>` : outcome(c, "Received: seen on a statement", "holding")}`;
    },
    monitoring(c, s) {
      const ok = s.monitoring === "ok";
      return `${from(c, ok ? chip("holding", "Fixed") : chip("violated", "Interrupted"))}<h3 class="fcard__title">I can't read new replies right now</h3><div class="fcard__body"><p>Access to the family mailbox has expired. Until it's reconnected I can't see what organisations send, so nothing will be checked or marked done in the meantime.</p></div>
        ${s.monitoring === "interrupted" ? `<div class="fcard__actions btn-row">${btn("Reconnect", "reconnect", { primary: true, desc: "Simulated: no sign-in happens" })}</div>` : outcome(c, "Reconnected", "holding")}`;
    },
    finished(c) {
      const sum = c.data.summary;
      return `<div class="speech" style="margin-bottom:var(--s-3);background:var(--c-dawn-soft)"><p class="speech__who" style="color:var(--c-dawn-ink)">You asked</p><p class="speech__text">Did you finish everything?</p></div>
        ${from(c)}<h3 class="fcard__title">${esc(sum.headline)}</h3><div class="fcard__body"><ul class="finished__lines" role="list">${sum.lines.map((l) => `<li>${chip(l.tone, l.text)}<small>${esc(l.who)}</small></li>`).join("")}</ul><p class="fcard__note">${esc(sum.caveat)}</p></div>`;
    },
  };

  /* ---------------- Render ---------------- */
  function isActive(c, s) {
    if (c.status !== "open") return false;
    if (c.kind === "approval") return ["open", "notnow"].includes(s.approvals.nl);
    if (c.kind === "plan_changed") return !s.planReviewed;
    if (c.kind === "routine") return ["cp", "sb", "fl"].some((k) => s.approvals[k] !== "approved");
    return true;
  }
  function render() {
    const s = AW.state, P = PEOPLE[persona];
    const mine = s.cards.filter((c) => c.to === persona);
    const active = mine.filter((c) => isActive(c, s));
    const rest = mine.filter((c) => !isActive(c, s)).reverse();
    const cardHtml = (c, act) => {
      const cls = c.status === "void" ? "fcard--void" : act ? "fcard--active" : "";
      const inner = R[c.kind] ? R[c.kind](c, s) : "";
      return c.kind === "approval" ? `<article class="settle" data-card="${c.id}" aria-label="Approval: Northline request">${inner}</article>` : `<article class="fcard ${cls}" data-card="${c.id}">${inner}</article>`;
    };
    const statusLine = active.length ? `${chip("review", `${active.length} need${active.length === 1 ? "s" : ""} you`)}` : `${chip("holding", "Nothing needs you right now")}`;
    phone.innerHTML = `
      <div class="persona"><span class="avatar avatar--${persona}" aria-hidden="true">${P.initial}</span><div><p class="persona__name" id="persona-name">${esc(P.name)}</p><p class="persona__role">${esc(P.role)}</p></div></div>
      <p class="statusline" role="status">${statusLine}<span class="muted">· case time ${esc(AW.fmtTime(s.now))}</span></p>
      ${persona === "sara" && s.monitoring === "interrupted" ? `<div class="banner banner--interrupted">${icon("eye-off")}<p class="banner__title">Monitoring interrupted</p><p class="banner__body">Replies aren't being read until the mailbox is reconnected.</p></div>` : ""}
      ${persona === "sara" && s.control !== "active" ? `<div class="banner banner--hold">${icon(s.control === "quiet" ? "moon" : s.control === "hold" ? "hand" : "stop")}<p class="banner__title">${{ quiet: "Quiet for 24 hours", hold: "Case on hold", stopped: "Case stopped" }[s.control]}</p><p class="banner__body">${{ quiet: "No messages to you. Monitoring and approved routine work continue.", hold: "Nothing goes out to organisations. Monitoring continues.", stopped: "Everything has stopped, including monitoring." }[s.control]}</p></div>` : ""}
      ${active.length ? `<section class="feed" aria-labelledby="needs-you" id="active"><h2 class="feed-head h4" id="needs-you">Needs you <span class="pill-count">${active.length}</span></h2>${active.map((c) => cardHtml(c, true)).join("")}</section>` : ""}
      <section class="feed" aria-labelledby="earlier"><h2 class="horizon" id="earlier">${active.length ? "Earlier" : "Latest"}</h2>
        ${rest.length ? rest.map((c) => cardHtml(c, false)).join("") : `<div class="empty"><svg class="empty__art" viewBox="0 0 96 56" aria-hidden="true"><path d="M8 48H88" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M34 48A14 14 0 0 1 62 48" fill="currentColor"/><path d="M24 40A24 24 0 0 1 72 40" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg><p class="empty__title">Nothing here yet</p><p>${persona === "amina" ? "Afterward will only message you when there's something only you can answer." : "Your updates will appear here."}</p></div>`}
      </section>
      ${persona === "sara" ? `<div class="composer">
        ${btn("Did you finish everything?", "finished", { icon: "chat", disabled: s.intake !== "confirmed" })}
        <button class="btn" type="button" data-act="controls" aria-expanded="${showControls}" aria-controls="controls-panel">${icon("pause")}Pause<span class="visually-hidden"> or stop</span></button>
      </div>
      <div class="card card--flat" id="controls-panel" ${showControls ? "" : "hidden"}>
        <h2 class="h4">Pause or stop</h2>
        <p class="small secondary" style="margin-block:var(--s-2) var(--s-3)">Three separate controls, so pausing means what you expect.</p>
        <div class="btn-row btn-row--stack decision-btns">
          ${btn(s.control === "quiet" ? "Quiet is on: turn it off" : "Not today", "control", { data: { v: s.control === "quiet" ? "active" : "quiet" }, icon: "moon", desc: "No messages to you for 24 hours. Work continues." })}
          ${btn(s.control === "hold" ? "Hold is on: resume" : "Hold", "control", { data: { v: s.control === "hold" ? "active" : "hold" }, icon: "hand", desc: "Nothing goes out to organisations. Monitoring continues." })}
          ${btn(s.control === "stopped" ? "Restart the case (prototype)" : "Stop the case", "control", { data: { v: s.control === "stopped" ? "active" : "stopped" }, icon: "stop", cls: s.control === "stopped" ? "" : "btn--danger", desc: "Everything stops, including monitoring. Export and delete offered." })}
        </div>
      </div>` : ""}`;

    ctx.innerHTML = `
      <section class="card card--sim stack stack-sm" aria-labelledby="persona-switch">
        <h2 class="clock__label" id="persona-switch">${icon("ring")}Prototype: view as</h2>
        <div class="segmented" role="group" aria-labelledby="persona-switch">
          <button type="button" data-persona="sara" aria-pressed="${persona === "sara"}">Sara (owner)</button>
          <button type="button" data-persona="amina" aria-pressed="${persona === "amina"}">Amina (household)</button>
        </div>
        <p class="small">In the real product each person sees only their own cards, on their own phone.</p>
      </section>
      <section class="card card--flat stack stack-sm">
        <h2 class="h4">The same cards as chat</h2>
        <p class="small secondary">Each card here is also sent in Telegram (primary) or WhatsApp, with the same words and at most three buttons. This page is the fallback and the place for longer details.</p>
        <p class="small secondary">Free text that implies a decision ("just keep Mum's line") is always read back as a card to confirm.</p>
      </section>
      <section class="card card--flat stack stack-sm">
        <h2 class="h4">Support</h2>
        <p class="small secondary">If things feel like too much, Afterward pauses the admin and shares support options such as <a href="https://findahelpline.com" rel="noopener">findahelpline.com</a>. Nothing continues until you choose to.</p>
      </section>`;
  }

  /* ---------------- Events ---------------- */
  const act = {
    "intake.confirm": () => AW.dispatch("intake.confirm"),
    "intake.fix": () => AW.dispatch("intake.fix"),
    "ownership": (b) => AW.dispatch("ownership.set", { id: b.dataset.id, value: b.dataset.v }),
    "candidates.continue": () => AW.dispatch("candidates.continue"),
    "amina.voice": (b) => { b.setAttribute("aria-busy", "true"); b.disabled = true; b.querySelector("span").firstChild.textContent = "Transcribing (simulated)…"; setTimeout(() => AW.dispatch("amina.voice"), 900); },
    "amina.typing": () => { typing = true; render(); const t = document.getElementById("amina-text"); if (t) t.focus(); },
    "amina.cancel": () => { typing = false; render(); },
    "amina.type": () => { const t = document.getElementById("amina-text"); typing = false; AW.dispatch("amina.type", { text: t ? t.value : "" }); },
    "amina.confirm": () => AW.dispatch("amina.confirm"),
    "amina.fix": () => AW.dispatch("amina.fix"),
    "crescent": (b) => AW.dispatch("crescent.joint", { value: b.dataset.v }),
    "plan.reviewed": () => { AW.dispatch("plan.reviewed"); const a = document.getElementById("approval-nl"); if (a) { a.scrollIntoView({ block: "start", behavior: "smooth" }); UI.focusFirst(a.querySelector(".approval__foot")); } },
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
    "refund.later": () => UI.announce("Okay. I'll ask again when the next statement is due."),
    "reconnect": () => AW.dispatch("monitoring.set", { value: "ok" }),
    "finished": () => { AW.dispatch("finished.ask"); window.scrollTo({ top: 0, behavior: "smooth" }); },
    "controls": () => { showControls = !showControls; render(); document.querySelector('[data-act="controls"]').focus(); },
    "control": (b) => { if (b.dataset.v === "stopped" && !window.confirm("Stop the whole case? Everything stops, including monitoring. You'll be offered an export, then deletion of Afterward's copies.")) return; AW.dispatch("control.set", { value: b.dataset.v }); },
  };
  UI.on(document.body, "[data-act]", "click", (e, b) => { if (b.disabled) return; const f = act[b.dataset.act]; if (f) f(b); });
  UI.on(document.body, "[data-persona]", "click", (e, b) => {
    persona = b.dataset.persona; typing = false;
    const u = new URL(location.href); u.searchParams.set("as", persona); history.replaceState(null, "", u);
    render(); document.querySelector(`[data-persona="${persona}"]`).focus();
    UI.announce(`Viewing as ${PEOPLE[persona].name}.`, { toast: false });
  });
  document.body.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("[data-cands]")) candOpen = e.target.open; }, true);

  // After a re-render, move focus to the newest active card so keyboard and screen-reader users land on the next decision.
  AW.subscribe((s, local) => {
    const before = document.activeElement && document.activeElement.closest("[data-card]");
    const beforeId = before && before.dataset.card;
    render();
    if (!local) return;
    const still = beforeId && document.querySelector(`[data-card="${beforeId}"] .fcard__actions button:not([disabled]), [data-card="${beforeId}"] .approval__foot button:not([disabled])`);
    if (still) { still.focus(); return; }
    const next = document.querySelector("#active [data-card]");
    if (next) { const f = next.querySelector("button:not([disabled])"); if (f) f.focus(); }
  });
  render();
  if (location.hash === "#active") { const a = document.getElementById("active"); if (a) a.scrollIntoView(); }
})();
