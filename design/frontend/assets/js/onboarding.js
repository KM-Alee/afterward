/* Onboarding: where to look for accounts. The family chooses every source; a discovery agent
   combs through only what they granted, proposes candidates and suggests next steps. Nothing is
   confirmed, sent or filed here. Fictional data; nothing leaves this browser. */
(function () {
  "use strict";
  const { esc, icon, status, simTag } = UI;
  UI.shell("onboarding", { context: "Finding accounts", wide: true });

  /* ---------------- Fixtures (fictional) ---------------- */
  const HEADERS = [
    { id: "h1", from: "Northline Mobile", subject: "Your bill for the line ending 4417", date: "2 Mar", ref: "4417" },
    { id: "h2", from: "Crescent Bank", subject: "Your statement is ready, Mr Y Malik", date: "28 Feb", ref: "0932" },
    { id: "h3", from: "StreamBox", subject: "Your plan renews on 12 March", date: "26 Feb", ref: "SB-88213" },
    { id: "h4", from: "FitLife Gym", subject: "Membership FL-5531: February payment", date: "1 Feb", ref: "FL-5531" },
    { id: "h5", from: "Paperleaf Books", subject: "Your annual subscription renews on 2 November", date: "20 Jan", ref: "PB-3017" },
    { id: "h6", from: "Northline Mobile", subject: "Reminder: line ending 4417", date: "15 Jan", ref: "4417" },
    { id: "h7", from: "Orchard Row Residents", subject: "Newsletter: spring clean-up at 14 Orchard Row", date: "9 Jan", ref: null },
  ];
  const ACCOUNTS = {
    "4417": { provider: "Northline Mobile", label: "Mobile line ending 4417", track: "ordinary" },
    "0932": { provider: "Crescent Bank", label: "Current account ending 0932", track: "financial" },
    "SB-88213": { provider: "StreamBox", label: "Streaming subscription", track: "ordinary" },
    "FL-5531": { provider: "FitLife Gym", label: "Membership FL-5531", track: "ordinary" },
    "PB-3017": { provider: "Paperleaf Books", label: "Annual subscription", track: "ordinary" },
    "2290": { provider: "Northline Mobile", label: "Mobile line ending 2290", track: "ordinary" },
    "CP-77120": { provider: "City Power", label: "Electricity, 14 Orchard Row", track: "ordinary" },
    "HW-20418": { provider: "Harbor Water", label: "Water, 14 Orchard Row", track: "ordinary" },
    "ML-6610": { provider: "Meridian Life", label: "Life policy ML-6610", track: "insurance" },
  };
  const PHOTOS = ["2290", "CP-77120", "HW-20418", "ML-6610"];
  const TRACK = {
    ordinary: { kind: "neutral", icon: "mail", text: "Can be handled by email" },
    financial: { kind: "info", icon: "lock", text: "Notify only · closing may need probate" },
    insurance: { kind: "info", icon: "hand", text: "Notify only · claim is yours to file" },
    unknown: { kind: "unknown", icon: "question", text: "Not in our directory yet" },
  };
  const STATE = {
    proposed: { kind: "review", icon: "question", text: "Unconfirmed" },
    confirmed: { kind: "holding", icon: "check", text: "Yusuf's (you confirmed)" },
    removed: { kind: "void", icon: "cross", text: "Not his" },
    needs_check: { kind: "uncertain", icon: "users", text: "Shared or not sure" },
  };
  const HANDBACK = [
    { id: "copies", title: "Certified copies of the death certificate", body: "A phone photo is never a certified copy. Order copies from the register office; you'll post or take them in where an organisation insists.", always: true },
    { id: "gov", title: "Tell government offices", body: "Prepared: the reference numbers they usually ask for. You do this through the official service. We don't file anything with government.", always: true },
    { id: "probate", title: "Apply for probate (the grant)", body: "Banks often need the grant before closing an account. We list what the application asks for. A person applies; we don't file it.", when: (s) => s.cands["0932"] && s.cands["0932"].state === "confirmed" },
    { id: "claim", title: "Meridian Life claim", body: "The beneficiary files the claim with the insurer. We can send a notification once you approve it; the claim itself is handed to you.", when: (s) => s.cands["ML-6610"] && s.cands["ML-6610"].state === "confirmed" },
  ];

  /* ---------------- State ---------------- */
  const s = {
    inbox: "off", // off → connected → listed → read
    ticked: new Set(),
    photos: false, statement: false, hisMail: false,
    locators: { policy: "none", unclaimed: "none" },
    cands: {}, order: [], told: [],
    dismissed: new Set(), handDone: new Set(),
    log: [], busy: false, priority: null, keep: null,
  };

  function propose(ref, source, extra) {
    const known = ACCOUNTS[ref];
    if (!s.cands[ref]) {
      s.cands[ref] = Object.assign({ ref, provider: known ? known.provider : "", label: known ? known.label : ref, track: known ? known.track : "unknown", state: "proposed", sources: new Set() }, extra || {});
      s.order.push(ref);
    }
    s.cands[ref].sources.add(source); // a merge adds evidence; it never moves the state
  }
  function agent(lines, then) {
    s.busy = true; render();
    setTimeout(() => { s.log.push(...lines); s.busy = false; if (then) then(); render(); }, 900);
  }

  /* ---------------- Suggestions (what the agent would put on the family's card) ---------------- */
  function suggestions() {
    const out = [];
    const has = (r) => !!s.cands[r];
    const granted = s.inbox === "read" || s.photos || s.statement || s.told.length;
    if (!granted && s.inbox === "off") out.push({ id: "start", text: "Most accounts show up in bills. The quickest start is an inbox Yusuf's bills came to, if it's one you control, or photos of the post on the table.", why: "Nothing has been shared yet.", opts: [["Search my inbox", "connect"], ["Send photos", "photos"]] });
    if (has("2290") && s.cands["2290"].state === "proposed") out.push({ id: "2290", text: "The Northline bill shows a second line, ending 2290, as well as 4417. Whose is 2290?", why: "Photo of a Northline bill · two references on one page.", opts: [["Yusuf's", "c:2290:confirmed"], ["Someone else's", "c:2290:removed"], ["Not sure", "c:2290:needs_check"]] });
    if (has("PB-3017") && !s.priority) out.push({ id: "pb", text: "Paperleaf renews on 2 November. Do you want it stopped before it charges again?", why: "Email from Paperleaf Books, 20 Jan: \"renews on 2 November\".", opts: [["Yes, put it first", "prio"], ["No", "dismiss"]] });
    if (s.inbox === "read" && s.keep === null) out.push({ id: "keep", text: "Before anything is closed: could his email or phone hold photos or documents you'll want to keep?", why: "Closing a line or an email account can lose what's on it.", opts: [["Yes, keep them", "keep:yes"], ["No", "keep:no"], ["Not sure", "keep:unsure"]] });
    if (has("0932") && !s.statement) out.push({ id: "stmt", text: "Crescent Bank emails mention monthly statements. A photo of one statement usually shows direct debits that email doesn't.", why: "Email from Crescent Bank, 28 Feb.", opts: [["Send a statement", "statement"], ["Later", "dismiss"]] });
    if (has("ML-6610") && s.locators.policy === "none") out.push({ id: "loc", text: "There's a Meridian Life letter. A policy locator can check whether he had other policies. Insurers answer the beneficiary directly.", why: "Photo of a Meridian Life letter.", opts: [["Prepare it for me", "loc:policy:prepared"], ["Not now", "dismiss"]] });
    return out.filter((x) => !s.dismissed.has(x.id));
  }

  /* ---------------- Render ---------------- */
  const card = (ic, title, sub, body, extra) => `<article class="card ob-src ${extra || ""}"><header class="ob-src__head">${icon(ic, "icon--lg")}<div><h2 class="h3">${esc(title)}</h2><p class="hint">${sub}</p></div></header><div class="stack">${body}</div></article>`;
  const btn = (label, act, o) => { o = o || {}; return `<button class="btn ${o.primary ? "btn--primary" : ""} ${o.sm ? "btn--sm" : ""}" type="button" data-act="${esc(act)}" ${o.disabled ? "disabled" : ""}>${o.icon ? icon(o.icon) : ""}${esc(label)}</button>`; };

  function renderSuggest() {
    const list = suggestions();
    if (s.busy) return `<article class="card ob-sugg" aria-live="polite"><p class="ob-sugg__who">${icon("waves")}Looking through what you gave me…</p></article>`;
    if (!list.length) return `<article class="card card--sunken ob-sugg ob-sugg--quiet"><p class="ob-sugg__who">${icon("check")}No suggestions right now.</p><p class="hint">New photos, forwards or a statement can always add more.</p></article>`;
    const x = list[0];
    return `<article class="card ob-sugg" aria-labelledby="sugg-text">
      <p class="ob-sugg__who">${icon("chat")}Afterward noticed${list.length > 1 ? ` <span class="pill-count">${list.length - 1} more</span>` : ""}</p>
      <p class="ob-sugg__text" id="sugg-text">${esc(x.text)}</p>
      <p class="hint">${icon("quote", "icon--sm")} From: ${esc(x.why)}</p>
      <div class="btn-row">${x.opts.map(([l, a], i) => btn(l, `s:${x.id}:${a}`, { primary: i === 0 })).join("")}</div>
      <p class="xsmall muted">A suggestion only. Nothing is searched, sent or confirmed unless you choose it.</p>
    </article>`;
  }

  function renderInbox() {
    if (s.inbox === "off") return card("mail", "An inbox you control", "If Yusuf's bills came to a shared or household address, connect it. You own it; we only read what you tick.",
      `<div class="btn-row">${btn("Connect Gmail", "connect", { primary: true, icon: "link" })}</div><p class="xsmall muted">${simTag("Prototype")} In the live demo this is the connected demo Gmail. Read-only for this step.</p>`);
    if (s.inbox === "connected") return card("mail", "Household inbox · connected", `${simTag("Demo Gmail")} Owned by you. Disconnect any time.`,
      `<div class="field"><span class="label">I'll search only for mail that names him or the house</span>
        <div class="ob-tags">${["Yusuf Malik", "Y Malik", "14 Orchard Row", "since Oct 2023"].map((t) => `<span class="ob-tag">${esc(t)}</span>`).join("")}</div>
        <code class="ob-query">("Yusuf Malik" OR "Y Malik" OR "14 Orchard Row") (bill OR invoice OR statement OR renewal OR "direct debit" OR membership OR policy OR subscription) newer_than:3y</code>
        <p class="hint">Built by code from the case, not by the AI. The AI can narrow it, never widen it.</p></div>
       <div class="btn-row">${btn("Search headers only", "headers", { primary: true })}</div>`);
    const rows = HEADERS.map((h) => `<li class="ob-hdr"><label><input type="checkbox" data-tick="${h.id}" ${s.ticked.has(h.id) ? "checked" : ""} ${s.inbox === "read" ? "disabled" : ""}><span><b>${esc(h.from)}</b> <span class="muted">· ${esc(h.date)}</span><br><span class="small">${esc(h.subject)}</span></span></label>${s.inbox === "read" ? (s.ticked.has(h.id) ? status({ kind: "holding", icon: "check", text: "Read" }) : status({ kind: "neutral", icon: "eye-off", text: "Not read" })) : ""}</li>`).join("");
    const n = s.ticked.size;
    const foot = s.inbox === "listed"
      ? `<p class="hint">${icon("eye-off", "icon--sm")} Nothing has been read yet. Tick what I may read; the rest stays unread.</p><div class="btn-row">${btn(`Read ${n} ticked`, "read", { primary: true, disabled: !n })}${btn("Tick all", "tickall")}</div>`
      : `<p class="small">Read ${n} of ${HEADERS.length} with your OK. ${HEADERS.length - n} left unread.</p>`;
    return card("mail", "Household inbox · 7 matches", "From, subject and date only.", `<ul class="ob-hdrs" role="list">${rows}</ul>${foot}`);
  }

  function renderPhotos() {
    return card("photo", "Photos and forwarded emails", "Send them to the Afterward chat in Telegram, or forward mail to the case address. Bills, letters, renewal notices.",
      s.photos ? `<p class="small">${icon("check", "icon--sm")} 4 photos read: Northline, City Power, Harbor Water, Meridian Life.</p><p class="hint">Phone photos are kept as photos, never as certified copies.</p>`
        : `<div class="btn-row">${btn("Sara sends 4 photos", "photos", { icon: "photo" })}</div><p class="xsmall muted">${simTag("Simulated")} In the live demo these arrive as real Telegram photos.</p>`);
  }

  function renderStatement() {
    return card("money", "A bank or card statement", "Recurring payments show accounts that never emailed anyone. We list payees; we don't use balances.",
      s.statement ? `<p class="small">${icon("check", "icon--sm")} 3 payees: FitLife and Harbor Water (added as evidence) and one new payment with no reference.</p>`
        : `<div class="btn-row">${btn("Send a statement", "statement", { icon: "doc" })}</div>`);
  }

  function renderHisMail() {
    return card("shield", "Yusuf's own email", "We can't open his inbox, and we won't sign in as him, even with his password. His email provider has its own process for family.",
      `<ul class="ob-list small">
        <li><b>Google:</b> a trusted contact he set up, or a request about a deceased user's account</li>
        <li><b>Apple:</b> a Legacy Contact with the access key</li>
        <li><b>Microsoft:</b> a next-of-kin request</li></ul>
       ${s.hisMail ? `<div class="banner banner--info">${icon("doc")}<div class="banner__body"><p class="banner__title">Prepared for you</p><p class="small">His full name, email address, date of death and your relationship, plus a note that they will ask for the death certificate. You send the request; the provider decides.</p></div></div>` : `<div class="btn-row">${btn("Prepare what they ask for", "hismail")}</div>`}
       <p class="hint">If the provider gives you an export, upload it and I'll search it the same way as an inbox.</p>
       <div class="btn-row">${btn("Upload an export (.mbox)", "noop", { disabled: true, icon: "doc" })}</div>`);
  }

  function renderLocators() {
    const row = (id, name, what) => {
      const st = s.locators[id];
      const state = st === "none" ? "" : st === "prepared" ? status({ kind: "info", icon: "doc", text: "Prepared" }) : status({ kind: "waiting", icon: "clock", text: "Started by Sara · waiting" });
      const body = st === "prepared"
        ? `<dl class="deflist small"><dt>Name</dt><dd>Yusuf Malik</dd><dt>Died</dt><dd>3 March 2026</dd><dt>Last address</dt><dd>14 Orchard Row</dd><dt>You</dt><dd>Sara Malik, daughter (stated)</dd></dl>
           <div class="btn-row">${btn("Open the official site", "noop", { disabled: true, icon: "link" })}${btn("I started it", `loc:${id}:started`, { primary: true })}</div>
           <p class="xsmall muted">You submit it yourself. We don't create accounts or fill forms on their site.</p>`
        : st === "started" ? `<p class="hint">Results go to you, not to us. Forward or photograph the reply when it comes. "No match" means none was reported, not that none exists.</p>`
          : `<div class="btn-row">${btn("Prepare it", `loc:${id}:prepared`, { sm: true })}</div>`;
      return `<li class="ob-loc"><div class="cluster cluster--between"><span><b>${esc(name)}</b> ${simTag("Fictional")}</span>${state}</div><p class="small muted">${esc(what)}</p>${body}</li>`;
    };
    return card("building", "Searches you can run", "Official locators and registers. You run them; I prepare what they ask for.",
      `<ul class="ob-locs" role="list">${row("policy", "Policy locator (demo)", "Asks insurers whether he held a life policy.")}${row("unclaimed", "Unclaimed money search (demo)", "Dormant accounts and unclaimed property.")}</ul>
       <p class="xsmall muted">Real services vary by country. Pakistan: not researched yet.</p>`);
  }

  function renderTell() {
    return card("mic", "Tell me yourself", "A name is enough, like \"he had a gym membership\" or \"a storage unit in town\".",
      `<form class="ob-tell" data-tell><label class="visually-hidden" for="tell">Something he had</label><input class="input" id="tell" placeholder="He had…" autocomplete="off"><button class="btn" type="submit">Add</button></form>`);
  }

  function renderFound() {
    const list = s.order.map((r) => s.cands[r]);
    const need = list.filter((c) => c.state === "proposed").length;
    const items = list.map((c) => `<li class="cand ${c.ref === s.priority ? "ob-prio" : ""}">
        <span class="cand__name">${esc(c.provider || "Unknown organisation")} <span class="muted">· ${esc(c.label)}</span></span>
        ${status(STATE[c.state])}
        <span class="cand__meta"><span>${icon("link", "icon--sm")} ${esc([...c.sources].join(" · "))}</span>${status(TRACK[c.track], "status--plain")}${c.ref === s.priority ? `<span>${icon("clock", "icon--sm")} You put this first</span>` : ""}</span>
        ${c.state === "proposed" ? `<span class="cand__ask">${btn("Yes, his", `c:${c.ref}:confirmed`, { sm: true, primary: true })}${btn("Not his", `c:${c.ref}:removed`, { sm: true })}${btn("Shared or not sure", `c:${c.ref}:needs_check`, { sm: true })}</span>` : ""}
      </li>`).join("");
    return `<div class="panel__head"><h2 class="section-title" id="ob-found-title">${icon("building")}Possible accounts</h2><span class="small">${list.length} found · ${need} need you</span></div>
      ${list.length ? `<ul class="cands">${items}</ul>` : `<p class="hint">Nothing yet. Accounts appear here only from places you choose.</p>`}
      <p class="xsmall muted">Nothing is planned or sent for an account until you say it's his.</p>`;
  }

  function renderCoverage() {
    const searched = [];
    if (s.inbox === "read") searched.push(`Household inbox: 7 matches, ${s.ticked.size} read with your OK`);
    if (s.photos) searched.push("4 photos of bills and letters");
    if (s.statement) searched.push("1 bank statement");
    if (s.told.length) searched.push(`${s.told.length} you told me about`);
    const waiting = Object.entries(s.locators).filter(([, v]) => v === "started").map(([k]) => k === "policy" ? "Policy locator: started by Sara, result not back" : "Unclaimed money search: started by Sara, result not back");
    const notRun = Object.entries(s.locators).filter(([, v]) => v !== "started").map(([k]) => k === "policy" ? "Policy locator" : "Unclaimed money search");
    if (!s.statement) notRun.push("Bank statements");
    const ul = (xs, empty) => xs.length ? `<ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="hint">${esc(empty)}</p>`;
    return `<div class="panel__head"><h2 class="section-title" id="ob-coverage-title">${icon("eye-off")}What we did and didn't search</h2></div>
      <div class="ob-cov">
        <div><h3 class="h4">${icon("check", "icon--sm")} Searched</h3>${ul(searched, "Nothing yet.")}</div>
        ${waiting.length ? `<div><h3 class="h4">${icon("clock", "icon--sm")} Started, waiting</h3>${ul(waiting)}</div>` : ""}
        <div><h3 class="h4">${icon("dash", "icon--sm")} Not run yet</h3>${ul(notRun, "None.")}</div>
        <div><h3 class="h4">${icon("lock", "icon--sm")} Not searched, by design</h3>${ul(["Yusuf's own inbox and phone", "Government, court and tax records", "His credit file", "Anything paid in cash", "Post that hasn't been photographed"])}</div>
        <div><h3 class="h4">${icon("info", "icon--sm")} Where else to look</h3>${ul(["App-store subscriptions on his phone", "Post over the next few weeks"])}</div>
      </div>
      <p class="small">This list stays open. Anything you send later can add to it.</p>`;
  }

  function renderHandback() {
    const items = HANDBACK.filter((h) => h.always || h.when(s));
    return `<div class="panel__head"><h2 class="section-title" id="ob-handback-title">${icon("hand")}Prepared for you, done by you</h2></div>
      <p class="hint">Legal, government, tax and certified-document steps. We get them ready; a person does them.</p>
      <ul class="ob-hb" role="list">${items.map((h) => `<li><div class="cluster cluster--between"><b>${esc(h.title)}</b>${s.handDone.has(h.id) ? status({ kind: "info", icon: "user", text: "Sara says done" }) : status({ kind: "neutral", icon: "hand", text: "You do this" })}</div>
        <p class="small">${esc(h.body)}</p>
        ${s.handDone.has(h.id) ? `<p class="xsmall muted">Stated by Sara, not evidenced. Forward the confirmation when it arrives.</p>` : `<div class="btn-row">${btn("I did this", `hb:${h.id}`, { sm: true })}</div>`}</li>`).join("")}</ul>`;
  }

  function renderLog() {
    if (!s.log.length) return "";
    return `<details class="card card--flat ob-log"><summary class="small"><b>What the agent did</b> · ${s.log.length} steps</summary><ol class="xsmall">${s.log.map((l) => `<li><code>${esc(l)}</code></li>`).join("")}</ol><p class="xsmall muted">Tools are read-only and bound to what you shared. It has no tool to confirm, send, sign in or open links.</p></details>`;
  }

  const srcEl = document.getElementById("ob-sources");
  function render() {
    const focusId = document.activeElement && document.activeElement.id;
    srcEl.innerHTML = renderSuggest() + renderInbox() + renderPhotos() + renderStatement() + renderLocators() + renderHisMail() + renderTell() + renderLog();
    document.getElementById("ob-found").innerHTML = renderFound();
    document.getElementById("ob-coverage").innerHTML = renderCoverage();
    document.getElementById("ob-handback").innerHTML = renderHandback();
    if (focusId && document.getElementById(focusId)) document.getElementById(focusId).focus();
  }
  document.getElementById("ob-boundary").innerHTML = `${icon("shield")}<div class="banner__body"><p class="banner__title">What we never do</p><p class="small">Sign in as Yusuf, use his password, or search government, court or credit records. Those steps are prepared here and handed to you. We also never say we've found everything.</p></div>`;

  /* ---------------- Actions ---------------- */
  function act(a) {
    const [k, x, y] = a.split(":");
    if (k === "connect") { s.inbox = "connected"; UI.announce("Inbox connected. Nothing searched yet."); return render(); }
    if (k === "headers") return agent(["search_inbox_headers(scope=case) → 7 headers", "ask_to_read(7 ids) → waiting for your ticks"], () => { s.inbox = "listed"; });
    if (k === "tickall") { HEADERS.forEach((h) => s.ticked.add(h.id)); return render(); }
    if (k === "read") {
      const ids = HEADERS.filter((h) => s.ticked.has(h.id));
      return agent([...ids.map((h) => `read_message(${h.id}) → ${h.ref ? `propose_candidate(${h.from}, ${h.ref})` : "no account found"}`), "provider_profile × 5 → tracks set by the directory"], () => {
        s.inbox = "read"; ids.forEach((h) => h.ref && propose(h.ref, "Household inbox"));
        UI.announce(`${s.order.length} possible accounts. Each one needs you to say whose it is.`);
      });
    }
    if (k === "photos") return agent(["document_fields(4 photos) → form forced to photo", ...PHOTOS.map((r) => `propose_candidate(${ACCOUNTS[r].provider}, ${r})`), "suggest_to_family(which_account, 2290)"], () => { s.photos = true; PHOTOS.forEach((r) => propose(r, "Photo of a bill or letter")); });
    if (k === "statement") return agent(["statement_payees(doc) → 3 payees", "propose_candidate(FitLife, FL-5531) → merged as evidence", "propose_candidate(Harbor Water, HW-20418) → merged as evidence", "propose_candidate(CloudVault, no reference) → kept separate"], () => {
      s.statement = true; s.dismissed.add("stmt");
      propose("FL-5531", "Bank statement"); propose("HW-20418", "Bank statement");
      propose("cloudvault", "Bank statement", { provider: "CloudVault", label: "Monthly payment, no reference", track: "unknown" });
    });
    if (k === "hismail") { s.hisMail = true; return render(); }
    if (k === "loc") { s.locators[x] = y; if (x === "policy") s.dismissed.add("loc"); UI.announce(y === "started" ? "Recorded as started by you. Waiting for the result." : "Prepared. You submit it yourself."); return render(); }
    if (k === "c") { s.cands[x].state = y; UI.announce(`${s.cands[x].provider}: ${STATE[y].text}.`); return render(); }
    if (k === "hb") { s.handDone.add(x); return render(); }
    if (k === "s") {
      const [, id, ...rest] = a.split(":"); const sub = rest.join(":");
      if (sub === "dismiss") s.dismissed.add(id);
      else if (sub === "prio") { s.priority = "PB-3017"; }
      else if (sub.startsWith("keep:")) { s.keep = sub.slice(5); UI.announce("Noted. Nothing is closed without asking you about this first."); }
      else { s.dismissed.add(id); return act(sub); }
      return render();
    }
  }
  UI.on(document.body, "[data-act]", "click", (e, t) => act(t.dataset.act));
  UI.on(document.body, "[data-tick]", "change", (e, t) => { if (t.checked) s.ticked.add(t.dataset.tick); else s.ticked.delete(t.dataset.tick); render(); });
  document.body.addEventListener("submit", (e) => {
    if (!e.target.matches("[data-tell]")) return;
    e.preventDefault();
    const input = e.target.querySelector("input"); const v = input.value.trim(); if (!v) return;
    s.told.push(v); const ref = `told-${s.told.length}`;
    agent([`provider_profile("${v}") → unknown`, `propose_candidate("${v}", no reference)`], () => propose(ref, `You said: "${v}"`, { provider: v, label: "No reference yet", track: "unknown" }));
  });
  render();
})();
