# meetrec

Record a meeting on macOS, get a speaker-labeled Czech/English transcript out of the
Soniox async API, in the exact format the `meeting` Claude Code skill expects.

## Install

Nothing to install. `uv` handles the one dependency on first run.

```sh
chmod +x meetrec.py     # already done
./meetrec.py selftest
```

## API key

Env var wins, file is the fallback. Never committed, never printed.

```sh
mkdir -p ~/.config/soniox
printf %s '<your-soniox-key>' > ~/.config/soniox/api_key
chmod 600 ~/.config/soniox/api_key
```

## Config

Who and what your meetings are about is data, so it stays out of git. Copy
`config.example.json` to `config.json` (git-ignored) and fill in the meeting context and
the proper nouns the transcriber should expect. Without the file meetrec uses generic
defaults and no terms.

```sh
cp config.example.json config.json
```

## Usage

```sh
./meetrec.py record --title "Weekly sync"          # records until Ctrl-C, then transcribes
./meetrec.py transcribe ~/meetings/audio/2026-09-07-1430-porada.flac --title "Porada"
./meetrec.py devices                                # list audio inputs
```

Options on `record` and `transcribe`: `--title`, `--lang cs,en`, `--context "..."`,
`--terms "Acme,Kubernetes,..."`. `record` also takes `--device` (default `default` =
whatever System Settings > Sound has selected) and `--online` (see below).

`--terms` is the cheapest accuracy knob the API has — proper nouns Czech ASR mangles.
The standing list lives in `config.json` (see below); **edit it** as people and product
names come and go.

Ctrl-C is trapped: ffmpeg is asked to quit cleanly, the FLAC is finalized, ffprobe
confirms it decodes, and only then does it upload.

Output:

- `~/meetings/audio/YYYY-MM-DD-HHMM-<slug>.flac` — kept forever, never deleted.
- `~/meetings/YYYY-MM-DD-HHMM-<slug>.md` — the transcript.
- `~/meetings/audio/<same>.tokens.json` — the raw Soniox tokens, saved before the
  server-side copy is deleted. Re-render the markdown from this without paying again.

If the upload or transcription fails, the audio is still there — rerun with
`transcribe <path>`. The uploaded copy and the transcription record are deleted from
Soniox once the transcript is saved (their storage quota is 10 GB / 30 days, and other
people's voices should not sit on a vendor longer than needed).

## Diarization is unreliable — measured, not assumed

7-person porada came back with **2** speaker labels. 2-person call came back with
**3**. The API has no `num_speakers` hint (checked the full request schema), so there
is no knob to fix this.

What still works: **turn boundaries are correct**, and the words are accurate even at
table distance. Only the identity behind `Speaker N` is wrong. The `meeting` skill
therefore compares the label count against the real attendee list and falls back to
attributing from content (vocatives — `A Jano, za tebe ten web?` — self-reference to
owned work, being asked for status by name).

Best lever is microphone placement, not settings: `./meetrec.py devices` lists the
iPhone as an input (Continuity). Putting the phone in the middle of the table instead
of relying on the laptop in front of one person is the cheapest thing to try.

## Recovering a failed run

Upload and transcription happen server-side; the transcription id prints before
polling starts. If the network dies mid-poll, the transcript is still on Soniox:

```sh
./meetrec.py recover                  # the only completed one
./meetrec.py recover <transcription-id>
```

Network errors retry with backoff (8 attempts). `caffeinate` runs for the length of
the recording so idle sleep cannot kill the upload — but **closing the lid still kills
it**, that is a hard clamshell sleep nothing in userspace can override. No connection
at all (recording in a car) fails at upload; the FLAC is kept, run `transcribe <path>`
later.

Limits: Soniox caps one file at **300 minutes** (hard, cannot be raised) and 15
speakers. Longer than 5 hours → split it yourself, no chunking here.

## ⚠️ The microphone only records you

**The default input is the mic. In a remote meeting that captures you and nobody
else** — Teams/Zoom participants come out of the speakers, and macOS has no built-in
loopback to capture that. You will get a one-sided transcript.

In-person meetings never hit this: the microphone hears the room. It is **headphones**
that break it. On speakers the mic can at least pick the far end back up acoustically;
with AirPods the far end plays inside your ears and no microphone can reach it. Measured
2026-09-17 — a 14-minute remote call transcribed to `speakers=1` and one turn.

Fix it once (needs an admin password, so it is not done here):

1. `brew install blackhole-2ch`, then reboot.
2. **Audio MIDI Setup** → `+` → **Create Aggregate Device**: tick **MacBook Pro
   Microphone** *and* **BlackHole 2ch**. Name it **`Meeting In`**. Set the microphone as
   the **clock source** and tick **Drift Correction** on BlackHole.
   ⚠ **Use the built-in microphone here, not the AirPods microphone**, even if you wear
   AirPods on calls. Bluetooth is an unstable clock inside an aggregate and can drop and
   reconnect mid-call, and activating the AirPods mic forces the HFP profile, which
   collapses AirPods output to narrowband — degrading the very far-end audio BlackHole is
   capturing. The built-in mic hears you fine at laptop distance; it carried a 7-person
   room.
3. **Audio MIDI Setup** → `+` → **Create Multi-Output Device**: tick your **AirPods**
   *and* **BlackHole 2ch**. Name it **`Meeting Out`**. A Multi-Output referencing AirPods
   only works while they are connected — connect them first, then create it.
4. Set the meeting app's (or the system's) **output** to `Meeting Out` so you still hear
   people while BlackHole gets a copy.
5. `./meetrec.py record --online` — it finds the Aggregate device by name, no need to
   remember which one. Without a loopback device present, `--online` refuses to record
   and prints these steps rather than quietly capturing one side of the meeting.

`./meetrec.py devices` marks whichever input `--online` would pick.

Worth 30 seconds before installing anything: this Mac already exposes a
`Microsoft Teams Audio` input (Teams' own driver). If it happens to carry the
meeting's far-end audio, BlackHole is unnecessary — test it with
`./meetrec.py record --device "Microsoft Teams Audio"` during a call and read the
transcript. Untested, treat as a lead, not a solution.

Note: Microsoft Teams also has built-in transcription with real speaker names — for a
Teams-only meeting that is strictly better than this tool, use it instead.
