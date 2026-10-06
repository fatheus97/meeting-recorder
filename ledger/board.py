#!/usr/bin/env python3
"""Local board for the meetings ledger (OPEN.md). Stdlib only.

    python3 board.py --me Alice                          # serve http://127.0.0.1:8765/
    python3 board.py --me Alice --deadline 2031-12-31    # also: handover view + days-left meter
    python3 board.py --ledger PATH                       # another ledger (default ~/meetings/OPEN.md)
    python3 board.py --selftest                          # every action on a temp copy of example/OPEN.md

--me (or $LEDGER_ME) is your name as it appears in the ledger: it marks "mine" and signs
the history lines the board writes. Format contract: LEDGER.md next to this file.
Parsing is best effort ("?" when a field cannot be read); writes are minimal, locked,
atomic and verified.
"""
import argparse, datetime, fcntl, html, json, os, re, sys, tempfile, unicodedata
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
HOSTS = {f'127.0.0.1:{PORT}', f'localhost:{PORT}'}
ORIGINS = {f'http://{h}' for h in HOSTS}
EXAMPLE = Path(__file__).resolve().parent / 'example' / 'OPEN.md'
ME = 'Alice'            # set from --me / $LEDGER_ME in main(); 'Alice' is the example ledger's user
DEADLINE = None         # --deadline: a datetime.date, or None to hide the handover view and meter

# item head, at line start; group 3 = the leading run of project tags (LEDGER.md), first = primary
HEAD = re.compile(r'- \[(.)\] `(OI-[0-9]+)`((?: +#[a-z][a-z_-]*(?=\s|$))*)')
CONT = re.compile(r'[ \t]+\S')                            # indented = belongs to the item above
SECTION = re.compile(r'(#{2,3}) +(.*\S)')
SEEN = re.compile(r'seen (\d{4}-\d{2}-\d{2})')
SEEN_AT = re.compile(r'— seen \d{4}-\d{2}-\d{2}')
# The ideal head: " — **owner** — <next-mover> — seen YYYY-MM-DD" (a short plain aside after the owner,
# e.g. "(set by Alice 3.3)", is allowed and kept). Only this shape is edited in place.
STRUCT = re.compile(r' — \*\*([^*\n]+)\*\*([^—*\n]{0,60}?) — (me\b[^—]*?|waiting on [^—]+?|—) — seen \d{4}-\d{2}-\d{2}')
OWNER = re.compile(r' — \*\*([^*\n]+)\*\*')
OWNER_BEFORE_SEEN = re.compile(r'\*\*([^*\n]+)\*\*[^*\n]{0,40}? — seen \d')
OWNER_CONT = re.compile(r'— \*\*([^*\n]+)\*\*[^*\n]{0,40}? — seen \d')    # owner on a continuation line
TRAIL = re.compile(r'— (waiting on [^—*]+?|me)\s*$')      # "… — waiting on Bob" ending another writer's ↳ line
MARK = re.compile(r'\s(?:[⚠✅🔴❌✖♻⏳🔎✉]|·\s)')             # start of an inline annotation
UNOWNED = re.compile(r'unowned|unresolved', re.I)
PRECOND = re.compile(r'precondition', re.I)                # section heading -> kind
THREAT = re.compile(r'threat', re.I)
KINDS = ['Task', 'Precondition', 'Threat']
NO_PROJECT = 'no project'
PERSON = re.compile(r"[\w .,'+/&()\-]{1,60}")
ACTIONS = {'done', 'wait', 'mine', 'note', 'handover'}
VIEWS = [('mine', 'Mine'), ('waiting', 'Waiting on others'), ('unowned', 'Unowned'),
         ('open', 'All open'), ('done', 'Done'), ('handover', 'Handover')]
BOX_LABEL = {' ': 'open', '~': 'changed', 'x': 'done', 'X': 'done'}


def board_re(me):
    """A history line the board itself wrote for `me` (only those move owner / next-mover)."""
    return re.compile(rf'\s*↳ \[\d{{1,2}}\.\d{{1,2}}\] {re.escape(me)}: '
                      r'(?:waiting on (?P<wait>.+?)|(?P<mine>mine)|handed over to (?P<hand>.+?))'
                      r'(?: \(was: .*?\))?(?: — .*)?$')


BOARD = board_re(ME)


def views():
    return VIEWS if DEADLINE else VIEWS[:-1]


class ActionError(Exception):
    pass


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).casefold()


def is_me(s):
    """First name of --me as a whole word: 'Alice' matches 'Alice + Bob', 'me' never matches 'James'."""
    return bool(re.search(rf'(?<!\w){re.escape(fold(ME).split()[0])}(?!\w)', fold(s)))


def clean(s):
    """One line, no control or line-separator characters, single spaces."""
    s = ''.join(' ' if unicodedata.category(c) in ('Cc', 'Zl', 'Zp') else c for c in str(s))
    return ' '.join(s.split())


def strip_md(s):
    return ' '.join(re.sub(r'\*\*|`', '', s).split())


# ---------------------------------------------------------------- parsing

def parse(text):
    """-> (items, warnings). Never drops an item: every head line becomes one item."""
    lines = text.split('\n')
    items, warnings, orphans, h2, h3, cur = [], [], [], '', '', None

    def flush_orphans():
        if orphans:
            a, b, first = orphans[0], orphans[-1], lines[orphans[0]].strip()
            warnings.append(f'lines {a + 1}–{b + 1}: indented block with no item above it '
                            f'(after a blank line), not attached: "{first[:70]}…"')
            orphans.clear()

    for n, line in enumerate(lines):
        m = HEAD.match(line)
        if m:
            flush_orphans()
            cur = {'id': m[2], 'box': m[1], 'section': h2 + (f' › {h3}' if h3 else ''),
                   'line': n + 1, 'lines': [line]}
            items.append(cur)
            continue
        if cur and CONT.match(line):
            cur['lines'].append(line)
            continue
        cur = None
        if CONT.match(line):
            orphans.append(n)
            continue
        flush_orphans()
        s = SECTION.match(line)
        if s:
            h2, h3 = (s[2], '') if len(s[1]) == 2 else (h2, s[2])
        elif line.startswith('- '):
            warnings.append(f'line {n + 1}: bullet without an `OI-…` id, not an item: "{line[2:72]}…"')
    flush_orphans()
    for oid, c in Counter(i['id'] for i in items).items():
        if c > 1:
            warnings.append(f'{oid} appears {c}× in the file — the board refuses to write to it')
    for it in items:
        derive(it)
    return items, warnings


def derive(it):
    head_line = it['lines'][0]
    hm = HEAD.match(head_line)
    rest = head_line[hm.end():]                    # tags are not part of the head text
    tags = hm[3].split()
    it['primary'], it['secondary'] = (tags[0], tags[1:]) if tags else (NO_PROJECT, [])
    it['kind'] = 'Precondition' if PRECOND.search(it['section']) else 'Threat' if THREAT.search(it['section']) else 'Task'
    cont = it['lines'][1:]
    arrows = [l for l in cont if l.lstrip().startswith('↳')]
    it['history'] = cont
    m = SEEN.search(head_line) or SEEN.search('\n'.join(cont))
    it['seen'] = m[1] if m else '?'

    sm = list(STRUCT.finditer(rest))
    owner, mover, cut = '?', '?', None
    if len(sm) == 1:
        owner, mover, cut = sm[0][1].strip(), sm[0][3].strip(), sm[0].start()
    else:
        s = SEEN_AT.search(rest)
        before = rest[:s.start()] if s else rest
        o = OWNER.search(before) or (OWNER_BEFORE_SEEN.search(rest) if s else None)
        if o:
            owner, cut = o[1].strip(), o.start()
        else:
            for l in cont:
                if not l.lstrip().startswith('↳') and (o := OWNER_CONT.search(l)):
                    owner = o[1].strip()
                    break
    it['structured'] = len(sm) == 1

    handed = False
    got_mover = got_owner = it['structured']      # a structured head is the truth; history cannot override it
    for l in arrows:                               # newest first (LEDGER order)
        b = BOARD.match(l)
        if b:
            handed = handed or bool(b['wait'] or b['hand'])
            if not got_mover:
                mover = 'me' if b['mine'] else f"waiting on {b['wait'] or b['hand']}"
                got_mover = True
            if not got_owner and b['hand']:
                owner, got_owner = b['hand'], True
        elif not got_mover and (t := TRAIL.search(l)):
            mover, got_mover = t[1].strip(), True
    it['owner'], it['mover'], it['handed'] = owner, mover, handed

    mk = MARK.search(rest)
    cut = min(cut if cut is not None else len(rest), mk.start() if mk else len(rest))
    head = strip_md(rest[:cut]).strip(' —') or strip_md(rest)
    it['head'] = head if len(head) <= 140 else head[:140].rsplit(' ', 1)[0] + ' …'

    closed = it['box'] in 'xX'
    me_owner, me_next = is_me(owner), re.match(r'me\b', mover) is not None
    it['mine_now'] = not closed and (me_owner or me_next)
    it['mine_ever'] = me_owner or me_next or handed
    v = ['done'] if closed else ['open']
    if not closed:
        if me_next or (mover == '?' and me_owner):
            v.append('mine')
        if mover.startswith('waiting on'):
            v.append('waiting')
        if UNOWNED.search(owner):
            v.append('unowned')
        if it['mine_now'] and DEADLINE:
            v.append('handover')
    it['views'] = v


def projects(items):
    """Project dropdown: [(tag, items carrying it as primary or secondary)], by count; #handover and untagged last."""
    c = Counter(t for i in items for t in [i['primary'], *i['secondary']])
    tail = [(t, c.pop(t)) for t in ('#handover', NO_PROJECT) if t in c]
    return sorted(c.items(), key=lambda x: (-x[1], x[0])) + tail


def stats(items):
    ever = [i for i in items if i['mine_ever']]
    left = sum(i['mine_now'] for i in ever)
    return {'total': len(items), 'box': dict(Counter(i['box'] for i in items)),
            'projects': projects(items), 'kinds': {k: sum(i['kind'] == k for i in items) for k in KINDS},
            'no_owner': sum(i['owner'] == '?' for i in items),
            'views': {k: sum(k in i['views'] for i in items) for k, _ in views()},
            'mine_total': len(ever), 'mine_done': len(ever) - left, 'mine_left': left}


# ---------------------------------------------------------------- writing

def verify(old, new, oid, h, k):
    """Pure check of an edit before it is written. -> error text or None."""
    if len(new) != len(old) + 1:
        return 'line count is off'
    if not new[k].startswith('  ↳ [') or '\n' in new[k]:
        return 'the inserted line is not a history line'
    rest = new[:k] + new[k + 1:]
    changed = [i for i, (a, b) in enumerate(zip(old, rest)) if a != b]
    if changed not in ([], [h]):
        return f'other lines would change too ({changed[:5]})'
    m = HEAD.match(rest[h])
    if not m or m[2] != oid or m[3] != HEAD.match(old[h])[3]:     # id and tag prefix byte-for-byte
        return 'the item head would be damaged'
    ids = lambda ls: sorted(m[2] for l in ls if (m := HEAD.match(l)))
    new_ids = ids(new)
    if new_ids != ids(old) or new_ids.count(oid) != 1:
        return 'the set of items would change'
    return None


def atomic_write(path, data):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def perform(path, oid, action, person='', note='', today=None):
    """One edit to one item, re-read from disk under lock. Returns the item id."""
    if not isinstance(oid, str) or not re.fullmatch(r'OI-[0-9]{1,6}', oid):
        raise ActionError('invalid id')
    if action not in ACTIONS:
        raise ActionError('unknown action')
    person, note = clean(person or ''), clean(note or '')
    if action in ('wait', 'handover') and not (PERSON.fullmatch(person) and person.strip(' .,')):
        raise ActionError('invalid name (letters, spaces, . , + / & ( ) - ; max 60 characters)')
    if action == 'note' and not note:
        raise ActionError('empty note')
    if len(note) > 2000:
        raise ActionError('note is longer than 2000 characters')
    today = today or datetime.date.today()

    lock = os.open(path.parent, os.O_RDONLY)       # flock on the directory: survives os.replace, no lock file
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for _ in range(3):
            old_b = path.read_bytes()
            try:
                lines = old_b.decode('utf-8').split('\n')
            except UnicodeDecodeError:
                raise ActionError('OPEN.md is not valid UTF-8 — nothing written')
            hits = [i for i, l in enumerate(lines) if (m := HEAD.match(l)) and m[2] == oid]
            if len(hits) != 1:
                raise ActionError(f'{oid} not found in OPEN.md' if not hits
                                  else f'{oid} appears {len(hits)}× in OPEN.md — fix it by hand, nothing written')
            h = hits[0]
            end = h + 1
            while end < len(lines) and CONT.match(lines[end]):
                end += 1
            arrows = [j for j in range(h + 1, end) if lines[j].lstrip().startswith('↳')]
            k = arrows[0] if arrows else end         # newest history first, as LEDGER.md shows it

            head = lines[h]
            if head[3] in 'xX' and action != 'note':
                raise ActionError(f'{oid} is closed — only Note works')
            start = HEAD.match(head).end()
            sm = list(STRUCT.finditer(head, start))
            s = sm[0] if len(sm) == 1 else None
            if action == 'done':
                head, text = head[:3] + 'x' + head[4:], 'done'
            elif action == 'note':
                text = note
            else:
                mover = 'me' if action == 'mine' else f'waiting on {person}'
                owner = person if action == 'handover' else (s[1] if s else None)
                text = {'wait': f'waiting on {person}', 'mine': 'mine', 'handover': f'handed over to {person}'}[action]
                if s:                                  # ideal-format head: replace in place, keep the old value in history
                    text += f' (was: {s[1]} / {s[3]})' if action == 'handover' else f' (was: {s[3]})'
                    head = head[:s.start(1)] + owner + head[s.end(1):s.start(3)] + mover + head[s.end(3):]
            if note and action != 'note':
                text += f' — {note}'
            new = lines[:h] + [head] + lines[h + 1:k] + [f'  ↳ [{today.day}.{today.month}] {ME}: {text}'] + lines[k:]
            problem = verify(lines, new, oid, h, k)
            if problem:
                raise ActionError(f'pre-write check failed: {problem} — nothing written')
            new_b = '\n'.join(new).encode('utf-8')

            try:                                       # one-time safety copy before the first ever write
                with open(path.with_name(path.name + '.board-backup'), 'xb') as f:
                    f.write(old_b)
            except FileExistsError:
                pass
            if path.read_bytes() != old_b:            # someone wrote meanwhile: redo from their version
                continue
            atomic_write(path, new_b)
            if path.read_bytes() != new_b:
                # Not restored on purpose: the file now holds another writer's newer content,
                # and putting ours back would erase theirs. The edit itself was verified above.
                raise ActionError('another writer changed OPEN.md right after the write — check the item by hand')
            return oid
        raise ActionError('OPEN.md kept changing during the write — try again')
    finally:
        os.close(lock)


# ---------------------------------------------------------------- page

CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1b1b1b;--mut:#666;--card:#f6f7f8;--bd:#d9dcdf;--acc:#0a5fc2;--ok:#1a7f37;--chg:#9a6700;--bar:#e6e8ea}
@media (prefers-color-scheme:dark){:root{--bg:#151617;--fg:#e6e6e6;--mut:#9aa0a6;--card:#1f2123;--bd:#3a3d41;--acc:#6ea8ff;--ok:#4ac26b;--chg:#d4a72c;--bar:#2c2f33}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:1;background:var(--bg);border-bottom:1px solid var(--bd);padding:10px 16px}
header>*,main,footer{max-width:1100px;margin-left:auto;margin-right:auto}
#meter{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;font-size:18px}
#meter strong{font-size:20px}
#meter .bar{flex:1 1 220px;height:12px;background:var(--bar);border-radius:6px;overflow:hidden}
#meter .bar i{display:block;height:100%;background:var(--ok)}
#meter small{color:var(--mut);font-size:14px}
#tabs{display:flex;flex-wrap:wrap;gap:6px;margin:10px auto 8px}
button{font:inherit;color:inherit;background:var(--card);border:1px solid var(--bd);border-radius:5px;padding:4px 10px;cursor:pointer}
button:hover{border-color:var(--acc)} button:disabled{opacity:.5;cursor:wait}
#tabs button.on{background:var(--acc);border-color:var(--acc);color:#fff}
#tabs b{font-weight:600;opacity:.8}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
input,select{font:inherit;color:inherit;background:var(--bg);border:1px solid var(--bd);border-radius:5px;padding:4px 8px;min-width:0}
#q{flex:1 1 260px} #proj,#kind{max-width:100%} #shown{color:var(--mut)}
main{padding:12px 16px}
.who{margin:0 0 10px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--bd);border-left:4px solid var(--acc);border-radius:6px;margin:0 0 8px}
.card.b-chg{border-left-color:var(--chg)} .card.b-done{border-left-color:var(--ok);opacity:.85}
summary{cursor:pointer;padding:8px 12px;list-style:none} summary::-webkit-details-marker{display:none}
.top{display:flex;gap:8px;align-items:baseline}
.id{font-weight:700;white-space:nowrap} .box{font:12px ui-monospace,Menlo,monospace;color:var(--mut);white-space:nowrap}
.head{overflow-wrap:anywhere;min-width:0}
.tag{display:inline-block;font-size:12px;line-height:1.5;padding:0 6px;margin-right:4px;border:1px solid var(--bd);border-radius:9px;color:var(--mut);white-space:nowrap}
.tag.p{background:var(--acc);border-color:var(--acc);color:var(--bg);font-weight:600}
.meta{color:var(--mut);font-size:13px;margin-top:3px;overflow-wrap:anywhere}
.meta b{color:var(--fg);font-weight:600}
.body{border-top:1px solid var(--bd);padding:8px 12px 10px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 8px;font:13px/1.45 ui-monospace,Menlo,monospace}
.hist{border-left:3px solid var(--bd);padding-left:8px}
.act{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.act input[name=person]{flex:0 1 200px} .act input[name=note]{flex:1 1 280px}
footer{padding:0 16px 30px;color:var(--mut);font-size:13px}
footer li{overflow-wrap:anywhere}
"""

JS = r"""
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const norm = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const VIEWS = [...document.querySelectorAll('#tabs [data-view]')].map(b => b.dataset.view);
let view = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'mine';
function apply() {
  const q = norm($('#q').value.trim()), proj = $('#proj').value, kind = $('#kind').value;
  let n = 0;
  for (const c of $$('.card')) {
    const ok = c.dataset.views.split(' ').includes(view) && (!proj || c.dataset.proj.split('|').includes(proj)) &&
      (!kind || c.dataset.kind === kind) &&
      (!q || (c._t ??= norm(c.querySelector('.raw').textContent)).includes(q));
    c.hidden = !ok; n += ok;
  }
  for (const b of $$('#tabs [data-view]')) b.classList.toggle('on', b.dataset.view === view);
  for (const e of $$('[data-only]')) e.hidden = e.dataset.only !== view;
  $('#shown').textContent = n ? `showing ${n}` : 'nothing here';
  history.replaceState(null, '', '#' + view);
}
async function refresh(keepOpen) {
  const open = new Set($$('.card details[open]').map(d => d.closest('.card').dataset.id));
  if (keepOpen) open.add(keepOpen);
  const r = await fetch('/', {cache: 'no-store'});
  if (!r.ok) { alert('Reload failed: HTTP ' + r.status); return; }
  const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
  const keep = ['#proj', '#kind'].map(s => [s, $(s).value]);
  for (const s of ['#meter', '#tabs', '#proj', '#kind', '#list', 'footer']) $(s).replaceWith(doc.querySelector(s));
  for (const [s, v] of keep) { $(s).value = v; if ($(s).selectedIndex < 0) $(s).selectedIndex = 0; }
  for (const c of $$('.card')) if (open.has(c.dataset.id)) c.querySelector('details').open = true;
  apply();
}
async function act(btn) {
  const card = btn.closest('.card'), id = card.dataset.id, a = btn.dataset.a;
  const person = (card.querySelector('[name=person]')?.value || '').trim();
  const note = card.querySelector('[name=note]').value.trim();
  if ((a === 'wait' || a === 'handover') && !person) return alert('Enter a name.');
  if (a === 'note' && !note) return alert('Write a note.');
  if (a === 'done' && !confirm(`Close ${id} as done?`)) return;
  if (a === 'handover' && !confirm(`Hand ${id} over to ${person}?`)) return;
  btn.disabled = true;
  try {
    const r = await fetch('/api/action', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id, action: a, person, note})});
    const j = await r.json().catch(() => ({error: 'HTTP ' + r.status}));
    if (!r.ok || j.error) { alert('Not written: ' + (j.error || r.status)); btn.disabled = false; return; }
    await refresh(id);
  } catch (e) { alert('Error: ' + e); btn.disabled = false; }
}
document.addEventListener('click', e => {
  const t = e.target.closest('[data-view]');
  if (t) { view = t.dataset.view; apply(); return; }
  const b = e.target.closest('button[data-a]');
  if (b) act(b);
  if (e.target.id === 'reload') refresh();
});
document.addEventListener('input', e => { if (e.target.id === 'q') apply(); });
document.addEventListener('change', e => { if (['proj', 'kind'].includes(e.target.id)) apply(); });
addEventListener('focus', () => { if (!$$('#list input').some(i => i.value)) refresh(); });
apply();
"""


def render_card(it):
    e = html.escape
    closed = it['box'] in 'xX'
    cls = 'b-done' if closed else 'b-chg' if it['box'] == '~' else 'b-open'
    hist = '\n'.join(it['history'])
    person = '' if closed else '<input name="person" placeholder="Name (Waiting on… / Hand over)" maxlength="60">'
    buttons = ('<button data-a="note">Note</button>' if closed else
               '<button data-a="done">✅ Done</button><button data-a="wait">Waiting on…</button>'
               '<button data-a="mine">Mine</button><button data-a="handover">Hand over</button>'
               '<button data-a="note">Note</button>')
    tags = [it['primary'], *it['secondary']]
    chips = ''.join(f'<span class="tag{" p" if n == 0 else ""}">{e(t)}</span>' for n, t in enumerate(tags))
    return (
        f'<article class="card {cls}" data-id="{e(it["id"])}" data-views="{e(" ".join(it["views"]))}" '
        f'data-proj="{e("|".join(tags))}" data-kind="{e(it["kind"])}"><details><summary>'
        f'<div class="top"><span class="id">{e(it["id"])}</span>'
        f'<span class="box">[{e(it["box"])}] {e(BOX_LABEL.get(it["box"], "?"))}</span>'
        f'<span class="head">{chips}{e(it["head"])}</span></div>'
        f'<div class="meta">owner <b>{e(it["owner"])}</b> · next <b>{e(it["mover"])}</b> · '
        f'seen {e(it["seen"])} · {e(it["kind"])} · {e(it["section"] or "?")} · line {it["line"]}</div></summary>'
        f'<div class="body"><pre class="raw">{e(it["lines"][0])}</pre>'
        + (f'<pre class="hist">{e(hist)}</pre>' if hist else '')
        + f'<div class="act">{person}<input name="note" placeholder="Note" maxlength="2000">{buttons}</div>'
        f'</div></details></article>')


def render_page(items, warnings, path):
    e = html.escape
    st = stats(items)
    pct = round(100 * st['mine_done'] / st['mine_total']) if st['mine_total'] else 0
    meter = '<div id="meter" hidden></div>'
    if DEADLINE:
        days = (DEADLINE - datetime.date.today()).days
        meter = (f'<div id="meter" title="Items where you are owner or next mover. Done = closed, handed over '
                 f'or moved to someone else."><strong>Your items: {st["mine_done"]} done of {st["mine_total"]} · '
                 f'{st["mine_left"]} left</strong><span class="bar"><i style="width:{pct}%"></i></span>'
                 f'<small>{pct} % · {days} days left until {DEADLINE.isoformat()}</small></div>')
    tabs = ''.join(f'<button data-view="{k}">{e(label)} <b>{st["views"][k]}</b></button>' for k, label in views())
    proj = '<option value="">All projects</option>' + ''.join(
        f'<option value="{e(t)}">{e(t)} ({n})</option>' for t, n in st['projects'])
    kind = '<option value="">All kinds</option>' + ''.join(
        f'<option value="{e(k)}">{e(k)} ({st["kinds"][k]})</option>' for k in KINDS)
    who = Counter(i['mover'][len('waiting on '):] for i in items if 'waiting' in i['views'])
    who_txt = ' · '.join(f'{e(p)} ({n})' for p, n in who.most_common()) or 'nobody'
    warn = ''.join(f'<li>{e(w)}</li>' for w in warnings)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ledger board</title><style>{CSS}</style></head><body>
<header>
{meter}
<nav id="tabs">{tabs}</nav>
<div class="filters"><input id="q" type="search" placeholder="Search ids and full text…" autocomplete="off">
<select id="proj" title="Project">{proj}</select><select id="kind" title="Kind">{kind}</select><span id="shown"></span><button id="reload" type="button">↻ Reload</button></div>
</header>
<main id="list"><p class="who" data-only="waiting">Waiting on: {who_txt}</p>
{''.join(render_card(i) for i in items)}</main>
<footer><details><summary>File and parser warnings ({len(warnings)})</summary>
<p>{e(str(path))} · {st['total']} items · no recognised owner: {st['no_owner']}</p><ul>{warn}</ul></details></footer>
<script>{JS}</script></body></html>"""


# ---------------------------------------------------------------- server

def make_handler(path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            data = body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def json(self, code, obj):
            self.send(code, json.dumps(obj, ensure_ascii=False), 'application/json; charset=utf-8')

        def guard(self):                        # DNS-rebinding guard: only our own host names
            if self.headers.get('Host') not in HOSTS:
                self.send(403, 'forbidden host', 'text/plain; charset=utf-8')
                return False
            return True

        def do_GET(self):
            if not self.guard():
                return
            try:
                items, warnings = parse(path.read_text('utf-8'))
            except Exception as ex:
                return self.send(500, f'cannot read OPEN.md: {ex}', 'text/plain; charset=utf-8')
            if self.path == '/':
                self.send(200, render_page(items, warnings, path), 'text/html; charset=utf-8')
            elif self.path == '/api/items':
                self.json(200, {'ledger': str(path), 'stats': stats(items), 'warnings': warnings, 'items': items})
            else:
                self.send(404, 'not found', 'text/plain; charset=utf-8')

        def do_POST(self):
            if not self.guard():
                return
            # Cross-site guard: a foreign page cannot send JSON without a preflight we never answer,
            # and a browser always tells us its Origin on POST.
            if self.path != '/api/action' or self.headers.get('Origin', next(iter(ORIGINS))) not in ORIGINS \
                    or not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.json(403, {'error': 'refused'})
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 20000:
                    raise ValueError
                req = json.loads(self.rfile.read(n))
                if not isinstance(req, dict):
                    raise ValueError
            except ValueError:
                return self.json(400, {'error': 'invalid request'})
            try:
                oid = perform(path, req.get('id'), req.get('action'), req.get('person', ''), req.get('note', ''))
            except ActionError as ex:
                return self.json(409, {'error': str(ex)})
            except Exception as ex:
                return self.json(500, {'error': f'{type(ex).__name__}: {ex}'})
            item = next((i for i in parse(path.read_text('utf-8'))[0] if i['id'] == oid), None)
            print(f'{datetime.datetime.now():%H:%M:%S} {req.get("action")} {oid}', flush=True)
            self.json(200, {'ok': True, 'item': item})
    return Handler


def report(items, warnings, path):
    st = stats(items)
    b, v = st['box'], st['views']
    print(f'{path}: {st["total"]} items parsed  [ ] {b.get(" ", 0)}  [~] {b.get("~", 0)}  [x] {b.get("x", 0) + b.get("X", 0)}'
          f'  · no parseable owner: {st["no_owner"]}')
    print('views: ' + ' · '.join(f'{label} {v[k]}' for k, label in views()))
    print(f'mine: {st["mine_done"]} done of {st["mine_total"]} · {st["mine_left"]} left')
    print('project: ' + ' · '.join(f'{t} {n}' for t, n in st['projects']))
    print('kind: ' + ' · '.join(f'{k} {n}' for k, n in st['kinds'].items()))
    for w in warnings:
        print('warning:', w)


# ---------------------------------------------------------------- self-test

def selftest(src):
    """Every action on a temp copy; asserts only the intended lines change. Never touches src.
    On the bundled example every shape must exist; a live ledger may lack some (skipped)."""
    import shutil
    global DEADLINE
    strict = src == EXAMPLE
    t, _ = parse('## New from x\n### New preconditions\n- [ ] `OI-1` #a-b  #handover #c_d Text #not — **Bob** — me — seen 2025-03-01\n'
                 '## Threats (1.3)\n- [~] `OI-2` #x:y Plain\n## Handover\n- [ ] `OI-3` #z')
    got = [(i['primary'], i['secondary'], i['kind'], i['head'], i['structured'], i['owner'], i['mover']) for i in t]
    assert got == [('#a-b', ['#handover', '#c_d'], 'Precondition', 'Text #not', True, 'Bob', 'me'),
                   (NO_PROJECT, [], 'Threat', '#x:y Plain', False, '?', '?'),
                   ('#z', [], 'Task', '', False, '?', '?')], got
    assert projects(t) == [('#a-b', 1), ('#c_d', 1), ('#z', 1), ('#handover', 1), (NO_PROJECT, 1)], projects(t)
    assert is_me(f'{ME} + Bob') and not is_me(f'X{ME}') and not is_me('?')
    d = Path(tempfile.mkdtemp())
    try:
        p = d / 'OPEN.md'
        snap0 = src.read_bytes()
        p.write_bytes(snap0)
        items, _ = parse(p.read_text('utf-8'))
        dup = {i for i, c in Counter(x['id'] for x in items).items() if c > 1}
        ok = [i for i in items if i['id'] not in dup]
        # prefer multi-tag items, so the tag-prefix checks below see more than one tag
        pick = lambda f, skip=(): next((i['id'] for i in sorted(ok, key=lambda i: not i['secondary'])
                                       if f(i) and i['id'] not in skip), None)   # the live ledger may lack a shape
        s1 = pick(lambda i: i['box'] != 'x' and i['structured'])
        cases = [
            (s1, 'wait', 'Bob', 'a < b & "c" `d`'),   # escaping case: s1 always exists
            (pick(lambda i: i['box'] != 'x' and not i['structured'] and len(i['lines']) == 1), 'mine', '', ''),
            (pick(lambda i: i['box'] != 'x' and not i['structured'] and any('↳' in l for l in i['lines'])), 'handover', 'Carol Jones', 'handover'),
            (pick(lambda i: i['box'] != 'x' and len(i['lines']) > 1 and not any('↳' in l for l in i['lines'])), 'note', '', 'test'),
            (pick(lambda i: i['box'] != 'x' and i['structured'], {s1}), 'handover', 'Carol Jones', ''),
            (s1, 'done', '', ''),
            (pick(lambda i: i['box'] == 'x'), 'note', '', 'after closing'),
        ]
        ids_of = lambda t: Counter(m[2] for l in t.split('\n') if (m := HEAD.match(l)))
        # "] `OI-n` #tags" -- everything of the head prefix except the box character
        prefix = lambda ls, oid: next(l[4:m.end()] for l in ls if (m := HEAD.match(l)) and m[2] == oid)
        tagged = set()
        for oid, action, person, note in cases:
            if oid is None:
                assert not strict, f'example/OPEN.md lacks the shape for {action}'
                print(f'  skip {action:8} no item of this shape in the ledger')
                continue
            before = p.read_text('utf-8').split('\n')
            perform(p, oid, action, person, note)
            after = p.read_text('utf-8').split('\n')
            ins = list((Counter(after) - Counter(before)).elements())   # multiset: a ↳ line may repeat elsewhere
            assert len(after) == len(before) + 1, (oid, action)
            assert sum(l.startswith('  ↳ [') for l in ins) == 1, (oid, action, ins)
            assert len(ins) <= 2 and all(l.startswith('  ↳ [') or HEAD.match(l)[2] == oid for l in ins), ins
            assert ids_of('\n'.join(after)) == ids_of('\n'.join(before))
            it = next(i for i in parse('\n'.join(after))[0] if i['id'] == oid)
            want = {'wait': ('mover', 'waiting on Bob'), 'mine': ('mover', 'me'), 'handover': ('owner', 'Carol Jones')}
            if action in want:
                assert it[want[action][0]] == want[action][1], (oid, action, it['owner'], it['mover'])
            if action == 'done':
                assert it['box'] == 'x'
            mode = 'in place' if len(ins) == 2 else 'history only'
            assert prefix(after, oid) == prefix(before, oid), (oid, action, prefix(before, oid), prefix(after, oid))
            if '#' in prefix(before, oid):
                tagged.add(mode)
            print(f'  ok  {action:8} {oid}  {mode:12}  tags kept: {prefix(after, oid).split("`")[-1].strip() or "-"}')
        assert tagged >= {'in place', 'history only'}, f'tag prefix not exercised: {tagged}'
        for bad in [('OI-1; rm', 'note'), ('OI-0', 'note'), (s1, 'done'), ('OI-1', 'drop')]:
            snap = p.read_bytes()
            try:
                perform(p, bad[0], bad[1], '', 'x')
                raise AssertionError(f'accepted {bad}')
            except ActionError:
                assert p.read_bytes() == snap
        page = render_page(parse(p.read_text('utf-8'))[0], [], p)
        assert 'a &lt; b &amp; &quot;c&quot; `d`' in page and 'a < b & "c"' not in page
        assert 'data-proj="' in page and '<select id="proj"' in page and 'id="sec"' not in page
        saved = DEADLINE
        try:                                       # --deadline on/off: handover tab and days-left meter follow it
            for DEADLINE in (None, datetime.date.today()):
                page = render_page(parse(p.read_text('utf-8'))[0], [], p)
                assert ('data-view="handover"' in page) == ('days left' in page) == bool(DEADLINE), DEADLINE
        finally:
            DEADLINE = saved
        assert (d / 'OPEN.md.board-backup').read_bytes() == snap0
        print('selftest OK')
    finally:
        shutil.rmtree(d)


def main():
    global ME, BOARD, DEADLINE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--ledger', type=Path, help='default ~/meetings/OPEN.md (--selftest: example/OPEN.md)')
    ap.add_argument('--me', default=os.environ.get('LEDGER_ME', ''),
                    help='your name as written in the ledger (default $LEDGER_ME)')
    ap.add_argument('--deadline', type=datetime.date.fromisoformat,
                    help='YYYY-MM-DD: show the handover view and a days-left meter')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.me.strip():
        ME, BOARD = a.me.strip(), board_re(a.me.strip())
    elif not a.selftest:
        ap.error('--me NAME (or LEDGER_ME) is required: it marks your items and signs the board\'s history lines')
    DEADLINE = a.deadline
    path = (a.ledger or (EXAMPLE if a.selftest else Path.home() / 'meetings' / 'OPEN.md')).expanduser().resolve()
    items, warnings = parse(path.read_text('utf-8'))
    report(items, warnings, path)
    if a.selftest:
        return selftest(path)
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), make_handler(path))
    print(f'Board: http://127.0.0.1:{PORT}/  (Ctrl+C to stop)', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
