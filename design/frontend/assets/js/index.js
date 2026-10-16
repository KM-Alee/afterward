/* Entry page: passcode form states (appearance only), surface navigation and the story list. */
(function () {
  "use strict";
  const { esc, icon } = UI;
  UI.shell("index");

  const SURFACES = [
    { href: "desk.html", icon: "desk", title: "Case desk", who: "Judges · projector", desc: "Requested vs provider says vs Afterward concludes, the four-dimension ledger, timeline and demo clock." },
    { href: "family.html?as=sara", icon: "users", title: "Family view", who: "Sara and Amina · phone", desc: "The same cards as chat: confirm, answer, approve. Never more than three choices." },
    { href: "call.html", icon: "phone", title: "Call room", who: "A judge as Northline", desc: "Talk to the AI agent. Offer or change terms and watch approval bind to them. Simulated." },
    { href: "provider.html", icon: "building", title: "Provider console", who: "A judge as any provider", desc: "Reply as Northline, City Power and others with prepared or free text. Simulated sends." },
    { href: "proofs.html", icon: "flask", title: "Proof panel", who: "Judges", desc: "The 14 adversarial cases with their inputs and required behaviour. Preview states only." },
    { href: "style.html", icon: "palette", title: "Style guide", who: "Agent D and the team", desc: "Identity, tokens, components and states for the real build." },
  ];
  document.getElementById("surfaces").innerHTML = SURFACES.map((s) => `<a class="surface" href="${s.href}"><span class="surface__icon">${icon(s.icon)}</span><span class="surface__title">${esc(s.title)}${icon("arrow-right", "icon--sm")}</span><span class="surface__who">${esc(s.who)}</span><span class="surface__desc">${esc(s.desc)}</span></a>`).join("");

  function renderSteps() {
    const s = AW.state, cur = AW.currentStep();
    document.getElementById("story-steps").innerHTML = AW.STEPS.map((x) => { const done = x.done(s), isCur = cur && cur.n === x.n; return `<li class="step ${done ? "is-done" : ""} ${isCur ? "is-current" : ""}"><span class="step__marker" aria-hidden="true">${done ? icon("check", "icon--sm") : x.n}</span><span class="step__title">${esc(x.title)}<span class="visually-hidden">${done ? " (done)" : isCur ? " (next)" : ""}</span></span><span class="step__where">${esc(x.where)}</span></li>`; }).join("");
  }
  renderSteps();
  AW.subscribe(renderSteps);
  document.getElementById("start-story").addEventListener("click", () => { AW.reset([]); location.href = "family.html?as=sara"; });
  document.querySelector("[data-open-guide]").addEventListener("click", UI.openStory);

  /* Passcode form: shows empty, loading, error, retry and success states. Nothing is checked. */
  const form = document.getElementById("access"), input = document.getElementById("passcode");
  const err = document.getElementById("pass-error"), retry = document.getElementById("access-retry");
  const submit = document.getElementById("access-submit"), statusEl = document.getElementById("access-status");
  let attempts = 0;
  function setError(msg) {
    err.hidden = !msg; err.innerHTML = msg ? `${icon("warning", "icon--sm")}<span>${esc(msg)}</span>` : "";
    input.setAttribute("aria-invalid", msg ? "true" : "false");
  }
  function check() {
    const v = input.value.trim().toLowerCase();
    retry.hidden = true; setError("");
    if (!v) { setError("Enter the demo passcode."); input.focus(); return; }
    attempts++;
    submit.setAttribute("aria-busy", "true"); submit.disabled = true; submit.textContent = "Checking…"; statusEl.textContent = "Checking the passcode…";
    setTimeout(() => {
      submit.removeAttribute("aria-busy"); submit.disabled = false; submit.textContent = "Enter"; statusEl.textContent = "";
      if (v === "wrong") { setError("That passcode didn't work. Check the submission PDF, or ask the team."); input.select(); input.focus(); return; }
      if (v === "offline") {
        retry.hidden = false;
        retry.innerHTML = `<div class="banner banner--error">${icon("warning")}<p class="banner__title">Couldn't reach Afterward</p><p class="banner__body">This is a simulated connection error. Your passcode wasn't sent anywhere. Attempt ${attempts}.</p><div class="banner__actions"><button class="btn btn--sm" type="button" id="retry-btn">${icon("retry")}Try the connection again</button></div></div>`;
        document.getElementById("retry-btn").addEventListener("click", () => { input.value = "demo"; check(); });
        document.getElementById("retry-btn").focus();
        return;
      }
      try { sessionStorage.setItem("afterward.access", "1"); } catch (e) { /* ignore */ }
      form.innerHTML = `<div><p class="eyebrow">Demo access</p><h2 class="h2">You're in</h2></div><div class="banner banner--success">${icon("check")}<p class="banner__title">Access granted (prototype)</p><p class="banner__body">Nothing was checked. In the real app this unlocks the desk and the proof panel.</p></div><div class="btn-row"><a class="btn btn--primary" href="desk.html">${icon("desk")}Open the case desk</a><button class="btn" type="button" id="sign-out">Show the form again</button></div>`;
      document.getElementById("sign-out").addEventListener("click", () => { try { sessionStorage.removeItem("afterward.access"); } catch (e) { /* ignore */ } location.reload(); });
      form.querySelector("a").focus();
      UI.announce("Access granted. Prototype only: nothing was checked.", { toast: false });
    }, 800);
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); check(); });
})();
