# meeting-recorder

Record a meeting on macOS, get a speaker-labeled transcript, and turn it into a standing
ledger of open items that Claude Code keeps honest between meetings.

```
meetrec.py record ──► ~/meetings/<date>-<slug>.md ──► /meeting ──► ~/meetings/OPEN.md (+ DECISIONS, COACHING)
                                                                        │
     /note (between meetings) ──────────────────────────────────────────┤
                                                                        ▼
               board.py (local web UI) · /open-items · /meeting-prep · /wrap-up · daily brief
```

| Piece | What it does |
|---|---|
| `meetrec.py` | Records audio, transcribes it with the Soniox async API (Czech/English by default), writes a markdown transcript with `Speaker N` turns. |
| `skills/meeting` | `/meeting`: turns a transcript into a record (decided / open / preconditions / threats, each with a timestamp), reconciles it against the ledger, adds one coaching tip. One run per meeting. |
| `skills/note` | `/note`: the light path for things that happen between meetings. |
| `skills/open-items` | `/open-items`: read-only "what's on me for this project", checked against the repo. |
| `skills/meeting-prep` | `/meeting-prep`: what to say, ask and chase at the next meeting. |
| `skills/wrap-up` | `/wrap-up`: pre-archive loose-ends check for any session; proposes ledger updates for what the session moved. |
| `skills/daily-brief` | Morning brief: due soon, ledger changes, merged PRs that may close items, who owes whom. Meant for a scheduled task. |
| `ledger/LEDGER.md` | The contract every skill and the board read: item format, owner vs next-mover, reading rules, ID allocation, project tags. |
| `ledger/board.py` | Local web board over `OPEN.md` (stdlib only): views, filters, and one-click done / waiting on / mine / hand over / note. |
| `ledger/templates/` | Empty `OPEN.md`, `NOTES.md`, `DECISIONS.md`, `COACHING.md`, `PEOPLE.md`. |
| `ledger/example/OPEN.md` | A small synthetic ledger showing every item shape. |

**Your data never lives in this repo.** Transcripts, audio and the ledger live in
`~/meetings/` (personal recordings in `~/meetings-personal/`). The repo holds only code,
skills and empty templates; `.gitignore` also keeps audio, keys, `config.json` and any
stray root-level `.md` out of git.

## Install

macOS, Python 3.11+, [`uv`](https://docs.astral.sh/uv/) (meetrec's one dependency installs
on first run), `ffmpeg` (`brew install ffmpeg`), [Claude Code](https://claude.com/claude-code),
and `gh` if you want the repo checks in the skills.

```sh
git clone https://github.com/fatheus97/meeting-recorder.git && cd meeting-recorder
./meetrec.py selftest
python3 ledger/board.py --selftest

# the ledger: contract + empty files (-n never overwrites an existing ledger)
mkdir -p ~/meetings
cp -n ledger/LEDGER.md ledger/templates/*.md ~/meetings/

# the skills (symlink instead of cp if you want `git pull` to update them)
mkdir -p ~/.claude/skills
cp -Rn skills/* ~/.claude/skills/   # -n: never overwrites a skill you already have
```

Then edit `~/meetings/LEDGER.md`: replace the example tag table with your own projects.
Optionally seed `~/meetings/PEOPLE.md` with the people you meet; attribution runs on it.

**Different directory?** Everything defaults to `~/meetings`. To move it, change
`MEETINGS` (and `PERSONAL`) in `meetrec.py`, pass `--ledger PATH/OPEN.md` to `board.py`, and replace
`~/meetings` in the installed skills
and the copied contract
(`sed -i '' 's|~/meetings|~/somewhere/else|g' ~/.claude/skills/*/SKILL.md ~/somewhere/else/LEDGER.md`).

## The loop

1. **Before** a meeting: `/meeting-prep` in a Claude Code session.
2. **During**: `./meetrec.py record --title "Weekly sync"`, Ctrl-C at the end.
3. **After**: `/meeting` in the session that knows the project best (or `/meeting --dry-run`
   the first time). It writes the record into the transcript file and updates `OPEN.md`,
   `DECISIONS.md`, `COACHING.md`. Other project sessions use `/open-items`; they never
   re-run `/meeting`.
4. **Between** meetings: `/note we decided X` for calls and chats that were not recorded.
5. **Every morning**: the daily brief, as a scheduled task (see below).
6. **End of a session**: `/wrap-up` before archiving it.
7. **Any time**: the board.

## The board

```sh
python3 ledger/board.py --me "Alice"                         # http://127.0.0.1:8765/
python3 ledger/board.py --me "Alice" --deadline 2031-06-30   # + handover view and days-left meter
```

- `--me NAME` (or `export LEDGER_ME=...`): your name as the ledger writes it. It decides
  what is "mine" and signs the `↳` history lines the board appends.
- `--deadline YYYY-MM-DD`: optional. When you are leaving a role or project, it adds a
  *Handover* view (everything still on you) and a meter of how much is closed or handed
  over. Without it neither is shown.
- `--ledger PATH`: default `~/meetings/OPEN.md`.
- `--selftest`: runs every action on a temp copy of `ledger/example/OPEN.md` (or of
  `--ledger` if given) and checks that only the intended lines changed. Never touches the
  original.

It binds to 127.0.0.1 only and checks `Host` and `Origin`, so other machines and other
web pages cannot reach it. Every write re-reads the file under a directory lock, verifies
the edit before it lands, writes atomically, and keeps a one-time `OPEN.md.board-backup`
from before its first write.

## The daily brief

`skills/daily-brief` is written to run unattended. In the Claude Code desktop app, create a
scheduled task (e.g. weekdays 07:30) whose prompt is `/daily-brief`. Before the first run,
point its repo loop at your clones (default `~/code/*/`). It writes only
`~/meetings/.daily-snapshot.md`, which it diffs against the next day.

## Recording: meetrec

### API key

Env var wins, file is the fallback. Never committed, never printed.

```sh
mkdir -p ~/.config/soniox
printf %s '<your-soniox-key>' > ~/.config/soniox/api_key
chmod 600 ~/.config/soniox/api_key
```

### Config

Who and what your meetings are about is data, so it stays out of git. Copy
`config.example.json` to `config.json` (git-ignored) and fill in the meeting context and
the proper nouns the transcriber should expect. Without the file meetrec uses generic
defaults and no terms.

```sh
cp config.example.json config.json
```

### Usage

```sh
./meetrec.py record --title "Weekly sync"          # records until Ctrl-C, then transcribes
./meetrec.py transcribe ~/meetings/audio/2025-03-04-1430-weekly-sync.flac --title "Weekly sync"
./meetrec.py devices                                # list audio inputs
```

Options on `record` and `transcribe`: `--title`, `--lang cs,en`, `--context "..."`,
`--terms "Acme,Kubernetes,..."`, `--personal`. `record` also takes `--device` (default
`default` = whatever System Settings > Sound has selected) and `--online` (see below).

`--personal` writes to `~/meetings-personal/` and sends no work context or terms to the API.
The skills never read that folder: personal recordings stay out of the work ledger.

`--terms` is the cheapest accuracy knob the API has: proper nouns that speech recognition
mangles. The standing list lives in `config.json`; **edit it** as people and product names
come and go.

Ctrl-C is trapped: ffmpeg is asked to quit cleanly, the FLAC is finalized, ffprobe
confirms it decodes, and only then does it upload.

Output:

- `~/meetings/audio/YYYY-MM-DD-HHMM-<slug>.flac`: kept forever, never deleted.
- `~/meetings/YYYY-MM-DD-HHMM-<slug>.md`: the transcript.
- `~/meetings/audio/<same>.tokens.json`: the raw Soniox tokens, saved before the
  server-side copy is deleted. Re-render the markdown from this without paying again.

If the upload or transcription fails, the audio is still there: rerun with
`transcribe <path>`. The uploaded copy and the transcription record are deleted from
Soniox once the transcript is saved (their storage quota is 10 GB / 30 days, and other
people's voices should not sit on a vendor longer than needed).

### Diarization is unreliable (measured, not assumed)

A seven-person meeting came back with **2** speaker labels; a two-person call came back
with **3**. The API has no `num_speakers` hint (checked the full request schema), so there
is no knob to fix this.

What still works: **turn boundaries are correct**, and the words are accurate even at
table distance. Only the identity behind `Speaker N` is wrong. The `meeting` skill
therefore compares the label count against the real attendee list and falls back to
attributing from content (vocatives such as Czech `Karle, jak jsi na tom s fakturací?`, self-reference
to owned work, being asked for status by name).

Best lever is microphone placement, not settings: `./meetrec.py devices` lists the iPhone
as an input (Continuity). Putting the phone in the middle of the table instead of relying
on the laptop in front of one person is the cheapest thing to try.

### Recovering a failed run

Upload and transcription happen server-side; the transcription id prints before polling
starts. If the network dies mid-poll, the transcript is still on Soniox:

```sh
./meetrec.py recover                  # the only completed one
./meetrec.py recover <transcription-id>
```

Network errors retry with backoff (8 attempts). `caffeinate` runs for the length of the
recording so idle sleep cannot kill the upload, but **closing the lid still kills it**:
that is a hard clamshell sleep nothing in userspace can override. No connection at all
(recording in a car) fails at upload; the FLAC is kept, run `transcribe <path>` later.

Limits: Soniox caps one file at **300 minutes** (hard, cannot be raised) and 15 speakers.
Longer than 5 hours → split it yourself, no chunking here.

### ⚠️ The microphone only records you

**The default input is the mic. In a remote meeting that captures you and nobody else**:
Teams/Zoom participants come out of the speakers, and macOS has no built-in loopback to
capture that. You will get a one-sided transcript.

In-person meetings never hit this: the microphone hears the room. It is **headphones** that
break it. On speakers the mic can at least pick the far end back up acoustically; with
AirPods the far end plays inside your ears and no microphone can reach it. Measured: a
14-minute remote call transcribed to `speakers=1` and one turn.

Fix it once (needs an admin password, so it is not done here):

1. `brew install blackhole-2ch`, then reboot.
2. **Audio MIDI Setup** → `+` → **Create Aggregate Device**: tick your Mac's
   **built-in microphone** *and* **BlackHole 2ch**. Name it **`Meeting In`**. Set the microphone as
   the **clock source** and tick **Drift Correction** on BlackHole.
   ⚠ **Use the built-in microphone here, not the AirPods microphone**, even if you wear
   AirPods on calls. Bluetooth is an unstable clock inside an aggregate and can drop and
   reconnect mid-call, and activating the AirPods mic forces the HFP profile, which
   collapses AirPods output to narrowband, degrading the very far-end audio BlackHole is
   capturing. The built-in mic hears you fine at laptop distance; it carried a seven-person
   room.
3. **Audio MIDI Setup** → `+` → **Create Multi-Output Device**: tick your **AirPods**
   *and* **BlackHole 2ch**. Name it **`Meeting Out`**. A Multi-Output referencing AirPods
   only works while they are connected: connect them first, then create it.
4. Set the meeting app's (or the system's) **output** to `Meeting Out` so you still hear
   people while BlackHole gets a copy.
5. `./meetrec.py record --online`: it finds the Aggregate device by name, no need to
   remember which one. Without a loopback device present, `--online` refuses to record and
   prints these steps rather than quietly capturing one side of the meeting.

`./meetrec.py devices` marks whichever input `--online` would pick.

Worth 30 seconds before installing anything: if your Mac exposes a `Microsoft Teams Audio`
input (Teams' own driver) and it happens to carry the meeting's far-end audio, BlackHole is
unnecessary. Test it with `./meetrec.py record --device "Microsoft Teams Audio"` during a
call and read the transcript. Untested; treat it as a lead, not a solution.

Note: Microsoft Teams also has built-in transcription with real speaker names. For a
Teams-only meeting that is strictly better than this tool; use it instead.
