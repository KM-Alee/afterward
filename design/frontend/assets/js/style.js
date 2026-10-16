/* Style guide: swatches and contrast ratios computed from the live tokens, plus the icon grid. */
(function () {
  "use strict";
  const { esc, icon } = UI;
  UI.shell("style");
  const css = () => getComputedStyle(document.documentElement);
  const TOKENS = [
    ["--c-paper", "Paper", "Page ground"], ["--c-surface", "Surface", "Cards"], ["--c-sunken", "Sunken", "Wells, hover"], ["--c-line", "Line", "Dividers"], ["--c-line-strong", "Line strong", "Input borders"],
    ["--c-ink", "Ink", "Text, primary buttons"], ["--c-ink-2", "Ink 2", "Secondary text"], ["--c-ink-3", "Ink 3", "Meta text"], ["--c-dawn", "Dawn", "Brand disc, focus"], ["--c-dawn-ink", "Dawn ink", "Links"],
    ["--c-moss", "Moss", "Holding, confirmed"], ["--c-rust", "Rust", "Violated, unauthorised"], ["--c-ochre", "Ochre", "Review, waiting"], ["--c-dusk", "Dusk", "Requested, info"], ["--c-plum", "Plum", "Simulated"],
  ];
  const PAIRS = [
    ["--c-ink", "--c-paper", "Body text", 4.5], ["--c-ink-2", "--c-paper", "Secondary text", 4.5], ["--c-ink-3", "--c-paper", "Meta text", 4.5], ["--c-ink-3", "--c-sunken", "Meta on sunken", 4.5],
    ["--c-on-ink", "--c-ink", "Primary button", 4.5], ["--c-dawn-ink", "--c-paper", "Links", 4.5], ["--c-dawn", "--c-paper", "Focus ring, disc (non-text)", 3],
    ["--c-line-strong", "--c-surface", "Input border (non-text)", 3], ["--c-moss", "--c-moss-soft", "Holding chip", 4.5], ["--c-rust", "--c-rust-soft", "Violated chip", 4.5],
    ["--c-ochre", "--c-ochre-soft", "Review chip", 4.5], ["--c-dusk", "--c-dusk-soft", "Info chip", 4.5], ["--c-plum", "--c-plum-soft", "Simulated tag", 4.5], ["--c-ink", "--c-dawn-soft", "Current step", 4.5],
  ];
  function rgb(v) { const c = document.createElement("canvas").getContext("2d"); c.fillStyle = v.trim(); const h = c.fillStyle; if (h.startsWith("#")) return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); return h.match(/\d+/g).slice(0, 3).map(Number); }
  function lum(v) { return rgb(v).map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((a, c, i) => a + c * [0.2126, 0.7152, 0.0722][i], 0); }
  function ratio(a, b) { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
  function render() {
    const s = css(), v = (t) => s.getPropertyValue(t).trim();
    document.getElementById("swatches").innerHTML = TOKENS.map(([t, n, use]) => { const val = v(t), dark = lum(val) < 0.25; return `<div class="swatch"><div class="swatch__chip" style="background:${val};color:${dark ? "#fff" : "#1E2A2B"}">${esc(n)}</div><div class="swatch__meta"><code>${t}</code><span>${esc(val.toUpperCase())}</span><span class="muted">${esc(use)}</span></div></div>`; }).join("");
    document.querySelector("#contrast tbody").innerHTML = PAIRS.map(([f, b, use, min]) => { const r = ratio(v(f), v(b)); const pass = r >= min; const aaa = min === 4.5 && r >= 7; return `<tr><td><code>${f}</code></td><td><code>${b}</code></td><td><span style="background:${v(b)};color:${v(f)};padding:2px 8px;border-radius:4px;font-weight:700">Aa ●</span></td><td class="num">${r.toFixed(2)}:1</td><td>${esc(use)} (needs ${min}:1)</td><td>${pass ? `<span class="status status--holding">${icon("check")}${aaa ? "AAA" : "AA"}</span>` : `<span class="status status--violated">${icon("cross")}Fails</span>`}</td></tr>`; }).join("");
  }
  document.getElementById("space-scale").innerHTML = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `<div class="space-row"><span><code>--s-${n}</code></span><span class="space-bar" style="width:var(--s-${n})"></span><span class="muted">${getComputedStyle(document.documentElement).getPropertyValue(`--s-${n}`).trim()}</span></div>`).join("");
  const ICONS = "check cross question bang plus dash dot ring slash arrow-right arrow-left chevron-down chevron-right close clock mail send phone mic keyboard speaker pause stop moon hand retry doc photo building user users shield lock eye-off link info warning calendar fast-forward money quote chat waves flask palette desk sun contrast projector horizon".split(" ");
  document.getElementById("icon-grid").innerHTML = ICONS.map((n) => `<div class="icon-cell">${icon(n)}<span>${n}</span></div>`).join("");
  render();
  // Re-run when the theme changes (prototype bar toggle or OS setting).
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
})();
