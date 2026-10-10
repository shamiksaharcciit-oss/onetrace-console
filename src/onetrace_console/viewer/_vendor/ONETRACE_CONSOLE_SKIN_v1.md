# onetrace Console Skin, v1: the sealed token block for the console and the viewer

**Source:** the v6 canvas ("release edition", 65Qi…), boards 1–7. The values were taken from the boards' own CSS, not retyped from screenshots.

## 1. Ruling

- **Canary's proposal is accepted.** The rule that tokens come from a sealed source stands. This document is that source for onetrace's console and viewer.
- **The viewer switches source.** `viewer/tokens.py` vendors §3's block from this document instead of `ONEVIEW_DESIGN_SPEC.md`:
  - **pins:** the sha256 of this whole file, and the sha256 of §3's block;
  - **X-6 still holds:** drift raises an error, and there's no fallback palette;
  - **untouched:** onedoor's and onewatch's copies of the oneview spec. onewatch's `canary.viewer.tokens` doesn't change.
- **The oneview spec's §3 scope fence** ("no dashboards…") doesn't bind the console. It predates the console and was written for the single-receipt viewer.
- **The free viewer file** uses the same block, with font stacks that fall back to system fonts.
- **The console** serves IBM Plex locally.

## 2. Rules that travel with the tokens

1. **Colour signals verdicts only.**
   - The four state pairs (`ok`, `cc`, `bad`, `neu`) mark verdicts and states.
   - Navy (`--accent`, `--nav-*`) is brand and navigation. It never signals state, just as `--seal` worked in oneview.
2. **Every text-on-background pair in use meets WCAG AA** (4.5:1), and the contrast test enumerates them.
   - The boards' faint grey `#8a96a8` measures 3.0:1 on white, so it's **not a text colour**. It's kept only as `--line-strong`, for graph edges and connectors, where the 3:1 rule for non-text elements applies.
   - Faint text uses `--ink-faint: #667185`: 4.92:1 on white and 4.55:1 on the page. This is core's one change to the boards, made for accessibility.
3. **One theme, light.** No dark theme in release 1.
4. **No shadows.** Radii are 8, 6 and 4 px only, plus 13 px for the round step number.

## 3. The block (vendor verbatim)

```css
:root{
  --page:#f5f6f8; --surface:#ffffff; --surface-sunk:#fbfcfd; --surface-alt:#f9fafb;
  --ink:#16202e; --ink-soft:#3a4556; --ink-muted:#4a5566; --ink-faint:#667185;
  --line:#dde2ea; --line-soft:#eef1f5; --line-node:#c9d0db; --line-strong:#8a96a8;
  --accent:#1f3a5f; --accent-ink:#ffffff;
  --nav-bg:#0f1b2d; --nav-ink:#c9d3e0; --nav-ink-faint:#8fa0b8; --nav-on-bg:#1f3a5f; --nav-on-ink:#ffffff;
  --ok-bg:#e6f4ea;  --ok-ink:#17663a;
  --cc-bg:#fdf3dc;  --cc-ink:#7a4f00;  --hl:#fdf3dc;
  --bad-bg:#fdeaea; --bad-ink:#a4161a;
  --neu-bg:#eef1f5; --neu-ink:#3a4556;
  --font-sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
  --font-mono:'IBM Plex Mono',ui-monospace,'Cascadia Mono',Consolas,monospace;
  --fs-small:12px; --fs-body:13px; --fs-nav:14px; --fs-h1:26px; --fs-kpi:30px;
  --r-card:8px; --r-ctl:6px; --r-pill:4px; --r-num:13px;
  --nav-width:232px;
}
```

## 4. What the canvas shows and this block leaves out

- **The boards' colours not in §3:** `#fdf3dc`'s border tint `#ecd9a8`, `#fff6f6`, `#fffaf0`, `#b26b00`, `#5c3d00`, `#d5dbe4`, `#b8c1ce`.
  - Canary maps each use on a board to a §3 token and lists the mapping in the item 12 report.
  - If a use can't be mapped without losing meaning, canary stops and reports. Core then issues v1.1. Canary never adds a token itself.
- **An "info" pill:** an inventory named one, but none was found in the boards' CSS (the pill classes are `ok`, `cc`, `bad`, `neu`). If a board shows one, the board and the element are named, and the pill is decided then.
- **Check against the live canvas:** core took these values from its own copy of the canvas source. Canary checks §3 against the latest live version it read (`1790854027-339d`), and reports any difference before vendoring.

## 5. Tests first (canary)

- **Pins:** both pins, with a drift sabotage.
- **Contrast:** the AA test over every pair the CSS uses. Sabotage: `--ink-faint` set back to `#8a96a8`.
- **Colour use:** no colour literal in any stylesheet or template outside the vendored block. Sabotage: one hex literal typed into a page.
