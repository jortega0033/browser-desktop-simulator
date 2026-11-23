# Design tokens

The page uses the Pipenzo "Flow look" tokens: a black page, Flow-style alpha layers and one accent, Pipenzo yellow `#FECE02`. Red is only for danger.

## Source

`browser_desktop/static/tokens.css` is a byte-for-byte copy of `extension/sidepanel/tokens.css` in jortega0033/clip-to-reel-studio at commit `a13378ce73e5b27213c9a200fc960ec93afef054` (2026-11-21). Never edit the copy.

## Resync

Copy the file over `browser_desktop/static/tokens.css`. Nothing else changes.

## Rule

New UI uses these tokens. No new colour literals in CSS or JavaScript. Yellow appears only on the primary action and the current-step marker. Text never sits on a bare alpha layer; use a solid surface token.

## Light and dark

Dark is the primary design. The light values are in `:root`; the operating system colour scheme (`prefers-color-scheme: dark`) switches to the dark block. There is no manual switch.

## Token names by role

- Surfaces: `--bg`, `--bg-raised`, `--surface`, `--bg-sunken`
- Text: `--fg`, `--muted`, `--faint`
- Lines: `--border`, `--hairline`, `--control-border`, `--input-border`
- Accent: `--primary`, `--primary-press`, `--primary-edge`, `--on-primary`, `--focus`
- Dark block: `--ink`, `--on-ink`, `--on-ink-muted`, `--ink-border`
- Status: `--success`, `--ok`, `--ok-bg`, `--warn-fg`, `--warn-bg`, `--danger`, `--danger-bg`, `--info`
- Alpha layers: `--state-hover`, `--state-selected`, `--btn-secondary`, `--glass*`, `--scrim`
- Shadows: `--shadow-1` to `--shadow-3`
- Type: `--font`, `--font-display`, `--mono`
- Space and radius: `--space-1` to `--space-7`, `--radius-control`, `--radius-card`, `--radius-pill`
- Motion: `--dur-1` to `--dur-4`, `--ease-out`, `--ease-in-out`

The tokens name Google Sans Flex and Inter first; this repository bundles no fonts, so the system fonts in the stack apply.
