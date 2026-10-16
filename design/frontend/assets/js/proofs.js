/* Proof panel: the 14 adversarial cases (AFTERWARD.md §10.4). The prototype runs nothing.
   It shows the states the real panel needs, and says plainly that these are not results. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, simTag } = UI;
  UI.shell("proofs", { context: "Proof panel" });
  const root = document.getElementById("root");

  // Illustrative mixed results: chosen to show every state, not to predict anything.
  const MIXED = { 8: "fail", 11: "error", 13: "pending", 14: "pending" };
  let mode = "notrun"; // notrun | running | mixed
  let progress = 0;
  let timer = null;
  const open = new Set();

  const ST = {
    notrun: ["neutral", "Not run"], running: ["progress", "Running"], queued: ["neutral", "Queued"],
    pass: ["holding", "Pass (illustrative)"], fail: ["violated", "Fail (illustrative)"], error: ["review", "Error (illustrative)"], pending: ["waiting", "Pending (illustrative)"],
  };
  function stateOf(n) {
    if (mode === "notrun") return "notrun";
    if (mode === "running") return n < progress + 1 ? "pass_hidden" : n === progress + 1 ? "running" : "queued";
    return MIXED[n] || "pass";
  }
  const why = {
    fail: "Illustrative failure: the reply's Reply-To pointed elsewhere but the message was classified as approved. A real failure is shown like this and fixed, not hidden.",
    error: "Illustrative error: the worker-kill harness didn't start, so this case couldn't run. Errors are not counted as passes.",
    pending: "Illustrative: still running or waiting for a model response.",
  };

  function render() {
    const counts = { pass: 0, fail: 0, error: 0, pending: 0, notrun: 0 };
    F.proofs.forEach((p) => { const s = stateOf(p.n); if (counts[s] != null) counts[s]++; });
    const rows = F.proofs.map((p) => {
      let s = stateOf(p.n);
      if (s === "pass_hidden") s = "queued"; // during a preview run, completed rows stay neutral: nothing real ran
      const [k, l] = ST[s];
      const isOpen = open.has(p.n);
      return `<li class="proof">
        <div class="proof__row">
          <span class="proof__n" aria-hidden="true">${p.n}</span>
          <div><p class="proof__input"><span class="visually-hidden">Case ${p.n}: </span>${esc(p.input)}</p>
            <button class="link-btn small" type="button" data-open="${p.n}" aria-expanded="${isOpen}" aria-controls="pd-${p.n}">${isOpen ? "Hide" : "Show"} fixture and evidence</button></div>
          <p class="proof__req">${esc(p.required)}</p>
          <p class="proof__status">${s === "running" ? `<span class="status status--progress" aria-busy="true">${icon("clock")}Running</span>` : chip(k, l)}</p>
        </div>
        <div class="proof__detail" id="pd-${p.n}" ${isOpen ? "" : "hidden"}>
          <div><p class="eyebrow">Fixture input</p><pre>${esc(p.input)}</pre></div>
          <div><p class="eyebrow">Required record</p><pre>${esc(JSON.stringify(p.expected, null, 2))}</pre></div>
          <div><p class="eyebrow">Extracted and verdict</p><pre>${mode === "mixed" ? esc(MIXED[p.n] ? why[MIXED[p.n]] : "Illustrative: matches the required record.") : "Not run. The real panel shows the extracted commitment records, the outcome check and model latency here."}</pre><p class="xsmall muted" style="margin-top:var(--s-2)">Model latency: not measured in the prototype.</p></div>
        </div>
      </li>`;
    }).join("");

    root.innerHTML = `<div class="page-head"><div class="page-head__titles"><p class="eyebrow">Adversarial cases from the product spec</p><h1 class="h1">Proof panel</h1></div>
        <div class="btn-row btn-row--inline"><button class="btn btn--primary" type="button" data-run ${mode === "running" ? 'disabled aria-busy="true"' : ""}>${mode === "running" ? "Running preview…" : `${icon("fast-forward")}Run preview`}</button><button class="btn" type="button" data-reset ${mode === "notrun" ? "disabled" : ""}>${icon("retry")}Clear</button></div></div>
      <div class="banner banner--sim" role="note">${icon("ring")}<p class="banner__title">Preview data: these are not test results</p><p class="banner__body">Nothing runs in this prototype. "Run preview" animates the states the real panel uses, then shows illustrative mixed results so every state can be reviewed. The deployed panel runs each case through the same code path as live email and shows the real outcome, including failures.</p></div>
      <div class="metrics" style="margin-block:var(--s-5)" aria-live="polite">
        <div class="metric"><span class="metric__value">${mode === "mixed" ? counts.pass : "—"}</span><span class="metric__label">Pass</span></div>
        <div class="metric"><span class="metric__value">${mode === "mixed" ? counts.fail : "—"}</span><span class="metric__label">Fail</span></div>
        <div class="metric"><span class="metric__value">${mode === "mixed" ? counts.error : "—"}</span><span class="metric__label">Error</span></div>
        <div class="metric"><span class="metric__value">${mode === "mixed" ? counts.pending : "—"}</span><span class="metric__label">Pending</span></div>
        <div class="metric"><span class="metric__value">${mode === "notrun" ? 14 : mode === "running" ? 14 - progress : 0}</span><span class="metric__label">${mode === "running" ? "Not finished" : "Not run"}</span></div>
      </div>
      ${mode === "mixed" ? `<p class="small" style="margin-bottom:var(--s-3)">${simTag("Illustrative")} Mixed results shown for design review only.</p>` : ""}
      <ol class="proof-list" role="list" aria-label="Proof cases">${rows}</ol>`;
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.matches("[data-open]")) { const n = Number(b.dataset.open); open.has(n) ? open.delete(n) : open.add(n); render(); root.querySelector(`[data-open="${n}"]`).focus(); }
    if (b.matches("[data-run]")) {
      mode = "running"; progress = 0; render();
      UI.announce("Preview run started. Nothing real is being tested.", { toast: false });
      timer = setInterval(() => { progress++; if (progress >= 14) { clearInterval(timer); mode = "mixed"; render(); UI.announce("Preview finished: illustrative mixed results shown."); root.querySelector("[data-run]").focus(); return; } render(); }, matchMedia("(prefers-reduced-motion: reduce)").matches ? 40 : 160);
    }
    if (b.matches("[data-reset]")) { clearInterval(timer); mode = "notrun"; render(); root.querySelector("[data-run]").focus(); }
  });
  render();
})();
