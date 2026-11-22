# Architecture notes and PRD reconciliation

Written during repository preparation on 2026-11-22 against `main` at `494e561`. Line references are to that commit. The product specification is [PRD.md](PRD.md); this file records how the code is actually built, one traced workflow, the rules the code keeps, and where the PRD, the issues and the code differ.

Status words used below:

- **Implemented**: in the code at `494e561` and exercised by a test or by a run during preparation.
- **Planned**: in the PRD or an issue, not in the code.
- **Needs verification**: claimed somewhere, not reproduced during preparation.

New tickets proposed during preparation are named NEW-A, NEW-B and NEW-C here until they have issue numbers. The epic, issue #1, lists them.

## 1. Shape of the system

A three-layer program with no framework and no dependency outside the Python standard library.

| Layer | Files | Job | Does not do |
|---|---|---|---|
| Command line | `browser_desktop/__main__.py`, `browser_desktop/cli.py` | Parse `--data-dir` and `--port` (both required, `cli.py:30-33`), start the server, print the URL, map start-up failures to exit codes 2 (`cli.py:38-40`) and 1 (`cli.py:41-43`) | No HTTP, no SQL |
| HTTP | `browser_desktop/server.py` | `ThreadingHTTPServer` bound to `127.0.0.1` (`server.py:376`), request guards, routing (`server.py:197-246`), exact JSON key sets (`server.py:250-291`), static allowlist (`server.py:20-25`), security headers (`server.py:27-37`), error envelope | No SQL; never joins request input into a host path |
| Storage | `browser_desktop/storage.py` | The only user of `sqlite3`. Validation of names, text and revisions (`storage.py:77-108`), migrations (`storage.py:25-37`, `183-199`), every transaction | No HTTP objects |
| Page | `browser_desktop/static/index.html`, `app.css`, `app.js` | One page, one script (a single function scope with one `state` object, `app.js:27-36`), talks to `/api/v1` only (`app.js:4`) | No storage in the browser, no HTML sinks, no inline script or style |

Data ownership: the server owns all data, in `<data-dir>/desktop.sqlite3`. The page keeps only the text it loaded (`state.baseText`) and the revision it loaded (`state.revision`) so that it can send `base_revision` on save.

Concurrency: each request runs on its own thread, and each storage operation opens its own short-lived SQLite connection (`storage.py:146-155`), so the one `Storage` object is shared safely. Writes run inside `BEGIN IMMEDIATE` (`storage.py:165-181`) with `busy_timeout=5000`.

## 2. Traced workflow: edit a file, save it, find it after a restart

Status: **Implemented**. Every step was read in source; steps 1 to 8 were also run over HTTP and in a browser during preparation (section 7).

1. **Launch.** `python -m browser_desktop --data-dir D --port P` reaches `cli.main` (`cli.py:25`). `create_server` (`server.py:367-380`) opens storage first, then binds `127.0.0.1:P`. A storage problem exits 2; a bind failure exits 1.
2. **Storage open.** `Storage.__init__` (`storage.py:136-142`) validates and creates the data directory (`prepare_data_dir`, `storage.py:115-132`) and runs `_migrate` (`storage.py:183-199`): all pending migrations inside one transaction, each recorded in `schema_migrations`. A database whose highest version is above `LATEST_VERSION` raises `SchemaTooNew` and is left untouched (`storage.py:189-193`).
3. **Page load.** `GET /` passes the Host check (`_check_origin`, `server.py:183-195`) and is served from `STATIC_ROUTES` (`server.py:295-301`). The script asks for `GET /api/v1/files` (`app.js:145-155`, called at `app.js:348`), served by `_list_files` (`server.py:313`) from `Storage.list_files` (`storage.py:230-238`).
4. **Load the fixture.** "Load example files" runs `loadFixtures` (`app.js:260-276`): `POST /api/v1/fixtures` with `{}` reaches `_fixtures` (`server.py:345-349`) and `ensure_fixture` (`storage.py:288-303`), which inserts `launch-notes.txt` at revision 1 only when it is missing.
5. **Open.** A click runs `openFile` (`app.js:164-179`): `GET /api/v1/files/{name}`. The name is percent-decoded once and validated (`server.py:326-331`), then read by `get_file` (`storage.py:240-249`).
6. **Save.** `save` (`app.js:227-258`) checks size and NUL on the page, then sends `PUT /api/v1/files/{name}` with `{text, base_revision}`. `_put_file` (`server.py:337-343`) requires exactly those two keys. `update_file` (`storage.py:267-286`) runs `UPDATE files SET text=?, revision=revision+1, updated_at=? WHERE name=? AND revision=?` inside `BEGIN IMMEDIATE`.
7. **Stale save.** When no row matches, storage raises `NotFound` or `Conflict(current)` (`storage.py:282-285`); the server answers 404 or 409 with the stored file under `current` (`server.py:240-246`). The page keeps the typed text, shows the conflict group and offers "Load latest" or "Keep mine and save" (`app.js:217-220`, `302-312`).
8. **Restart.** Nothing is cached in the process. `Storage.close` folds the WAL into the main file on a clean stop (`storage.py:201-210`). A process that is killed skips that step; the data was still there after the next start in two runs during preparation (section 7).

## 3. Rules the code keeps

| Rule | Where | Status |
|---|---|---|
| File names are database keys, never host paths | `storage.py:5`, `storage.py:20`, `77-84`; static files from a fixed table, `server.py:20-25` | Implemented |
| A revision starts at 1 and grows by exactly 1 per successful save; exactly one of several writers with the same base revision wins | `storage.py:262`, `273-277`; `tests/test_storage.py` `ConcurrencyTests`, `tests/test_api.py` `test_concurrent_writers_single_winner` | Implemented |
| A failed write leaves no partial state | `_tx` rolls back on any exception, `storage.py:165-181`; `test_failed_write_leaves_no_partial_state` | Implemented |
| Limits: name 1 to 64 characters from `A-Za-z0-9._-`, first character a letter or digit, no `..`; text at most 65,536 UTF-8 bytes, no NUL; at most 500 files; body at most 131,072 bytes | `storage.py:18-20`, `77-100`, `258`, `296`; `server.py:15`, `260-264`; also CHECK constraints in the table, `storage.py:28-34` | Implemented |
| Every request must carry `Host: 127.0.0.1:<port>` or `localhost:<port>`; mutating methods also check `Origin` when the header is present | `server.py:183-195` | Implemented |
| Every response carries the CSP, `nosniff`, `no-referrer` and `no-store`; errors use `{"error": {"code", "message"}}`; an unexpected exception becomes a generic 500 | `server.py:27-37`, `74-95`, `149-154` | Implemented |
| Request bodies need `Content-Length`, `application/json`, valid UTF-8 JSON and exactly the documented keys | `server.py:250-291` | Implemented |
| The application starts no process and runs no host command | no `subprocess` or `os.system` use in `browser_desktop/` (read) | Implemented, not enforced by a test |
| File text reaches the page only through `.value` and `textContent` | `app.js` (read); `tests/test_static_assets.py` `test_js_safety` scans `app.js` | Implemented |

## 4. PRD capabilities against the code

| PRD item | Status | Evidence |
|---|---|---|
| M1 workspace: file list and text editor (section 5.4) | Implemented | `index.html`, `app.js`; browser run in section 7 |
| API of section 5.1: health, list, get, create, save, fixtures | Implemented | `server.py:203-217`; `tests/test_api.py`; HTTP run in section 7 |
| Schema and migrations (section 5.2) | Implemented | `storage.py:25-37`, `183-199`; `MigrationTests` |
| Optimistic concurrency (section 5.3, A4, A8) | Implemented | 409 with `current` observed over HTTP and in the browser |
| Security rules (section 10, A5, A6) | Implemented | foreign Host 403, foreign Origin 403, traversal path 404 observed |
| Fixture (section 6, A9) | Implemented | size 54, `created` list, second call creates nothing, observed |
| Restart keeps data (section 8, A3) | Implemented | observed over HTTP and in the browser |
| No page overflow at 800x600 (section 7, A11) | Implemented | measured in the browser: document scroll size equals the viewport |
| 360 pixels wide (section 7) | Needs verification | the browser window would not go below 500 pixels; at 500x640 there was no overflow and the panels were stacked |
| Keyboard operation (section 7, A11) | Partly verified | Ctrl+S, Alt+N and focus outlines observed; Up and Down in the list and Esc were not exercised |
| Contrast of at least 4.5:1, screen reader output (section 7) | Needs verification | not measured |
| Linux and Python 3.12 (README "Baseline verification") | Needs verification | preparation ran on Windows 11 with Python 3.13.14 only |
| P1 virtual filesystem with folders and versions (BD-1) | Planned | issue #2; page work in NEW-B |
| P2 window manager (BD-2) | Planned | issue #3 |
| P3 command interpreter (BD-3) | Planned | issue #4 |
| P4 write journal and recovery (BD-4) | Planned | issue #5 |
| P5 app registry and full workflow (BD-5) | Planned | issue #6; close-out in NEW-C |

## 5. Findings: drift between PRD, issues and code, and risks for the planned work

Each finding names the ticket that deals with it. "Open" means the owner has to decide.

| Id | Finding | Evidence | Handled by |
|---|---|---|---|
| D1 | The README requires "Python 3.12"; the code also runs on 3.13.14. The bound is a minimum, not an exact version. | README "Requirements"; test run in section 7 | NEW-C (README) |
| D2 | A migration is one SQL statement: `_migrate` calls `conn.execute(sql)` once per entry (`storage.py:194-199`). P1 needs several statements and a data copy from the M1 table, and three tickets add migrations. | source | NEW-A |
| D3 | The `files` table is `WITHOUT ROWID`, keyed by `name` with `CHECK(length(name) BETWEEN 1 AND 64)` (`storage.py:28-34`). SQLite cannot change a CHECK in place, so the path model needs a new table and a copy. | source | #2 |
| D4 | The PRD reserves only migration 2 (section 9). The issues use 2 for paths and versions (#2), 3 for the layout (#3) and 4 for the journal (#5), and #3 and #5 can be built at the same time. | PRD section 9; issues #3, #5 | Epic: the numbers are reserved per ticket; NEW-A makes the runner apply any missing number, keeps the list sorted and takes its highest number as the latest version |
| D5 | Routing is one `if/elif` chain with the error mapping inline (`server.py:197-246`). Every planned ticket adds routes there, so parallel tickets would edit the same lines. | source | NEW-A (route table) |
| D6 | Static files are a fixed table of four routes, and a test pins exactly that set (`tests/test_api.py` `test_static_routes_cover_exactly_the_allowlist`). A new script or style sheet answers 404 until both change. | source | NEW-A (manifest), then each ticket adds its files |
| D7 | The static safety tests read `index.html`, `app.css` and `app.js` only (`tests/test_static_assets.py:41-44`). A new script would not be scanned for `innerHTML` or external URLs. | source | NEW-A |
| D8 | The page is one function scope with one `state` object (`app.js:27`). Windows, a terminal and a registry need separate modules. The CSP allows same-origin module scripts (`script-src 'self'`). | source | NEW-A (module entry point), NEW-B, #3 |
| D9 | The page hard-codes `/api/v1` (`app.js:4`) and repeats the name rule (`app.js:5`, `storage.py:20`); two tests assert the `/api/v1` strings in `app.js` (`test_js_safety`). | source | NEW-B |
| D10 | Issue #2 says `/api/v1` "stays read-compatible for flat names" and does not say what happens to `POST` and `PUT` on `/api/v1`, which the page and most of the 46 HTTP tests use. | issue #2 | #2 decides: `/api/v1` keeps working, reads and writes, for files in the root folder. Open for the owner to confirm. |
| D11 | Issue #2 defines the virtual filesystem as API and storage only. No ticket gives the page folders, rename, copy, move or a version list, yet #6 needs a file browser. | issues #2, #6 | NEW-B |
| D12 | PRD section 5.4 defers the read-only Preview to "P2/P5"; issue #3 lists Preview as one of three windows without saying what it shows before #6. | PRD 5.4; issue #3 | #3 defines it: the saved text of the open file, read-only |
| D13 | There is no way to delete a file or folder, in the code (`DELETE` answers 405) or in any PRD story or issue; `rm` is listed as an unknown command on purpose. The 500 file limit can be reached and never relieved. | HTTP run; PRD section 3; issue #4 | Open. Not in the batch because the PRD does not ask for it. |
| D14 | The repository has no JavaScript test runner, and the standard-library rule rules out adding one. Clamping, focus order and rendering in the page cannot be proven by `unittest`. | PRD sections 1 and 4 | Epic rule: provable logic lives in Python; the page mirrors it and is checked by a recorded browser run. Open: whether the built-in `node --test` runner is acceptable later. |
| D15 | Timestamps have one-second resolution (`storage.py:111-112`). Several saves in one second share a timestamp. | source | #2 and #5 order versions and journal entries by number, never by time |
| D16 | With SQLite, one transaction is already all-or-nothing. A journal entry written in its own transaction before the apply step is what creates a state to recover. Issue #5 does not say which transactions exist or what recovery does with each state. | issue #5; `storage.py:165-181` | #5 fixes the states and the recovery table |
| D17 | Issue #5 asks for simulated interruptions. An exception raised in the process is rolled back by `_tx`; a killed process is not, although SQLite reaches the same result. Only the first is easy to script. | `storage.py:172-177` | #5 adds one real process kill per interruption point next to the seeded in-process runs |
| D18 | Issue #6 puts capability tokens on "write or run requests". The Origin check passes when no `Origin` header is sent (`server.py:190-195`), and `/api/v1` writes exist. If only `/api/v2` checked the token, the check would be bypassed through `/api/v1`. | source; issue #6 | #6: every mutating route of every API version needs a token. Open for the owner to confirm. |
| D19 | The health response and a test pin `"version": "0.1.0"` and `"schema_version": 1` (`tests/test_api.py` `test_health`); `MigrationTests` pins `[1]`. Neither the PRD nor an issue says when the application version changes. | source; PRD section 9 | NEW-A removes the schema literals from tests; the version bump is decided in NEW-C. Open. |
| D20 | Every page load logs a console error: the browser asks for `/favicon.ico` and gets 404. The evidence rule "console free of errors" cannot be met as long as that happens. | browser run | NEW-A (an empty `data:` icon link; the CSP allows `img-src data:`) |
| D21 | `body` has `overflow: hidden` (`app.css:21-24`). The page cannot overflow, but content that does not fit is clipped instead of scrolled unless a panel scrolls it. | source | #3 and NEW-B check their layouts at the small sizes |
| D22 | The discard prompt is `window.confirm` (`app.js:159-162`), a blocking native dialog. It works for one editor; with several windows it blocks all of them. | source | #3 keeps it and states so; a replacement is not in the batch |
| D23 | The 46 HTTP tests take about 25 of the suite's 30 seconds, about half a second each. `Running.stop` calls `shutdown()`, which waits for the default 0.5 second poll of `serve_forever`. The cause was not confirmed by an experiment. | timing in section 7; `tests/test_api.py:30-40` | NEW-A measures and shortens the poll in the test helper |
| D24 | The Host check accepts only the exact port the server listens on (`server.py:184-185`). A forwarded port or a proxy gets 403. This is intended (PRD section 10). | source | none; recorded so that nobody "fixes" it |
| D25 | The no-external-URL test uses the pattern `//host.tld` (`tests/test_static_assets.py:98`). A script comment written without a space after `//` and containing a dot fails it. | source | none; write comments with a space |

No difference was found between PRD section 5 (the M1 contracts) and the routes, status codes, schema and limits in the code.

## 6. Shape of the planned work

Status: **Planned**. This is the design the epic and its tickets assume. Nothing here is in the code.

- **Paths.** One table of nodes (folders and files) keyed by the full normalized path, with the M1 rules per segment, at most 8 segments, and versions in a second table. Folder rename and move rewrite every descendant path in one transaction (#2).
- **API versions.** `/api/v2` carries paths. `/api/v1` keeps answering for files in the root folder (#2). From #6 on, every mutating route needs an app token.
- **One write path.** Every change to a file goes through `Storage`. The command interpreter (#4), the fixtures and demo workspace (#6) and restore (#5) call `Storage` methods and never run SQL, so the journal of #5 covers them without knowing about them.
- **Logic in Python.** Path rules, layout validation and clamping, the interpreter and the registry schema are Python modules with unit tests. The page mirrors what it needs.
- **Page.** ES modules loaded from the static manifest: an API client, the file browser (NEW-B), the window manager (#3), the terminal panel (#4), the apps and registry mirror (#6).
- **Migrations.** 2: nodes and versions (#2). 3: layout (#3). 4: journal (#5). Each is applied when missing, whatever the merge order. `MIGRATIONS` stays sorted by version and the latest version is its highest number (NEW-A). Today `LATEST_VERSION` is the last entry (`storage.py:37`), which is only correct for a sorted list.

## 7. What was run during preparation

Windows 11, Python 3.13.14, SQLite 3.50.4, prep worktree at `494e561`. No file under `browser_desktop/` or `tests/` was changed.

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -t .` | `Ran 78 tests in 30.320s`, `OK` |
| `python -m unittest tests.test_storage tests.test_static_assets` | `Ran 32 tests in 5.107s`, `OK` |
| `python -m unittest tests.test_storage.CrudTests.test_update_cas` | `Ran 1 test`, `OK` |
| `python -m browser_desktop --data-dir <scratch> --port 0` | printed `Serving on http://127.0.0.1:<port>/` |
| `curl -s http://127.0.0.1:<port>/api/v1/health` | `{"status": "ok", "version": "0.1.0", "schema_version": 1}` |
| HTTP run with `http.client` | `GET /` 200 with the CSP header; `/static/../storage.py` 404; fixtures 200 with `created` `["launch-notes.txt"]`, size 54, then `created` `[]`; save with base revision 1 gave revision 2; the same base again gave 409 `conflict` with `current.revision` 2; create 201; name `../x` 400 `invalid_name`; `DELETE` 405; foreign Host 403; foreign Origin on POST 403; `/api/v2/files` 404 |
| Kill the process, start again on the same data directory | both files listed, `launch-notes.txt` at revision 2 with the added line |
| Empty `--data-dir` | exit code 2, one line on stderr |
| Missing `--port` | exit code 2 (argparse) |
| Browser run, Chrome 157, `http://127.0.0.1:18793/` | load fixture, open, edit, Ctrl+S ("Saved launch-notes.txt (revision 2)"), Alt+N, create `scratch.txt`, markup shown as text, stale save gave the conflict group with the text kept, "Keep mine and save" gave revision 3, no overflow at 800x600 and at 500x640, data present after a server restart and reload, 15 requests all to `127.0.0.1`, console errors only for `/favicon.ico` (404) and the expected 409 |

Not run: Linux, Python 3.12, Firefox, 360 pixels wide, "Load latest", Up and Down and Esc, the unsaved-changes prompts, a screen reader, a contrast measurement.
