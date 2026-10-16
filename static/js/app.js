/* Desk, call room and theme behaviour. Pages are server-rendered. */
(function () {
  "use strict";

  var root = document.documentElement;
  var themeKey = "afterward.theme";

  function applyTheme(theme) {
    if (!theme || theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }

  document.querySelectorAll("[data-theme-set]").forEach(function (button) {
    button.addEventListener("click", function () {
      var theme = button.getAttribute("data-theme-set");
      try { localStorage.setItem(themeKey, theme); } catch (err) { /* ignore */ }
      applyTheme(theme);
      document.querySelectorAll("[data-theme-set]").forEach(function (item) {
        item.setAttribute("aria-pressed", String(item === button));
      });
    });
  });

  var navToggle = document.querySelector(".nav__toggle");
  var nav = document.getElementById("site-nav");
  if (navToggle && nav) {
    navToggle.addEventListener("click", function () {
      var open = navToggle.getAttribute("aria-expanded") !== "true";
      navToggle.setAttribute("aria-expanded", String(open));
      nav.dataset.open = String(open);
    });
  }

  document.querySelectorAll("[data-open]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dialog = document.getElementById(button.getAttribute("data-open"));
      if (dialog && typeof dialog.showModal === "function") dialog.showModal();
    });
  });

  document.querySelectorAll("dialog [data-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      var dialog = button.closest("dialog");
      if (dialog) dialog.close();
    });
  });

  document.querySelectorAll("dialog").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", function () {
      var opener = document.querySelector('[data-open="' + dialog.id + '"]');
      if (opener) opener.focus();
    });
  });

  var projector = document.querySelector("[data-projector]");
  if (projector) {
    projector.addEventListener("click", function () {
      var on = root.classList.toggle("is-projector");
      projector.setAttribute("aria-pressed", String(on));
      try { localStorage.setItem("afterward.projector", on ? "on" : "off"); } catch (err) { /* ignore */ }
    });
  }

  document.querySelectorAll("[data-tab]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-tab");
      document.querySelectorAll("[data-tab]").forEach(function (item) {
        item.setAttribute("aria-selected", String(item === tab));
      });
      document.querySelectorAll("[data-panel]").forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-panel") !== name;
      });
    });
  });

  var stream = document.querySelector("[data-events]");
  if (stream && window.WebSocket) {
    var caseId = stream.getAttribute("data-events");
    var protocol = location.protocol === "https:" ? "wss" : "ws";
    var socket = new WebSocket(protocol + "://" + location.host + "/ws/cases/" + caseId);
    socket.addEventListener("message", function (event) {
      var data;
      try { data = JSON.parse(event.data); } catch (err) { return; }
      if (!data || data.kind === "stream.ready" || data.kind === "denied" || data.kind === "missing") return;
      if (stream.hasAttribute("data-reload") || stream.querySelector(".tl")) {
        window.setTimeout(function () {
          if (!document.querySelector("dialog[open]") && document.activeElement.tagName !== "INPUT") location.reload();
        }, 700);
      }
      var list = stream.querySelector(".tl");
      if (!list) return;
      var item = document.createElement("li");
      item.className = "t--system";
      var text = document.createElement("p");
      text.className = "tl__text";
      var summary = data.payload && data.payload.summary ? data.payload.summary : data.kind;
      text.textContent = summary;
      item.appendChild(text);
      list.prepend(item);
    });
  }

  var ptt = document.querySelector("[data-ptt]");
  var toggle = document.querySelector("[data-toggle-mode]");
  if (ptt) {
    var holding = false;
    function label() {
      var tap = toggle && toggle.checked;
      if (holding) ptt.lastChild.textContent = tap ? " Tap to finish" : " Release to send";
      else ptt.lastChild.textContent = tap ? " Tap to talk" : " Hold to talk";
    }
    ptt.addEventListener("pointerdown", function (event) {
      if (toggle && toggle.checked) return;
      event.preventDefault();
      holding = true;
      ptt.setAttribute("aria-pressed", "true");
      label();
    });
    window.addEventListener("pointerup", function () {
      if (!holding || (toggle && toggle.checked)) return;
      holding = false;
      ptt.setAttribute("aria-pressed", "false");
      label();
      if (typeof ptt.form.requestSubmit === "function") ptt.form.requestSubmit();
    });
    ptt.addEventListener("keydown", function (event) {
      if (event.key !== " " && event.key !== "Enter") return;
      if (event.repeat) { event.preventDefault(); return; }
      ptt.setAttribute("aria-pressed", "true");
      holding = true;
      label();
    });
    ptt.addEventListener("keyup", function (event) {
      if (event.key !== " " && event.key !== "Enter") return;
      holding = false;
      ptt.setAttribute("aria-pressed", "false");
      label();
    });
    if (toggle) toggle.addEventListener("change", label);
  }
})();
