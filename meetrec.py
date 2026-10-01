#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""Record a meeting, transcribe it with speaker labels via the Soniox async API.

meetrec.py record [--title T] [--device SPEC] [--lang cs,en] [--context TEXT]
meetrec.py transcribe PATH [--title T] [--lang cs,en] [--context TEXT]
meetrec.py devices
meetrec.py selftest
"""
import argparse
import datetime
import os
import pathlib
import re
import signal
import subprocess
import json
import os
import sys
import tempfile
import time
import unicodedata

import requests

API = "https://api.soniox.com/v1"
MODEL = "stt-async-v5"
MAX_MINUTES = 300  # Soniox hard limit, cannot be raised
# Who and what your meetings are about is data, not code: it lives in config.json next to
# this script (git-ignored, see config.example.json). Missing file = generic defaults.
CONFIG = pathlib.Path(__file__).with_name("config.json")
_cfg = json.loads(CONFIG.read_text()) if CONFIG.is_file() else {}
DEFAULT_CONTEXT = _cfg.get("context", "Czech/English business meeting")
# Proper nouns Czech ASR reliably mangles — the cheapest accuracy knob the API has.
DEFAULT_TERMS = _cfg.get("terms", [])
MEETINGS = pathlib.Path.home() / "meetings"
# Personal meetings live outside the work tree entirely: different Claude account,
# different ledger, and no work vocabulary in the transcription request.
PERSONAL = pathlib.Path.home() / "meetings-personal"
PERSONAL_CONTEXT = _cfg.get("personal_context", "Czech/English conversation, personal meeting")
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
# A stalled aggregate recorded a whole meeting at -91.0 dB (2026-09-24, digital silence);
# all 16 real recordings to 2026-10-01 read -25.6 to -44.2. Below this is a dead input.
SILENCE_DB = -80.0


# ---------- helpers ----------

def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def api_key():
    k = os.environ.get("SONIOX_API_KEY", "").strip()
    if k:
        return k
    f = pathlib.Path.home() / ".config" / "soniox" / "api_key"
    if f.is_file():
        if f.stat().st_mode & 0o077:
            print(f"warning: {f} is readable by others; run: chmod 600 {f}", file=sys.stderr)
        k = f.read_text().strip()
        if k:
            return k
    die(f"no API key. Either:\n"
        f"  export SONIOX_API_KEY=...\n"
        f"  or: mkdir -p {f.parent} && printf %s '<key>' > {f} && chmod 600 {f}")


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "meeting"


def hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"


def dur_short(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec // 60 % 60, sec % 60
    return f"{h}h{m}m{s}s" if h else f"{m}m{s}s"


def probe_seconds(path):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        die(f"{path} does not decode ({out.stderr.strip() or 'no duration'}) — "
            f"the recording is truncated or corrupt")


def mean_volume(path):
    """Mean level in dB, or None if ffmpeg says nothing parseable (then do not block)."""
    out = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(path),
                          "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True)
    m = re.search(r"mean_volume: (\S+) dB", out.stderr)
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


# ---------- the only non-trivial logic ----------

def build_body(tokens):
    """Render the '## Speakers' + '## Transcript' sections from Soniox tokens.

    Groups consecutive tokens with the same speaker into one turn. Token text
    carries its own leading whitespace, so turns are concatenated, not joined.
    """
    turns = []  # [start_ms, speaker, [text, ...]]
    for t in tokens:
        spk = t.get("speaker")
        if turns and turns[-1][1] == spk:
            turns[-1][2].append(t.get("text", ""))
        else:
            turns.append([t.get("start_ms") or 0, spk, [t.get("text", "")]])

    lines = []
    for start_ms, spk, parts in turns:
        text = "".join(parts).strip()
        if text:
            label = f"Speaker {spk}" if spk is not None else "Speaker ?"
            lines.append(f"[{hms(start_ms / 1000)}] {label}: {text}")

    present = sorted({t["speaker"] for t in tokens if t.get("speaker") is not None},
                     key=lambda s: int(s) if str(s).isdigit() else 0)
    roster = "\n".join(f"Speaker {s} = ?" for s in present) or "Speaker ? = ?"
    return f"## Speakers\n\n{roster}\n\n## Transcript\n\n" + "\n".join(lines) + "\n"


def selftest():
    tokens = [
        {"text": "Ahoj", "speaker": "1", "start_ms": 3200},
        {"text": " vsichni", "speaker": "1", "start_ms": 3600},
        {"text": ".", "speaker": "1", "start_ms": 4000},
        {"text": " Hello", "speaker": "2", "start_ms": 72400},
        {"text": " there", "speaker": "2", "start_ms": 72900},
        {"text": " mumble", "start_ms": 3661000},
    ]
    expected = (
        "## Speakers\n"
        "\n"
        "Speaker 1 = ?\n"
        "Speaker 2 = ?\n"
        "\n"
        "## Transcript\n"
        "\n"
        "[00:00:03] Speaker 1: Ahoj vsichni.\n"
        "[00:01:12] Speaker 2: Hello there\n"
        "[01:01:01] Speaker ?: mumble\n"
    )
    got = build_body(tokens)
    assert got == expected, f"\n--- got ---\n{got}\n--- want ---\n{expected}"
    assert slugify("Porada — plán Q4 (čeština)") == "porada-plan-q4-cestina"
    assert dur_short(2538) == "42m18s" and dur_short(3725) == "1h2m5s"
    with tempfile.TemporaryDirectory() as d:
        quiet, tone = pathlib.Path(d, "quiet.flac"), pathlib.Path(d, "tone.flac")
        for src, f in (("anullsrc=r=16000:cl=mono", quiet), ("sine=f=440:r=16000", tone)):
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", src, "-t", "2",
                            "-sample_fmt", "s16", str(f)], check=True)
        assert mean_volume(quiet) < SILENCE_DB < mean_volume(tone), \
            (mean_volume(quiet), mean_volume(tone))
    print("selftest ok")


# ---------- soniox ----------

def req(method, url, *, tries=8, before=None, **kw):
    """A network blip must not throw away a paid transcription. Closed lid, dropped
    wifi, DNS hiccup mid-poll — back off and retry instead of dying.

    `before` runs ahead of every attempt. An upload MUST use it to rewind its file
    handle: requests consumes the stream as it sends, so a retry that reuses the same
    handle uploads only the unsent tail. Soniox then rejects it as
    `invalid_audio_file`, which reads like a corrupt recording and is not one."""
    for n in range(tries):
        try:
            if before:
                before()
            return getattr(requests, method)(url, **kw)
        except requests.RequestException as e:
            if n == tries - 1:
                die(f"{method.upper()} {url} failed after {tries} tries: {e}")
            wait = min(30, 2 ** n)
            print(f"\r  network error, retrying in {wait}s ({n + 1}/{tries - 1})...   ",
                  end="", flush=True)
            time.sleep(wait)


def soniox_upload(path, langs, context, key):
    h = {"Authorization": f"Bearer {key}"}
    print("uploading...")
    with open(path, "rb") as fh:
        r = req("post", f"{API}/files", headers=h, before=lambda: fh.seek(0),
                files={"file": (path.name, fh)}, timeout=1800)
    if not r.ok:
        die(f"upload failed ({r.status_code}): {r.text[:500]}")
    file_id = r.json()["id"]

    r = req("post", f"{API}/transcriptions", headers=h, timeout=60, json={
        "model": MODEL,
        "file_id": file_id,
        "enable_speaker_diarization": True,
        "enable_language_identification": True,
        "language_hints": langs,
        "context": context,
    })
    if not r.ok:
        die(f"transcription request failed ({r.status_code}): {r.text[:500]}")
    tid = r.json()["id"]
    # Printed before polling on purpose: if everything after this dies, this id is
    # what gets the meeting back.
    print(f"  transcription {tid}")
    return tid, file_id


def soniox_collect(tid, file_id, path, secs, key):
    h = {"Authorization": f"Bearer {key}"}
    deadline = time.time() + max(1800, 4 * secs)
    while True:
        if time.time() > deadline:
            die(f"timed out waiting for {tid}. It is still on Soniox — get it with:\n"
                f"  ./meetrec.py recover {tid}")
        r = req("get", f"{API}/transcriptions/{tid}", headers=h, timeout=60)
        if not r.ok:
            die(f"poll failed ({r.status_code}): {r.text[:500]}")
        st = r.json()
        if st.get("status") == "completed":
            break
        if st.get("status") == "error":
            # A failed job still occupies the quota, and its uploaded file is junk.
            for url in (f"{API}/transcriptions/{tid}", f"{API}/files/{file_id}"):
                try:
                    requests.delete(url, headers=h, timeout=60)
                except requests.RequestException:
                    pass
            die(f"soniox: {st.get('error_type')}: {st.get('error_message')}\n"
                f"The local audio is untouched at {path} — fix the cause and rerun "
                f"with: ./meetrec.py transcribe {path}")
        print(f"\r  {st.get('status', '?')}...            ", end="", flush=True)
        time.sleep(1)
    print("\r  completed            ")

    r = req("get", f"{API}/transcriptions/{tid}/transcript", headers=h, timeout=300)
    if not r.ok:
        die(f"transcript fetch failed ({r.status_code}): {r.text[:500]}")
    tokens = r.json().get("tokens") or []

    # ponytail: stash the paid raw result before the DELETEs below make it
    # unrecoverable — a crash in rendering would otherwise cost a re-transcription.
    path.with_suffix(".tokens.json").write_text(
        json.dumps(tokens, ensure_ascii=False, indent=1))

    # Housekeeping: 10 GB / 1000-file and 2000-transcription quotas, and we do not
    # want meeting audio parked on a vendor for 30 days. Best effort.
    for url in (f"{API}/transcriptions/{tid}", f"{API}/files/{file_id}"):
        try:
            requests.delete(url, headers=h, timeout=60)
        except requests.RequestException:
            pass
    return tokens


def soniox_transcribe(path, secs, langs, context, key):
    tid, file_id = soniox_upload(path, langs, context, key)
    return soniox_collect(tid, file_id, path, secs, key)


def salvage(audio):
    """A FLAC whose writer was killed has no STREAMINFO and a partial final frame, so
    ffprobe reports no duration and decoders give up at the break. Everything before
    that frame is intact — re-encode it rather than lose the meeting. Costs the last
    few seconds of audio, which beats losing all of it.

    Measured 2026-09-17 on macOS 27: ffmpeg's avfoundation input hung on teardown and
    ignored q, SIGINT and SIGTERM. 13m47s of a 14m38s recording came back this way."""
    fixed = audio.with_suffix(".salvaged.flac")
    subprocess.run([FFMPEG, "-v", "error", "-err_detect", "ignore_err", "-i", str(audio),
                    "-c:a", "flac", "-y", str(fixed)], capture_output=True)
    secs = probe_seconds(fixed)
    if secs <= 0:
        fixed.unlink(missing_ok=True)
        return 0
    fixed.replace(audio)
    return secs


# ---------- pipeline ----------

def write_md(audio, when, title, langs, context, key, tokens=None):
    secs = probe_seconds(audio)
    if secs <= 0:
        die(f"{audio} decodes to 0 seconds")
    if secs > MAX_MINUTES * 60:
        die(f"{audio} is {dur_short(secs)}; Soniox async caps a single file at "
            f"{MAX_MINUTES} minutes (hard limit). Split it with ffmpeg and transcribe "
            f"the parts separately.")
    print(f"audio: {audio} ({dur_short(secs)})")

    if tokens is None:
        # ponytail: whole-file mean only; a stall halfway through still passes.
        # Per-minute volumedetect if partial stalls ever show up.
        db = mean_volume(audio)
        if db is not None and db < SILENCE_DB:
            die(f"{audio} is silent (mean {db:.1f} dB): the input delivered no sound, "
                f"so it was not sent to Soniox. Check the device level before the next "
                f"recording (./meetrec.py devices).")
        tokens = soniox_transcribe(audio, secs, langs, context, key)
    if not tokens:
        die("soniox returned no tokens")
    if not any(t.get("speaker") is not None for t in tokens):
        print("\n*** WARNING: no speaker labels came back — diarization produced nothing. "
              "Every turn is 'Speaker ?'. ***\n", file=sys.stderr)

    try:
        rel = audio.relative_to(MEETINGS)
    except ValueError:
        rel = audio
    slug = slugify(title)
    out = MEETINGS / f"{when:%Y-%m-%d-%H%M}-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    nspk = len({t["speaker"] for t in tokens if t.get("speaker") is not None})
    out.write_text(
        f"# {when:%Y-%m-%d %H:%M} — {title}\n\n"
        f"<!-- meetrec: duration={dur_short(secs)} speakers={nspk} model={MODEL} "
        f"audio={rel} -->\n\n"
        + build_body(tokens))
    print(f"wrote {out}")


def record(args):
    key = api_key()  # fail before recording, not after
    when = datetime.datetime.now()
    audio = MEETINGS / "audio" / f"{when:%Y-%m-%d-%H%M}-{slugify(args.title)}.flac"
    audio.parent.mkdir(parents=True, exist_ok=True)

    dev = resolve_device(args.device, args.online)
    cmd = [FFMPEG, "-hide_banner", "-f", "avfoundation", "-i", f":{dev}",
           "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", "-c:a", "flac", str(audio)]
    # A 50-minute meeting is 50 minutes of no keyboard input. Idle sleep would kill
    # the network mid-upload. Exits with us. Does NOT beat closing the lid — that is
    # a hard clamshell sleep nothing in userspace can veto.
    subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])

    log = tempfile.TemporaryFile()
    # start_new_session: Ctrl-C hits only us, so we own the graceful shutdown.
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log,
                         start_new_session=True)

    # A terminal Ctrl-C signals the whole process group, and `uv run` forwards it too,
    # so we get SIGINT more than once. A raised KeyboardInterrupt would land inside the
    # flush-and-wait below and truncate the FLAC. Flag it, then go deaf.
    stop = []

    def on_sigint(*_):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        stop.append(1)

    signal.signal(signal.SIGINT, on_sigint)

    print(f"recording -> {audio}\ndevice :{args.device} — press Ctrl-C to stop")
    t0 = time.time()
    while p.poll() is None and not stop:
        print(f"\r  {hms(time.time() - t0)} elapsed", end="", flush=True)
        time.sleep(1)
    print()
    if not stop:
        log.seek(0)
        die(f"ffmpeg exited early (code {p.returncode}):\n"
            f"{log.read().decode(errors='replace')[-2000:]}")

    print("stopping...")
    try:
        p.stdin.write(b"q")
        p.stdin.flush()
    except OSError:
        pass
    for sig in (None, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if sig:
            p.send_signal(sig)
        try:
            p.wait(timeout=10)
            break
        except subprocess.TimeoutExpired:
            print("ffmpeg will not exit, escalating...", file=sys.stderr)

    # A killed writer never wrote STREAMINFO. Do not hand the user a dead end —
    # everything up to the break is still there.
    if probe_seconds(audio) <= 0:
        print("file was never finalized, salvaging...", file=sys.stderr)
        secs = salvage(audio)
        if secs <= 0:
            die(f"{audio} could not be salvaged. The raw file is still there.")
        print(f"salvaged {dur_short(secs)} — the last few seconds are lost",
              file=sys.stderr)

    write_md(audio, when, args.title, args.langs, args.context, key)


def when_and_title(audio, title):
    """Recover both from the filename meetrec itself chose, so re-runs do not need
    --title restated."""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)-(\d\d)(\d\d)-(.+)\.\w+$", audio.name)
    when = (datetime.datetime(*map(int, m.groups()[:5])) if m
            else datetime.datetime.fromtimestamp(audio.stat().st_mtime))
    if m and title == "Meeting":
        title = m.group(6).replace("-", " ")
    return when, title


def transcribe(args):
    key = api_key()
    audio = pathlib.Path(args.path).expanduser().resolve()
    if not audio.is_file():
        die(f"no such file: {audio}")
    when, title = when_and_title(audio, args.title)
    write_md(audio, when, title, args.langs, args.context, key)


def recover(args):
    """The transcript is already paid for and sitting on Soniox. Losing the network
    while polling must never cost the meeting."""
    key = api_key()
    h = {"Authorization": f"Bearer {key}"}
    tid = args.tid
    if not tid:
        r = req("get", f"{API}/transcriptions", headers=h, timeout=60)
        done = [t for t in r.json().get("transcriptions", [])
                if t.get("status") == "completed"]
        if not done:
            die("nothing completed on Soniox to recover")
        if len(done) > 1:
            die("several waiting, pass one id:\n  " + "\n  ".join(
                f'{t["id"]}  {t.get("filename")}' for t in done))
        tid = done[0]["id"]
    meta = req("get", f"{API}/transcriptions/{tid}", headers=h, timeout=60).json()
    if meta.get("status") != "completed":
        die(f"transcription {tid} is {meta.get('status')}, not completed")
    audio = MEETINGS / "audio" / (meta.get("filename") or f"{tid}.flac")
    if not audio.is_file():
        die(f"{audio} is gone — cannot name or date the output")
    secs = (meta.get("audio_duration_ms") or 0) / 1000 or probe_seconds(audio)
    when, title = when_and_title(audio, args.title)
    print(f"recovering {tid} -> {audio.name} ({dur_short(secs)})")
    tokens = soniox_collect(tid, meta["file_id"], audio, secs, key)
    write_md(audio, when, title, args.langs, args.context, key, tokens=tokens)


def list_audio_inputs():
    """[(index, name)] of avfoundation audio inputs. Indices shift with what is
    plugged in, so never hardcode one."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-f", "avfoundation",
                        "-list_devices", "true", "-i", ""],
                       capture_output=True, text=True)
    out, audio = [], False
    for line in r.stderr.splitlines():
        line = re.sub(r"^\[AVFoundation indev @ 0x[0-9a-f]+\] ", "", line)
        if "audio devices" in line:
            audio = True
        elif audio:
            m = re.match(r"\[(\d+)\] (.+)$", line)
            if m:
                out.append((m.group(1), m.group(2).strip()))
    return out


# An AGGREGATE device combines the microphone with the loopback, so it carries both
# sides of a call. Bare BlackHole carries system audio ONLY — picking it would record
# everyone except you, which is today's bug inverted. Prefer aggregates, warn on bare.
AGGREGATE_RE = re.compile(r"aggregate|meeting in", re.I)
LOOPBACK_RE = re.compile(r"blackhole|loopback|soundflower", re.I)


def pick_online(inputs):
    """What --online would choose, and why. One source of truth, so `devices` cannot
    disagree with what actually happens. Returns (idx, name, kind) or None."""
    for idx, name in inputs:
        if AGGREGATE_RE.search(name):
            return idx, name, "aggregate"
    for idx, name in inputs:
        if LOOPBACK_RE.search(name):
            return idx, name, "bare"
    return None


def resolve_device(spec, online):
    """--online means: the other people are in Teams/Zoom, so the microphone alone
    records only you. macOS has no built-in loopback, hence the extra device."""
    if not online:
        return spec
    pick = pick_online(list_audio_inputs())
    if pick:
        idx, name, kind = pick
        if kind == "aggregate":
            print(f"online mode: [{idx}] {name}")
            return idx
        print(f"\n*** WARNING: [{idx}] {name} is a bare loopback, not an aggregate.\n"
              f"    It carries system audio only — the other participants will be\n"
              f"    recorded and YOU WILL NOT BE. Build an Aggregate Device combining\n"
              f"    your microphone with BlackHole 2ch (see the README) and rerun.\n"
              f"    Recording anyway in 5s — Ctrl-C now if that is not what you want.\n",
              file=sys.stderr)
        time.sleep(5)
        return idx
    die("--online found no loopback or aggregate input. One-time setup (needs your "
        "password):\n"
        "  1) brew install blackhole-2ch\n"
        "  2) Audio MIDI Setup > + > Create Aggregate Device: tick your mic AND "
        "BlackHole 2ch\n"
        "  3) Audio MIDI Setup > + > Create Multi-Output Device: tick your speakers "
        "AND BlackHole 2ch\n"
        "  4) Set the meeting app's output (or System Settings > Sound > Output) to "
        "that Multi-Output Device\n"
        "Then --online picks the Aggregate up automatically. In-person meetings need "
        "none of this — just drop the flag.")


def devices(_):
    inputs = list_audio_inputs()
    pick = pick_online(inputs)
    print("audio inputs (use the number or the name with --device):")
    for idx, name in inputs:
        tag = ""
        if pick and idx == pick[0]:
            tag = ("   <- --online uses this" if pick[2] == "aggregate"
                   else "   <- --online would fall back to this (BARE LOOPBACK: "
                        "records everyone except you)")
        print(f"  [{idx}] {name}{tag}")
    print("  default  (whatever System Settings > Sound has selected)")
    if pick and pick[2] == "bare":
        print("\n  No aggregate device found. Build one (mic + BlackHole 2ch) before "
              "relying on --online — see the README.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--title", default="Meeting")
        p.add_argument("--lang", dest="langs", default="cs,en",
                       type=lambda s: [x.strip() for x in s.split(",") if x.strip()])
        p.add_argument("--context", default=None)
        p.add_argument("--personal", action="store_true",
                       help="a personal meeting: write to ~/meetings-personal and send "
                            "no work context or terms to the API")
        # Extends DEFAULT_TERMS rather than replacing it — passing one meeting's
        # names should not silently drop the standing vocabulary.
        p.add_argument("--terms", default=[],
                       type=lambda s: [x.strip() for x in s.split(",") if x.strip()])

    r = sub.add_parser("record", help="record until Ctrl-C, then transcribe")
    r.add_argument("--device", default="default", help="avfoundation audio input (see: devices)")
    r.add_argument("--online", action="store_true",
                   help="remote meeting: use the BlackHole/Aggregate loopback input, "
                        "so the other participants are recorded too")
    common(r)
    r.set_defaults(func=record)

    t = sub.add_parser("transcribe", help="transcribe an existing audio file")
    t.add_argument("path")
    common(t)
    t.set_defaults(func=transcribe)

    v = sub.add_parser("recover", help="fetch a transcript already completed on Soniox")
    v.add_argument("tid", nargs="?", help="transcription id (default: the only completed one)")
    common(v)
    v.set_defaults(func=recover)

    sub.add_parser("devices", help="list avfoundation audio inputs").set_defaults(func=devices)
    sub.add_parser("selftest", help="check turn grouping").set_defaults(func=lambda _: selftest())

    args = ap.parse_args()
    if getattr(args, "personal", False):
        global MEETINGS
        MEETINGS = PERSONAL
    # The API takes context as an object, not a string — a string 400s, and it would
    # 400 *after* the upload, i.e. after the meeting.
    if hasattr(args, "context"):
        personal = getattr(args, "personal", False)
        text = args.context or (PERSONAL_CONTEXT if personal else DEFAULT_CONTEXT)
        terms = args.terms if personal else DEFAULT_TERMS + args.terms
        args.context = {"text": text, "terms": terms}
    args.func(args)


if __name__ == "__main__":
    main()
