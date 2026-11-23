# Design tokens

The page uses the Pipenzo "Flow look" tokens: a black page, Flow-style alpha layers and one accent, Pipenzo yellow `#FECE02` (see "Yellow accent" under Rule). Red is only for danger.

## Source

`browser_desktop/static/tokens.css` is a byte-for-byte copy of `extension/sidepanel/tokens.css` in jortega0033/clip-to-reel-studio at commit `a13378ce73e5b27213c9a200fc960ec93afef054` (2026-11-21). Never edit the copy.

## Resync

Copy the file over `browser_desktop/static/tokens.css`. Nothing else changes.

## Rule

New UI uses these tokens. No new colour literals in CSS or JavaScript. Text never sits on a bare alpha layer; use a solid surface token. Yellow follows the rules below.

### Yellow accent

The header comment of `tokens.css` says yellow is used only on the primary button and the current-step marker, among other places. That comment is narrower than the rule. The copy must stay identical to its source, so the comment cannot be corrected here. This document takes precedence over it.

1. Current selection (decided by the owner on 2026-11-23). The yellow accent is used for the primary action, the current-step marker and the current selection (UI rule 8 in `ui-quality.md`). How (recommended by the orchestrator, adopted under the owner's delegation of the same day): a selection uses a solid `--primary` fill with `--on-primary` text, not only a yellow border, which has about 1.5:1 against white on light. It also carries a second sign that is not colour (weight, icon or text) and the existing aria attribute (for example `aria-current` or `aria-selected`). Never a tint with a same-hue border and never a thick one-sided border.
2. Focus ring (recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23). `--focus` is a focus indicator and is exempt from the accent limit, including where it is yellow in dark. A ticket that says the focus style stays unchanged means the rule on `main` after the token pull request.
3. Themes (recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23). Contrast and no-colour-alone checks cover both the light block and the dark block of `tokens.css`.

Status: the page does not yet follow rule 1. The file list in `app.css` (`.files button[aria-current="true"]`) still marks the current file with a neutral fill, a neutral border and bold weight. The page follows in ticket work.

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
