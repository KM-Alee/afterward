# Afterward design guide

Status: **prototype design system, awaiting user review.** Not approved until the lead records
approval in docs/FRONTEND-APPROVAL.md. The live visual reference is `style.html`; the CSS in
`assets/css/` is the implementation. This document explains the decisions and how Agent D
carries them into the FastAPI/Jinja2 app without redesigning them.

Companion documents: [UX.md](UX.md) (who, flows, states, responsive rules) and
[REVIEW.md](REVIEW.md) (how to review, what was tested).

---

## 1. Brand

### Concept: first light

The symbol is a **low half-disc resting on a horizon line**, with one whole arc and one arc
broken into three parts above it.

| Element | Meaning |
|---|---|
| Horizon line | The steady line Afterward keeps: the approved plan and record that every reply is checked against. In the lockup it is also the text baseline. |
| Half-disc (dawn) | The family's one voice note: said once, warm and low. It reads as first light rather than sunset: the time *after*. |
| Inner arc | The message carried outward. |
| Outer arc, three parts | It reaches many organisations, and each one is followed up separately. |

Tone: calm and plain, not cheerful. The dawn colour is used sparingly (the disc, focus rings,
the current story step, the active nav underline). Everything else is ink on linen.

### Logo files (`assets/brand/`)

All masters are hand-authored SVG. The wordmark is **Newsreader Medium converted to outlines**
(tracking −1%), so masters don't depend on installed fonts. PNGs are exports of the masters,
rendered with `rsvg-convert`. No generated raster artwork is used anywhere.

| Use | File |
|---|---|
| Primary lockup on linen or white | `afterward-lockup.svg` |
| Lockup on ink / dark UI | `afterward-lockup-dark.svg` |
| One-colour print, photos | `afterward-lockup-mono-black.svg`, `afterward-lockup-mono-white.svg` |
| Square spaces | `afterward-lockup-stacked.svg`, `afterward-lockup-stacked-dark.svg` |
| Wordmark alone | `afterward-wordmark.svg`, `afterward-wordmark-dark.svg` |
| Symbol alone (≥ 32 px) | `afterward-symbol.svg`, `-dark`, `-mono-black`, `-mono-white` |
| Compact mark (< 32 px, nav, avatars) | `afterward-mark-compact.svg`, `-dark`, `-mono-black`, `-mono-white` |
| Web UI lockup that follows the theme | `afterward-lockup-tokens.svg#lockup` (a `<symbol>` coloured by `--c-ink` / `--c-dawn`) |
| App icon | `afterward-app-icon.svg`, `afterward-app-icon-maskable.svg`, `png/app-icon-192.png`, `png/app-icon-512.png`, `png/app-icon-maskable-512.png` |
| Favicon | `favicon.svg`, `favicon.ico` (16/32/48), `png/favicon-16/32/48.png`, `png/apple-touch-icon-180.png`, `site.webmanifest` |
| Exports for slides/docs | `png/afterward-lockup-1200.png`, `png/afterward-lockup-dark-1200.png`, `png/afterward-symbol-512.png`, `png/afterward-symbol-dark-512.png` |

**Rules.** Clear space equals the disc's height on every side. Full symbol at 32 px and above,
compact mark below that. Minimum lockup width 96 px on screen. Don't recolour the disc as a
status, add rays, halos, hearts or doves, animate the header logo, or reset the wordmark in
another face or in capitals. Verified at 16 px on light and dark tab bars (style guide
"Compact mark and icons at real size").

### Voice

- Warm, plain, brief. One idea per sentence. Names, not roles: "Yusuf", never "the deceased".
- Roles are **stated**: "handling the estate (as you've told me)". Never "executor" or "verified".
- Separate **said**, **promised** and **evidenced**: "Refund issued. Waiting for it to show on a statement."
- No exclamation marks, emoji or celebration of completion.
- Everything simulated says so at the point of use, with the hatched `sim-tag`.
- Honest-claims rules from AFTERWARD.md §11 apply to every string: no complete-discovery
  promise, a photo is a photo, the call room is not a phone call, timings are measured or absent.

---

## 2. Colour

Tokens live in `assets/css/tokens.css`. Dark values apply through `prefers-color-scheme`
unless `<html data-theme="light|dark">` overrides. Ratios below are WCAG 2.2 and are
recomputed live on `style.html` from whichever theme is active.

| Token | Light | Dark | Role |
|---|---|---|---|
| `--c-paper` | `#F5F0E8` | `#111716` | Page ground (linen / night) |
| `--c-surface` | `#FFFCF7` | `#19211F` | Cards |
| `--c-sunken` | `#ECE5D9` | `#0C1110` | Wells, hover, disabled |
| `--c-line` | `#DCD2C3` | `#2E3A38` | Dividers (decorative) |
| `--c-line-strong` | `#80735F` | `#71807C` | Input borders: 4.5 / 4.0:1 on surface (≥ 3:1 required) |
| `--c-ink` | `#1E2A2B` | `#EFE9DE` | Text, primary buttons: 13.0 / 15.0:1 on paper |
| `--c-ink-2` | `#434E4C` | `#C6BFB2` | Secondary text: 7.6 / 9.9:1 |
| `--c-ink-3` | `#5B6461` | `#A49E93` | Meta text: 5.4 / 6.8:1 (4.9 on sunken) |
| `--c-dawn` | `#C8643B` | `#E9875C` | Brand disc, focus ring: 3.5 / 7.0:1 (non-text, ≥ 3:1) |
| `--c-dawn-ink` | `#94401F` | `#F2A47F` | Links, dawn text: 6.2 / 9.0:1 |
| `--c-moss` / `-soft` | `#2C6644` / `#DCEADF` | `#8FCBA3` / `#1B3024` | Holding, matched, confirmed, received: 5.5 / 7.5:1 on soft |
| `--c-rust` / `-soft` | `#A1372A` / `#F7DCD5` | `#F3907E` / `#3B1E19` | Violated, unauthorised, failed: 5.2 / 6.6:1 |
| `--c-ochre` / `-soft` | `#7E570A` / `#F4E7C6` | `#E6BE63` / `#372C12` | Needs review, not stated, waiting, uncertain: 5.3 / 7.8:1 |
| `--c-dusk` / `-soft` | `#315781` / `#DCE6F1` | `#9CBCE3` / `#1A2A3C` | Requested, acknowledged, information: 5.9 / 7.4:1 |
| `--c-plum` / `-soft` | `#644878` / `#ECE3F1` | `#CDB0E0` / `#2C2236` | Simulated, mock, prototype-only: 6.1 / 7.8:1 |

**Colour is never the only signal.** Every status chip pairs a hue with an icon shape and a
word; evidence labels also differ by border style (solid, double, dashed); quote highlights
carry an underline as well as a tint. The `--hatch` diagonal pattern is reserved for
simulated things.

---

## 3. Typography

| Family | Use | Files |
|---|---|---|
| **Newsreader** 400, 400 italic, 500, 600 | Headings, card titles, verdicts, and *anything quoted* (voice notes, providers' words). Serif = "someone else's words". | `assets/fonts/newsreader-latin-*.woff2` |
| **Atkinson Hyperlegible Next** 400, 400 italic, 600, 700 | All interface text. Chosen for older readers (Amina) and projectors. Its zero is slashed by design, which keeps references unambiguous. | `assets/fonts/atkinson-hyperlegible-next-latin-*.woff2` |
| **Atkinson Hyperlegible Mono** 400, 600 | References, hashes, addresses. | `assets/fonts/atkinson-hyperlegible-mono-latin-*.woff2` |

Scale (rem at 16 px root; projector mode raises the root to 20 px): 13 · 15 · **17 body** · 20 ·
24 · 32 · 44 · 56. Classes: `.display`, `.h1`, `.h2`, `.h3`, `.h4`, `.lede`, `.eyebrow`, `.small`,
`.xsmall`, `.muted`, `.secondary`, `.ref`, `.serif`. Body line height 1.55, measure 38 rem.
Large dates (case clock, "Died 3 March 2026") use Newsreader so the slashed zero stays in references.

---

## 4. Space, grid and breakpoints

- Spacing scale `--s-1 … --s-8` = 4, 8, 12, 16, 24, 32, 48, 64 px. Gutter 16 px, 24 px from 1024 px.
- Radius: 6 (chips, small buttons), 10 (buttons, inputs, banners), 16 (cards). Touch target ≥ 44 px.
- Containers: `.wrap` 78 rem, `.wrap--wide` 112 rem (desk), `.wrap--narrow` 46 rem.
- Breakpoints (viewport): < 480 phone · 480–1023 single column · ≥ 1024 two columns · ≥ 1600 desk three columns.
- **Container queries** for components that live in columns of varying width:
  `.ledger-wrap` turns ledger rows into cards below 880 px; `.compare-wrap` uses three
  columns from 760 px. This is what keeps projector mode (20 px root) from overflowing.
- Every page grid declares `grid-template-columns: minmax(0, 1fr)` as its base. Implicit
  `auto` tracks grow to the widest table or chip and overflow; don't remove these.

---

## 5. Components (class contract)

All components are plain HTML + the classes below. Markup examples are on `style.html` and
in the page scripts' template strings (`assets/js/*.js`).

| Component | Classes | Notes |
|---|---|---|
| Header + nav | `.site-header`, `.brand`, `.brand__lockup`, `.nav`, `.nav__toggle` | Current page: `aria-current="page"` (dawn underline). Under 768 px links fold behind "Menu". |
| Buttons | `.btn`, `--primary`, `--quiet`, `--danger`, `--sim`, `--sm`, `--lg`, `--block`; `.btn-row`, `--stack`, `--inline` | Loading: `aria-busy="true"` + disabled. Disabled is a sunken fill, not opacity. |
| Decision options | `.btn-row--stack.decision-btns` + `<span class="option-desc">` | **Max three per card.** Consequence in the description. Nothing pre-selected. |
| Fields | `.field`, `.label`, `.input`, `.textarea`, `.select`, `.hint`, `.error-text` | Error: `aria-invalid="true"` + `aria-describedby` to the error text. |
| Choice list | `.choice-list`, `.choice`, `.choice__title`, `.choice__meta` | Radio cards; disabled options state why in `.choice__meta`. |
| Segmented | `.segmented > button[aria-pressed]` | Autopilot, control, persona, theme. |
| Cards | `.card`, `--flat`, `--sunken`, `--focus`, `--sim`; `.panel`, `.section-title`, `.horizon` | `.horizon` is the logo baseline used as a divider. |
| Family card | `.fcard`, `--active`, `--void`; `__meta`, `__from`, `__title`, `__body`, `__actions`, `__outcome`, `__note`; `.speech` | Same words and buttons as the chat card. |
| Approval card | `.approval`, `__head`, `__body`, `__foot`, `__binding`, `--approved`, `--void`; `.deflist` | Must show To (exact address + "from profile"), Account, Request, Conditions, Documents (with form), Consequence, If not met, plan version + hash. |
| Status chip | `.status--holding / violated / unauthorised / unknown / review / waiting / uncertain / info / progress / neutral / sim / void` | Icon map in `AW.ICON` (check, cross, plus, question, bang, clock, dot, arrow-right, dash, ring, slash). |
| Evidence label | `.ev--writing / family / statement / spoken / unverified`, `.sim-tag` | AFTERWARD.md F17 labels. |
| Banner | `.banner`, `--interrupted`, `--error`, `--uncertain`, `--hold`, `--warning`, `--success`, `--sim` | Title says what; body says what is affected and what happens next. Use `role="alert"` only for new blocking states. |
| Evidence quote | `.quote`, `.quote__text`, `mark.hl-holding / hl-violated / hl-review`, `.quote__source` | Never truncated in its primary place. Shows "Quote found in the message" only when verified. |
| Comparison | `.compare-wrap > .compare > .compare__col`, `.verdict--notdone / open / resolved`, `.checks` | Requested → provider says → Afterward concludes. |
| Ledger | `.ledger-wrap > table.ledger`, `.dim-label`, `.next`, `tr.is-focus` | Four dimensions + conditions; becomes cards in narrow containers. |
| Timeline | `ol.timeline > li.t--provider / family / alert / good / sim`, `__time`, `__text`, `__meta` | Newest first, each with evidence label where relevant. |
| Coverage | `.coverage` | Searched / not searched / where else. No "complete" button, ever. |
| Plan diff | `.diff`, `__row--old / --new`, `__v` | v1 struck through, v2 on dawn-soft. |
| Clock | `.clock`, `__label`, `__now` | Demo cases only; hatched to show it's simulated time. |
| Loading / empty | `.skeleton > .skeleton__line`, `.empty`, `__art`, `__title` | Skeletons carry a `role="status"` label. |
| Dialog, toast | `dialog.dialog`, `.toasts > .toast` | Native `<dialog>` for focus handling. Toasts are `aria-hidden`; the live region carries the message. |
| Call room | `.disclosure`, `.stage`, `.agent-orb[data-state]`, `.ptt`, `.typed`, `.transcript > .turn--agent / rep / system`, `.turn--discarded / queued / suspended`, `.terms-table`, `.latency` | Orb states: idle, listening, thinking, speaking, waiting_family, acceptance_queued. |

## 6. Interaction states

| State | Treatment |
|---|---|
| Focus | `box-shadow: var(--focus-ring)` (2 px paper gap + 3 px dawn) on every focusable element; `outline` in forced-colours mode. Never removed. |
| Hover | Fill shifts one step (`--c-sunken`); primary buttons mix 14% dawn into ink. |
| Disabled | Sunken fill, ink-3 text, `cursor: not-allowed`; the reason appears next to it. |
| Loading | Skeleton for regions; `aria-busy` + spinner (dotted ring under reduced motion) for buttons. |
| Error | Rust banner or `.error-text`, what failed, what is safe, retry with what it will do. No raw exception text. |
| Success | Moss, only with the evidence label that supports it. |
| Stale | Card goes `--void`, title struck through, a warning banner "This changed. Here's why." with the time; buttons disabled. |
| Uncertain / interrupted | Ochre / rust banners: distinct states, not errors. |

## 7. Iconography and motion

- One original stroke set in `assets/icons/sprite.svg`: 20 px grid, 1.75 stroke, round caps and joins
  to echo the logo. Use `<svg class="icon" aria-hidden="true"><use href=".../sprite.svg#i-name"/></svg>`.
  Meaning always comes from adjacent text.
- Motion: 120 ms (hover), 220 ms (state), 420 ms (content settles with a 6 px rise). No bounce.
  The only continuous motion is the call room orb (pulse while speaking, dash while reviewing)
  and loading shimmer. `prefers-reduced-motion: reduce` sets all durations to zero; the orb
  holds still and its state is carried by the text label.

## 8. Assets and licences

| Asset | Licence |
|---|---|
| Logo masters, exports, icon sprite | Original work for Afterward, created on this branch. |
| Newsreader | © The Newsreader Project Authors (Production Type). SIL Open Font License 1.1, `assets/fonts/OFL-Newsreader.txt`. Latin subset via Fontsource 5.3.0. |
| Atkinson Hyperlegible Next / Mono | © The Atkinson Hyperlegible Next / Mono Project Authors (originally commissioned by Braille Institute). SIL OFL 1.1, `assets/fonts/OFL-AtkinsonHyperlegible*.txt`. Latin subset via Fontsource 5.3.0. |
| Wordmark outlines | Newsreader Medium glyphs as paths; the OFL permits this for logos. |

Add both fonts to the README credits. No remote fonts, scripts or images are loaded.

---

## 9. Implementation guide for Agent D

D implements this design in its own paths (`app/web/`, `app/call/`, `static/`). The prototype
folder stays as the reference; D doesn't edit `design/frontend/`. Anything that must live in a
shared path goes through the lead.

### 9.1 Copy, don't redraw

| From `design/frontend/` | To | Change |
|---|---|---|
| `assets/css/tokens.css`, `base.css`, `components.css` | `static/css/` | None. Keep class names. |
| `assets/css/pages.css` | `static/css/pages.css` | Delete `.protobar*`, `.shortcut`, Story-guide `.step` usage if unused. |
| `assets/fonts/*` incl. OFL texts | `static/fonts/` | None. Fix `url()` paths if the folder depth changes. |
| `assets/icons/sprite.svg`, `assets/brand/*`, `favicon.*`, `site.webmanifest` | `static/` | Update icon `href`s to `/static/...`. |
| Template strings in `assets/js/desk.js`, `family.js`, `call.js`, `provider.js`, `proofs.js`, `index.js` | Jinja2 templates + partials | Same markup, rendered on the server. |

Suggested templates: `base.html` (head, skip link, header, live region), partials for
`_status.html` (chip), `_ev.html`, `_approval_card.html`, `_decision_card.html`, `_quote.html`,
`_compare.html`, `_ledger_row.html`, `_timeline_item.html`, `_banner.html`; pages `desk.html`,
`family.html`, `call.html`, `provider.html`, `proofs.html`, `index.html`.

### 9.2 Remove prototype-only pieces

- The hatched **prototype bar**, the **Story guide**, the call room's **"Prototype shortcut: Sara's
  phone"** panel, the desk's **"Prototype scenarios"** box, the provider console's "make the next
  send fail" checkbox and the passcode hint about `wrong` / `offline`.
- `fixtures/case.js` and `assets/js/store.js` (the replayed action log). Server state replaces them.
- Keep the **demo case clock** (demo cases only, still hatched and labelled) and the
  **"Simulated provider call"** labels: those are honest in production too.
- Replace "Simulated send" labels with real action status (`pending / sent / uncertain /
  reconciled / failed`). Replace simulated latency with measured values, or show nothing.

### 9.3 Map mock state to the real model (AFTERWARD-TECH T4)

| Prototype | Real source |
|---|---|
| `AW.accounts()` → `service / money / docs / next / conditions` | `accounts.status_service / status_money / status_docs / next_step` + latest `outcome_checks.results` |
| `d.bucket` and `AW.summary()` | The engine's "did you finish everything?" generator (A); copy wording from here |
| `AW.comparison()` | Approved `plans` row + latest `commitments` (verified quotes) + `outcome_checks.verdict` |
| `s.cards` per person | `decisions` and `approvals` rows for that member (≤ 3 options) |
| `s.events` | `events` table (timeline), with an evidence label per event |
| `s.call.terms`, `queued`, `turns` | Call room terms hash, approval binding, transcript (T9) |
| `storage` event cross-tab sync | WebSocket `EventBus` fan-out; re-render the affected partials |
| `fmtTime(s.now)` | `Clock.case_now(case)` |

### 9.4 Behaviour that must survive the port

1. At most three choices per decision card, with consequences visible before choosing.
2. Approval cards show the exact recipient address and its source, documents **with their form**,
   consequence, fallback and the plan version/hash they're bound to.
3. A stale approval is shown as void with its reason and time, never silently replaced (409 → stale card).
4. Desk reading order: banners → Now (requested / provider says / concludes) → ledger → coverage →
   "did you finish everything?"; spine and timeline alongside on wide screens.
5. No "complete" control on coverage. Evidence labels on every success.
6. Call room: the disclosure strip is permanent; the orb state always has a text label; talk works
   by hold *and* by tap-toggle, with Space/Enter; typed fallback is always present.
7. Accessibility checks to re-run: axe-core (wcag2a/aa, 21a/aa, 22aa) clean in both themes;
   every tab stop shows the focus ring; no horizontal overflow at 320, 390, 768, 1024, 1280 (projector) and 1440 px.

### 9.5 Material changes need the user

Changes to the flows, the card contents, the three-option rule, colours, type, the logo or the
desk composition are material UX changes: propose them to the user instead of making them.
