---
name: wrap-up
description: >-
  Pre-archive loose-ends check for the current session. Sweep the working tree,
  branches, PRs, stashes, background processes and the repo's own record-keeping
  rules and the meetings ledger if there is one (proposing which OI items this
  session closed or moved), then report whether anything is still open or undocumented — so the
  session can be archived without losing work or context. Use whenever the user
  asks "is everything closed?", "is it all documented?", "anything left open?",
  "can I archive this?", "are we done here?", "loose ends?", "wrap up", or types
  /wrap-up — and also when the user signals they are finishing for the day and
  wants a final status before closing. READ-ONLY on the user's work: it reports
  and offers, it does not commit, push, merge, delete or clean up unless the user
  says so — with one exception, it clears up its own verification leftovers
  (throwaway worktrees, scratch branches) without being asked. Dependabot PRs are
  never reported as loose ends.
---

# Wrap-up — can this session be archived?

The user archives sessions and wants one honest answer before doing it: **is
anything still open, and is everything worth keeping written down somewhere that
outlives this conversation?**

## Why this exists

The user used to type that question by hand every time. The point is not to make
Claude *say* "all good" — it is to **verify**, because the two things that
actually get lost are (a) work that never left the working tree, and (b) reasoning
and decisions that only ever existed in the chat. A session transcript is not a
record. Git, the repo's docs, and the memory files are.

**Do not answer from memory of the conversation.** Run the checks. An "all clear"
that was not measured is worse than no check at all.

## Step 1 — Mechanical sweep (run these, in parallel)

In the current repo (skip gracefully if not a git repo):

```bash
git status --porcelain                    # uncommitted + untracked
git log --oneline @{u}..                  # commits not pushed (or: no upstream at all)
git stash list                            # stashes — see the warning below
git branch -vv                            # gone upstreams, stale local branches
gh pr list --state open --author @me      # open PRs — see the Dependabot rule below
gh pr status                              # their CI state at a glance
```

**Never report Dependabot PRs as loose ends.** They are a standing backlog that
exists whether or not this session happened, they arrive and close on their own
schedule, and listing them trains the user to skim the wrap-up. `--author @me`
already excludes them — so do not "helpfully" widen the query to
`gh pr list --state open` and then explain which ones to ignore. If a dependency
bump genuinely needs attention it is its own conversation, not a line in a
pre-archive check.

The one thing that *is* worth a line: a Dependabot PR **this session touched** —
reviewed, pulled, tested, approved. That is session work with an unfinished end,
and it gets reported like any other open PR.

Interpret rather than dump:

- **Uncommitted changes** — separate real work from deliberate local files
  (`.env`, gitignored scratch). Name the files, not the count.
- **Unpushed commits** — anything local-only is one machine failure from gone.
- **Stashes are the sharpest trap.** A stash goes stale silently: if `main` moved
  under it, applying it later can *revert merged work*. For each stash, say what
  it holds and whether it is still safe to apply, or should be dropped. Never
  advise `git stash pop` on a stash older than the session without diffing it
  first (`git diff stash@{n}`). Remember indices renumber after every drop —
  dropping `{0}` then `{1}` skips one; drop `{0}` repeatedly instead.
- **Open PRs** — for each: CI green or red, review posted or not, waiting on the
  user's merge call or on someone else. A PR waiting only on the user is the most
  common real loose end.
- **Merged PRs whose branch still exists** — say so; it is one command to tidy.

## Step 2 — Is anything still running?

Background tasks, monitors, dev servers and scheduled work this session started
do not survive archiving, and a half-finished one that nobody will see again is a
loose end. Check background task state, and list any server this session started
(with the port). Say plainly which will die on archive and whether that matters.

Two different things hide in here, so separate them. A **preview or dev server
you started for your own verification** is scaffolding — stop it in Step 5 and
name the port. A **task still doing real work** (a suite mid-run, a deploy, a
long build) is a genuine loose end: report it and let the user decide whether to
wait for it, because killing it is the one thing they cannot undo.

## Step 3 — Records the repo itself demands

Read the project's own contract (`CLAUDE.md` / `AGENTS.md` and any
`.claude/rules/*`) and check the record-keeping it requires — many repos require
more than commits: a status-board row or a worklog entry per meaningful block of
work, a changelog, a task tracker, or nothing.

Verify by looking, not by remembering: did this session's commits actually touch
those files? If a block of work landed without its record, that is the single most
valuable thing this skill can catch — the next session starts from those files.

## Step 3b — The meetings ledger (`~/meetings/OPEN.md`)

The meetings ledger tracks every open item across all projects in one file, and the
session that did the work is the only one that knows what moved. A PR merged here that
finishes an `OI-` item nobody ticks is how the ledger goes stale, one session at a time.
Skip this step silently if `~/meetings/OPEN.md` does not exist.

Read `~/meetings/LEDGER.md` first (item format, reading rules, tag set). Then re-read
`OPEN.md` and find the open items (`[ ]`, `[~]`) this session touched:

- items carrying this repo's project tag (the LEDGER.md tag table), primary or secondary;
- any `OI-` id named in this conversation, or in this session's commits and PR bodies;
- any PR number or branch this session opened or merged that an item's head or history names.

For each one, propose exactly one of these:

| Proposal | When |
|---|---|
| **close** `[x]` | this session's work finished it; cite the evidence (merged PR, commit on `main`), checked with `gh`/`git` now, not remembered |
| **update** | the state moved but is not done: a new head line with the current truth, the old head pushed down as `↳ [D.M]` |
| **history line** | touched, but the head is still true |
| **new item** | this session leaves something open for the user, or waiting on someone, with no item yet; tag it per LEDGER.md |

Leave untouched items alone: no bulk pass, no normalising old items.

**Evidence proposes, the user decides** (LEDGER.md reading rule 4). Put the proposals in the
report and write them only on the user's yes. One yes may cover the whole list, minus
anything they strike. Write by LEDGER.md's rules: re-read `OPEN.md` immediately before writing, never
change an item's id or tags, use the ID max rule for new items, and run its duplicate and
untagged checks afterwards. Diff against a copy taken just before the write, and confirm
only the intended lines changed: other sessions write the same file.

## Step 4 — What only exists in this conversation

This is the part no command can find, and it is the reason the check is worth
running. Sweep the session for:

- **Promises** — anything Claude said it would do, that it did not do.
- **Unanswered questions** — questions put to the user that never got an answer,
  and decisions taken verbally that are not written in the repo.
- **Findings worth outliving the session** — a diagnosed root cause, a measured
  number, a "this looks like a bug but is not", an owner's name, an upstream that
  is broken. If it would save the next session an hour, it belongs in the repo's
  docs (or memory, per the memory instructions) — not only in the transcript.
- **Deliberate deviations and shortcuts** — anything knowingly left simplified or
  unfinished, and whether that decision is recorded anywhere.

## Step 5 — Clear your own leftovers, without asking

A session that verified something usually leaves scaffolding behind: a throwaway
worktree, a scratch branch cut only to build in, a downloaded artifact in the
scratchpad. **That is your mess, not a loose end for the user to decide about.**
Reporting it as item 4 of a numbered list, with the command to remove it, just
makes the user paste back a command you could have run — so run it, then say
what you removed in one line.

**Clear, silently and without asking:**

- Worktrees this session created **for its own verification** — the tree is
  clean (`git -C <wt> status --porcelain` empty) and its branch holds nothing
  unique.
- Scratch branches this session created that hold **no unpushed commit** — a
  branch pointing at a commit already on `main`, or whose upstream is gone
  because you deleted the merged PR branch yourself.
- Scratch files in the session scratchpad, and any local dev server or preview
  **this session started** (name the port in the report).

**Never touch, even if it looks like yours:**

- Anything with uncommitted changes or an unpushed commit. If the tree is dirty
  or the branch holds work `main` does not, it stops being scaffolding — report
  it instead.
- **Stashes.** Never, under any circumstances, as part of a wrap-up. See the
  Step 1 warning; a wrong `drop` is unrecoverable and a wrong `pop` can revert
  merged work.
- Worktrees, branches or servers **another session** created. In a repo where
  parallel sessions are the norm, "there is a worktree I do not recognise" means
  leave it alone, not tidy it.
- Any remote branch, other than a merged PR branch you were told to delete.
- The user's own branches, however stale their upstreams look. A backlog of
  `gone` upstreams is theirs to prune, and mentioning it once in passing is
  enough — it is not a task and not yours to clear.

The test is ownership plus emptiness, and **both** are required: did this
session create it, and does removing it destroy nothing? If you cannot answer
yes to both from a command's output rather than from memory, report it and let
the user decide.

## Step 6 — Report

Keep it short. Two shapes only:

**Everything closed** — say so in one line, then a two-to-four-line summary of
what the session landed (merged PRs, what is on `main`, what was recorded where),
so the user archives knowing what they are archiving.

Ledger proposals from Step 3b count as open. When there are any, they are one numbered
item listing each `OI-` id with its proposal and evidence, ending "say yes to apply".

**Something open** — a numbered list, most consequential first. One line each:
what is open, why it matters, and the exact command or action that closes it. No
essays, no repetition of what is already fine.

Then end with the one question the checks cannot answer:

> Anything you decided, promised someone, or are waiting on that is not written
> down in the repo?

## Rules

- **Read-only on the user's work.** Report and offer. Do not commit, push, merge,
  delete their branches, drop stashes or write docs as part of the check — the
  user may want the loose end left open on purpose. Offer, then act only when
  asked. The single exception is Step 5: your own verification scaffolding, which
  you clear without asking because it was never the user's decision to make.
  Ledger writes (Step 3b) are offer-then-act like everything else: proposed in the
  report, written on the user's yes.
  When in doubt about which side of that line something falls on, it is theirs.
- **Do not invent work.** If it is all clean, say it is all clean in one line.
  Padding a wrap-up with hypothetical follow-ups trains the user to skip it.
- **Be specific.** "Uncommitted changes in `src/foo.ts` and `docs/bar.md`" beats
  "some uncommitted changes". File names, PR numbers, ports, commands.
- **Distinguish "open" from "broken".** A PR waiting on a merge call is open; a
  red CI is broken. Say which.
