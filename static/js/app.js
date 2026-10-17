/* Desk, call room and theme behaviour. Pages are server-rendered. */
(function () {
  "use strict";

  var root = document.documentElement;
  var themeKey = "afterward.theme";
  var reduceMotion = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  function applyTheme(theme) {
    if (!theme || theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }

  (function markTheme() {
    var current = "auto";
    try { current = localStorage.getItem(themeKey) || "auto"; } catch (err) { /* ignore */ }
    document.querySelectorAll("[data-theme-set]").forEach(function (item) {
      item.setAttribute("aria-pressed", String(item.getAttribute("data-theme-set") === current));
    });
  })();

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

  // Dialogs and drawers close with a short exit animation.
  function closeDialog(dialog) {
    if (!dialog || !dialog.open) return;
    if (reduceMotion) { dialog.close(); return; }
    dialog.classList.add("is-closing");
    window.setTimeout(function () {
      dialog.classList.remove("is-closing");
      if (dialog.open) dialog.close();
    }, 190);
  }

  document.querySelectorAll("dialog [data-close]").forEach(function (button) {
    button.addEventListener("click", function () { closeDialog(button.closest("dialog")); });
  });

  document.querySelectorAll("dialog").forEach(function (dialog) {
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) closeDialog(dialog);
    });
    dialog.addEventListener("cancel", function (event) {
      if (reduceMotion) return;
      event.preventDefault();
      closeDialog(dialog);
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

  document.querySelectorAll("#talk-form, .typed__row").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var button = form.querySelector("button[type=submit]");
      // The live call sends over its socket and stays on the page; only a real post waits.
      window.setTimeout(function () {
        if (!e.defaultPrevented && button) {
          button.disabled = true;
          button.textContent = "Sending…";
        }
      }, 0);
    });
  });

  // ---- Motion and polish ----

  // Scroll reveal. Targets are visible unless scripts have marked <html class="js">.
  var revealTargets = document.querySelectorAll("[data-reveal]");
  document.querySelectorAll("[data-stagger]").forEach(function (group) {
    var index = 0;
    group.querySelectorAll(":scope > [data-reveal]").forEach(function (item) { item.style.setProperty("--i", String(index++)); });
  });
  if (revealTargets.length) {
    if (reduceMotion || !("IntersectionObserver" in window)) {
      revealTargets.forEach(function (item) { item.classList.add("is-in"); });
    } else {
      var seen = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) { entry.target.classList.add("is-in"); seen.unobserve(entry.target); }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
      revealTargets.forEach(function (item) { seen.observe(item); });
    }
  }

  // Number count-up. The final value is already in the markup, so no script means no loss.
  function countUp(node) {
    var target = parseInt(node.getAttribute("data-count"), 10);
    if (isNaN(target) || target < 1 || reduceMotion) return;
    var start = null;
    var duration = 900;
    node.textContent = "0";
    function frame(now) {
      if (start === null) start = now;
      var t = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      node.textContent = String(Math.round(target * eased));
      if (t < 1) window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  }
  document.querySelectorAll("[data-count]").forEach(countUp);

  // Account filter on the desk board.
  var filterButtons = document.querySelectorAll("[data-filter]");
  filterButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var wanted = button.getAttribute("data-filter");
      filterButtons.forEach(function (item) { item.setAttribute("aria-pressed", String(item === button)); });
      var shown = 0;
      document.querySelectorAll(".tile[data-group]").forEach(function (tile) {
        var match = wanted === "all" || tile.getAttribute("data-group") === wanted;
        tile.classList.toggle("is-hidden", !match);
        if (match) shown++;
      });
      var empty = document.querySelector(".filters__empty");
      if (empty) empty.hidden = shown !== 0;
    });
  });

  // Forms that take a moment: busy button, shimmer over the board, skeleton rows for lists.
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      window.setTimeout(function () {
        if (event.defaultPrevented) return;
        var submitter = event.submitter || form.querySelector("button[type=submit]");
        var shell = document.getElementById("desk-root");
        if (shell) shell.classList.add("is-loading");
        var skeletonSelector = form.getAttribute("data-skeleton");
        var skeletonTarget = skeletonSelector ? document.querySelector(skeletonSelector) : null;
        if (skeletonTarget) {
          var rows = document.createElement("div");
          rows.className = "skeleton skeleton-rows";
          rows.setAttribute("aria-hidden", "true");
          for (var n = 0; n < 6; n++) { var line = document.createElement("div"); line.className = "skeleton__line"; rows.appendChild(line); }
          skeletonTarget.replaceChildren(rows);
        }
        if (submitter && !submitter.disabled) {
          submitter.setAttribute("aria-busy", "true");
          // Disabling right away would drop the button's value from the post, so wait a tick.
          window.setTimeout(function () { submitter.disabled = true; }, 30);
        }
      }, 0);
    });
  });

  // Case switcher closes on outside click and Escape.
  document.addEventListener("click", function (event) {
    document.querySelectorAll("details[data-switcher][open]").forEach(function (menu) {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details[data-switcher][open]").forEach(function (menu) { menu.removeAttribute("open"); });
  });

  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    document.querySelectorAll(".is-loading").forEach(function (node) { node.classList.remove("is-loading"); });
    document.querySelectorAll("[aria-busy=true]").forEach(function (node) { node.removeAttribute("aria-busy"); node.disabled = false; });
  });
})();
