# CLAUDE.md

Working instructions for this repository. Read this file first, then the documents it links to. It does not repeat them.

## What this is

An offline desktop simulation in the browser for one person. One Python package, standard library only, serves a JSON API and a static page on `127.0.0.1` and keeps named text files in one SQLite file. M1 (file list, text editor, create, save, reopen after restart, stale-revision handling, example fixture) is implemented. Virtual folders with versions, a window manager, an in-app command interpreter, a write journal with recovery and an app registry are planned and tracked in the epic, issue #1.

## Sources of truth

| Topic | Document |
|---|---|
| Product scope, milestones, M1 contracts, fixture, acceptance matrix, open choices | [docs/PRD.md](docs/PRD.md) |
| How the code is built, the traced save workflow, the rules the code keeps, differences between the PRD and the code, what is still unverified | [docs/architecture.md](docs/architecture.md) |
| Launch, smoke steps, limits, baseline verification | [README.md](README.md) |
| Backlog | Epic issue #1 and its sub-issues on GitHub, in dependency order: #7, #2, #8, #4, #5, #3, #6, #9. The epic gives the dependencies, the parallel tracks and the estimates. |
| Loop setup and its limits | [LOOP.md](LOOP.md), [loop-constraints.md](loop-constraints.md) |
| Project subagents and their origin | [.claude/agency-agents/README.md](.claude/agency-agents/README.md) |

When the PRD and the code disagree, the code is the baseline and [docs/architecture.md](docs/architecture.md) records the difference. A ticket that changes a contract updates the PRD in the same pull request.

## Setup

Python 3.12 or newer. Nothing to install: there is no package manifest, no virtual environment requirement, no build step and no lint step. On Windows the interpreter is `python`; on Linux it is `python3`.

## Commands

All of them were run during preparation on Windows 11 with Python 3.13.14, from the repository root (the server on a free port and a scratch data directory instead of the values shown).

Run the tests (78 tests, about 30 seconds; 46 of them start a real server each):

```
python -m unittest discover -s tests -t .
```

The run is good when the last line is `OK`. A single test: `python -m unittest tests.test_storage.CrudTests.test_update_cas`. The tests that do not start a server (32 tests, about 5 seconds): `python -m unittest tests.test_storage tests.test_static_assets`.

Run the server (binds `127.0.0.1` only; `--data-dir` and `--port` are both required; the data directory is created if missing; stop with Ctrl+C):

```
python -m browser_desktop --data-dir ./data --port 8765
```

`--port 0` picks a free port and prints it as `Serving on http://127.0.0.1:<port>/`. `data/` and `*.sqlite*` are ignored by Git. For experiments, use a scratch directory outside the repository and delete it afterwards.

Quick check that a running server answers:

```
curl -s http://127.0.0.1:8765/api/v1/health
```

Expected: `{"status": "ok", "version": "0.1.0", "schema_version": 1}`.

On Windows, `kill` from Git Bash can leave the Python process running, and the server does not set `SO_REUSEADDR` there. Stop a server you started in the background by process id (`taskkill //PID <pid> //F` or `Stop-Process -Id <pid>`), then confirm that nothing listens on the port.

## Hard rules

These come from PRD sections 1, 4 and 10. A change that breaks one needs the owner's approval first, not a pull request.

- Standard library only, in the application and in the tests. No pip or npm dependency, no build tooling, no CDN, font, image or script from another host.
- Loopback only. The server binds `127.0.0.1`. No CORS headers. No outgoing request from the server, the page or the tests.
- No host shell, no host command, no process started by the application: no `subprocess`, `os.system`, `os.exec*`, `os.spawn*` or `os.popen` anywhere under `browser_desktop/`.
- File names and virtual paths are database keys. Request input is never joined into a host path. The only host directory the application writes is the data directory given on the command line. Static files come from the fixed allowlist in `browser_desktop/server.py`.
- No accounts, sign-in, remote sync, hosting, model integration or native GUI.
- File text is data. It reaches the page through `textContent` or `.value`, or through DOM nodes built with `createElement`, never through `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or `eval`. No inline script, inline style or event-handler attribute: the CSP forbids them. `tests/test_static_assets.py` enforces part of this, today for `index.html`, `app.css` and `app.js` only.
- Tests use a temporary directory and port 0. No fixed port, no network, no dependence on wall-clock timing for a pass.

## Architecture boundaries

Details and line references are in [docs/architecture.md](docs/architecture.md). The short form:

- `browser_desktop/__main__.py`, `browser_desktop/cli.py`: command line only. Arguments, exit code 2 for a data directory or schema problem, exit code 1 when the port cannot be bound.
- `browser_desktop/server.py`: HTTP only. Host and Origin checks, body length cap, media type, exact JSON key sets, routing, the static allowlist, security headers, mapping of storage errors to status codes, the generic 500. It never runs SQL.
- `browser_desktop/storage.py`: the only module that imports `sqlite3`. It owns the validation rules for names, text and revisions, the migrations, and every transaction. One connection per operation; every write inside one `BEGIN IMMEDIATE` transaction. It never touches HTTP objects.
- `browser_desktop/static/`: one page, native JavaScript, no framework. It talks to the server through `/api/v1` only and stores nothing in the browser.
- `tests/`: `unittest`. `test_storage.py` drives `Storage`, `test_api.py` drives a real server on port 0 over `http.client` and also covers `create_server` and the command line, `test_static_assets.py` scans the static files as text.

Keep new code on the correct side of these lines. A new module is right when a file would otherwise take on a second job (for example path rules, the command interpreter, layout rules or the app registry).

Rules that every change must keep:

- A save succeeds only when `base_revision` equals the stored revision. A stale save changes nothing and answers 409 with the stored file under `current`. Any new write to a file (rename, move, copy target, redirect from a command, restore) keeps the same guarantee inside one transaction together with its derived rows.
- Existing databases open under new code. A schema change adds an entry to `MIGRATIONS` at its reserved number (the epic, issue #1, reserves the numbers), keeping the list sorted by version. It never edits an entry that has shipped, and it comes with a test that opens a database made by the previous version. The latest version is read from the list (today from its last entry, `storage.py:37`), so an entry out of order would make the code refuse valid databases as too new. A database newer than the code is refused untouched.
- Every route checks `Host`. Every mutating route also checks `Origin` when the header is present. Error responses use the envelope `{"error": {"code", "message"}}` and never contain a traceback.
- Limits stay enforced on the server, and on the page where the page can know them: name 1 to 64 characters from `A-Za-z0-9._-` starting with a letter or digit, text at most 65,536 UTF-8 bytes with no NUL, request body at most 131,072 bytes, at most 500 files.
- Typed text is never discarded without the person choosing it.
- Logic that must be proven by an automated test lives in Python. The repository has no JavaScript test runner and may not add one without the owner's approval, so the page keeps thin mirrors of server rules and is checked by a recorded browser run.

## Git workflow

- `main` is the default branch and is not protected. There is no CI. Checks are run locally and reported with their output.
- One branch per issue. The repository has no naming rule yet; `<issue-number>-<short-slug>` is the suggested form. Small commits with imperative subjects and a type prefix, as in the existing history (`feat:`, and by extension `fix:`, `docs:`, `test:`, `chore:`).
- Open a draft pull request that names the issue (`Part of #1`, `Closes #n`). Do not merge your own pull request and do not push to `main`.
- Never commit a data directory, a SQLite file, `.env*`, or `.prep/`.
- Do not change `.claude/agents/`, `LOOP.md`, `loop-constraints.md` or `loop-budget.md` as part of a feature ticket.

## Evidence before a ticket is called done

Put these in the pull request description. Paste real output; do not summarise a run you did not make.

1. The output tail of `python -m unittest discover -s tests -t .` from a clean checkout, with the Python version and the operating system. State the test count before and after the change.
2. For each acceptance criterion of the issue: the name of the test that proves it, or the exact manual step and what was observed.
3. For a schema change: the test that opens a database created by the previous schema version, and the new schema version reported by `/api/v1/health`.
4. For a new or changed route: one request and response pair per success and per error code, taken from a server started with `--port 0` on a scratch data directory, and the PRD diff that documents the route.
5. For a change under `browser_desktop/static/`: a browser run on `http://127.0.0.1:<port>/` with the browser name and version, the viewport sizes checked (800x600 and 360 pixels wide, or the narrowest width the browser allows, stated), keyboard-only operation of the changed controls, and the console and network log free of errors and of requests to any other host. Browser checks are manual: the repository has no approved browser automation.
6. `git status` showing no stray files, and confirmation that no dependency, external URL, host command or non-loopback listener was added.
7. Anything not verified, said plainly.

## Subagents

Project-local roles are in `.claude/agents/`. Reviewer roles (Software Architect, Code Reviewer, Codebase Onboarding Engineer, Database Optimizer, Application Security Engineer, Accessibility Auditor, Reality Checker, `loop-verifier`) are limited to `Read, Grep, Glob`. Implementing roles (Backend Architect, Frontend Developer, API Tester) are written for larger stacks; the hard rules above override anything in their text. See [.claude/agency-agents/README.md](.claude/agency-agents/README.md) for sources, licence and the name collision with a user-level install.

## Loop

Issue triage runs at L1: report-only, started by hand, no scheduler, no GitHub writes. See [LOOP.md](LOOP.md).

## Ticket implementation: agent roles run automatically

When asked to implement, continue or finish a GitHub issue, follow the playbook in [`.claude/skills/implement-ticket/SKILL.md`](.claude/skills/implement-ticket/SKILL.md). Claude Code loads it on its own for ticket work; `/implement-ticket <issue number>` starts it by hand.

Delegate to the project subagents in `.claude/agents/` without waiting to be asked:

- **Before coding:** Codebase Onboarding Engineer and Software Architect, as their descriptions say.
- **While coding:** the implementing role that matches the files being changed.
- **After coding:** each specialist reviewer whose trigger matches the change.
- **On every ticket, before it is called done:** Code Reviewer, then Reality Checker.
- The session that wrote a change does not count as its reviewer.
- List the roles that ran and their verdicts in the pull request description under "Agent roles run".

Each role's `description` ends with a "Use proactively ..." sentence, which is what makes Claude Code delegate to it without being told.
