/* Call room: a judge plays the Northline representative. Push-to-talk and typed turns are
   simulated: no microphone access, no recording, no speech synthesis. One screen. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, simTag } = UI;
  UI.shell("call", { context: "Call room" });
  const root = document.getElementById("root");

  let phase = null;       // UI-only: listening | thinking | speaking
  let toggleMode = false;
  let selected = null;
  let typedText = "";

  const STATE = {
    idle: ["Your turn", "Pick a line, then hold the button and speak."],
    listening: ["Listening", "Release to send. Nothing is recorded."],
    thinking: ["Thinking", "Checking what you said against the plan."],
    speaking: ["Speaking", ""],
    waiting_family: ["Checking with the family", "It can't agree to new terms on its own. Sara has been asked."],
    acceptance_queued: ["Ready to accept", "It speaks when you let it. If you speak first, it stops and checks again."],
  };
  const CHIP = { greet: "Say hello", offer_t1: "Offer $30 a month", change_t2: "Change it to $35", confirm: "Promise it in writing" };
  const TERM = { pending: ["review", "Sara deciding"], approved: ["holding", "Sara approved"], void: ["void", "Void: offer changed"], declined: ["neutral", "Declined"], accepted: ["holding", "Accepted"] };

  function nextLine(s) {
    if (!s.call.turns.some((t) => t.who === "rep")) return "greet";
    if (!s.call.terms.length) return "offer_t1";
    if (s.call.terms.some((t) => t.status === "accepted")) return "confirm";
    return s.call.terms.length === 1 ? "change_t2" : "confirm";
  }
  const orb = (state) => `<div class="agent-orb" data-state="${esc(state)}" aria-hidden="true"><svg viewBox="0 0 64 64"><path class="arc arc--2" d="M11.69 30.3A24.5 24.5 0 0 1 52.31 30.3"/><path class="arc arc--1" d="M16.03 38.19A17 17 0 0 1 47.97 38.19"/><path class="disc" d="M21 44A11 11 0 0 1 43 44Z"/><path class="base" d="M8 44H56"/></svg></div>`;

  const timing = UI.drawer({ id: "timing", title: "Time per turn", render: () => {
    const c = AW.state.call;
    if (!c.latency.length) return `<p class="muted">No turns yet.</p>`;
    return `<p class="small">${simTag("Made-up numbers")} The real call room shows measured times only.</p>
      <table class="latency"><thead><tr><th scope="col">Turn</th><th scope="col">Hearing</th><th scope="col">Thinking</th><th scope="col">Speaking</th><th scope="col">Total</th></tr></thead><tbody>
      ${c.latency.map((l) => `<tr><td>${l.turn}</td><td>${l.stages.upload + l.stages.transcribe}</td><td>${l.stages.reason + l.stages.validate}</td><td>${l.stages.firstByte + l.stages.playback}</td><td><b>${l.total}</b></td></tr>`).join("")}</tbody></table>
      <p class="xsmall muted">Milliseconds from letting go of the button to the first sound.</p>`;
  } });

  function render() {
    const s = AW.state, c = s.call;
    const agentState = phase || (c.status === "live" ? c.agent : "idle");
    const busy = phase === "thinking" || phase === "speaking";
    if (!selected) selected = nextLine(s);
    let stage;
    if (c.status === "none") {
      stage = `${orb("idle")}<div><p class="agent-state">No call yet</p><p class="agent-sub">A call starts only when Sara asks for one.</p></div><div class="btn-row btn-row--inline"><a class="btn btn--primary" href="family.html?as=sara">Go to Sara's view</a><button class="btn" type="button" data-story>Jump in the story</button></div>`;
    } else if (c.status === "ready") {
      stage = `${orb("idle")}<div><p class="agent-state">Ready</p><p class="agent-sub">You're the Northline representative. The agent will introduce itself.</p></div><button class="btn btn--primary btn--lg" type="button" data-join>${icon("phone")}Join the call</button>`;
    } else if (c.status === "ended") {
      stage = `${orb("idle")}<div><p class="agent-state">Call ended</p><p class="agent-sub">A promise on a call isn't done. Northline needs to confirm in writing.</p></div><div class="btn-row btn-row--inline"><a class="btn btn--primary" href="provider.html?reply=nl_written">Reply in writing as Northline</a><a class="btn" href="desk.html">See the desk</a></div>`;
    } else {
      const [title, sub] = STATE[agentState] || STATE.idle;
      const line = F.callLines.find((l) => l.id === selected);
      stage = `${orb(agentState)}
        <div aria-live="polite"><p class="agent-state" id="agent-state">${esc(title)}</p>${sub ? `<p class="agent-sub">${esc(sub)}</p>` : ""}</div>
        ${c.queued ? `<button class="btn btn--primary" type="button" data-continue ${busy ? "disabled" : ""}>${icon("speaker")}Let the agent continue</button>` : ""}
        <div class="say__chips" role="group" aria-label="What you'll say">${F.callLines.map((l) => `<button type="button" class="say__chip" data-line="${l.id}" aria-pressed="${selected === l.id}">${esc(CHIP[l.id])}</button>`).join("")}</div>
        <p class="say__line">“${esc(line ? line.text : "")}”</p>
        <button class="btn btn--primary ptt" type="button" data-ptt aria-pressed="${phase === "listening"}" ${busy ? "disabled" : ""}>${icon("mic")}${phase === "listening" ? (toggleMode ? "Tap to finish" : "Release to send") : toggleMode ? "Tap to talk" : "Hold to talk"}</button>
        <div class="typed__row"><label class="visually-hidden" for="typed">Type instead</label><input class="input" id="typed" autocomplete="off" placeholder="Or type what you'd say" value="${esc(typedText)}"><button class="btn" type="button" data-typed ${busy ? "disabled" : ""}>${icon("send")}Send</button></div>
        <label class="cluster cluster--tight small muted"><input type="checkbox" data-toggle-mode ${toggleMode ? "checked" : ""}> Tap instead of holding</label>`;
    }
    const pending = c.terms.find((t) => t.status === "pending");
    const statusChip = c.status === "live" ? chip("progress", "Live") : c.status === "ended" ? chip("neutral", "Ended") : c.status === "ready" ? chip("info", "Ready") : chip("neutral", "Not started");
    const chatEl = root.querySelector(".chat-scroll"), atBottom = !chatEl || chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 40;
    root.innerHTML = `
      <div class="page-row">
        <div><h1 class="page-title">Call with Northline</h1><p class="page-sub">Line 4417. You're the Northline representative.</p></div>
        <div class="toolbar">${statusChip}<button class="btn btn--sm" type="button" data-timing ${c.latency.length ? "" : "disabled"}>${icon("clock")}Timing</button></div>
      </div>
      <div class="disclosure" role="note">${icon("shield")}<span>You're talking to <b>Afterward, an AI assistant</b> acting for the Malik family.</span>${simTag("Browser call, not a phone call")}</div>
      <div class="call">
        <section class="stage" aria-label="Agent">${stage}</section>
        <section class="panel-box" aria-labelledby="tr-title">
          <div class="panel-box__head"><h2 class="panel-box__title" id="tr-title">Transcript</h2>${simTag("Transcribed")}</div>
          ${c.terms.length ? `<ul class="terms" role="list" style="padding:var(--s-3) var(--s-4);border-bottom:var(--rule)">${c.terms.map((t) => { const [k, l] = TERM[t.status]; return `<li><span>${t.months} months at $${t.price}/month</span>${chip(k, l)}</li>`; }).join("")}</ul>` : ""}
          <div class="panel-box__body scroll chat-scroll" tabindex="0" aria-label="Transcript">${c.turns.length ? `<ol class="chat" role="list">${c.turns.map((t) => t.who === "system" ? `<li class="bubble bubble--system ${t.kind === "discarded" ? "bubble--discarded" : ""}">${t.kind === "discarded" ? icon("slash", "icon--sm") + " " : ""}<span class="bubble__text">${esc(t.text)}</span></li>` : `<li class="bubble bubble--${t.who}"><span class="bubble__who">${t.who === "agent" ? (t.kind === "template" ? "Afterward (AI), approved wording" : "Afterward (AI)") : t.via === "typed" ? "You, typed" : "You"}</span>${esc(t.text)}</li>`).join("")}</ol>` : `<p class="muted">Nothing said yet.</p>`}</div>
        </section>
      </div>
      ${pending ? `<aside class="mirror" aria-label="Sara's phone (demo)"><p class="mirror__label">${icon("ring", "icon--sm")}Sara's phone (demo shortcut)</p><p><b>Accept ${pending.months} months at $${pending.price}?</b></p><div class="btn-row btn-row--inline"><button class="btn btn--primary btn--sm" type="button" data-sara="approve" data-t="${pending.id}">Sara accepts</button><button class="btn btn--sm" type="button" data-sara="decline" data-t="${pending.id}">Sara declines</button></div></aside>` : ""}`;
    const ce = root.querySelector(".chat-scroll"); if (ce && atBottom) ce.scrollTop = ce.scrollHeight;
    timing.refresh();
  }

  function sendTurn(payload) {
    phase = "thinking"; render();
    setTimeout(() => {
      phase = "speaking"; selected = null;
      AW.dispatch("call.say", payload);
      setTimeout(() => { phase = null; render(); const p = root.querySelector("[data-ptt]"); if (p) p.focus(); }, 1200);
    }, 900);
  }
  function startTalk() { if (phase) return; phase = "listening"; render(); const p = root.querySelector("[data-ptt]"); if (p) p.focus(); }
  function endTalk() { if (phase !== "listening") return; sendTurn({ line: selected, via: "voice" }); }

  root.addEventListener("pointerdown", (e) => { const b = e.target.closest("[data-ptt]"); if (!b || b.disabled) return; e.preventDefault(); if (toggleMode) { phase === "listening" ? endTalk() : startTalk(); } else startTalk(); });
  window.addEventListener("pointerup", () => { if (!toggleMode) endTalk(); });
  root.addEventListener("keydown", (e) => {
    const b = e.target.closest("[data-ptt]");
    if (b && (e.key === " " || e.key === "Enter")) { e.preventDefault(); if (e.repeat) return; if (toggleMode) { phase === "listening" ? endTalk() : startTalk(); } else startTalk(); }
    if (e.target.id === "typed" && e.key === "Enter") { e.preventDefault(); root.querySelector("[data-typed]").click(); }
  });
  root.addEventListener("keyup", (e) => { if (e.target.closest("[data-ptt]") && !toggleMode && (e.key === " " || e.key === "Enter")) endTalk(); });
  root.addEventListener("change", (e) => { if (e.target.matches("[data-toggle-mode]")) { toggleMode = e.target.checked; render(); root.querySelector("[data-toggle-mode]").focus(); } });
  root.addEventListener("input", (e) => { if (e.target.id === "typed") typedText = e.target.value; });
  root.addEventListener("click", (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.line) { selected = t.dataset.line; render(); root.querySelector(`[data-line="${selected}"]`).focus(); }
    if (t.matches("[data-join]")) { phase = "speaking"; AW.dispatch("call.join"); setTimeout(() => { phase = null; render(); UI.focusFirst(root.querySelector(".stage")); }, 1400); }
    if (t.matches("[data-continue]")) { phase = "speaking"; AW.dispatch("call.continue"); setTimeout(() => { phase = null; render(); }, 1400); }
    if (t.matches("[data-typed]")) {
      const v = typedText.trim(); if (!v) { root.querySelector("#typed").focus(); return; }
      const match = F.callLines.find((l) => l.text.toLowerCase() === v.toLowerCase());
      typedText = ""; sendTurn(match ? { line: match.id, via: "typed" } : { text: v, via: "typed" });
    }
    if (t.matches("[data-sara]")) AW.dispatch("terms.decide", { terms: t.dataset.t, choice: t.dataset.sara });
    if (t.matches("[data-timing]")) timing.open();
    if (t.matches("[data-story]")) UI.openStory();
  });

  AW.subscribe(() => { if (phase !== "listening") render(); });
  render();
})();
