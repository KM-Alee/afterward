/* Start page: passcode states (appearance only), the surfaces and a way into the story. */
(function () {
  "use strict";
  const { esc, icon } = UI;
  UI.shell("index");

  const DOORS = [
    ["family.html?as=sara", "users", "Family", "Sara and Amina's phone"],
    ["desk.html", "desk", "Case desk", "The whole case at a glance"],
    ["call.html", "phone", "Call room", "Talk to the AI agent"],
    ["provider.html", "building", "Provider console", "Reply as an organisation"],
    ["proofs.html", "flask", "Proofs", "The 14 tricky cases"],
    ["style.html", "palette", "Style guide", "Brand and components"],
  ];
  document.getElementById("doors").innerHTML = DOORS.map(([h, i, t, d]) => `<a class="door" href="${h}">${icon(i)}<span><b>${esc(t)}</b><small>${esc(d)}</small></span></a>`).join("");
  document.getElementById("start-story").addEventListener("click", () => { AW.reset([]); location.href = "family.html?as=sara"; });
  document.querySelector("[data-open-guide]").addEventListener("click", UI.openStory);

  /* Nothing is checked. "wrong" and "offline" show the error states. */
  const form = document.getElementById("access"), input = document.getElementById("passcode");
  const submit = document.getElementById("access-submit"), out = document.getElementById("pass-status");
  const say = (html, kind) => { out.innerHTML = html; out.style.color = kind === "error" ? "var(--c-rust)" : kind === "ok" ? "var(--c-moss)" : ""; };
  function check() {
    const v = input.value.trim().toLowerCase();
    input.removeAttribute("aria-invalid");
    if (!v) { input.setAttribute("aria-invalid", "true"); say("Enter the demo passcode. It's in the submission PDF.", "error"); input.focus(); return; }
    submit.setAttribute("aria-busy", "true"); submit.disabled = true; say("Checking…");
    setTimeout(() => {
      submit.removeAttribute("aria-busy"); submit.disabled = false;
      if (v === "wrong") { input.setAttribute("aria-invalid", "true"); say("That passcode didn't work. Check the submission PDF.", "error"); input.select(); return; }
      if (v === "offline") { say(`Can't reach Afterward. <button class="link-btn" type="button" id="retry">Try again</button>`, "error"); document.getElementById("retry").addEventListener("click", () => { input.value = "demo"; check(); }); document.getElementById("retry").focus(); return; }
      say(`${icon("check", "icon--sm")} You're in. Pick where to go below.`, "ok");
      document.querySelector(".door").focus();
    }, 700);
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); check(); });
})();
