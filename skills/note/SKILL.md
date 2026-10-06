---
name: note
description: >-
  Log something that happened between meetings: a decision, a call, a corridor
  conversation, a blocker someone mentioned, a fact worth keeping. Appends to
  ~/meetings/NOTES.md and, when the note contains one, adds or updates an item in
  OPEN.md or a line in DECISIONS.md. Use when the user says "note that…", "just talked
  to X", "X said…", "we decided…", "for the record" (or e.g. Czech "zapiš si"), or types
  /note. This is the LIGHT path: no transcript, no subagent, no meeting file, no coaching
  tip. /meeting is for recorded meetings, this is for everything else. Fast by design.
---

# /note — capture something between meetings

**Read `~/meetings/LEDGER.md` first.** It defines the item format (head line = current
truth, owner vs next-mover, `↳` history lines), the reading rules every consumer shares,
the project tag set, and ID allocation. It is the single source of those rules: do not
restate or diverge from them here.

The ledger only moves when a meeting is processed. Most of what actually happens does not
arrive that way: a two-minute corridor answer, a chat reply, a decision taken on a call
nobody recorded. This is where that goes, and it should cost one tool call.

**Be fast. Ask nothing.** If something is ambiguous, record it with the ambiguity marked
rather than stopping to ask. A note that takes a conversation to file will not get filed.

## Step 1 — Read what you need, once

Re-read `~/meetings/OPEN.md` immediately before writing: several sessions may edit it and
your copy goes stale in minutes. Take the `<!-- next-id: N -->` counter from that read.
`~/meetings/PEOPLE.md` is worth a look when the note names someone unfamiliar.

## Step 2 — Split the note

One note can contain several kinds of thing. Sort each piece:

- **Context** → `~/meetings/NOTES.md`. Facts, explanations, things learned, who said what.
  Not everything is a task, and this is the half that usually gets lost.
- **A decision** (an owner and a change of state) → append one line to
  `~/meetings/DECISIONS.md` in its existing format.
- **A new item** (something open, blocked, owed or threatened) → a fresh `OI-` id in
  `OPEN.md`, counter bumped, **tagged** right after the id (one primary, at most two
  secondary, from the set in `LEDGER.md`). An untagged item is invisible to the board's
  project filter.
- **Movement on an existing item** → annotate that item's head in place, dated, exactly as
  `/meeting` does: `✅ **[24.3]** …` or `⚠ **[24.3]** …`. Flip the box to `[x]` only when
  the note plainly says it is finished.

Everything goes in `NOTES.md` as well, even when it also became an item: the note is the
narrative, the item is the tracking.

## Step 3 — Write

**ID allocation:** take `max(next-id, highest existing OI number + 1)` from a fresh read,
then run the duplicate check from `LEDGER.md`. Output must be empty; if not, renumber the
item YOU just added (never the older one), bump the counter, and say so.

`NOTES.md` entry format:

```
## 2025-03-24 — <short subject>

<the note, in the user's own words where they carry meaning; quotes verbatim in their language>

→ `OI-12` (new) · `OI-6` updated
```

Rules, same as the ledger's:

- **Never invent a date, a name or an owner.** `UNOWNED` and `no date` are real answers,
  and an unowned item is itself worth flagging.
- **Source it.** These notes have no timestamps and no recording: attribute to
  "<user>, <date>" so a later reader knows the provenance is first-hand testimony, not a
  transcript.
- **The user's account is ground truth.** If it contradicts the ledger, the ledger is what
  is wrong; correct it and mark it `CORRECTED <date>`.
- **Never assert repo state from talk.** If the note says something shipped, record that
  the user said so; verify with `gh`/`git` only if it is cheap, and say which you did.
- Writes go to `~/meetings/` only. No repos, no commits.

## Step 4 — Echo back, briefly

Three or four lines: what was recorded, which ids were created or touched, and anything
you deliberately left out. Not a report: the user is mid-flow and about to do something
else.

If the note contained nothing trackable, say so in one line and write only `NOTES.md`.
That is a normal outcome.
