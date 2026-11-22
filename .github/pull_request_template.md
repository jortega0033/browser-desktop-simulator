## Ticket

Closes #

## What changed

## Evidence

Each command and its result (paste real output; see `CLAUDE.md`, "Evidence before a ticket is called done").

```
python -m unittest discover -s tests -t .
```

## Agent roles run

| Role | Asked | Verdict |
|---|---|---|
| Code Reviewer (review gate) | | |
| Reality Checker (acceptance gate) | | |

## Risks and rollback

## Checklist

- [ ] CI is green on this diff
- [ ] Tests added or changed for each acceptance criterion
- [ ] PRD and README updated where a contract or the page changed
- [ ] UI changes checked against `docs/ui-quality.md`
- [ ] Copy and documentation went through the `unslop` skill
- [ ] One line added to `CHANGELOG.md`
- [ ] No dependency, external URL, host command or non-loopback listener added
