---
name: meeting-prep
description: >-
  Build the user's agenda for an upcoming meeting: what to say, what to ask for, what to
  chase, and what not to let slide. Composes three sources: a short "what I did" status
  (from a status-report skill if you have one, otherwise from merged PRs since the last
  meeting), the standing ledger (~/meetings/OPEN.md) for what is open, stale, blocking or
  undated, and the last coaching tip so the user walks in aware of it. Use when the user
  says "prepare me for the meeting", "what should I say tomorrow", "agenda", "prep for the
  meeting" (or e.g. Czech "co mám říct na schůzce"), or types /meeting-prep. Read-only: it
  reports, it never writes to the ledger. Run it BEFORE the meeting; /meeting processes the
  transcript after.
---

# Agenda for the next meeting

**Read `~/meetings/LEDGER.md` first.** It defines the item format (head line = current
truth, owner vs next-mover, `↳` history lines), the reading rules every consumer shares,
the project tag set, and ID allocation. It is the single source of those rules: do not
restate or diverge from them here.

Not a report. A thing to walk in holding.

The usual failure is not forgetting what you did. It is **discounting your own status**,
**accepting non-answers to your asks**, and **leaving with undated commitments** while
others leave with dates. `~/meetings/COACHING.md` records which of these this user actually
does. This skill exists to put them on a page before the user sits down.

Write anything the user will **say out loud** in the language the meeting is held in, so
they speak it rather than translate it live. Your own framing around it can stay in the
user's working language.

## Step 1 — Window

The window is **since the last processed meeting**, not a fixed 7 days:

```bash
ls -1 ~/meetings/20*.md | tail -2
```

Use the date of the most recent meeting file. If none, fall back to 7 days.

## Step 2 — What I did

If you have a status-report skill (a weekly report, a changelog generator), invoke it with
that window. Otherwise summarise the user's merged PRs since the window start across the
repos this session can see (`gh pr list --state merged --author @me --search "merged:>=DATE"`),
plus anything recorded in `~/meetings/NOTES.md` since then.

Then **cut it down to a spoken status**: 30–60 seconds, three or four things, outcomes not
activity. What gets cut is what the user would have apologised for including.

Add one line naming the single most substantial thing in there: the item the user is most
likely to bury. A production incident handled well, compressed into a subordinate clause,
is the classic case. That line exists so it does not happen.

## Step 3 — The ledger

Read `~/meetings/OPEN.md` and produce four lists. Every entry keeps its `OI-` id.

1. **Mine, still open**: next-mover `me`, with age in meetings. Anything the user can close
   with one sentence, mark `→ close it out loud`.
2. **Blocking me, owned by someone else**: next-mover `waiting on X`; who, since when, how
   many meetings. This is the chase list, and each one needs a name to say out loud.
3. **Unowned but on my critical path**: the dangerous category. These die silently because
   nobody thinks they are theirs.
4. **Going stale**: untouched for 2+ meetings. If nobody raises it today it should be raised
   *by the user*, or explicitly dropped. Silence is not a decision.

## Step 4 — The asks (the part that matters)

For each thing the user needs out of this meeting, write one line they can actually say,
plus what a real answer looks like:

```
ASK: <the question, short enough to say in one breath>
  from: <person>
  a real answer = <owner> + <date>. Anything else is a non-answer.
  if deflected: <the one follow-up sentence>
```

A non-answer sounds like "sure, let's sort that out with the others later": agreement with
no owner and no date. If the ledger shows the user accepted one of those before on the same
item, say so next to the ask.

## Step 5 — What I committed to last time

From the previous meeting's `## Record` section (read that section only, **never the
`## Transcript`**), list what the user agreed to and whether it had a date. For each:

- done → say so, one sentence, out loud
- not done → bring a date *before* someone asks for one
- no date → this is the one to fix today

## Step 6 — Last tip

Read the newest entry in `~/meetings/COACHING.md` and restate it in one line. Not to
re-teach it: to put it in the user's head twenty minutes before it matters.

## Output

```
# Meeting prep — <date>

## What I'll say (30–60 s)
<speakable, 3–4 bullets>
Don't bury: <the one thing>

## What I must ask
<the asks, with the owner+date test>

## What to chase
<OI-ids, person, how long>

## What I still owe, undated
<undated commitments from last time>

## About to go stale
<stale items: raise or drop>

## Last time's tip
<one line from COACHING.md>
```

Keep the whole thing short enough to read on a phone walking to the room.

## Constraints

- Read-only. Never write to `~/meetings/`. The ledger is `/meeting`'s to update, after.
- Never read a `## Transcript` section.
- If `OPEN.md` has no items, say so plainly: it means no meeting has been processed yet,
  and step 2 alone is the prep.
- Do not invent asks. If the user has nothing to ask for, say that; it is a useful finding.
