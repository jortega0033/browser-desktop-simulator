# Owner decisions

Dated record of the decisions the owner made for this repository. Changing any entry needs the owner; an agent that finds a decision blocking a ticket stops and says so.

| # | Date | Decision | Implemented in |
|---|---|---|---|
| 1 | 2026-11-22 | The instructions, tooling and playbook live on the default branch (`main`). | `CLAUDE.md`, `.claude/`, `.github/` on `main` |
| 2 | 2026-11-22 | Persona agents run automatically during ticket work and carry instructions tailored to this project. | `.claude/agents/`, `.claude/skills/implement-ticket/SKILL.md`, `.claude/agency-agents/README.md` |
| 3 | 2026-11-22 | Every open ticket is about app implementation; tooling is installed, not ticketed. | `CLAUDE.md` ("Delivery workflow"), epic #1 |
| 4 | 2026-11-22 | Agents may take a ticket up to a ready pull request. Only the owner merges and releases. | `CLAUDE.md` ("Git workflow", "Delivery workflow"), `.claude/skills/next-ticket/SKILL.md`, `docs/RELEASING.md`, `.claude/settings.json` (deny rules) |
| 5 | 2026-11-22 | No scheduler. Ticket work starts only on the owner's go signal (`/next-ticket`), because the repository is used to train AI models. | `.claude/skills/next-ticket/SKILL.md` (`disable-model-invocation: true`), `LOOP.md` |
| 6 | 2026-11-22 | A review gate hook blocks opening or readying a pull request until the gate roles have run after the last code edit. | `.claude/hooks/role_gate.py`, `.claude/settings.json` (`hooks`) |
| 7 | 2026-11-22 | Loop Engineering stays at L1, report-only and unscheduled. | `LOOP.md` |
| 8 | 2026-11-22 | Continuous integration runs on Linux and Windows; the default branch requires a pull request and green checks. | `.github/workflows/ci.yml`; branch protection is set on GitHub after the merge |
| 9 | 2026-11-22 | Permission rules: documented commands are allowed; force pushes, pushes to the default branch, merges, releases and reads of secrets are denied; edits to CI, agent configuration and Loop files ask first. | `.claude/settings.json` (`permissions`) |
| 10 | 2026-11-22 | Open decisions on tickets are settled with the ticket's stated default (list below). | Issues on GitHub, listed here |
| 12 | 2026-11-22 | The ten UI rules in `docs/ui-quality.md` are binding; the `ui-ux-pro-max` and `unslop` skills are installed and used for UI work and for copy. | `docs/ui-quality.md`, `.claude/skills/ui-ux-pro-max/`, `.claude/skills/unslop/`, `.claude/skills/implement-ticket/SKILL.md` |
| 13 | 2026-11-23 | Visual system: Pipenzo Flow look tokens (docs/design-tokens.md). SDLC kit version: jortega0033/sdlc-kit v1.0.0. | `docs/design-tokens.md`, `browser_desktop/static/tokens.css`, `browser_desktop/static/app.css` |
| 14 | 2026-11-23 | Yellow accent rules. D1 Current selection: the yellow accent is used for the primary action, the current-step marker and the current selection (UI rule 8). Decided by the owner on 2026-11-23. How (recommended by the orchestrator, adopted under the owner's delegation of the same day): a selection uses a solid --primary fill with --on-primary text (not only a yellow border, which has about 1.5:1 against white on light), plus a second sign that is not colour (weight, icon or text) and the existing aria attribute. Never a tint with a same-hue border and never a thick one-sided border. D2 Focus ring: --focus is a focus indicator, exempt from the accent limit, including where it is yellow in dark. A ticket that says the focus style stays unchanged means the rule on main after the token pull request. Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23. D3 Themes: contrast and no-colour-alone checks cover both the light and the dark block of tokens.css. Recommended by the orchestrator, adopted under the owner's delegation of 2026-11-23. | `docs/design-tokens.md` ("Yellow accent"); page follows in ticket work |

Entry 11 (Rust verified in CI only) does not apply: this repository has no Rust.

## Entry 10: open decisions settled by the ticket default

Decisions that each ticket states as "to be confirmed by the owner in review" stand as written in the ticket until the owner changes them.

- #1 (epic): no `node --test` runner is used in this batch (open owner question; conservative default: not used; flag in issue).
- #1: no delete of files or folders is added (open question D13; default: no delete).
- #1: `/api/v1` keeps working for root-level files; every mutating route needs an app token from #6 on.
- #2: `/api/v1` stays usable for root files; creating a file does not create parent folders (404 `parent_not_found`), creating a folder creates missing ancestors; 500 folders at most; paths in query parameters and bodies.
- #3: stacked mode below 720 pixels; a window bar for reopening; the stated Ctrl+Alt+`Backquote` rule replaces the M1 Escape behaviour; Ctrl+Alt+digit also reopens a closed window.
- #4: the response has a `stderr` field; a line is checked completely before it runs and a failing stage stops it; limit violations answer status 2 with a `limit:` message instead of truncating.
- #5: recovery discards a `pending` entry and does not roll forward; four tests start a child Python process with `subprocess` from the test module only (kept; drop them only if the owner says the no-process rule covers tests).
- #6: tokens are required on `/api/v1` writes too; `PUT /api/v2/layout` needs no token; file kind is decided by content and reported as `file_kind`; syntax, limit and unknown-command answers win over a missing `write` capability; "Load demo workspace" replaces "Load example files".
- #9: the version becomes `0.2.0` when the epic closes.
- #7 and #8 state no open decision; nothing to settle.
