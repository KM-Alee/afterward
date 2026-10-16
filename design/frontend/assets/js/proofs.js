/* Proof panel: the 14 adversarial cases (AFTERWARD.md §10.4). The prototype runs nothing; it
   shows the states the real panel needs and says so. One screen; details open in a drawer. */
(function () {
  "use strict";
  const F = window.AW_FIXTURES, { esc, icon, chip, simTag } = UI;
  UI.shell("proofs", { context: "Proofs" });
  const root = document.getElementById("root");

  const MIXED = { 8: "fail", 11: "error", 13: "pending", 14: "pending" };
  let mode = "notrun", progress = 0, timer = null, current = null;
  const ST = { notrun: ["neutral", "Not run"], running: ["progress", "Running"], queued: ["neutral", "Waiting"], pass: ["holding", "Pass"], fail: ["violated", "Fail"], error: ["review", "Error"], pending: ["waiting", "Pending"] };
  const NOTE = { fail: "Example failure: a mismatched Reply-To was let through. A real failure shows like this and gets fixed, not hidden.", error: "Example error: the test harness didn't start, so the case couldn't run. Errors never count as passes.", pending: "Still waiting for the model." };
  const stateOf = (n) => mode === "notrun" ? "notrun" : mode === "running" ? (n === progress + 1 ? "running" : "queued") : MIXED[n] || "pass";

  const detail = UI.drawer({ id: "proof", title: () => current ? `Case ${current.n}` : "Case", render: () => {
    if (!current) return "";
    const st = stateOf(current.n), [k, l] = ST[st];
    return `<p class="lede" style="font-size:var(--fs-md)">${esc(current.input)}</p>
      <div class="drawer__group"><p class="drawer__label">Must</p><p>${esc(current.required)}</p></div>
      <div class="drawer__group"><p class="drawer__label">Expected record</p><pre class="fixture">${esc(JSON.stringify(current.expected, null, 2))}</pre></div>
      <div class="drawer__group"><p class="drawer__label">Result</p><p>${chip(k, l)} ${mode === "mixed" ? simTag("Example") : ""}</p><p class="small muted">${mode === "mixed" ? esc(NOTE[st] || "Example: matches the expected record.") : "Not run. The real panel shows what was extracted, the verdict and how long the model took."}</p></div>`;
  } });

  function render() {
    const counts = { pass: 0, fail: 0, error: 0, pending: 0 };
    if (mode === "mixed") F.proofs.forEach((p) => { counts[stateOf(p.n)]++; });
    root.innerHTML = `
      <div class="page-row">
        <div><h1 class="page-title">Proofs</h1><p class="page-sub">14 tricky cases the system must handle. ${mode === "mixed" ? "Showing example results." : "Nothing has been run here."}</p></div>
        <div class="toolbar">
          ${mode === "mixed" ? `<span class="metrics-inline"><span><b>${counts.pass}</b>pass</span><span><b>${counts.fail}</b>fail</span><span><b>${counts.error}</b>error</span><span><b>${counts.pending}</b>pending</span></span>${simTag("Examples, not results")}` : simTag("Preview only")}
          <button class="btn btn--primary" type="button" data-run ${mode === "running" ? 'disabled aria-busy="true"' : ""}>${mode === "running" ? "Running…" : `${icon("fast-forward")}Run preview`}</button>
          <button class="btn" type="button" data-reset ${mode === "notrun" ? "disabled" : ""}>Clear</button>
        </div>
      </div>
      <section class="panel-box" style="flex:1" aria-label="Cases">
        <div class="panel-box__body scroll"><ol class="proof-list" role="list">${F.proofs.map((p) => { const st = stateOf(p.n), [k, l] = ST[st]; return `<li><button class="proof__row" type="button" data-case="${p.n}"><span class="proof__n" aria-hidden="true">${p.n}</span><span><span class="proof__input">${esc(p.input)}</span><span class="proof__req" style="display:block">${esc(p.required)}</span></span>${st === "running" ? `<span class="status status--progress" aria-busy="true">${icon("clock")}Running</span>` : chip(k, l)}</button></li>`; }).join("")}</ol></div>
      </section>`;
    detail.refresh();
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.case) { current = F.proofs.find((p) => String(p.n) === b.dataset.case); detail.open(); }
    if (b.matches("[data-run]")) {
      mode = "running"; progress = 0; render();
      timer = setInterval(() => { progress++; if (progress >= 14) { clearInterval(timer); mode = "mixed"; render(); UI.announce("Preview finished. These are example results."); root.querySelector("[data-run]").focus(); return; } render(); }, matchMedia("(prefers-reduced-motion: reduce)").matches ? 40 : 150);
    }
    if (b.matches("[data-reset]")) { clearInterval(timer); mode = "notrun"; render(); root.querySelector("[data-run]").focus(); }
  });
  render();
})();
