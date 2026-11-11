---
name: daily-brief
description: >-
  Weekday morning brief from the meetings ledger and the repos: what is dated and
  imminent, what changed in the ledger since yesterday, what landed in the repos that may
  close ledger items, and who owes the user what. Meant to run as a scheduled task (e.g.
  weekdays 07:30); also works on demand ("morning brief", "daily brief", /daily-brief).
---

# Daily brief

**This is meant for a scheduled task.** In the Claude Code desktop app, create a scheduled
task that runs this skill on weekday mornings (or use whatever scheduler you have that can
start a Claude Code session). It also works when invoked by hand. It diffs against a
snapshot it wrote on its previous run, so it is most useful when it runs every day.

Produce the user's morning brief from the meetings ledger and the repos. Keep it short
enough to read on a phone. **READ-ONLY everywhere**: the only file you may write is the
snapshot named below. Never commit, push, branch, or modify a repo; `git log` and
`gh pr list` only.

## Sources

- `~/meetings/LEDGER.md`: **read this first, and it wins on any conflict.** It defines the
  item format (head line = current truth, owner vs next-mover, `↳` history lines), the
  reading rules shared by every consumer, and ID allocation. Rules restated below are a
  convenience copy; where they differ, LEDGER.md is correct.
- `~/meetings/OPEN.md`: the standing ledger. `[ ]` open, `[~]` changed, `[x]` closed
  (ignore closed).
- `~/meetings/DECISIONS.md`: append-only decision log, for dates and context.
- `~/meetings/NOTES.md`: between-meeting notes and corrections from the user.
- `~/meetings/PEOPLE.md`: who these people are.
- `~/meetings/.daily-snapshot.md`: yesterday's copy of OPEN.md that YOU wrote on the last
  run. If it does not exist, this is the first run: skip the diff, say so in one line, and
  still do everything else.
- The user's git clones. **Set this once:** the default here is every repo directly under
  `~/code/`; change the glob in section 3 to wherever the clones live.

Never read a `## Transcript` section of any meeting file. Read a `## Record` section only
if you need context for a specific item.

## What to produce

**1 — Due soon.** Only items carrying a REAL date within the next 7 days, or already past.
Compute against today's actual date. Fixed dates the user recorded in `NOTES.md` or
`DECISIONS.md` (a launch, a release, a leave) count. Overdue first, marked overdue. **Only
items where the user has the next move or is directly blocked by it**: another person's own
task that does not block the user does not belong here; mention it in section 5 only if
the user is waiting on it. For each item, say in two words who moves next (`me` /
`waiting on X`). If nothing is dated inside the window, write "Nothing with a fixed date
this week" and move on; never pad this section with undated items.

**2 — Ledger changes.** Diff `~/meetings/OPEN.md` against `~/meetings/.daily-snapshot.md`:
newly added `OI-` ids, items that flipped to `[x]` or `[~]`, items whose text gained a ⚠
or a date. One line per change, with the id. **If nothing changed, write exactly one line
saying so and list nothing.** This rule matters more than completeness: a brief that
repeats itself daily stops being read.

**3 — Landed in the repos** (the ledger's blind spot).

Between meetings, reality moves in the repos and the ledger does not follow. It is normal
to find several items still open, one even reading "next quarter", that merged code
resolved days ago and nobody mentioned.

Find what landed since the last run. Merged PRs, from `gh`:

```bash
for r in ~/code/*/; do [ -e "$r/.git" ] || continue; echo "== $(basename $r)"; (cd "$r" && gh pr list --state merged --search "merged:>=YYYY-MM-DD" --limit 20 --json number,title,author --jq '.[] | "\(.number) \(.title) — \(.author.login)"' 2>/dev/null); done
```

`gh` sees only GitHub, and only merges. Work still on a branch, or in a repo hosted
elsewhere (Azure DevOps), shows up only as commits, so also list the commits on every local
branch:

```bash
for r in ~/code/*/; do [ -e "$r/.git" ] || continue; echo "== $(basename $r)"; (cd "$r" && git log --all --no-merges --since=YYYY-MM-DD --date=short --format='%h %ad %s'); done
```

In both loops use the date of the previous run (the snapshot file's modification date), or
yesterday if there is none. **For merges, trust `gh` over the local `git log`**: local `main`
lags behind the remote, so `git log` misses what others merged since the last pull. The
commit loop is for the user's own work, merged or not.

Then match merged PRs and commits against **open** `OI-` items by subject, and report the
matches as **candidates**:

`OI-12 looks done: PR #42 "…" (merged 21.3). Confirm?`
`OI-15 looks done: commit 3f2a91c "…" (21.3). Confirm?`

Hard rules for this section:
- **Never close anything. Never edit the ledger.** Flag candidates only; the user or
  `/meeting` confirms. A merged PR or a commit is evidence, not proof: the item may be
  broader than the change.
- Cap at five candidates, strongest first. Say how many more merged PRs and commits went
  unmatched.
- Also flag the reverse when you see it: an item the ledger calls done or in progress that
  the repo contradicts.
- If `gh` is unavailable or unauthenticated, say so in one line and skip the PR loop; do not
  fall back to guessing. The commit loop still runs.

**4 — On you.** Items whose next-mover is `me` (or, with no next-mover, owned by the user),
ranked by: blocking someone else > dated > blocking another item > age. **Cap at five**,
say how many more exist. Prefer items the user can close in one action.

**5 — Who owes whom.** Per person: for each person who owns an item the user is waiting
on, one line: name, what, since when, how many meetings it has survived. Then a final line
starting `You:` naming what other people are waiting on *the user* for.

**6 — One line.** The single most useful thing to do today, and why. Not a summary of the
above.

## Rules

- **The owner field is often stale: read the whole item, newest annotation wins.**
  `CORRECTED` annotations and board-written `↳ [D.M] <user>: …` lines override the head
  text. Also read `~/meetings/NOTES.md`. A typical miss: the head says "the user e-mails X"
  while a later note says the user is actually waiting for X's e-mail.
- **Duplicate-ID check:** run the duplicate check from `LEDGER.md`. If non-empty, one line
  at the end naming the ids (do not fix: read-only).
- Write in the user's preferred language; quote `OI-` ids so they can be grepped.
- Never invent a date. No date, no place in section 1.
- Never claim an item is done unless it is marked `[x]` in the ledger: section 3 proposes,
  it does not decide.
- Total length: aim under 45 lines. If longer, cut section 4 first, then section 5.

## Last step, always

Copy the current `~/meetings/OPEN.md` over `~/meetings/.daily-snapshot.md` so tomorrow can
diff against today. Do this even if the brief came out empty.
