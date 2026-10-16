/* Call room: a judge plays the Northline representative. Push-to-talk and typed turns are
   simulated: no microphone access, no recording, no speech synthesis. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, simTag, evLabel } = UI;
  UI.shell("call", { context: "Call room" });
  const root = document.getElementById("root");

  let phase = null;       // UI-only: listening | thinking | speaking
  let toggleMode = false; // tap to start / tap to stop, for people who can't hold a key
  let selected = null;    // chosen script line
  let typedText = "";

  const STATE = {
    idle: ["Your turn", "Hold the button (or Space) and speak. Release when you've finished."],
    listening: ["Listening", "Simulated: no audio is recorded. Release to send the selected line."],
    thinking: ["Reviewing…", "Transcribing, choosing a structured action and checking it against the plan (simulated)."],
    speaking: ["Speaking", "The agent's reply appears in the transcript."],
    waiting_family: ["Checking with the family", "The agent said it can't agree without them. A decision card has gone to Sara. You can keep talking; anything new is checked first."],
    acceptance_queued: ["Acceptance ready", "Prepared from the server template and bound to the approved terms. It plays when you let the agent continue. If you speak first, it's suspended and re-checked."],
  };

  function nextLine(s) {
    const reps = s.call.turns.filter((t) => t.who === "rep").length;
    if (!reps) return "greet";
    if (!s.call.terms.length) return "offer_t1";
    if (s.call.terms.some((t) => t.status === "accepted")) return "confirm";
    if (s.call.terms.length === 1) return "change_t2";
    return "confirm";
  }

  const orb = (state) => `<div class="agent-orb" data-state="${esc(state)}" aria-hidden="true"><svg viewBox="0 0 64 64">
      <path class="arc arc--2" d="M11.69 30.3A24.5 24.5 0 0 1 52.31 30.3"/><path class="arc arc--1" d="M16.03 38.19A17 17 0 0 1 47.97 38.19"/>
      <path class="disc" d="M21 44A11 11 0 0 1 43 44Z"/><path class="base" d="M8 44H56"/></svg></div>`;

  function turnHtml(t) {
    if (t.who === "system") return `<li class="turn turn--system turn--${esc(t.kind)}"><p class="turn__text">${t.kind === "discarded" ? icon("slash", "icon--sm") + " " : t.kind === "suspended" ? icon("pause", "icon--sm") + " " : t.kind === "queued" ? icon("clock", "icon--sm") + " " : ""}${esc(t.text)}</p></li>`;
    const agent = t.who === "agent";
    const kind = { disclosure: "AI disclosure", hold: "hold template", template: "acceptance · server template", clarify: "clarification", explain: "explains the request", end: "closing" }[t.kind] || "";
    return `<li class="turn turn--${t.who}"><span class="avatar ${agent ? "avatar--agent" : "avatar--rep"}" aria-hidden="true">${agent ? "AI" : "N"}</span><div><p class="turn__who">${agent ? "Afterward (AI)" : "You, as Northline"}${kind ? ` · ${kind}` : ""}${t.via === "typed" ? " · typed" : t.who === "rep" ? " · spoken (simulated)" : ""}</p><p class="turn__text">${esc(t.text)}</p></div></li>`;
  }

  const TERM = { pending: ["review", "Waiting for Sara"], approved: ["holding", "Approved by Sara"], void: ["void", "Void: terms changed"], declined: ["neutral", "Declined"], accepted: ["holding", "Accepted from template"] };

  function render() {
    const s = AW.state, c = s.call;
    const head = `<div class="page-head"><div class="page-head__titles"><p class="eyebrow">Case AW-1042 · Northline Mobile · line ending 4417</p><h1 class="h1">Call room</h1></div>
      <div class="cluster cluster--tight">${c.status === "live" ? chip("progress", "Call in progress") : c.status === "ended" ? chip("neutral", "Call ended") : c.status === "ready" ? chip("info", "Ready to join") : chip("neutral", "No call open")}${simTag("Simulated provider call")}</div></div>
      <div class="disclosure" role="note">${icon("shield")}<p><strong>You're speaking with Afterward, an AI assistant acting for the Malik family.</strong> This is a simulated provider call in the browser, not a phone call. No audio is recorded in this prototype.</p></div>`;

    if (c.status === "none") {
      root.innerHTML = `${head}<div class="stage" style="margin-top:var(--s-5)">${orb("idle")}<p class="agent-state">No call is open</p><p class="agent-sub">A call starts only when Sara chooses "Call them for me" after Northline's reply. The agent can't start one on its own.</p><div class="btn-row"><button class="btn btn--sim" type="button" data-open-story-btn>${icon("horizon")}Open the Story guide</button><a class="btn" href="family.html?as=sara">Go to Sara's view</a></div></div>`;
      return;
    }

    const agentState = phase || (c.status === "live" ? c.agent : "idle");
    const [stTitle, stSub] = c.status === "ready" ? ["Ready", "Join to hear the agent's opening disclosure."] : c.status === "ended" ? ["Call ended", "Northline said it will confirm in writing. Done means written evidence, not a promise on a call."] : STATE[agentState] || STATE.idle;
    if (!selected || !F.callLines.some((l) => l.id === selected)) selected = nextLine(s);
    const live = c.status === "live";
    const busy = phase === "thinking" || phase === "speaking";
    const queued = c.queued;

    const stage = `<section class="stage" aria-labelledby="agent-state">
      ${orb(agentState)}
      <div aria-live="polite"><p class="agent-state" id="agent-state">${esc(stTitle)}</p><p class="agent-sub">${esc(stSub)}</p></div>
      ${c.status === "ready" ? `<button class="btn btn--primary btn--lg" type="button" data-join>${icon("phone")}Join the call</button>` : ""}
      ${live && queued ? `<div class="banner banner--sim" style="text-align:left;width:100%">${icon("clock")}<p class="banner__title">Acceptance for ${esc(queued.terms)} is ready</p><p class="banner__body">Bound to terms #${esc(queued.hash)}. The hash is re-checked immediately before it plays.</p><div class="banner__actions"><button class="btn btn--primary btn--sm" type="button" data-continue ${busy ? "disabled" : ""}>Let the agent continue</button></div></div>` : ""}
      ${live ? `
        <fieldset class="typed" style="border:0;padding:0;margin:0">
          <legend class="label" style="margin-bottom:var(--s-2)">What you'll say <span class="sim-tag">Simulated speech</span></legend>
          <div class="choice-list">${F.callLines.map((l) => `<label class="choice"><input type="radio" name="line" value="${l.id}" ${selected === l.id ? "checked" : ""}><span class="choice__title">${esc(l.label)}</span><span class="choice__meta">“${esc(l.text)}”</span></label>`).join("")}</div>
        </fieldset>
        <button class="btn btn--primary ptt" type="button" data-ptt aria-pressed="${phase === "listening"}" aria-describedby="ptt-help" ${busy ? "disabled" : ""}>${icon("mic")}${phase === "listening" ? (toggleMode ? "Tap to finish" : "Release to send") : toggleMode ? "Tap to talk" : "Hold to talk"}</button>
        <p class="ptt-help" id="ptt-help">${toggleMode ? "Tap once to start and again to finish." : "Hold with the mouse, touch, Space or Enter. Release to send."} Pressing talk suspends any queued acceptance.</p>
        <label class="cluster cluster--tight small"><input type="checkbox" data-toggle-mode ${toggleMode ? "checked" : ""}> Tap to start and stop instead of holding</label>
        <div class="typed">
          <label class="label" for="typed">${icon("keyboard")} Typed fallback</label>
          <div class="typed__row"><input class="input" id="typed" autocomplete="off" placeholder="Type what you'd say" value="${esc(typedText)}"><button class="btn" type="button" data-typed ${busy ? "disabled" : ""}>${icon("send")}Send</button></div>
          <p class="hint">Use this if audio fails. <button class="link-btn" type="button" data-fill>Fill with the selected line</button>. Other text gets a clarification request: the prototype has no model.</p>
        </div>` : ""}
      ${c.status === "ended" ? `<div class="btn-row"><a class="btn btn--primary" href="provider.html?reply=nl_written">Reply in writing as Northline</a><a class="btn" href="desk.html">See the desk</a></div>` : ""}
    </section>`;

    const terms = c.terms.length ? `<section class="card card--flat stack stack-sm" aria-labelledby="terms-title"><h2 class="h4" id="terms-title">Terms on the table</h2>
      <div style="overflow-x:auto" tabindex="0" role="region" aria-label="Terms table"><table class="terms-table"><thead><tr><th scope="col">Terms</th><th scope="col">Offer</th><th scope="col">Status</th></tr></thead><tbody>
      ${c.terms.map((t) => { const [k, l] = TERM[t.status]; return `<tr><td><span class="ref">${esc(t.id)} · #${esc(t.hash)}</span></td><td>Keep number and voicemail · ${t.months} months at $${t.price}/month</td><td>${chip(k, l)}</td></tr>`; }).join("")}
      </tbody></table></div><p class="xsmall muted">The agent never chooses to accept. Acceptance is spoken only from a server template, only for the terms Sara approved.</p></section>` : "";

    const lat = c.latency.length ? `<section class="card card--flat stack stack-sm" aria-labelledby="lat-title"><div class="cluster cluster--between"><h2 class="h4" id="lat-title">Per-turn timing</h2>${simTag("Simulated, not measured")}</div>
      <div style="overflow-x:auto" tabindex="0" role="region" aria-label="Per-turn timing table"><table class="latency"><thead><tr><th scope="col">Turn</th><th scope="col">Upload</th><th scope="col">Transcribe</th><th scope="col">Reason</th><th scope="col">Check</th><th scope="col">First byte</th><th scope="col">Total</th></tr></thead><tbody>
      ${c.latency.slice(-6).map((l) => `<tr><td>${l.turn}</td><td>${l.stages.upload}</td><td>${l.stages.transcribe}</td><td>${l.stages.reason}</td><td>${l.stages.validate}</td><td>${l.stages.firstByte}</td><td><b>${l.total}</b></td></tr>`).join("")}</tbody></table></div>
      <p class="xsmall muted">Milliseconds, from releasing talk to the first audible sample. The deployed call room reports measured values only.</p></section>` : "";

    const pending = c.terms.find((t) => t.status === "pending");
    const shortcut = `<section class="shortcut stack stack-sm" aria-labelledby="sc-title" style="margin-top:var(--s-5)">
      <h2 class="clock__label" id="sc-title">${icon("ring")}Prototype shortcut: Sara's phone</h2>
      <p class="small">Not part of the call room: a representative never sees this. It mirrors Sara's decision card so you can test the flow in one tab. <a href="family.html?as=sara">Open Sara's view</a></p>
      ${pending ? `<p><b>Terms ${esc(pending.id)}:</b> keep number and voicemail, ${pending.months} months at $${pending.price}/month.</p><div class="btn-row"><button class="btn btn--primary btn--sm" type="button" data-sara="approve" data-t="${pending.id}">Sara accepts ${pending.months} months at $${pending.price}</button><button class="btn btn--sm" type="button" data-sara="decline" data-t="${pending.id}">Sara declines</button></div>` : `<p class="small muted">No decision is waiting for Sara.</p>`}
    </section>`;

    root.innerHTML = `${head}<div class="call__grid">${stage}<div class="stack">
      <section class="card card--flat" aria-labelledby="tr-title"><div class="cluster cluster--between" style="margin-bottom:var(--s-3)"><h2 class="h4" id="tr-title">Transcript</h2>${simTag("Simulated transcription")}</div>
        <ol class="transcript" role="list" aria-live="polite">${c.turns.map(turnHtml).join("")}</ol></section>
      ${terms}${lat}</div></div>${shortcut}`;
  }

  /* ---------------- Simulated turn timing ---------------- */
  function sendTurn(payload) {
    phase = "thinking"; render();
    setTimeout(() => {
      phase = "speaking";
      selected = null;
      AW.dispatch("call.say", payload);
      setTimeout(() => { phase = null; render(); const p = document.querySelector("[data-ptt]"); if (p) p.focus(); }, 1200);
    }, 900);
  }
  function startTalk() { if (phase) return; phase = "listening"; render(); const p = document.querySelector("[data-ptt]"); if (p) p.focus(); }
  function endTalk() { if (phase !== "listening") return; sendTurn({ line: selected, via: "voice" }); }

  root.addEventListener("pointerdown", (e) => { const b = e.target.closest("[data-ptt]"); if (!b || b.disabled) return; e.preventDefault(); if (toggleMode) { phase === "listening" ? endTalk() : startTalk(); } else { startTalk(); } });
  window.addEventListener("pointerup", () => { if (!toggleMode) endTalk(); });
  root.addEventListener("keydown", (e) => {
    const b = e.target.closest("[data-ptt]");
    if (b && (e.key === " " || e.key === "Enter")) { e.preventDefault(); if (e.repeat) return; if (toggleMode) { phase === "listening" ? endTalk() : startTalk(); } else startTalk(); }
    if (e.target.id === "typed" && e.key === "Enter") { e.preventDefault(); root.querySelector("[data-typed]").click(); }
  });
  root.addEventListener("keyup", (e) => { const b = e.target.closest("[data-ptt]"); if (b && !toggleMode && (e.key === " " || e.key === "Enter")) endTalk(); });
  root.addEventListener("change", (e) => {
    if (e.target.name === "line") { selected = e.target.value; }
    if (e.target.matches("[data-toggle-mode]")) { toggleMode = e.target.checked; render(); root.querySelector("[data-toggle-mode]").focus(); }
  });
  root.addEventListener("input", (e) => { if (e.target.id === "typed") typedText = e.target.value; });
  root.addEventListener("click", (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.matches("[data-join]")) { phase = "speaking"; AW.dispatch("call.join"); setTimeout(() => { phase = null; render(); UI.focusFirst(root.querySelector(".stage")); }, 1400); }
    if (t.matches("[data-continue]")) { phase = "speaking"; AW.dispatch("call.continue"); setTimeout(() => { phase = null; render(); }, 1400); }
    if (t.matches("[data-typed]")) {
      const v = typedText.trim(); if (!v) { UI.announce("Type a line first.", { toast: false }); root.querySelector("#typed").focus(); return; }
      const match = F.callLines.find((l) => l.text.toLowerCase() === v.toLowerCase());
      typedText = ""; sendTurn(match ? { line: match.id, via: "typed" } : { text: v, via: "typed" });
    }
    if (t.matches("[data-fill]")) { const l = F.callLines.find((x) => x.id === selected); typedText = l ? l.text : ""; render(); root.querySelector("#typed").focus(); }
    if (t.matches("[data-sara]")) AW.dispatch("terms.decide", { terms: t.dataset.t, choice: t.dataset.sara });
    if (t.matches("[data-open-story-btn]")) UI.openStory();
  });

  AW.subscribe(() => { if (phase !== "listening") render(); });
  render();
})();
