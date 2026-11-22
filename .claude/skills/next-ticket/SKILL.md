---
name: next-ticket
description: Owner-started driver that takes one ticket of epic #1 up to a ready pull request. Starting it is the owner's go signal.
disable-model-invocation: true
argument-hint: "[issue number]"
---

# Next ticket

Only the owner starts this skill, with `/next-ticket` or `/next-ticket <issue number>`. Starting it is the owner's request, for this run, to push the ticket branch and open the pull request; where `CLAUDE.md` says not to push or open a pull request unless the owner asked, this run counts as that request. It runs one ticket and stops. It never merges, never releases, and never starts another run.

Epic: issue #1, a `tracking` container: it is never picked. Order from the epic table: #7, #2, #8, #4, #5, #3, #6, #11, #9; when a ticket has sub-issues, its sub-issues in their listed order replace it. Labels: `status:ready`, `status:blocked`, `status:in-progress`, `needs-decision`.

## Steps

1. **Refresh the queue.** `gh issue list --state open --limit 100` and `gh issue view` on the epic's children; list sub-issues with `gh api repos/jortega0033/browser-desktop-simulator/issues/<n>/sub_issues`. A `status:blocked` ticket whose blockers are all closed becomes `status:ready` (`gh issue edit <n> --add-label status:ready --remove-label status:blocked`). A parent whose sub-issues are all closed is closed with a comment.
2. **Pick leaf tickets only.** A ticket labelled `tracking` or with open sub-issues is a container and is never picked. With an issue number, use that ticket if it is open, not blocked and a leaf; if it is a `tracking` parent or has open sub-issues, refuse and list its open sub-issues. Without a number, take the first `status:ready` leaf ticket that is neither `status:in-progress` nor `needs-decision`, in the order of the epic table (parents), then the order of the sub-issues inside each parent. If none qualifies, say so and stop.
3. **Claim.** Add `status:in-progress` to the ticket.
4. **Worktree and branch.** From the repository root, `git fetch origin` and `git worktree add ../browser-desktop-simulator-worktrees/<number>-<short-slug> -b <number>-<short-slug> origin/main`, as the Git workflow in `CLAUDE.md` says (one branch per issue, `<issue-number>-<short-slug>`). Work only inside that worktree. Never work on `main`.
5. **Implement.** Follow `.claude/skills/implement-ticket/SKILL.md` completely: the roles, the checks, the review gate and the acceptance gate.
6. **Pull request.** Run the local checks, then write the review material: before calling the gates, write `git diff --stat origin/main...HEAD`, `git diff origin/main...HEAD` and the check outputs to `.claude/state/review/` in the ticket worktree and name those files in the request to Code Reviewer and Reality Checker (they have no shell). Run both gates, then push the ticket branch and open a draft pull request (`gh pr create --draft`) with `.github/pull_request_template.md`. If the ticket is the last open sub-issue of a parent, the pull request says `Closes #<sub-issue>` and `Closes #<parent>`. The review gate hook blocks `gh pr create` and `gh pr ready` until the gate roles have run after the last code edit. Never run a gate half way: if a gate cannot pass, keep working or stop and report; do not open or ready the pull request.
7. **Wait for CI without polling.** Bind the pull request to the session when the app offers it, then end the turn with the line "Draft pull request #N is waiting for CI". Do not loop, sleep or watch. When the session is woken (a CI event, or the owner says "continue"), read `gh pr checks <n>` once: green, then mark it ready (`gh pr ready`; you check this, not Reality Checker); red, then fix, re-run the local checks and both gates, and push; still running, then end the turn again with the same line.
8. **Report.** Comment on the issue with the pull request link, the CI run link and the evidence summary. List any acceptance step that needs a person under "Owner checks" in the pull request. Leave `status:in-progress` on the ticket.

## Never

- Merge, enable auto-merge, push to `main`, force push, tag or release. Only the owner merges and releases.
- Start a second ticket in the same run.
- Edit CI, `.claude/` configuration or Loop files unless the ticket says so.
- Settle a `needs-decision` ticket by guessing: stop and say what the owner must decide.
