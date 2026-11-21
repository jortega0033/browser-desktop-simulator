# Browser Desktop Simulator

A small, fully offline, single-person workbench that runs in your browser and explores how a local interactive desktop manages focus and virtual data safely. The M1 baseline provides a **File list** and a **Text editor** over named plain-text files stored in SQLite.

M1 implements virtual text-file editing. See the baseline verification below.

## Requirements

Python 3.12 (standard library only). No install step, no network access beyond loopback.

## Launch

Linux:

```bash
python3 -m browser_desktop --data-dir ./data --port 8765
```

Windows (PowerShell or cmd):

```powershell
python -m browser_desktop --data-dir .\data --port 8765
```

Then open http://127.0.0.1:8765/. Use `--port 0` to pick a free port (the chosen URL is printed). The server binds `127.0.0.1` only. Stop with Ctrl+C. An empty `--data-dir` value, or a path that is an existing file, exits with code 2.

## M1 smoke steps

1. Start the server with a fresh data directory and open the page.
2. Choose **Load example files**; `launch-notes.txt` appears in the File list. Open it: three lines, two of them containing `orbit`.
3. Add a line in **File text** and press **Save** (or Ctrl+S). The status reads `Saved launch-notes.txt (revision 2)`.
4. Choose **New file**, type `scratch.txt` in **File name**, some text in **File text**, press **Save**. The file appears in the list.
5. Stop the server (Ctrl+C), start it again with the same `--data-dir`, reload: both files and their text are still there.
6. Resize the window to 800×600: the page should not scroll as a whole; the panels scroll internally.
7. Keyboard: Alt+N new file, Up/Down in the list, Esc from the editor back to the list.

## Limits

File name 1–64 chars from `A-Za-z0-9._-` (starting alphanumeric); text up to 65,536 UTF-8 bytes; request body up to 131,072 bytes; up to 500 files. Plain text only. A save based on a stale revision is refused with a conflict; the editor keeps your text and lets you load the latest or save yours over it.

## Local persistence

Everything is stored in `<data-dir>/desktop.sqlite3` (WAL mode). The app stores data only in that directory, runs no host commands and starts no other processes.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

(`python` on Windows.) Tests use temporary directories and ephemeral ports.

## Expected future scope

Scoped virtual folders with rename/copy/move and versions; a window manager with keyboard focus and persisted, clamped bounds; a sandboxed in-app command interpreter with string pipelines; a crash-safe write journal with revision recovery; a typed app registry and a complete offline browser/editor/preview/terminal workflow. None of these are implemented in M1.

## Documentation

Product and technical spec: [docs/PRD.md](docs/PRD.md).

## Baseline verification

- Windows with Python 3.13.14 and Ubuntu 24.04 WSL with Python 3.12.3 each passed 78 unit and API tests. WSL unit tests used temporary storage on tmpfs.
- Chrome 157 verified virtual file editing with external requests blocked. The saved file reopened with the expected content after a server restart.
