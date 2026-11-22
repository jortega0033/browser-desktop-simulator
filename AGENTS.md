# AGENTS.md

The full repository instructions are in [CLAUDE.md](CLAUDE.md). This file repeats only what an agent needs before it reads that.

## Test commands

```
python -m unittest discover -s tests -t .
```

(`python3` on Linux.) Run it from the repository root. Python 3.12 or newer, standard library only. There is no lint step, no build step and no package manifest. Do not add pip or npm dependencies.

## Run

```
python -m browser_desktop --data-dir ./data --port 8765
```

The server binds `127.0.0.1` only. `--data-dir` and `--port` are both required. Stop it with Ctrl+C.

## Ticket work

To implement an issue, follow the steps in [.claude/skills/implement-ticket/SKILL.md](.claude/skills/implement-ticket/SKILL.md) and the section "Agent roles and ticket implementation" in [CLAUDE.md](CLAUDE.md). Each role file in `.claude/agents/` starts with a section "In this repository"; an agent that cannot launch those roles reads that section as the checklist for the step and says in the pull request that it did the step itself. The code review and the acceptance check against evidence run on every ticket.

## Loop conventions

- The loop runs at L1: report-only, started by hand. It proposes; it does not label, comment, close, edit source, push or merge.
- No scheduler and no workflow file is installed. Do not add one without the owner's approval.
- See [LOOP.md](LOOP.md) for the manual command and the human gates.
