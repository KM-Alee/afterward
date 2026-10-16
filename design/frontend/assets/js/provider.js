/* Provider console: a judge replies as a fictional demo provider. Sends are simulated and
   only change the local mock state. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, simTag } = UI;
  UI.shell("provider", { context: "Provider console" });
  const root = document.getElementById("root");

  const KEYS = { northline: "nl", citypower: "cp", streambox: "sb", fitlife: "fl", crescent: null };
  const REQUEST = {
    northline: { subject: "Bereavement request · line ending 4417", body: "Dear Northline bereavement team,\n\nI'm writing on behalf of Sara Malik, who is handling the estate of her father, Yusuf Malik (as she has told us). He died on 3 March 2026.\n\nAccount: mobile line ending 4417.\nRequest: please transfer the line to Amina Malik, his wife.\nConditions: please keep the existing number and the existing voicemail greeting, and don't start a new contract. If any of these can't be met, please don't go ahead; reply and we'll ask the family.\n\nAttached: a photo of the death certificate (your published process accepts a photo).\n\nPlease confirm in writing when it's done, naming the new account holder, the number and the voicemail.\n\nKind regards,\nAfterward, for the Malik family" },
    citypower: { subject: "Closing account CP-77120 · 14 Orchard Row", body: "Dear City Power accounts team,\n\nI'm writing on behalf of Sara Malik, who is handling the estate of her father, Yusuf Malik (as she has told us). He died on 3 March 2026.\n\nPlease close account CP-77120 at 14 Orchard Row at the end of the current billing month, with a final meter read, and send the final bill to this address.\n\nKind regards,\nAfterward, for the Malik family" },
    streambox: { subject: "Cancelling subscription SB-88213", body: "Dear StreamBox team,\n\nI'm writing on behalf of Sara Malik about her late father Yusuf Malik's subscription SB-88213. He died on 3 March 2026. Please cancel it and confirm in writing.\n\nKind regards,\nAfterward, for the Malik family" },
    fitlife: { subject: "Cancelling membership FL-5531", body: "Dear FitLife Gym members team,\n\nI'm writing on behalf of Sara Malik about her late father Yusuf Malik's membership FL-5531. He died on 3 March 2026. Please cancel the membership and stop further payments. A photo of the death certificate is attached.\n\nKind regards,\nAfterward, for the Malik family" },
  };

  const init = UI.param("reply");
  const initReply = F.replies.find((r) => r.id === init);
  let provider = initReply ? initReply.provider : "northline";
  let variant = initReply ? initReply.id : null;
  let text = initReply ? initReply.body : "";
  let failNext = false;
  let result = null; // { kind: "sent" | "error", at, label }
  let sending = false;

  function available(s, r) {
    if (r.needs === "call_accepted") return s.call.terms.some((t) => t.status === "accepted") ? null : "Available after the agent accepts terms on the call (story step 12).";
    const k = KEYS[r.provider];
    return k && s.sent[k] != null ? null : "Available once Afterward has sent this provider a request.";
  }

  function render() {
    const s = AW.state, P = F.providers[provider], k = KEYS[provider], open = k && s.sent[k] != null;
    const variants = F.replies.filter((r) => r.provider === provider);
    if (variant && variant !== "custom" && (!variants.some((r) => r.id === variant) || available(s, F.replies.find((r) => r.id === variant)))) { variant = null; text = ""; }
    const chosen = variant && variant !== "custom" ? F.replies.find((r) => r.id === variant) : null;
    const fromAddr = chosen && chosen.from ? chosen.from : P.recipient;
    const replies = s.replies.filter((r) => r.provider === provider);

    root.innerHTML = `<div class="page-head"><div class="page-head__titles"><p class="eyebrow">For judges playing the demo providers</p><h1 class="h1">Provider console</h1></div>${simTag("Simulated sends · nothing leaves this browser")}</div>
    <div class="console__grid">
      <form class="card stack" id="console" novalidate>
        <div class="console-step">
          <p class="console-step__title" id="st1"><span class="console-step__num">1</span>Choose a provider</p>
          <div class="provider-pick" role="radiogroup" aria-labelledby="st1">${Object.entries(F.providers).map(([id, p]) => { const kk = KEYS[id]; const has = kk && s.sent[kk] != null; return `<label class="choice"><input type="radio" name="provider" value="${id}" ${id === provider ? "checked" : ""}><span class="choice__title">${esc(p.name)}</span><span class="choice__meta">${has ? "Open request" : "No request yet"} · fictional</span></label>`; }).join("")}</div>
        </div>
        <div class="console-step">
          <p class="console-step__title"><span class="console-step__num">2</span>Thread</p>
          ${open ? `<p class="cluster cluster--tight">${icon("mail")}<b>${esc(REQUEST[provider].subject)}</b><span class="ref">Ref AW-1042-${k.toUpperCase()}1</span></p>` :
            `<div class="banner banner--warning">${icon("hand")}<p class="banner__title">Nothing to reply to yet</p><p class="banner__body">Afterward hasn't written to ${esc(P.name)}. ${provider === "crescent" ? "The plan says don't close this account; it may be joint with Amina." : provider === "northline" ? "Sara approves the request first (story step 5)." : "Its request goes out after Sara approves it (story step 5)."}</p><div class="banner__actions"><button class="btn btn--sm" type="button" data-story>${icon("horizon")}Open the Story guide</button></div></div>`}
        </div>
        <fieldset class="console-step" style="border:0;margin:0;padding-inline:0" ${open ? "" : "disabled"}>
          <legend class="console-step__title" style="padding:0"><span class="console-step__num">3</span>Choose a reply</legend>
          <div class="choice-list">
            ${variants.map((r) => { const why = available(s, r); return `<label class="choice"><input type="radio" name="variant" value="${r.id}" ${variant === r.id ? "checked" : ""} ${why ? "disabled" : ""}><span class="choice__title">${esc(r.label)}</span><span class="choice__meta">${esc(why || r.purpose)}${r.from ? ` · from ${esc(r.from)}` : ""}</span></label>`; }).join("")}
            <label class="choice"><input type="radio" name="variant" value="custom" ${variant === "custom" ? "checked" : ""}><span class="choice__title">Write my own</span><span class="choice__meta">The prototype can't read free text, so it is marked needs review (ambiguous)</span></label>
          </div>
          <div class="field">
            <label class="label" for="reply-text">Reply text</label>
            <textarea class="textarea" id="reply-text" ${variant ? "" : "disabled"} aria-describedby="reply-hint">${esc(text)}</textarea>
            <span class="hint" id="reply-hint">${variant === "custom" ? "Write anything a provider might send." : "Prepared text. Editing it makes it free text."}</span>
          </div>
        </fieldset>
        <div class="console-step">
          <p class="console-step__title"><span class="console-step__num">4</span>Send</p>
          <p class="small">From <b>${esc(P.name)} (demo)</b> <span class="ref">&lt;${esc(fromAddr)}&gt;</span>${chosen && chosen.from ? ` ${chip("violated", "Not an approved address")}` : ""}</p>
          ${result && result.kind === "error" ? `<div class="banner banner--error" role="alert">${icon("warning")}<p class="banner__title">Couldn't send (simulated failure)</p><p class="banner__body">The providers mailbox didn't accept the message. Nothing was sent, so there's nothing to reconcile.</p><div class="banner__actions"><button class="btn btn--sm" type="submit">${icon("retry")}Try again</button></div></div>` : ""}
          ${result && result.kind === "sent" ? `<div class="banner banner--success" role="status">${icon("check")}<p class="banner__title">Simulated send recorded</p><p class="banner__body">"${esc(result.label)}" arrived in the mock case at ${esc(AW.fmtTime(result.at))}. No email was sent.</p><div class="banner__actions"><a class="btn btn--sm btn--primary" href="desk.html">See what Afterward concluded</a><a class="btn btn--sm" href="family.html?as=sara">See Sara's view</a></div></div>` : ""}
          <label class="cluster cluster--tight small"><input type="checkbox" data-fail ${failNext ? "checked" : ""}> Prototype: make the next send fail</label>
          <div class="btn-row"><button class="btn btn--primary btn--lg" type="submit" ${open && variant && text.trim() && !sending ? "" : "disabled"} ${sending ? 'aria-busy="true"' : ""}>${sending ? "Sending…" : `${icon("send")}Send reply (simulated)`}</button></div>
        </div>
      </form>
      <section class="stack" aria-labelledby="thread-title">
        <h2 class="h4" id="thread-title">The thread</h2>
        ${open ? `<article class="email"><div class="email__head"><span><b>From</b> Afterward, for the Malik family</span><span><b>To</b> <span class="ref">${esc(P.recipient)}</span></span><span><b>Subject</b> ${esc(REQUEST[provider].subject)}</span><span class="muted">${esc(AW.fmtTime(s.sent[k]))} · ${simTag()}</span></div>
          <div class="email__body">${esc(REQUEST[provider].body)}</div>
          <div class="email__foot">Prepared by Afterward, an AI assistant, on behalf of Sara Malik (as stated). Ref AW-1042-${k.toUpperCase()}1</div></article>
          ${replies.map((r) => { const rr = F.replies.find((x) => x.id === r.id); return `<article class="email email--reply"><div class="email__head"><span><b>From</b> ${esc(P.name)} (demo) <span class="ref">&lt;${esc(rr && rr.from ? rr.from : P.recipient)}&gt;</span></span><span class="muted">${esc(AW.fmtTime(r.at))} · ${simTag()}</span></div><div class="email__body">${esc(r.custom || (rr && rr.body))}</div></article>`; }).join("")}`
          : `<div class="empty"><svg class="empty__art" viewBox="0 0 96 56" aria-hidden="true"><path d="M8 48H88" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M34 48A14 14 0 0 1 62 48" fill="currentColor"/><path d="M24 40A24 24 0 0 1 72 40" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg><p class="empty__title">No thread yet</p><p>When Afterward writes to ${esc(P.name)}, the request appears here.</p></div>`}
        <div class="card card--flat small secondary stack stack-sm"><p class="h4">How replies are treated</p><p>Only the latest text counts; quoted older emails are ignored. Words are quoted and checked to exist in the message. A reply can never add a recipient or widen what Afterward may share.</p></div>
      </section>
    </div>`;
  }

  root.addEventListener("change", (e) => {
    if (e.target.name === "provider") { provider = e.target.value; variant = null; text = ""; result = null; render(); root.querySelector(`input[name=provider][value=${provider}]`).focus(); }
    if (e.target.name === "variant") { variant = e.target.value; const r = F.replies.find((x) => x.id === variant); text = r ? r.body : ""; result = null; render(); root.querySelector(`input[name=variant][value=${variant}]`).focus(); }
    if (e.target.matches("[data-fail]")) failNext = e.target.checked;
  });
  root.addEventListener("input", (e) => {
    if (e.target.id === "reply-text") {
      text = e.target.value;
      const r = F.replies.find((x) => x.id === variant);
      if (r && text !== r.body) { variant = "custom"; render(); const t = root.querySelector("#reply-text"); t.focus(); t.setSelectionRange(t.value.length, t.value.length); return; }
      const btn = root.querySelector('button[type="submit"].btn--lg'); if (btn) btn.disabled = !text.trim();
    }
  });
  root.addEventListener("click", (e) => { if (e.target.closest("[data-story]")) UI.openStory(); });
  root.addEventListener("submit", (e) => {
    e.preventDefault();
    if (sending || !variant || !text.trim()) return;
    sending = true; result = null; render();
    setTimeout(() => {
      sending = false;
      if (failNext) { failNext = false; result = { kind: "error" }; render(); UI.announce("Simulated send failed. Nothing was sent."); const b = root.querySelector(".banner--error button"); if (b) b.focus(); return; }
      const label = variant === "custom" ? "Your own reply" : F.replies.find((x) => x.id === variant).label;
      if (variant === "custom") AW.dispatch("reply", { id: "custom", provider, text, delay: 120 });
      else AW.dispatch("reply", { id: variant });
      result = { kind: "sent", at: AW.state.now, label };
      variant = null; text = "";
      render();
      const b = root.querySelector(".banner--success a"); if (b) b.focus();
    }, 700);
  });

  AW.subscribe((s, local) => { if (!local) render(); });
  render();
})();
