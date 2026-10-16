/* Afterward prototype store.
   The mock state is derived by replaying an action log kept in localStorage, so any story
   step can be reached deterministically and every open tab stays in sync. Nothing here
   talks to a network. In production the server owns this state (AFTERWARD-TECH T5); the
   rules below only imitate its visible results for review. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES;
  const KEY = "afterward.prototype.v1";
  const START = new Date(2026, 2, 6, 9, 0, 0); // Fri 6 March 2026, 09:00 case time

  /* ---------------- Case time ---------------- */
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function dateAt(min) { return new Date(START.getTime() + min * 60000); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function fmtTime(min) { const d = dateAt(min); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}, ${pad(d.getHours())}:${pad(d.getMinutes())}`; }
  function fmtDay(min) { const d = dateAt(min); return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; }
  function businessDaysBetween(a, b) {
    let n = 0; const d = dateAt(a); d.setHours(0, 0, 0, 0); const end = dateAt(b); end.setHours(0, 0, 0, 0);
    while (d < end) { d.setDate(d.getDate() + 1); const w = d.getDay(); if (w !== 0 && w !== 6) n++; }
    return n;
  }
  function addBusinessDays(min, bd) {
    const d = dateAt(min); let n = 0;
    while (n < bd) { d.setDate(d.getDate() + 1); const w = d.getDay(); if (w !== 0 && w !== 6) n++; }
    return Math.round((d.getTime() - START.getTime()) / 60000);
  }

  /* ---------------- Initial state ---------------- */
  function initial() {
    return {
      now: 0,
      intake: "pending",            // pending | confirmed
      candidates: "found",          // found | reviewed
      ownership: { nl2290: "unconfirmed", cb0932: "unconfirmed", ml: "unconfirmed" },
      dependency: "none",           // none | asked | heard | confirmed
      aminaAnswer: null,            // { via, text }
      crescentJoint: null,          // null | yes | no | unsure
      planReviewed: false,
      approvals: {},                // id -> open | approved | notnow
      sent: {},                     // id -> minute sent
      replies: [],                  // { id, at, custom, provider }
      nlDecision: null,             // null | open | ask | call | accept
      nlCertified: false,
      call: { status: "none", agent: "idle", turns: [], terms: [], queued: null, latency: [] },
      written: false,
      voicemailBackup: null,        // null | yes | notyet
      cpClosed: false, cpBill: null, cpRefund: null, // bill: review | reviewed | asked ; refund: issued | received
      spoof: false,
      followups: {},                // id -> count
      escalation: {},
      monitoring: "ok",
      delivery: null,               // null | uncertain | reconciled
      control: "active",            // active | quiet | hold | stopped
      autopilot: "gentle",
      events: [],
      cards: [],
      finished: 0,
      announce: "",
    };
  }

  /* ---------------- Helpers used by the reducer ---------------- */
  function ev(s, kind, text, extra) { s.events.push(Object.assign({ at: s.now, kind, text }, extra || {})); }
  function card(s, to, kind, data, status) { const id = `${kind}-${s.cards.length}`; s.cards.push({ id, to, kind, at: s.now, status: status || "open", data: data || {} }); return id; }
  function findCard(s, kind, pred) { for (let i = s.cards.length - 1; i >= 0; i--) { const c = s.cards[i]; if (c.kind === kind && (!pred || pred(c))) return c; } return null; }
  function closeCard(s, kind, status, pred) { const c = findCard(s, kind, (x) => x.status === "open" && (!pred || pred(x))); if (c) { c.status = status; c.closedAt = s.now; } return c; }
  function hasReply(s, id) { return s.replies.some((r) => r.id === id); }
  function reply(id) { return F.replies.find((r) => r.id === id); }
  function shortHash(str) { let h = 2166136261; for (const ch of str) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); } return (h >>> 0).toString(16).slice(0, 6); }
  function termsOf(s, id) { return s.call.terms.find((t) => t.id === id); }
  function liveTerms(s) { return s.call.terms.filter((t) => t.status !== "void").slice(-1)[0] || null; }
  function latency(s, kind) {
    // Simulated stage timings: deterministic, labelled "simulated" everywhere they appear.
    const n = s.call.latency.length;
    const base = { upload: 140 + n * 9, transcribe: 520 + (n % 3) * 40, reason: 610 + (n % 2) * 70, validate: 18, firstByte: 330 + n * 11, playback: 60 };
    s.call.latency.push({ turn: n + 1, kind, stages: base, total: Object.values(base).reduce((a, b) => a + b, 0) });
  }
  function agentSay(s, text, kind, extra) { s.call.turns.push(Object.assign({ who: "agent", text, kind: kind || "free", at: s.now }, extra || {})); }

  const PLAN = {
    nl: {
      1: { action: "Hold: check with the household before any change", conditions: [], docs: "None", recipient: "None yet" },
      2: { action: "Transfer the line to Amina Malik", conditions: ["Keep the number", "Keep the voicemail", "No new contract"], docs: "Death certificate (photo)", recipient: F.providers.northline.recipient },
    },
  };
  function planHash(acc, v, extra) { return shortHash(`${acc}|${v}|${JSON.stringify(PLAN.nl[v] || extra || {})}`); }

  /* ---------------- Reducer ---------------- */
  const handlers = {
    "intake.confirm"(s) {
      if (s.intake === "confirmed") return;
      s.intake = "confirmed";
      closeCard(s, "intake", "confirmed");
      ev(s, "intake", "Sara confirmed the summary.", { actor: "Sara", tone: "family", ev: "family" });
      s.now += 6;
      ev(s, "discovery", "Found 9 possible accounts in 6 emails and 4 photos.", { actor: "Afterward" });
      card(s, "sara", "candidates");
      s.announce = "Confirmed. We found 9 possible accounts.";
    },
    "intake.fix"(s) { s.announce = "Editing isn't in this prototype yet."; },
    "ownership.set"(s, a) {
      s.ownership[a.id] = a.value;
      const acc = F.accounts.find((x) => x.id === a.id);
      ev(s, "ownership", `Sara said ${acc.name} (${acc.service}) is ${a.value === "yusuf" ? "Yusuf's" : a.value === "other" ? "not Yusuf's" : "not known yet"}.`, { actor: "Sara", tone: "family", ev: "family" });
      s.announce = "Saved.";
    },
    "candidates.continue"(s) {
      if (s.candidates === "reviewed") return;
      s.candidates = "reviewed";
      closeCard(s, "candidates", "reviewed");
      s.now += 3;
      s.dependency = "asked";
      ev(s, "dependency", "Asked Amina about the 4417 line.", { actor: "Afterward" });
      card(s, "sara", "dependency_notice", {}, "info");
      card(s, "amina", "dependency_question");
      s.announce = "We've asked Amina about the 4417 line.";
    },
    "amina.voice"(s) { aminaAnswer(s, "voice", F.transcripts.amina); },
    "amina.type"(s, a) { aminaAnswer(s, "typed", (a.text || "").trim() || F.transcripts.amina); },
    "amina.confirm"(s) {
      if (s.dependency !== "heard") return;
      s.dependency = "confirmed";
      closeCard(s, "dependency_reading", "confirmed");
      ev(s, "dependency", "Amina uses the 4417 line, gets bank codes on it, and wants the voicemail kept.", { actor: "Amina", tone: "family", ev: "family" });
      s.now += 2;
      ev(s, "plan", "Plan v2: transfer the 4417 line to Amina, with conditions. Crescent Bank stays open.", { actor: "Afterward" });
      card(s, "sara", "plan_changed");
      s.approvals.nl = "open";
      card(s, "sara", "approval", { acc: "nl", v: 2, hash: planHash("nl", 2) });
      card(s, "amina", "amina_thanks", {}, "info");
      card(s, "amina", "crescent_joint");
      s.announce = "Plan updated. Sara has a request to approve.";
    },
    "amina.fix"(s) { s.announce = "Editing isn't in this prototype yet."; },
    "crescent.joint"(s, a) {
      s.crescentJoint = a.value;
      closeCard(s, "crescent_joint", "answered");
      if (a.value === "yes") s.ownership.cb0932 = "joint";
      ev(s, "dependency", `Amina said the Crescent Bank account is ${a.value === "yes" ? "joint with her" : a.value === "no" ? "only Yusuf's" : "not known yet"}.`, { actor: "Amina", tone: "family", ev: "family" });
      s.announce = "Thank you. Saved.";
    },
    "plan.reviewed"(s) { s.planReviewed = true; },
    "approve"(s, a) {
      if (s.approvals[a.id] !== "open" && s.approvals[a.id] !== "notnow") return;
      s.approvals[a.id] = "approved";
      const map = { nl: "nl4417", cp: "cp77120", sb: "sb", fl: "fl5531" };
      const acc = F.accounts.find((x) => x.id === map[a.id]);
      const prov = F.providers[acc.provider];
      if (a.id === "nl") { closeCard(s, "approval", "approved", (c) => c.data.acc === "nl"); s.planReviewed = true; }
      ev(s, "approval", `Sara approved: ${a.id === "nl" ? "transfer the 4417 line to Amina (plan v2)" : routineLabel(a.id)}.`, { actor: "Sara", tone: "family", ev: "family" });
      s.now += 1;
      s.sent[a.id] = s.now;
      ev(s, "send", `Request sent to ${prov.name}.`, { actor: "Afterward", tone: "sim", ev: "sim" });
      if (a.id === "nl" && !findCard(s, "routine")) {
        s.approvals.cp = "open"; s.approvals.sb = "open"; s.approvals.fl = "open";
        card(s, "sara", "routine");
      }
      if (["cp", "sb", "fl"].every((k) => s.approvals[k] === "approved")) closeCard(s, "routine", "approved");
      s.announce = `Approved. Request sent to ${prov.name}.`;
    },
    "approval.notnow"(s, a) { s.approvals[a.id] = "notnow"; ev(s, "approval", `Sara chose "Not now" for ${a.id === "nl" ? "the Northline request" : routineLabel(a.id)}. Nothing was sent.`, { actor: "Sara", tone: "family", ev: "family" }); s.announce = "Okay. Nothing sent."; },
    "approval.change"(s) { s.announce = "Editing isn't in this prototype yet."; },
    "reply"(s, a) {
      const r = a.id === "custom" ? null : reply(a.id);
      const provider = r ? r.provider : a.provider;
      s.now += a.delay != null ? a.delay : 180;
      if (a.id === "custom") {
        s.replies.push({ id: "custom", at: s.now, custom: a.text, provider });
        ev(s, "reply", `${F.providers[provider].name} replied. Unclear, so marked for review.`, { actor: F.providers[provider].name, tone: "provider", ev: "unverified", quote: a.text });
        s.announce = "Reply sent. Marked for review.";
        return;
      }
      s.replies.push({ id: a.id, at: s.now, provider });
      const P = F.providers[provider];
      if (a.id === "spoof_will") {
        s.spoof = true;
        ev(s, "recipient", `Held an email from an unknown address (${r.from}). Nothing sent.`, { actor: "Afterward", tone: "alert", ev: "unverified", quote: r.body });
        card(s, "sara", "spoof", { from: r.from });
        s.announce = "Held. Nothing sent.";
        return;
      }
      ev(s, "reply", `${P.name} replied.`, { actor: P.name, tone: "provider", ev: "writing", quote: r.body });
      switch (a.id) {
        case "nl_contradictory":
          s.nlDecision = "open";
          s.now += 1;
          ev(s, "outcome", "Not done: voicemail reset and a new contract weren't approved.", { actor: "Afterward", tone: "alert" });
          card(s, "sara", "not_done");
          s.announce = "Northline says done. It isn't. Sara has a decision.";
          break;
        case "nl_ack": s.announce = "Acknowledged, not done yet."; break;
        case "nl_certified":
          s.nlCertified = true;
          ev(s, "documents", "Northline wants a certified copy. We only have a photo.", { actor: "Afterward", tone: "alert" });
          card(s, "sara", "certified");
          s.announce = "Certified copy needed.";
          break;
        case "nl_written":
          s.written = true;
          s.now += 1;
          ev(s, "outcome", "Done: every condition confirmed in writing.", { actor: "Afterward", tone: "good", ev: "writing" });
          card(s, "sara", "written");
          if (!s.voicemailBackup) card(s, "sara", "voicemail_backup");
          s.announce = "Confirmed in writing. Done.";
          break;
        case "cp_closed":
          s.cpClosed = true;
          ev(s, "outcome", "City Power closed the account from 31 March.", { actor: "Afterward", tone: "good", ev: "writing" });
          s.announce = "City Power closure confirmed.";
          break;
        case "cp_april_feb":
          s.cpBill = "review";
          ev(s, "money", "$61.40 bill for February. Before closure, so not disputed: needs review.", { actor: "Afterward", tone: "alert" });
          card(s, "sara", "bill");
          s.announce = "February bill: needs review.";
          break;
        case "cp_refund":
          s.cpRefund = "issued";
          ev(s, "money", "City Power issued a $42 refund. Waiting to see it arrive.", { actor: "Afterward" });
          card(s, "sara", "refund");
          s.announce = "Refund issued. Not received yet.";
          break;
        case "sb_ack": s.announce = "StreamBox acknowledged."; break;
        case "fl_ack": s.announce = "FitLife acknowledged."; break;
        default: break;
      }
    },
    "decide"(s, a) {
      if (s.nlDecision !== "open") { s.announce = "Already decided."; return; }
      s.nlDecision = a.choice;
      closeCard(s, "not_done", a.choice);
      const label = { ask: "Ask them to keep the voicemail, no contract", call: "Call them for me", accept: "Accept anyway" }[a.choice];
      ev(s, "decision", `Sara chose: ${label}.`, { actor: "Sara", tone: "family", ev: "family" });
      if (a.choice === "call") {
        s.call.status = "ready";
        card(s, "sara", "call_started", {}, "info");
        s.announce = "Calling Northline.";
      } else if (a.choice === "ask") {
        s.now += 2;
        ev(s, "send", "Asked Northline to keep the voicemail and drop the contract.", { actor: "Afterward", tone: "sim", ev: "sim" });
        s.announce = "Correction sent.";
      } else {
        ev(s, "plan", "Sara accepted Northline's changes.", { actor: "Afterward" });
        s.announce = "Accepted.";
      }
    },
    "call.join"(s) {
      if (s.call.status !== "ready") return;
      s.call.status = "live";
      s.now += 30;
      agentSay(s, "Hello, I'm Afterward, an AI assistant calling on behalf of the Malik family, about the Northline line ending 4417. This is a simulated provider call.", "disclosure");
      latency(s, "disclosure");
      ev(s, "call", "Call started. The agent said it's an AI acting for the family.", { actor: "Afterward", tone: "sim", ev: "sim" });
      s.call.agent = "idle";
      s.announce = "Call started.";
    },
    "call.say"(s, a) {
      if (s.call.status !== "live") return;
      const line = F.callLines.find((l) => l.id === a.line);
      const text = line ? line.text : (a.text || "").trim();
      if (!text) return;
      s.now += 1;
      s.call.turns.push({ who: "rep", text, via: a.via || "voice", at: s.now });
      // New representative speech suspends any queued acceptance until it has been processed.
      const queued = s.call.queued;
      if (queued) { s.call.turns.push({ who: "system", kind: "suspended", text: `Queued acceptance for ${queued.terms} suspended: the representative started speaking.`, at: s.now }); }
      const id = line ? line.id : "custom";
      if (id === "greet") {
        agentSay(s, "Thank you, Dana. The family has asked for the line to move to Amina Malik, keeping the number and the existing voicemail, with no new contract. Can you do that?", "explain");
      } else if (id === "offer_t1" || id === "change_t2") {
        const months = 12, price = id === "offer_t1" ? 30 : 35;
        const tid = `T${s.call.terms.length + 1}`;
        if (queued) {
          const old = termsOf(s, queued.terms);
          old.status = "void";
          s.call.turns.push({ who: "system", kind: "discarded", text: `Acceptance audio for ${queued.terms} discarded before playing. It was never spoken.`, at: s.now });
          ev(s, "approval", `Northline changed the offer. Sara's approval no longer applies; nothing was accepted.`, { actor: "Afterward", tone: "alert" });
          const oldCard = findCard(s, "terms", (c) => c.data.terms === queued.terms);
          if (oldCard) { oldCard.status = "void"; oldCard.closedAt = s.now; }
          s.call.queued = null;
        } else {
          s.call.terms.forEach((t) => { if (t.status === "pending") { t.status = "void"; const c = findCard(s, "terms", (x) => x.data.terms === t.id && x.status === "open"); if (c) { c.status = "void"; c.closedAt = s.now; } } });
        }
        const hash = shortHash(`${tid}|${months}|${price}|keep-number|keep-voicemail`);
        s.call.terms.push({ id: tid, months, price, hash, status: "pending", at: s.now, quote: text });
        agentSay(s, "I can't agree to a new contract without the family. Let me check with them now. Please hold.", "hold");
        s.call.agent = "waiting_family";
        ev(s, "call", `Northline offered ${months} months at $${price}/month. Asked Sara.`, { actor: "Northline (on call)", tone: "provider", ev: "spoken", quote: text });
        card(s, "sara", "terms", { terms: tid });
        s.announce = queued ? `Terms changed. Approval for ${queued.terms} is void. Nothing was accepted.` : "New terms offered. The agent paused and asked Sara.";
      } else if (id === "confirm") {
        agentSay(s, "Thank you. The family will look out for it. Goodbye.", "end");
        s.call.status = "ended";
        s.call.agent = "idle";
        ev(s, "call", "Call ended. Waiting for it in writing.", { actor: "Afterward" });
        s.announce = "Call ended.";
      } else {
        agentSay(s, "Sorry, I want to be sure I understand. Will the number and the existing voicemail be kept, and is any new contract involved?", "clarify");
        s.call.turns.push({ who: "system", kind: "note", text: "Prototype: typed lines outside the script get a clarification request. The real agent extracts offered terms with a model.", at: s.now });
      }
      latency(s, id);
      s.call.agent = s.call.agent === "waiting_family" ? "waiting_family" : "idle";
      if (s.call.status === "ended") s.call.agent = "idle";
    },
    "terms.decide"(s, a) {
      const t = termsOf(s, a.terms);
      if (!t || t.status !== "pending") { s.announce = "This offer changed. Nothing was accepted."; return; }
      const c = findCard(s, "terms", (x) => x.data.terms === a.terms);
      if (a.choice === "approve") {
        t.status = "approved";
        if (c) { c.status = "approved"; c.closedAt = s.now; }
        s.now += 1;
        const v = a.terms === "T1" ? 3 : 4;
        ev(s, "approval", `Sara approved ${t.months} months at $${t.price}/month.`, { actor: "Sara", tone: "family", ev: "family" });
        s.call.queued = { terms: a.terms, hash: t.hash };
        s.call.agent = "acceptance_queued";
        s.call.turns.push({ who: "system", kind: "queued", text: `Acceptance prepared from the server template, bound to ${a.terms} (#${t.hash}). It plays when the representative yields the floor.`, at: s.now });
        s.announce = `Approved. Ready to accept on the call.`;
      } else if (a.choice === "decline") {
        t.status = "declined";
        if (c) { c.status = "declined"; c.closedAt = s.now; }
        ev(s, "decision", `Sara declined the offer.`, { actor: "Sara", tone: "family", ev: "family" });
        agentSay(s, "The family can't accept a new contract. Can the transfer go ahead on the current terms?", "explain");
        s.call.agent = "idle";
        s.announce = "Declined.";
      } else {
        s.announce = "Okay. The call stays on hold.";
      }
    },
    "call.continue"(s) {
      const q = s.call.queued;
      if (!q) return;
      const t = termsOf(s, q.terms);
      // Re-check the terms hash immediately before speaking (AFTERWARD-TECH T9).
      if (!t || t.status !== "approved" || t.hash !== q.hash) { s.call.queued = null; return; }
      s.now += 1;
      agentSay(s, `On behalf of the Malik family, I accept: transfer of the line ending 4417 to Amina Malik, keeping the number and the existing voicemail, on a ${t.months}-month contract at $${t.price} per month. Please confirm this in writing to the family's email.`, "template", { terms: t.id });
      latency(s, "template");
      t.status = "accepted";
      s.call.queued = null;
      s.call.agent = "idle";
      ev(s, "call", `Accepted on the call: ${t.months} months at $${t.price}/month.`, { actor: "Afterward", tone: "sim", ev: "spoken" });
      card(s, "sara", "accepted", { terms: t.id }, "info");
      s.announce = "Accepted on the call.";
    },
    "voicemail.backup"(s, a) {
      s.voicemailBackup = a.value;
      closeCard(s, "voicemail_backup", a.value);
      if (a.value === "yes") ev(s, "memory", "Sara has her own copy of the voicemail.", { actor: "Sara", tone: "family", ev: "family" });
      s.announce = "Saved.";
    },
    "bill.decide"(s, a) { s.cpBill = a.value; closeCard(s, "bill", a.value); ev(s, "money", a.value === "reviewed" ? "Sara reviewed the City Power invoice and will pay it herself. Afterward never moves money." : "Asked City Power to explain the February charge (simulated send).", { actor: "Sara", tone: "family", ev: "family" }); s.announce = "Saved."; },
    "refund.received"(s) { s.cpRefund = "received"; closeCard(s, "refund", "received"); ev(s, "money", "$42 refund seen on a statement.", { actor: "Sara", tone: "good", ev: "statement" }); s.announce = "Refund received."; },
    "certified.ack"(s) { closeCard(s, "certified", "ack"); ev(s, "documents", "Sara will post a certified copy.", { actor: "Sara", tone: "family", ev: "family" }); s.announce = "Saved."; },
    "spoof.ack"(s) { closeCard(s, "spoof", "ack"); },
    "clock.advance"(s, a) {
      const before = s.now;
      s.now += a.days * 1440;
      ev(s, "clock", `Demo clock moved forward ${a.days} days.`, { actor: "Demo clock", tone: "sim", ev: "sim" });
      // Follow-ups on silence, per profile window: once per window, at most two, then escalation.
      [["fl", "fl5531", "fitlife", "fl_ack"], ["sb", "sb", "streambox", "sb_ack"], ["cp", "cp77120", "citypower", "cp_closed"], ["nl", "nl4417", "northline", null]].forEach(([k, , pid, ackId]) => {
        if (s.sent[k] == null) return;
        const anyReply = s.replies.some((r) => r.provider === pid);
        if (anyReply || (ackId && hasReply(s, ackId))) return;
        const win = F.providers[pid].windowBd;
        const due = Math.min(2, Math.floor(businessDaysBetween(s.sent[k], s.now) / win));
        const have = s.followups[k] || 0;
        for (let n = have + 1; n <= due; n++) {
          ev(s, "followup", `No reply from ${F.providers[pid].name} in ${win * n} working days. Follow-up ${n} sent.`, { actor: "Afterward", tone: "sim", ev: "sim" });
        }
        s.followups[k] = Math.max(have, due);
      });
      if (s.cpClosed && a.days >= 35) ev(s, "money", "Checked for City Power's final bill.", { actor: "Afterward" });
      s.announce = `Moved forward ${a.days} days.`;
    },
    "delivery.timeout"(s) {
      s.delivery = "uncertain";
      ev(s, "delivery", "FitLife follow-up may not have sent. Checking before trying again.", { actor: "Afterward", tone: "alert", ev: "unverified" });
      s.announce = "Not sure it sent. Checking.";
    },
    "delivery.reconcile"(s) {
      if (s.delivery !== "uncertain") return;
      s.delivery = "reconciled";
      s.now += 5;
      ev(s, "delivery", "FitLife follow-up found in Sent. It went once.", { actor: "Afterward", tone: "good" });
      s.announce = "Found it. Sent once.";
    },
    "monitoring.set"(s, a) {
      if (s.monitoring === a.value) return;
      s.monitoring = a.value;
      if (a.value === "interrupted") {
        ev(s, "monitoring", "Mailbox access expired. Replies aren't being read.", { actor: "Afterward", tone: "alert" });
        card(s, "sara", "monitoring");
        s.announce = "Mailbox disconnected.";
      } else {
        s.now += 2;
        ev(s, "monitoring", "Mailbox reconnected. Caught up on missed replies.", { actor: "Afterward", tone: "good" });
        closeCard(s, "monitoring", "resolved");
        s.announce = "Mailbox reconnected.";
      }
    },
    "control.set"(s, a) {
      s.control = a.value;
      const text = { active: "Case resumed.", quiet: "Quiet for 24 hours: no messages to the family. Monitoring and approved routine work continue.", hold: "Hold: no outgoing actions to organisations. Monitoring continues.", stopped: "Case stopped: everything stops, including monitoring. Export and delete offered." }[a.value];
      ev(s, "control", text, { actor: "Sara", tone: "family" });
      s.announce = text;
    },
    "autopilot.set"(s, a) { s.autopilot = a.value; ev(s, "control", `Autopilot set to ${a.value === "gentle" ? "Gentle (asks before every outbound action)" : "Steady (follow-ups and identical routine notices run automatically)"}.`, { actor: "Sara", tone: "family" }); s.announce = `Autopilot: ${a.value}.`; },
    "finished.ask"(s) {
      s.finished += 1;
      card(s, "sara", "finished", { summary: summary(s) }, "info");
      s.announce = "Here's where things stand.";
    },
  };

  function aminaAnswer(s, via, text) {
    if (s.dependency !== "asked") return;
    s.dependency = "heard";
    s.now += 95;
    s.aminaAnswer = { via, text };
    closeCard(s, "dependency_question", "answered");
    ev(s, "dependency", `Amina answered by ${via === "voice" ? "voice note (transcribed, simulated)" : "text"}.`, { actor: "Amina", tone: "family", ev: "family", quote: text });
    card(s, "amina", "dependency_reading");
    s.announce = "Thanks. Please check we understood.";
  }
  function routineLabel(id) { return { cp: "close City Power electricity", sb: "cancel StreamBox", fl: "cancel FitLife Gym membership" }[id]; }

  function apply(log) {
    const s = initial();
    card(s, "sara", "intake");
    ev(s, "intake", "Sara sent a voice note.", { actor: "Sara", tone: "family", quote: F.transcripts.sara });
    for (const a of log) {
      const h = handlers[a.type];
      s.announce = "";
      if (h) { s.now += 2; h(s, a); }
    }
    return s;
  }

  /* ---------------- Selectors ---------------- */
  function st(kind, text, icon) { return { kind, text, icon }; }
  const ICON = { holding: "check", violated: "cross", unauthorised: "plus", unknown: "question", review: "bang", waiting: "clock", uncertain: "question", info: "dot", progress: "arrow-right", neutral: "dash", sim: "ring", void: "slash" };

  function accounts(s) {
    const out = [];
    const nlT = s.call.terms.filter((t) => t.status === "accepted").slice(-1)[0];
    for (const a of F.accounts) {
      const d = { ...a, label: a.service, profile: a.provider ? F.providers[a.provider] : null, conditions: [], focus: false };
      d.ownership = s.ownership[a.id] || a.ownership;
      d.service = st("neutral", "Active", ICON.neutral);
      d.money = st("neutral", "None", ICON.neutral);
      d.docs = st("neutral", "None sent", ICON.neutral);
      d.next = { owner: "Afterward", action: "Waiting for intake", due: "" };
      d.plan = null; d.bucket = "not_started";
      if (s.intake !== "confirmed") { d.next = { owner: "Family", action: "Confirm the summary", due: "" }; out.push(d); continue; }

      if (d.ownership === "unconfirmed" || d.ownership === "unsure") {
        d.service = st("unknown", "Unconfirmed", ICON.unknown);
        d.next = { owner: "Family", action: "Confirm whose account this is", due: "" };
        d.bucket = "unconfirmed";
      }
      if (d.ownership === "other") {
        d.service = st("neutral", "Not his", ICON.neutral);
        d.next = { owner: "—", action: "Nothing. It stays listed in case that changes", due: "" };
        d.bucket = "not_theirs";
        out.push(d); continue;
      }
      switch (a.id) {
        case "nl4417": nl(s, d, nlT); break;
        case "cb0932":
          if (s.dependency === "confirmed") {
            d.plan = { v: 2, action: "Don't close. May be joint with Amina." };
            d.conditions.push({ label: "4417 line keeps receiving Crescent login codes", state: "holding", why: "Linked by Amina's answer" });
            if (s.crescentJoint === "yes") { d.service = st("holding", "Joint (stated)", ICON.holding); d.next = { owner: "Family", action: "Nothing needed unless Amina asks", due: "" }; d.bucket = "kept"; }
            else { d.next = { owner: "Family", action: "Amina to say whether it's joint", due: "" }; }
          }
          break;
        case "cp77120": routine(s, d, "cp"); break;
        case "sb": routine(s, d, "sb"); break;
        case "fl5531": routine(s, d, "fl"); break;
        case "hw": d.service = st("holding", "Kept", ICON.holding); d.next = { owner: "Family", action: "Change the account holder later, if you want", due: "" }; d.bucket = "kept"; break;
        case "pb":
          d.service = st("info", "With Sara (web form)", ICON.info);
          d.next = { owner: "Family", action: "Submit the prepared web form (details filled in)", due: "" };
          d.bucket = "handed"; break;
        default: break;
      }
      out.push(d);
    }
    return out;
  }

  function routine(s, d, k) {
    const sent = s.sent[k];
    const pid = d.provider;
    if (s.approvals[k] === "open" || s.approvals[k] === "notnow") { d.plan = { v: 1, action: k === "cp" ? "Close at the end of the billing month" : "Cancel" }; d.next = { owner: "Family", action: "Approve or not now", due: "" }; d.bucket = "decision"; return; }
    if (sent == null) { d.next = { owner: "Afterward", action: "Plan ready after Northline's approval", due: "" }; return; }
    d.plan = { v: 1, action: k === "cp" ? "Close at the end of the billing month" : "Cancel" };
    d.service = st("progress", k === "cp" ? "Close requested" : "Cancel requested", ICON.progress);
    d.bucket = "waiting";
    const win = F.providers[pid].windowBd;
    const fu = s.followups[k] || 0;
    d.next = { owner: "Provider", action: fu ? `Reply (follow-up ${fu} sent)` : "Reply", due: fmtDay(addBusinessDays(sent, win * (fu + 1))) };
    if (k === "fl" && s.delivery === "uncertain") d.next = { owner: "Afterward", action: "Reconcile follow-up 1 (delivery uncertain)", due: "" };
    if (k === "sb" && hasReply(s, "sb_ack")) { d.service = st("info", "Acknowledged", ICON.info); d.next = { owner: "Provider", action: "Confirm cancellation", due: fmtDay(addBusinessDays(sent, win * 2)) }; }
    if (k === "fl" && hasReply(s, "fl_ack")) { d.service = st("info", "Acknowledged", ICON.info); d.next = { owner: "Provider", action: "Confirm cancellation", due: fmtDay(addBusinessDays(sent, win)) }; }
    if (k === "cp") {
      if (s.cpClosed) { d.service = st("holding", "Closed 31 Mar", ICON.holding); d.bucket = "confirmed"; d.next = { owner: "Afterward", action: "Watch for the final bill", due: fmtDay(sent + 35 * 1440) }; }
      if (s.cpBill === "review") { d.money = st("review", "$61.40 bill to review", ICON.review); d.bucket = "review"; d.next = { owner: "Family", action: "Review the February invoice", due: "30 Apr" }; }
      if (s.cpBill === "reviewed") d.money = st("neutral", "$61.40 owed", ICON.neutral);
      if (s.cpBill === "asked") d.money = st("review", "$61.40 queried", ICON.review);
      const refund = s.cpRefund === "issued" ? st("waiting", "$42 refund pending", ICON.waiting) : s.cpRefund === "received" ? st("holding", "$42 refund received", ICON.holding) : null;
      if (refund) { if (s.cpBill) d.moneyExtra = [refund]; else d.money = refund; }
      if (s.cpRefund === "issued") { if (d.bucket !== "review") d.bucket = "promised"; if (s.cpBill !== "review") d.next = { owner: "Family", action: "Look for $42 on a statement", due: "" }; }
    }
  }

  function nl(s, d, accepted) {
    d.focus = s.dependency !== "none" && s.intake === "confirmed";
    if (s.dependency !== "confirmed") {
      d.plan = { v: 1, ...PLAN.nl[1] };
      d.next = { owner: s.dependency === "none" ? "Afterward" : "Family", action: s.dependency === "none" ? "Ask the household what could disappear" : "Amina to answer the 4417 question", due: "" };
      d.bucket = "decision";
      return;
    }
    const v = accepted ? (accepted.id === "T1" ? 3 : 4) : 2;
    d.plan = { v, ...PLAN.nl[2] };
    const conds = [
      { key: "number", label: "Keep the number", state: "unknown", why: "Not stated yet" },
      { key: "voicemail", label: "Keep the voicemail", state: "unknown", why: "Not stated yet" },
      { key: "contract", label: accepted ? `Contract: ${accepted.months} months at $${accepted.price} (approved)` : "No new contract", state: "unknown", why: "Not stated yet" },
    ];
    d.conditions = conds;
    if (s.approvals.nl !== "approved") { d.next = { owner: "Family", action: "Sara to approve the Northline request", due: "" }; d.bucket = "decision"; conds.forEach((c) => { c.state = "neutral"; c.why = "Not requested yet"; }); return; }
    d.service = st("progress", "Transfer requested", ICON.progress);
    d.docs = st("info", "Photo sent", ICON.info);
    d.bucket = "waiting";
    d.next = { owner: "Provider", action: "Reply", due: fmtDay(addBusinessDays(s.sent.nl, 5)) };
    if (hasReply(s, "nl_ack")) { d.service = st("info", "Acknowledged", ICON.info); }
    if (s.nlCertified) { d.docs = st("violated", "Certified copy needed", ICON.violated); d.next = { owner: "Family", action: "Post a certified copy", due: "" }; }
    if (hasReply(s, "nl_contradictory")) {
      d.service = st("review", "Not accepted", ICON.review);
      d.money = st("unauthorised", "Unapproved contract", ICON.unauthorised);
      conds[0].state = "unknown"; conds[0].why = "Not stated in the reply";
      conds[1].state = "violated"; conds[1].why = "\"Voicemail will be reset\"";
      conds[2].state = "unauthorised"; conds[2].why = "\"new 24-month plan\"";
      d.bucket = "decision";
      d.next = { owner: "Family", action: "Decide: correction, call, or accept", due: "" };
      if (s.nlDecision === "call") d.next = { owner: "Afterward", action: "Call Northline (simulated call room)", due: "" };
      if (s.nlDecision === "ask") { d.next = { owner: "Provider", action: "Reply to the correction", due: "" }; d.bucket = "waiting"; }
      if (s.nlDecision === "accept") { d.bucket = "confirmed"; d.service = st("holding", "Transferred", ICON.holding); conds[1].state = "neutral"; conds[1].why = "Sara accepted the reset"; conds[2].state = "neutral"; conds[2].why = "Sara accepted the 24-month plan"; d.money = st("neutral", "24-month plan accepted", ICON.neutral); }
    }
    const pending = s.call.terms.find((t) => t.status === "pending");
    if (pending) { d.next = { owner: "Family", action: `Decide on terms ${pending.id}`, due: "now (call on hold)" }; d.bucket = "decision"; }
    if (s.call.queued) d.next = { owner: "Afterward", action: `Speak acceptance for ${s.call.queued.terms}`, due: "" };
    if (accepted) {
      d.service = st("waiting", "Agreed, not in writing", ICON.waiting);
      d.money = st("info", `$${accepted.price}/mo approved`, ICON.info);
      conds.forEach((c) => { c.state = "unknown"; c.why = "Said on the call, not yet in writing"; c.ev = "spoken"; });
      d.bucket = "promised";
      d.next = { owner: "Provider", action: "Confirm in writing", due: fmtDay(addBusinessDays(accepted.at, 5)) };
    }
    if (s.written) {
      d.service = st("holding", "Transferred", ICON.holding);
      d.docs = st("holding", "Accepted", ICON.holding);
      conds.forEach((c) => { c.state = "holding"; c.why = "Northline confirmed in writing"; c.ev = "writing"; });
      if (s.voicemailBackup === "yes") conds[1].why = "Northline confirmed in writing; Sara has her own copy";
      d.bucket = "confirmed";
      d.next = { owner: "—", action: "Nothing outstanding", due: "" };
    }
  }

  function summary(s) {
    const acc = accounts(s);
    const b = {};
    acc.forEach((a) => { b[a.bucket] = (b[a.bucket] || []).concat(a); });
    const n = (k) => (b[k] || []).length;
    const names = (k) => (b[k] || []).map((a) => a.name + (a.id === "nl2290" ? " (2290)" : "")).join(", ");
    const lines = [];
    if (s.intake !== "confirmed") return { at: s.now, headline: "Not yet: the case hasn't started.", lines, caveat: "Nothing has been discovered, sent or checked yet." };
    if (n("confirmed")) lines.push({ k: "confirmed", tone: "holding", text: `${n("confirmed")} confirmed with written evidence`, who: names("confirmed") });
    const extra = acc.filter((a) => a.bucket !== "promised" && (a.moneyExtra || []).some((m) => m.kind === "waiting"));
    const promised = n("promised") + extra.length;
    if (promised) lines.push({ k: "promised", tone: "waiting", text: `${promised} promised but not yet evidenced`, who: (b.promised || []).map((a) => a.name).concat(extra.map((a) => `${a.name} refund`)).join(", ") });
    if (n("review")) lines.push({ k: "review", tone: "review", text: `${n("review")} needs your review`, who: names("review") });
    if (n("decision")) lines.push({ k: "decision", tone: "review", text: `${n("decision")} waiting for a family decision`, who: names("decision") });
    if (n("waiting")) lines.push({ k: "waiting", tone: "progress", text: `${n("waiting")} waiting on the organisation`, who: names("waiting") });
    if (n("blocked")) lines.push({ k: "blocked", tone: "violated", text: `${n("blocked")} blocked`, who: names("blocked") });
    if (n("handed")) lines.push({ k: "handed", tone: "info", text: `${n("handed")} handed to you`, who: names("handed") });
    if (n("kept")) lines.push({ k: "kept", tone: "neutral", text: `${n("kept")} kept on purpose`, who: names("kept") });
    if (n("unconfirmed")) lines.push({ k: "unconfirmed", tone: "unknown", text: `${n("unconfirmed")} candidate account${n("unconfirmed") > 1 ? "s" : ""} still unconfirmed`, who: names("unconfirmed") });
    if (n("not_theirs")) lines.push({ k: "not_theirs", tone: "neutral", text: `${n("not_theirs")} marked as not his`, who: names("not_theirs") });
    if (n("not_started")) lines.push({ k: "not_started", tone: "neutral", text: `${n("not_started")} not started`, who: names("not_started") });
    const done = n("confirmed");
    const headline = s.intake !== "confirmed" ? "Not yet: the case hasn't started." : done === acc.length ? "Everything on the list has written evidence." : "Not everything. Here's exactly where things stand.";
    return { at: s.now, headline, lines, caveat: "This only covers accounts we know about. Paper post, other email addresses and cash payments haven't been searched." };
  }

  function comparison(s) {
    const accs = accounts(s);
    const d = accs.find((a) => a.id === "nl4417");
    if (s.intake !== "confirmed" || s.dependency !== "confirmed" || s.approvals.nl !== "approved") return null;
    const accepted = s.call.terms.filter((t) => t.status === "accepted").slice(-1)[0];
    const res = { plan: d.plan, conditions: d.conditions, account: d };
    const last = s.replies.filter((r) => r.provider === "northline" && r.id !== "spoof_will").slice(-1)[0];
    if (s.written) {
      res.quote = { segs: [{ t: "Confirmed: " }, { t: "the line ending 4417 has been transferred to Amina Malik", hl: "holding" }, { t: ". " }, { t: "The number and the existing voicemail have been kept", hl: "holding" }, { t: ". " }, { t: `The new plan is 12 months at $${accepted ? accepted.price : 35} per month, as agreed on the call`, hl: "holding" }, { t: "." }], ev: "writing", at: last.at, source: "Email from bereavement@northline.example · latest text only" };
      res.verdict = { kind: "resolved", text: "Resolved", sub: "Completion evidence present and every condition holds." };
      res.action = st("holding", "Transfer: completed", ICON.holding);
    } else if (accepted) {
      res.quote = { segs: [{ t: s.call.terms.find((t) => t.id === accepted.id).quote }], ev: "spoken", at: accepted.at, source: "Said on the simulated call · not yet in writing" };
      res.verdict = { kind: "open", text: "Agreed, not done", sub: "Spoken on a call is not written evidence. Waiting for Northline to confirm in writing." };
      res.action = st("waiting", "Transfer: promised", ICON.waiting);
    } else if (hasReply(s, "nl_contradictory")) {
      res.quote = { segs: [{ t: "Request complete. " }, { t: "Line transferred to Mrs Malik", hl: "holding" }, { t: " on a " }, { t: "new 24-month plan", hl: "violated" }, { t: ". " }, { t: "Voicemail will be reset", hl: "violated" }, { t: " during migration." }], ev: "writing", at: (s.replies.find((r) => r.id === "nl_contradictory") || {}).at, source: "Email from bereavement@northline.example · latest text only · quote verified" };
      const inCall = s.call.status === "live" || s.call.status === "ready";
      res.verdict = { kind: "notdone", text: "Not done", sub: inCall ? "Two conditions violated, one not stated. Sara chose to call; the call room is open (simulated)." : s.nlDecision === "open" ? "Two conditions violated, one not stated. Decision sent to Sara." : "Two conditions violated, one not stated." };
      res.action = st("holding", "Transfer: completed", ICON.holding);
      if (s.nlDecision === "accept") res.verdict = { kind: "resolved", text: "Accepted by Sara", sub: "Sara chose to accept the outcome as reported, including the reset and the contract." };
    } else if (last) {
      res.quote = last.id === "custom" ? { segs: [{ t: last.custom }], ev: "unverified", at: last.at, source: "Free text · the prototype can't read it" } : { segs: [{ t: reply(last.id).body }], ev: "writing", at: last.at, source: "Email from bereavement@northline.example · latest text only" };
      res.verdict = last.id === "custom" ? { kind: "open", text: "Needs review", sub: "Ambiguous until read. Never upgraded to done." } : last.id === "nl_certified" ? { kind: "open", text: "Blocked on a document", sub: "Certified copy required; the vault holds a photo." } : { kind: "open", text: "Acknowledged, not completed", sub: "The follow-up timer keeps running." };
      res.action = st(last.id === "nl_certified" ? "violated" : "info", last.id === "nl_certified" ? "Transfer: blocked" : "Transfer: acknowledged", last.id === "nl_certified" ? ICON.violated : ICON.info);
    } else {
      res.quote = null;
      res.verdict = { kind: "open", text: "Waiting for a reply", sub: `Northline's response window is 5 business days (due ${fmtDay(addBusinessDays(s.sent.nl, 5))}).` };
      res.action = st("progress", "Transfer: requested", ICON.progress);
    }
    return res;
  }

  /* ---------------- Story ---------------- */
  const A = (type, extra) => Object.assign({ type }, extra || {});
  const CORE = [
    A("intake.confirm"), A("candidates.continue"), A("amina.voice"), A("amina.confirm"), A("plan.reviewed"),
    A("approve", { id: "nl" }), A("approve", { id: "cp" }), A("approve", { id: "sb" }), A("approve", { id: "fl" }),
    A("reply", { id: "nl_contradictory" }), A("decide", { choice: "call" }), A("call.join"), A("call.say", { line: "greet" }),
    A("call.say", { line: "offer_t1" }), A("terms.decide", { terms: "T1", choice: "approve" }), A("call.say", { line: "change_t2" }),
    A("terms.decide", { terms: "T2", choice: "approve" }), A("call.continue"), A("call.say", { line: "confirm" }), A("reply", { id: "nl_written" }),
  ];
  const upto = (n) => CORE.slice(0, n);
  const STEPS = [
    { n: 1, title: "Sara's voice note becomes the case", where: "Family view · Sara", href: "family.html?as=sara", setup: upto(0), done: (s) => s.intake === "confirmed" },
    { n: 2, title: "Candidate coverage: 9 possible accounts", where: "Family view · Sara", href: "family.html?as=sara", setup: upto(1), done: (s) => s.candidates === "reviewed" },
    { n: 3, title: "Amina answers the 4417 question", where: "Family view · Amina", href: "family.html?as=amina", setup: upto(2), done: (s) => s.dependency === "confirmed" },
    { n: 4, title: "The plan changes: v1 → v2", where: "Family view · Sara (also on the desk)", href: "family.html?as=sara", setup: upto(4), done: (s) => s.dependency === "confirmed" },
    { n: 5, title: "Sara approves the specific Northline request", where: "Family view · Sara", href: "family.html?as=sara#active", setup: upto(5), done: (s) => s.approvals.nl === "approved" },
    { n: 6, title: "Northline replies \"complete\"", where: "Provider console", href: "provider.html?reply=nl_contradictory", setup: upto(9), done: (s) => hasReply(s, "nl_contradictory") },
    { n: 7, title: "Afterward says: not done", where: "Case desk", href: "desk.html", setup: upto(10), done: (s) => s.nlDecision && s.nlDecision !== "open" },
    { n: 8, title: "Sara chooses \"Call them for me\"", where: "Family view · Sara", href: "family.html?as=sara", setup: upto(10), done: (s) => s.nlDecision === "call" },
    { n: 9, title: "On the call, Northline offers new terms", where: "Call room", href: "call.html", setup: upto(11), done: (s) => s.call.terms.length >= 1 },
    { n: 10, title: "Sara approves terms T1", where: "Family view · Sara", href: "family.html?as=sara", setup: upto(14), done: (s) => s.call.terms.some((t) => t.id === "T1" && t.status !== "pending") },
    { n: 11, title: "The rep changes the terms: approval void", where: "Call room", href: "call.html", setup: upto(15), done: (s) => s.call.terms.length >= 2 },
    { n: 12, title: "Re-approval, then acceptance from the template", where: "Family view, then call room", href: "family.html?as=sara", setup: upto(16), done: (s) => s.call.terms.some((t) => t.status === "accepted") },
  ];
  const SIDE = [
    { id: "written", title: "Northline confirms every condition in writing", where: "Provider console", href: "provider.html?reply=nl_written", setup: upto(19) },
    { id: "clock", title: "Clock +14 days: FitLife follow-up fires once", where: "Case desk", href: "desk.html#clock", setup: upto(9) },
    { id: "uncertain", title: "Delivery uncertain, then reconciled", where: "Case desk", href: "desk.html", setup: upto(9).concat([A("clock.advance", { days: 14 }), A("delivery.timeout")]) },
    { id: "monitoring", title: "Monitoring interrupted", where: "Case desk and family view", href: "desk.html", setup: upto(9).concat([A("monitoring.set", { value: "interrupted" })]) },
    { id: "coverage", title: "Incomplete candidate coverage", where: "Case desk", href: "desk.html#coverage", setup: upto(2) },
    { id: "bill", title: "April invoice for February service", where: "Provider console · City Power", href: "provider.html?reply=cp_april_feb", setup: upto(9).concat([A("reply", { id: "cp_closed" })]) },
    { id: "refund", title: "Refund issued, awaiting receipt", where: "Provider console · City Power", href: "provider.html?reply=cp_refund", setup: upto(9).concat([A("reply", { id: "cp_closed" }), A("reply", { id: "cp_april_feb" })]) },
    { id: "finished", title: "\"Did you finish everything?\"", where: "Family view · Sara", href: "family.html?as=sara", setup: CORE.concat([A("voicemail.backup", { value: "yes" }), A("reply", { id: "cp_closed" }), A("reply", { id: "cp_april_feb" }), A("reply", { id: "cp_refund" }), A("clock.advance", { days: 14 }), A("finished.ask")]) },
  ];
  function currentStep(s) { return STEPS.find((x) => !x.done(s)) || null; }

  /* ---------------- Persistence and subscription ---------------- */
  let log = load();
  let state = apply(log);
  const subs = new Set();
  function load() { try { const raw = localStorage.getItem(KEY); const v = raw ? JSON.parse(raw) : []; return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(log)); } catch (e) { /* private mode: state lives in memory only */ } }
  function emit(local) { subs.forEach((fn) => fn(state, local)); }
  window.addEventListener("storage", (e) => { if (e.key === KEY) { log = load(); state = apply(log); state.announce = ""; emit(false); } });

  window.AW = {
    get state() { return state; },
    dispatch(type, payload) { log.push(Object.assign({ type }, payload || {})); state = apply(log); save(); emit(true); return state; },
    reset(setup) { log = (setup || []).slice(); state = apply(log); state.announce = ""; save(); emit(true); },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    accounts: () => accounts(state),
    summary: () => summary(state),
    comparison: () => comparison(state),
    currentStep: () => currentStep(state),
    hasReply: (id) => hasReply(state, id),
    STEPS, SIDE, fmtTime, fmtDay, PLAN, ICON,
    get logLength() { return log.length; },
  };
})();
