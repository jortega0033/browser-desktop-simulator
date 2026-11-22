---
name: next-ticket
description: Owner-started driver that takes one ticket of epic #1 up to a ready pull request. Starting it is the owner's go signal.
disable-model-invocation: true
argument-hint: "[issue number]"
---

# Next ticket

Only the owner starts this skill, with `/next-ticket` or `/next-ticket <issue number>`. Starting it is the owner's request, for this run, to push the ticket branch and open the pull request; where `CLAUDE.md` says not to push or open a pull request unless the owner asked, this run counts as that request. It runs one ticket and stops. It never merges, never releases, and never starts another run.

Epic: issue #1. Dependency order from the epic: #7, #2, #8, #4, #5, #3, #6, #9. Labels: `status:ready`, `status:blocked`, `status:in-progress`, `needs-decision`.

## Steps

1. **Refresh the queue.** `gh issue list --state open --limit 100` and `gh issue view` on the epic's children. A `status:blocked` ticket whose blockers are all closed becomes `status:ready` (`gh issue edit <n> --add-label status:ready --remove-label status:blocked`).
2. **Pick.** With an issue number, use that ticket if it is open and not blocked. Without one, take the first `status:ready` ticket in the epic's dependency order that is neither `status:in-progress` nor `needs-decision`. If none qualifies, say so and stop.
3. **Claim.** Add `status:in-progress` to the ticket.
4. **Worktree and branch.** From the repository root, `git fetch origin` and `git worktree add ../browser-desktop-simulator-worktrees/<number>-<short-slug> -b <number>-<short-slug> origin/main`, as the Git workflow in `CLAUDE.md` says (one branch per issue, `<issue-number>-<short-slug>`). Work only inside that worktree. Never work on `main`.
5. **Implement.** Follow `.claude/skills/implement-ticket/SKILL.md` completely: the roles, the checks, the review gate and the acceptance gate.
6. **Pull request.** Push the ticket branch, open the pull request with `.github/pull_request_template.md`, and mark it ready only after both gates have passed on the current diff and CI is green on it. The review gate hook blocks `gh pr create` and `gh pr ready` until the gate roles have run after the last code edit. Never leave a gate open: if a gate cannot pass, keep working or stop and report; do not open or ready the pull request.
7. **Report.** Comment on the issue with the pull request link and the evidence summary. Leave `status:in-progress` on the ticket.

## Never

- Merge, enable auto-merge, push to `main`, force push, tag or release. Only the owner merges and releases.
- Start a second ticket in the same run.
- Edit CI, `.claude/` configuration or Loop files unless the ticket says so.
- Settle a `needs-decision` ticket by guessing: stop and say what the owner must decide.
