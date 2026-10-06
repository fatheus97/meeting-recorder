# The ledger contract

How `OPEN.md` is written and read. **Every skill that touches it reads this file first**:
`/meeting`, `/note`, `/open-items`, `/meeting-prep`, `/wrap-up` and the daily brief. If the
rules live in several skills they drift; they live here.

The ledger directory defaults to `~/meetings/` (where `meetrec.py` also writes transcripts).
Copy this file there next to `OPEN.md`, so the skills find it at `~/meetings/LEDGER.md`.
The repo's `ledger/example/OPEN.md` is a small synthetic ledger that shows every shape described below.

## Item format

```
- [ ] `OI-12` #website #handover <what is true NOW> — **owner** — <next-mover> — seen YYYY-MM-DD [00:14:08]
  ↳ [24.3] <dated history line, append-only, newest first>
  ↳ [17.3] <older history line>
```

`[00:14:08]` is the transcript timestamp the item came from (omit it for items from `/note`).
History dates are `[day.month]`.

**Project tags** sit immediately after the id: exactly **one primary** (the project that
owns the work), then at most two secondary. Tags are a fixed set that you define once; do
not invent new ones per meeting. Lowercase, `[a-z_-]` after the `#`.

The table below is an **example**. Replace it with your own projects:

| Tag | Owns |
|---|---|
| `#website` | the public site: pages, copy, its CI and deploy |
| `#billing` | invoicing, payments, the accountant's exports |
| `#org` | people, process, meetings, the ledger itself |
| `#handover` | *secondary only, optional*: work that must be closed or transferred before you leave a role or project |

Pick the primary by **where the work is actually done**: banner copy typed into a vendor's
admin panel belongs to the project that owns that account; the same banner removed in code
belongs to the repo. Closed items keep their tags, because filtering history by project
matters.

**Box:** `[ ]` open · `[~]` open but shape/owner/condition moved · `[x]` closed.

**Head line = current truth, one line.** Not the original claim. When an item is corrected,
**rewrite the head** and push the superseded text down as a `↳ [date]` history line. Never
delete history: corrections get reversed, and a diagnosis recorded as discarded is what
stops it from being proposed again next week.

**Owner** = who is accountable. **Next-mover** = who acts next. They differ often, and
conflating them is how another person's task ends up on your urgent list:

| Next-mover | Meaning |
|---|---|
| `me` | you act next: your queue |
| `waiting on X` | X acts next, and you are blocked by it: your chase list |
| `—` | neither; tracked for awareness only |

An item owned by **Bob** whose next-mover is `me` is Bob's work, but the next move is you
pinging him. Both facts matter and neither replaces the other.

**Annotations** on an existing item go at the end of the head, dated:
`✅ **[24.3]** …` (progress) or `⚠ **[24.3]** …` (problem). The board treats anything from
the first such mark onward as an annotation, not as the head text.

**Missing next-mover** is normal on older or hand-written items. Infer it; do not rewrite
the item just to add it. Items get normalised as they are touched, never in a bulk pass.

**Sections** (`##` / `###` headings) are free-form: group by project, by meeting, whatever
reads well. Two words in a heading carry meaning: an item under a heading containing
*precondition* is a precondition, under *threat* a threat; everything else is a task.

## Reading rules (the same for every consumer)

A list of "what's on me" must mean the same thing in the brief, `/open-items` and
`/meeting-prep`, or the user gets three answers to one question.

1. **Read the head line, not the accumulated tail.** The tail is history.
2. **Filter by next-mover, not by owner.** `me` is the queue; `waiting on X` is the chase
   list; `—` appears in neither unless specifically asked for.
3. **Dated means dated.** An item with no date never enters a "what's urgent" section. No
   inventing dates.
4. **Never close an item from evidence alone.** Merged PRs, "sounds done", a passing
   mention: all of these propose, they do not decide. Only the user or `/meeting` closes.
   (Repo state asserted from talk is wrong often enough to make this a rule.)
5. **Cap and say what was cut.** Five items plus "and 14 more" beats 19 items.

## ID allocation

Several sessions may append concurrently. **Re-read `OPEN.md` immediately before writing**
and allocate `max(next-id, highest existing OI number + 1)`, where `next-id` is the
`<!-- next-id: N -->` counter at the top of the file. The counter alone is not safe: it
goes stale when two writers race. After writing, verify:

```bash
grep -oE '^- \[.\] `OI-[0-9]+`' ~/meetings/OPEN.md | grep -oE 'OI-[0-9]+' | sort | uniq -d
```

Empty output means no duplicates. If not, renumber the item **you** just added (never the
older one, other lines may reference it) and bump the counter.

Then check every item carries a project tag. The board files an untagged item under
**no project**, where nobody filters for it:

```bash
grep -nE '^- \[.\] `OI-[0-9]+` +[^#]' ~/meetings/OPEN.md
```

Empty output means every item is tagged.

## The board

The repo's `ledger/board.py` is a local web UI over `OPEN.md` (stdlib only, binds 127.0.0.1:8765). Its
actions (done, waiting on, mine, hand over, note) each append one `↳` history line signed
with `--me`, and edit the head in place only when it has the full
`— **owner** — <next-mover> — seen …` shape. A board-written line like
`↳ [24.3] Alice: waiting on Bob` therefore sets the next-mover of an item whose head lacks
one. Every write re-reads the file under a lock, is checked before it lands, and is atomic.

## Files

| File | What it holds | Who writes |
|---|---|---|
| `OPEN.md` | Live items | `/meeting`, `/note`, `/wrap-up` (on the user's yes), the board, hand edits |
| `DECISIONS.md` | Append-only decisions | `/meeting`, `/note` |
| `NOTES.md` | Narrative between meetings | `/note` |
| `COACHING.md` | One behaviour note per recorded meeting | `/meeting` only |
| `PEOPLE.md` | Roster; hand-corrected, outranks inference | any, carefully |
| `<date>-<slug>.md` | Per-meeting record + raw transcript | `meetrec.py`, then `/meeting` |

Empty skeletons of the first five are in the repo's `ledger/templates/`. Nothing outside the ledger directory
is ever written by these skills.
