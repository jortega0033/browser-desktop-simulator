# Browser Desktop Simulator – PRD and Technical Spec

Status legend: **[Implemented baseline]** = implemented in M1 (see [baseline verification](../README.md#baseline-verification)); **[Future]** = planned, not built.

## 1. Intended user and workflow

A frontend engineer working alone on one machine who wants to explore, offline, how a local interactive desktop manages focus and virtual data safely. Workflow: start the local server, open the page, load the example file, create and edit named text files, save, stop the server, restart it, and find the data intact. Later milestones add folders, windows, an in-app terminal, crash-safe writes and an app registry.

Out of scope: paid services, sign-in, remote sync, deployment, real user data, external media, model integration, host shell access, processes outside the app, writes outside the app-owned data directory, native GUI. Any package or reference needed later must be offline-plannable and approved before it is staged.

## 2. Milestones

| Milestone | Status | Summary |
|---|---|---|
| M1 | **[Implemented baseline]** | Workspace with File list and Text editor; create, edit and save named plain-text files in SQLite; survive restarts; example fixture. |
| BD-1 (P1) | [Future] | Scoped virtual filesystem: folders, rename/copy/move, versions. |
| BD-2 (P2) | [Future] | Window manager: focus, lifecycle, clamped persisted bounds. |
| BD-3 (P3) | [Future] | Sandboxed command interpreter and string pipelines. |
| BD-4 (P4) | [Future] | Crash-safe write journal and revision recovery. |
| BD-5 (P5) | [Future] | Typed app registry and complete offline workflow. |

## 3. Epic and stories (future work)

**Epic: Offline desktop workbench** – a safe, offline, single-person desktop simulation built on the M1 workspace. Each story below is intended to become one issue.

| Key | Story | Depends on | Key acceptance criteria |
|---|---|---|---|
| P1 | As an engineer I organize files in folders and keep versions. | – | Rename `/a`→`/z` moves `/a/b/c.txt` to `/z/b/c.txt` atomically; `/a/../b`, `//a`, depth 9, 65-char segment rejected; moving `/a` into `/a/b` rejected; 50-version history cap; M1 data migrates to `/launch-notes.txt` keeping revision 2. |
| P2 | As an engineer I manage three windows by keyboard. | P1 | Bounds x=1400,y=900,w=600,h=400 clamp inside an 800×600 viewport with min 240×160; Ctrl+Alt+1/2/3 and Ctrl+Alt+\` focus order; layout (up to 4 window ids) persists across restart; invalid layouts rejected. |
| P3 | As an engineer I run safe commands on virtual files. | P1 | `cat launch-notes.txt \| grep orbit \| wc -l` → `2`; unknown command → status 127; `..` paths rejected; literal-only grep; 8 stages / 1024 chars / 64 KiB limits; no subprocess. |
| P4 | As an engineer I never see a half-written tree or file. | P1 | Multi-row operations interrupted at 4 points over 100 seeded runs (seed 7) yield only all-old or all-new state; checksum mismatch quarantined; restore of revision 2 creates revision 6 from 5. |
| P5 | As an engineer I run the whole workflow from an app registry. | P2, P3, P4 | Registry lists 4 apps; token-based capability denial returns 403 without losing text; 16×16 hex bitmap preview; demo workspace + pipeline gives `2` after restart; no external resources. |

Dependencies: P1 → P2, P3, P4; P2, P3, P4 → P5.

## 4. System stack

Python 3.12 standard library only: `http.server.ThreadingHTTPServer`, `sqlite3`, `argparse`, `json`, `threading`. Static HTML/CSS/native JS served from the package. No build tooling, no external dependencies. Server binds `127.0.0.1` only.

Layout: `browser_desktop/{__main__,cli,server,storage}.py`, `browser_desktop/static/{index.html,app.css,app.js}`, `tests/`.

Launch: `python -m browser_desktop --data-dir <path> --port <port>` (Windows), `python3 -m browser_desktop ...` (Linux).

## 5. Contracts (M1) **[Implemented baseline]**

The M1 contract follows. Extra limits: request bodies over 131,072 bytes get 413 even if the text is under its own limit (JSON escaping can inflate it); unsupported HTTP methods get a JSON error.

### 5.1 API

All JSON, `Cache-Control: no-store`. Errors: `{"error":{"code","message"}}`.

| Endpoint | Success | Errors |
|---|---|---|
| `GET /api/v1/health` | 200 `{"status":"ok","version":"0.1.0","schema_version":1}` | – |
| `GET /api/v1/files` | 200 `{"files":[{name,size,revision,updated_at}]}` by name | – |
| `GET /api/v1/files/{name}` | 200 `{name,text,revision,size,updated_at}` | 400 `invalid_name`, 404 `not_found` |
| `POST /api/v1/files` `{name,text}` | 201 file | 400, 409 `already_exists`, 409 `file_limit` |
| `PUT /api/v1/files/{name}` `{text,base_revision}` | 200 file, revision+1 | 400, 404, 409 `conflict` (+ `current`) |
| `POST /api/v1/fixtures` `{}` | 200 `{created:[...],files:[...]}`, never overwrites | 400, 403, 415, 409 `file_limit` |

General: 403 `forbidden_origin`, 404, 405 (+`Allow`), 411, 413, 415, 500 generic. No CORS headers. `GET /` serves HTML; static allowlist is `/`, `/index.html`, `/static/app.css`, `/static/app.js`.

### 5.2 Schema

`schema_migrations(version)`; `files(name PK, text, revision ≥ 1, created_at, updated_at)` with CHECK constraints on name length (1–64) and text bytes (≤ 65536). Migrations are numbered and applied in order inside a transaction; a database from a newer version is refused. WAL, `busy_timeout=5000`, `BEGIN IMMEDIATE` for writes.

### 5.3 Algorithms

- **Optimistic concurrency:** `UPDATE ... WHERE name=? AND revision=?`; zero rows → conflict (or 404). Exactly one of N concurrent writers with the same base revision succeeds.
- **Validation:** name regex `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` without `..`; text ≤ 65536 UTF-8 bytes, no NUL; body ≤ 131072 bytes; exact key sets; `base_revision` int ≥ 1.
- **Names are never filesystem paths**; static files come from a fixed allowlist.

### 5.4 UI

Original two-panel workbench: **File list** (buttons with exact file names, `New file`, `Load example files`) and **Text editor** (`File name`, `File text`, `Save`, size/revision line, `Unsaved changes` marker). `role="status"` live region for recoverable messages; conflict panel with `Load latest` and `Keep mine and save`. Shortcuts: Ctrl/Cmd+S save, Alt+N new file, Up/Down in list, Esc to list. User text is only set via `.value`/`textContent`. In M1 the editor textarea is the only view of file contents; a separate read-only Preview is deferred to P2/P5.

## 6. Deterministic fixtures

`launch-notes.txt` (3 lines, trailing newline):

```
orbit alpha ready
dock lights green
orbit beta synced
```

Expected: size 54 bytes (three lines of 17 characters plus a newline each); `grep orbit` matches lines 1 and 3 → 2 matches (used by P3/P5).

Expected after `POST /api/v1/fixtures` on an empty store: `created=["launch-notes.txt"]`, file revision 1, size 54. Second call: `created=[]`, revision unchanged.

## 7. Responsiveness and accessibility

At 800×600 and 360 px wide the document body has no scrollbar; panels scroll internally; panels stack below 720 px. Associated labels, `:focus-visible` outlines, contrast ≥ 4.5:1, system fonts, no icon or stock assets, polite live region for status, full keyboard operation.

## 8. Errors, retry, restart, concurrency

- Network failure or non-JSON response: status message, editor text kept, Save re-enabled for retry.
- Stale revision: 409 with the server's current version; the UI keeps local text and offers load-latest or keep-mine; nothing is overwritten silently.
- Restart: data in `<data-dir>/desktop.sqlite3`; reopening on the same directory shows the same files and revisions.
- Concurrency: `ThreadingHTTPServer`, per-request SQLite connections, immediate transactions, 10 s socket timeout, bounded body size.
- Bad data dir (empty string, existing file) exits with code 2.

## 9. Versioning

API prefix `/api/v1`; breaking changes get `/api/v2`. App version `0.1.0`. Schema version tracked by migrations; M1 = 1; P1 adds migration 2 (path model and history).

## 10. Security and validation

Loopback bind only; Host must be `127.0.0.1:<port>` or `localhost:<port>`; mutating requests also check `Origin` when present; no CORS headers; CSP `default-src 'self'` with no inline script/style; `nosniff`; no-referrer; static allowlist; size caps; strict JSON shapes; parameterized SQL; generic 500 messages; no host process or filesystem access beyond the data directory.

## 11. Acceptance matrix (M1)

| ID | Criterion | Method |
|---|---|---|
| A1 | `GET /` returns HTML; `/api/v1/health` returns status ok | `tests/test_api.py` |
| A2 | Create `launch-notes.txt`, edit, save → revision 2 | `tests/test_api.py` |
| A3 | Data survives server restart | `tests/test_api.py`, `tests/test_storage.py` |
| A4 | Stale save returns 409 with current version | `tests/test_api.py` |
| A5 | Traversal and non-allowlisted static paths are 404 | `tests/test_api.py` |
| A6 | Foreign Host/Origin on POST/PUT is 403 | `tests/test_api.py` |
| A7 | Oversize/invalid names, shapes, content type rejected | `tests/test_api.py` |
| A8 | Concurrent writers: exactly one wins per base revision | `tests/test_storage.py` |
| A9 | Fixture is 3 lines, 2 `orbit` matches, idempotent | `tests/test_api.py` |
| A10 | Required labels/ids present, no inline script/style/`innerHTML` | `tests/test_static_assets.py` |
| A11 | No body overflow at 800×600; keyboard operation | manual smoke (README) |

## 12. Sample demo

Start server → open page → `Load example files` → open `launch-notes.txt` → add a line → `Save` (status shows revision 2) → stop server → restart on the same data dir → file still shows revision 2 with the added line.

## 13. Test plan

Automated: `python -m unittest discover -s tests -t .` (uses temporary directories and port 0). Manual: README smoke steps in a real browser, including 800×600 and keyboard-only passes. Future tickets add their numbered checks from section 3.

## 14. Open choices

- Whether P1 keeps flat M1 names as `/name` (planned) or exposes both forms.
- Whether P2 layout is stored per viewport size or as one clamped layout (planned: one layout).
- Whether P5 bitmap preview uses a canvas or CSS grid (planned: CSS grid, no external assets).
- Any external reference or tool needed later requires offline plan and approval first.
