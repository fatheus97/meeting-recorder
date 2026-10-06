---
name: open-items
description: >-
  Report what the meetings left on the user for THIS project, and check it against what
  the repo actually shows. Reads the standing ledger (~/meetings/OPEN.md) and the record
  sections of recent meeting files (never the raw transcripts), then reconciles those
  items against the code, PRs and deploy state this session can see. Use when the user
  asks "what's on me", "what did the meeting leave me", "check the meeting result",
  "what's still open here", "am I blocked on anything" (or e.g. Czech "co mi zbylo"), or
  types /open-items. This is the cheap read-only consumer of the /meeting pipeline: a
  meeting is processed ONCE by /meeting, and every other project session uses this
  instead of re-running it. Read-only everywhere: it reports, it does not write.
---

# What the meetings left on me, checked against the repo

**Read `~/meetings/LEDGER.md` first.** It defines the item format (head line = current
truth, owner vs next-mover, `↳` history lines), the reading rules every consumer shares,
the project tag set, and ID allocation. It is the single source of those rules: do not
restate or diverge from them here.

`/meeting` processes each meeting **once**, in one session, and writes everything to
`~/meetings/`. This skill is how every *other* project session consumes that: a file read
plus a repo check, not another transcript grind. Never invoke `/meeting` to serve this
purpose; it costs a full transcript grind and would refuse anyway.

## Step 1 — Work out which project this is

From the working directory, the git remote, and the conversation, map it to a project tag
from `LEDGER.md`. If it is ambiguous, say what you assumed in one line rather than asking.

## Step 2 — Read the ledger

`~/meetings/OPEN.md`. Take the open items (`[ ]`, `[~]`):

- carrying this project's tag, primary or secondary;
- marked **UNOWNED** or **UNRESOLVED** that would block this project;
- under a *Threats* heading that name this project or its dependencies.

Note each item's ID, owner, next-mover, `seen` date and how many meetings it has survived.

## Step 3 — Read the records, never the transcripts

For meeting files that these items cite, read **only** the `## Record` section:

```bash
sed -n '/^## Record/,/^## Transcript/p' ~/meetings/<file>.md
```

**Never read past `## Transcript`.** That is an hour of raw speech, tens of thousands of
tokens, and the record already distills it. If you need a specific quote, grep for the
timestamp:

```bash
grep -n '^\[00:07:23\]' ~/meetings/<file>.md
```

`~/meetings/PEOPLE.md` is short and worth reading for who owns what.

## Step 4 — Reconcile against reality (this is the part only this session can do)

The ledger records what was *said*. This session can see what is *true*. For each item,
check the repo before reporting it:

- Already done? Look for the code, the merged PR, the deployed config. An item the meeting
  left open may have landed since. Say so, with the commit or PR as evidence.
- Blocked for a reason the meeting did not know about? Say that too.
- Impossible or much bigger than the meeting assumed? That is the most valuable thing you
  can report, because nobody in the room knew it.

Check `git log`, `gh pr list`, the actual files. Never guess from the item text alone.

## Step 5 — Report

```
## <project> — standing items from meetings

**On me, still real**
- `OI-2` … — why it is still open, what it blocks

**Already done since the meeting** (ledger is stale)
- `OI-n` … — landed in <commit/PR>

**Blocking me, owned by someone else**
- `OI-n` … — waiting on <person>, since <date>

**Threats that touch this project**
- `OI-n` …

**Dates**
- what has a hard date, and what that means for what is built
```

End with one line: whether anything in the ledger should be corrected, and the exact edit,
but **do not make it**. Ledger writes belong to `/meeting`, `/note`, the board, or the user
by hand; two sessions editing `OPEN.md` from stale copies is how items get lost.

## Constraints

- **Read-only. Everywhere.** No writes to `~/meetings/`, none to the repo. No commits, no
  branches, no PRs.
- Never read a `## Transcript` section.
- `~/meetings-personal/` is out of scope entirely: personal recordings stay out of the work
  ledger.
- If `~/meetings/OPEN.md` does not exist or has no items, say so in one line. It means no
  meeting has been processed yet, not that nothing is open.
