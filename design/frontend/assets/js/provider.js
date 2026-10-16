/* Provider console: a judge replies as a fictional demo provider. Sends are simulated and
   only change the local mock state. One screen: compose on the left, the thread on the right. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, simTag } = UI;
  UI.shell("provider", { context: "Provider console" });
  const root = document.getElementById("root");

  const KEYS = { northline: "nl", citypower: "cp", streambox: "sb", fitlife: "fl", crescent: null };
  const REQUEST = {
    northline: { subject: "Line ending 4417", body: "Dear Northline bereavement team,\n\nI'm writing for Sara Malik, who is handling the estate of her father, Yusuf Malik (as she has told us). He died on 3 March 2026.\n\nPlease move the mobile line ending 4417 to Amina Malik, his wife. Please keep the number and the existing voicemail, and don't start a new contract. If you can't do all of that, please don't go ahead; reply and we'll ask the family.\n\nA photo of the death certificate is attached.\n\nPlease confirm in writing when it's done.\n\nAfterward, for the Malik family" },
    citypower: { subject: "Account CP-77120", body: "Dear City Power,\n\nI'm writing for Sara Malik about her late father Yusuf Malik's account at 14 Orchard Row. Please close it at the end of this billing month with a final meter reading, and send the final bill here.\n\nAfterward, for the Malik family" },
    streambox: { subject: "Subscription SB-88213", body: "Dear StreamBox,\n\nPlease cancel Yusuf Malik's subscription SB-88213 and confirm in writing. He died on 3 March 2026.\n\nAfterward, for the Malik family" },
    fitlife: { subject: "Membership FL-5531", body: "Dear FitLife Gym,\n\nPlease cancel Yusuf Malik's membership FL-5531 and stop further payments. A photo of the death certificate is attached.\n\nAfterward, for the Malik family" },
  };
  const SHORT = { nl_contradictory: "Done, but changed", nl_ack: "Received it", nl_written: "Confirmed in writing", nl_certified: "Need a certified copy", cp_closed: "Account closed", cp_april_feb: "February bill", cp_refund: "Refund issued", sb_ack: "Received it", fl_ack: "Received it", spoof_will: "Fake: send the will" };

  const init = F.replies.find((r) => r.id === UI.param("reply"));
  let provider = init ? init.provider : "northline";
  let variant = init ? init.id : null;
  let text = init ? init.body : "";
  let failNext = false, sending = false, result = null;

  const why = (s, r) => r.needs === "call_accepted" ? (s.call.terms.some((t) => t.status === "accepted") ? null : "After the call") : (KEYS[r.provider] && s.sent[KEYS[r.provider]] != null ? null : "No request yet");

  function render() {
    const s = AW.state, P = F.providers[provider], k = KEYS[provider], open = k && s.sent[k] != null;
    const variants = F.replies.filter((r) => r.provider === provider);
    if (variant && variant !== "custom") { const r = F.replies.find((x) => x.id === variant); if (!r || r.provider !== provider || why(s, r)) { variant = null; text = ""; } }
    const chosen = variant && variant !== "custom" ? F.replies.find((r) => r.id === variant) : null;
    const replies = s.replies.filter((r) => r.provider === provider);
    const threadEl = root.querySelector(".thread-scroll"), y = threadEl ? threadEl.scrollTop : 0;
    root.innerHTML = `
      <div class="page-row">
        <div><h1 class="page-title">Reply as a provider</h1><p class="page-sub">Pick an organisation and answer Afterward's email.</p></div>
        ${simTag("Nothing is really sent")}
      </div>
      <div class="tabs" role="tablist" aria-label="Organisation">${Object.entries(F.providers).map(([id, p]) => { const kk = KEYS[id], has = kk && s.sent[kk] != null; return `<button type="button" role="tab" aria-selected="${id === provider}" data-provider="${id}">${has ? `<span class="dot" aria-hidden="true"></span>` : ""}${esc(p.name)}${has ? "" : `<span class="visually-hidden"> (no email yet)</span>`}</button>`; }).join("")}</div>
      <div class="console">
        <form class="compose" id="compose" novalidate aria-label="Your reply">
          ${open ? `
            <div class="quick" role="group" aria-label="Ready-made replies">${variants.map((r) => { const w = why(s, r); return `<button type="button" data-variant="${r.id}" aria-pressed="${variant === r.id}" ${w ? `disabled title="${esc(w)}"` : `title="${esc(r.purpose)}"`}>${esc(SHORT[r.id] || r.label)}</button>`; }).join("")}<button type="button" data-variant="custom" aria-pressed="${variant === "custom"}">Write my own</button></div>
            ${chosen ? `<p class="small muted">${esc(chosen.purpose)}.</p>` : variant === "custom" ? `<p class="small muted">Free text is marked for review: this demo can't read it.</p>` : `<p class="small muted">Choose a reply above, or write your own.</p>`}
            <label class="visually-hidden" for="reply-text">Reply</label>
            <textarea class="textarea" id="reply-text" ${variant ? "" : "disabled"} placeholder="Your reply">${esc(text)}</textarea>
            ${result && result.kind === "error" ? `<div class="banner-line banner-line--alert" role="alert">${icon("warning")}<span><b>Couldn't send.</b> Nothing went out.</span><button class="btn btn--sm" type="submit">Try again</button></div>` : ""}
            ${result && result.kind === "sent" ? `<div class="banner-line banner-line--good" role="status">${icon("check")}<span><b>Sent.</b> Afterward has it.</span><a class="btn btn--sm" href="desk.html">See the desk</a></div>` : ""}
            <div class="compose__foot">
              <span class="small muted">From ${esc(P.name)} &lt;${esc(chosen && chosen.from ? chosen.from : P.recipient)}&gt;</span>
              <span class="cluster cluster--tight"><label class="cluster cluster--tight xsmall muted"><input type="checkbox" data-fail ${failNext ? "checked" : ""}> Make it fail</label>
              <button class="btn btn--primary" type="submit" ${variant && text.trim() && !sending ? "" : "disabled"} ${sending ? 'aria-busy="true"' : ""}>${sending ? "Sending…" : `${icon("send")}Send reply`}</button></span>
            </div>` :
            `<div class="empty"><p class="empty__title">Nothing to answer yet</p><p>${provider === "crescent" ? "The plan keeps Crescent Bank open, so Afterward won't write to it." : `Afterward writes to ${esc(P.name)} once Sara approves.`}</p><button class="btn btn--sm" type="button" data-story>${icon("horizon")}Jump in the story</button></div>`}
        </form>
        <section class="panel-box" aria-labelledby="thread-title">
          <div class="panel-box__head"><h2 class="panel-box__title" id="thread-title">${open ? esc(REQUEST[provider].subject) : "Thread"}</h2>${open ? `<span class="xsmall muted">${replies.length + 1} message${replies.length ? "s" : ""}</span>` : ""}</div>
          <div class="panel-box__body scroll thread-scroll" tabindex="0" aria-label="Email thread">
            ${open ? `<article class="email"><div class="email__head"><b>Afterward, for the Malik family</b><span class="muted">${esc(AW.fmtTime(s.sent[k]))}</span></div><div class="email__body">${esc(REQUEST[provider].body)}</div></article>
              ${replies.map((r) => { const rr = F.replies.find((x) => x.id === r.id); return `<article class="email email--reply"><div class="email__head"><b>${esc(P.name)}${rr && rr.from ? ` (${esc(rr.from)})` : ""}</b><span class="muted">${esc(AW.fmtTime(r.at))}</span></div><div class="email__body">${esc(r.custom || (rr && rr.body))}</div></article>`; }).join("")}`
            : `<p class="muted">No emails yet.</p>`}
          </div>
        </section>
      </div>`;
    const t = root.querySelector(".thread-scroll"); if (t) t.scrollTop = result && result.kind === "sent" ? t.scrollHeight : y;
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.provider) { provider = b.dataset.provider; variant = null; text = ""; result = null; render(); root.querySelector(`[data-provider="${provider}"]`).focus(); }
    if (b.dataset.variant) { variant = b.dataset.variant; const r = F.replies.find((x) => x.id === variant); text = r ? r.body : ""; result = null; render(); root.querySelector(`[data-variant="${variant}"]`).focus(); }
    if (b.dataset.story != null) UI.openStory();
  });
  root.addEventListener("change", (e) => { if (e.target.matches("[data-fail]")) failNext = e.target.checked; });
  root.addEventListener("input", (e) => {
    if (e.target.id !== "reply-text") return;
    text = e.target.value;
    const r = F.replies.find((x) => x.id === variant);
    if (r && text !== r.body) { variant = "custom"; const pos = e.target.selectionStart; render(); const t = root.querySelector("#reply-text"); t.focus(); t.setSelectionRange(pos, pos); return; }
    const sb = root.querySelector('button[type="submit"].btn--primary'); if (sb) sb.disabled = !text.trim();
  });
  root.addEventListener("submit", (e) => {
    e.preventDefault();
    if (sending || !variant || !text.trim()) return;
    sending = true; result = null; render();
    setTimeout(() => {
      sending = false;
      if (failNext) { failNext = false; result = { kind: "error" }; render(); UI.announce("Couldn't send. Nothing went out."); return; }
      if (variant === "custom") AW.dispatch("reply", { id: "custom", provider, text, delay: 120 });
      else AW.dispatch("reply", { id: variant });
      result = { kind: "sent" }; variant = null; text = "";
      render(); const a = root.querySelector(".banner-line--good a"); if (a) a.focus();
    }, 600);
  });
  AW.subscribe((s, local) => { if (!local) render(); });
  render();
})();
