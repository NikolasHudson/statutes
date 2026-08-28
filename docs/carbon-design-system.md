# Carbon Design System — local reference for Hudson

Distilled from IBM Carbon v11 (carbondesignsystem.com) for use across the
marketing site and app mockups. This is the single local source of truth so we
don't re-derive tokens from web search each time. Existing implementations:

- `marketing-frontend/components/marketing/carbon.tsx` — marketing primitives
  (CarbonPage, PageHero, SectionHead, SolidLink, HairlineLink, Frame, footer)
- `chat-frontend/app/browse-carbon-mockup/page.tsx` — first app-shell mockup
- `chat-frontend/app/app-carbon-mockup/` — full app mockup suite (shared
  shell in `carbon.tsx`)

We do NOT install `@carbon/react`; we hand-roll the look with Tailwind +
these tokens, which keeps mockups self-contained and dependency-free.

## Core principles

- **Everything square.** No border radii anywhere — tiles, buttons, inputs,
  tags (Carbon tags are the one rounded element upstream; we keep ours square
  for a sharper, more "enterprise" read).
- **Hairline rules, not shadows.** Structure comes from 1px borders and layer
  color shifts, never drop shadows.
- **Productive type by default.** Small, dense, information-first. Expressive
  (light-weight, large) type only for page/section headings.
- **The grid is the aesthetic.** Full-bleed rows divided by hairlines; content
  aligned to a strict column grid; generous negative space at section tops.
- **One accent.** Blue 60 carries every action. Status colors appear only as
  status (support tokens below).

## Type

Font: **IBM Plex Sans** (300 light, 400 regular, 600 semibold) +
**IBM Plex Mono** (400) for eyebrows, spec labels, counts, code, citations.

| Role | Spec |
|---|---|
| Display / page H1 | Plex Sans **300**, 2.5–3.5rem, leading ~1.1 |
| Section H2 | Plex Sans **300**, 1.75–2.75rem |
| Card / row heading | Plex Sans **600**, 14px (`text-sm font-semibold`) |
| Body | Plex Sans 400, 14–15px, `leading-relaxed` |
| Helper / caption | 12–13px, `--cds-helper` color |
| Eyebrow / spec label | Plex Mono 400, 11px, uppercase, `tracking-[0.18em]`–`[0.22em]` |
| Numbers/counts | mono or `tabular-nums` |

Eyebrow pattern (opens every page/section): mono 11px uppercase label,
optionally numbered (`01 — Label`), above a light-weight heading.

## Color tokens (Carbon v11)

Applied as CSS custom properties on the page wrapper so one markup tree
serves both themes (see THEMES in the mockup files).

| Token (our var) | white theme | g100 theme |
|---|---|---|
| `--cds-bg` (background) | `#ffffff` | `#161616` |
| `--cds-layer` (layer-01: tiles, fields) | `#f4f4f4` | `#262626` |
| `--cds-layer-hover` | `#e8e8e8` | `#333333` |
| `--cds-layer-selected` | `#e0e0e0` | `#393939` |
| `--cds-field` (input bg) | `#f4f4f4` | `#262626` |
| `--cds-border` (border-subtle) | `#e0e0e0` | `#393939` |
| `--cds-border-strong` (input bottom rule) | `#8d8d8d` | `#6f6f6f` |
| `--cds-text` (text-primary) | `#161616` | `#f4f4f4` |
| `--cds-text-2` (text-secondary) | `#525252` | `#c6c6c6` |
| `--cds-helper` (text-helper) | `#6f6f6f` | `#8d8d8d` |
| `--cds-placeholder` | `#a8a8a8` | `#6f6f6f` |
| `--cds-link` | Blue 60 `#0f62fe` | Blue 40 `#78a9ff` |

App side nav (theme-independent — Carbon Blue 90 chrome in both themes,
see SIDEBAR_PLAN.md; set alongside the theme tokens in `NAV_TOKENS`):

| Token (our var) | Hex | Usage |
|---|---|---|
| `--cds-nav-bg` (Blue 90) | `#001d6c` | rail / flyout / docked nav background |
| `--cds-nav-border`, `-hover`, `-selected` (Blue 80) | `#002d9c` | rules, hover + active item background |
| `--cds-nav-text` (Blue 20) | `#d0e2ff` | item text |
| `--cds-nav-text-active` | `#ffffff` | active item, wordmark, user name |
| `--cds-nav-bar` (Blue 40) | `#78a9ff` | active item's 3px left bar; avatar background |
| `--cds-nav-helper` (Blue 30) | `#a6c8ff` | group eyebrows, helper text, "Corpus" in the wordmark |
| `--cds-nav-avatar-text` (Blue 100) | `#001141` | initials on the avatar |

Beta tag and the warning triangle keep `#f1c21b` on the navy.

Action palette (theme-independent):

| Role | Hex |
|---|---|
| Primary action (Blue 60) | `#0f62fe` |
| Primary hover | `#0353e9` |
| Primary active (Blue 80) | `#002d9c` |
| Focus outline | `#0f62fe` (2px, `-outline-offset-2`) |

Support / status (pair each with its icon, never color alone):

| Status | On light | On dark | Usage |
|---|---|---|---|
| Error / danger | Red 60 `#da1e28` | Red 50 `#fa4d56` | destructive buttons, negative treatment (overruled) |
| Success | Green 60 `#24a148` | Green 40 `#42be65` | verified citations, good-law |
| Warning | Yellow 30 `#f1c21b` (black text) | same | caution treatment (distinguished, criticized) |
| Info | Blue 70 `#0043ce` | Blue 50 `#4589ff` | informational banners |

Grays for the dark band (header/footer, both themes): bg `#161616`,
hairline `#393939`, secondary text `#c6c6c6`/`#a8a8a8`, muted `#6f6f6f`,
icon-hover bg `#353535`.

## Spacing

Carbon spacing scale (px): 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96.
In Tailwind: 0.5, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24. Section padding:
`py-16`–`py-24` marketing, `py-10`–`py-14` app. Gutters `px-5 sm:px-8`.

## Components (our hand-rolled specs)

**UI shell header** — 48px (`h-12`), always g100-dark (`#161616`) in both
themes. Left: 48px hamburger button → product name (`HUDSON` semibold +
muted suffix). Right: 48px icon buttons (`hover:bg-[#353535]`), then a
48px Blue-60 avatar square. Hairline bottom border `#393939`.

**Side nav** — 256px (`w-64`), page bg, right hairline. Group labels are
mono eyebrows. Items: 3px left accent border (Blue 60 + `layer-selected` bg
when active, transparent otherwise), icon 16px stroke-1.5, 14px label,
optional 12px detail line.

**Buttons** — 48px tall (`h-12`; 40px `h-10` for in-form), square, 16px
side padding. Primary: Blue 60 → hover `#0353e9` → active `#002d9c`, label
left + trailing arrow with a wide gap (`justify-between gap-10`).
Secondary (tertiary in Carbon terms): 1px outline in Blue 60 (light) or
white (dark), fills on hover. Ghost: link-color text, layer-hover bg on
hover. Danger: Red 60 fill.

**Inputs** — "fluid" style: square, `--cds-field` bg, no side borders,
1px `--cds-border-strong` bottom border; 2px Blue-60 outline (inset) on
focus. Height 40–48px. Labels 12px `--cds-text-2` above; helper 12px below.

**Tabs** — line tabs: 2px bottom border on active (Blue 60) + semibold;
inactive gets `border-strong` on hover. No pills.

**Tags** — square, 24px, 12px text, layer bg + hairline; status tags use the
support colors at low-alpha bg with the strong color as text/icon.

**Tiles / rows** — `--cds-layer` bg, hairline dividers (`divide-y`), whole
row clickable, hover to `layer-hover`, selected `layer-selected`. Trailing
mono metadata + Blue arrow that nudges right on hover (`translate-x-0.5`).

**Structured list / key-value rail** — bordered panel, mono uppercase
header bar, `divide-y` rows of `dt` (text-2) / `dd` (medium, tabular-nums).

**Progress indicator** (wizard) — horizontal steps, each: 1px top rule that
turns 2px Blue 60 when current/complete, 14px label, check icon when done.

**Inline notification** — 3px left accent in status color, layer bg,
status icon, 14px title semibold + body, optional action link. Used for
treatment banners (red = overruled, green = good law).

**Data table** — 32–48px rows, `layer` header bar with 12px semibold
uppercase-ish headers, hairline row dividers, zebra optional (we skip it),
row hover `layer-hover`.

**Modal** — full-bleed scrim `rgba(22,22,22,.5)`, square panel, header w/
close, 48px paired action bar at the bottom (secondary + primary, each 50%).

## Voice

Copy is IBM-terse: sentence case everywhere (headings included), no
exclamation marks, verbs first on buttons ("Open source", "Run search").
Numbers are real and specific (76,293 decisions — never "thousands").
