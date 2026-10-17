"""the utku times — a three-page print-style paper, built next to the daily brief.
page 1 the front page, page 2 the whole daily brief, page 3 sudokus + the sealed planner.

used by generate.py. stdlib only (plus the `openssl` binary for the sealed page).

inputs  : paper/YYYY-MM-DD.json            public content   (schema in README)
          content/YYYY-MM-DD.md            the daily brief, printed in full on page 2
          paper/YYYY-MM-DD.private.json    calendar + personal radar (gitignored)
          paper/YYYY-MM-DD.sealed.json     encrypted form of the private file (committed)
outputs : times/index.html                 newest edition
          times/YYYY-MM-DD.html            permalink per edition

the personal part of the back page is AES-256-CBC + HMAC-SHA256 encrypted with a
key from PBKDF2(TIMES_PASSPHRASE). the page ships only ciphertext and decrypts in
the browser with WebCrypto, so the public site never exposes calendar data.
"""
import base64
import datetime as dt
import hashlib
import hmac
import html
import json
import os
import pathlib
import random
import re
import subprocess
import unicodedata

PBKDF2_ITERS = 250_000
FIRST_ISSUE = dt.date(2026, 10, 17)


# ── small helpers ──────────────────────────────────────────────────────────

def esc(text) -> str:
    return html.escape(str(text), quote=True)


LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITAL = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def inline(text) -> str:
    out = html.escape(str(text), quote=False)
    out = LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = BOLD.sub(r"<strong>\1</strong>", out)
    return ITAL.sub(r"<em>\1</em>", out)


def long_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"


def seed_for(iso: str, salt: str) -> int:
    return int(hashlib.sha256(f"{iso}:{salt}".encode()).hexdigest()[:12], 16)


# ── sudoku ─────────────────────────────────────────────────────────────────

def _peers():
    peers = []
    for i in range(81):
        r, c = divmod(i, 9)
        s = {j for j in range(81) if j // 9 == r or j % 9 == c
             or (j // 27 == r // 3 and (j % 9) // 3 == c // 3)}
        s.discard(i)
        peers.append(sorted(s))
    return peers


PEERS = _peers()


def _candidates(grid, i):
    used = {grid[p] for p in PEERS[i]}
    return [v for v in range(1, 10) if v not in used]


def _count(grid, limit=2) -> int:
    """number of solutions, stopping at `limit` (mrv backtracking)."""
    best, best_c = None, None
    for i in range(81):
        if grid[i] == 0:
            c = _candidates(grid, i)
            if not c:
                return 0
            if best_c is None or len(c) < len(best_c):
                best, best_c = i, c
                if len(c) == 1:
                    break
    if best is None:
        return 1
    total = 0
    for v in best_c:
        grid[best] = v
        total += _count(grid, limit - total)
        if total >= limit:
            break
    grid[best] = 0
    return total


def _full_grid(rng) -> list:
    grid = [0] * 81

    def fill() -> bool:
        best, best_c = None, None
        for i in range(81):
            if grid[i] == 0:
                c = _candidates(grid, i)
                if not c:
                    return False
                if best_c is None or len(c) < len(best_c):
                    best, best_c = i, c
        if best is None:
            return True
        rng.shuffle(best_c)
        for v in best_c:
            grid[best] = v
            if fill():
                return True
        grid[best] = 0
        return False

    fill()
    return grid


def _needs_more_than_singles(puzzle) -> bool:
    """true when naked + hidden singles alone cannot finish the puzzle."""
    g = list(puzzle)
    units = ([[r * 9 + c for c in range(9)] for r in range(9)]
             + [[r * 9 + c for r in range(9)] for c in range(9)]
             + [[(br * 3 + r) * 9 + bc * 3 + c for r in range(3) for c in range(3)]
                for br in range(3) for bc in range(3)])
    progress = True
    while progress:
        progress = False
        for i in range(81):
            if g[i] == 0:
                c = _candidates(g, i)
                if len(c) == 1:
                    g[i] = c[0]
                    progress = True
        for unit in units:
            for v in range(1, 10):
                if v in (g[i] for i in unit):
                    continue
                spots = [i for i in unit if g[i] == 0 and v in _candidates(g, i)]
                if len(spots) == 1:
                    g[spots[0]] = v
                    progress = True
    return 0 in g


def make_sudoku(iso: str, salt: str, attempts: int):
    """returns (puzzle, solution). keeps the attempt with the fewest clues that
    still needs techniques beyond singles; every attempt has a unique solution."""
    rng = random.Random(seed_for(iso, salt))
    best = None
    for _ in range(attempts):
        solution = _full_grid(rng)
        puzzle = list(solution)
        order = list(range(81))
        rng.shuffle(order)
        for i in order:
            keep = puzzle[i]
            puzzle[i] = 0
            if _count(list(puzzle)) != 1:
                puzzle[i] = keep
        clues = sum(1 for v in puzzle if v)
        if _needs_more_than_singles(puzzle) and (best is None or clues < best[0]):
            best = (clues, puzzle, solution)
    if best is None:  # extremely unlikely; fall back to the last attempt
        best = (clues, puzzle, solution)
    return best[1], best[2]


def sudoku_html(puzzle, label: str, note: str) -> str:
    cells = []
    for r in range(9):
        for c in range(9):
            v = puzzle[r * 9 + c]
            cls = "sd" + (" r3" if r in (2, 5) else "") + (" c3" if c in (2, 5) else "")
            if v:
                cells.append(f'<div class="{cls} g">{v}</div>')
            else:
                cells.append(f'<div class="{cls}"><input inputmode="numeric" maxlength="1" '
                             f'aria-label="row {r + 1} column {c + 1}"></div>')
    clues = sum(1 for v in puzzle if v)
    return (f'<figure class="sudoku" title="{esc(note)}"><figcaption><b>{esc(label)}</b>'
            f'<span>{clues} givens</span></figcaption>'
            f'<div class="sdgrid">{"".join(cells)}</div></figure>')


def sudoku_key(solution) -> str:
    return "".join(str(v) for v in solution)


# ── generated engraving-style art (fallback when no photo is available) ────

def art_svg(kind: str, iso: str, w: int = 900, h: int = 380) -> str:
    rng = random.Random(seed_for(iso, "art:" + kind))
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" role="img" '
           f'preserveAspectRatio="xMidYMid slice"><rect width="{w}" height="{h}" fill="#111"/>'
           f'<g stroke="#f3f0e8" fill="none" stroke-linecap="round">']
    if kind == "skyline":
        x = 0
        while x < w:
            bw = rng.randint(34, 90)
            bh = rng.randint(70, h - 90)
            out.append(f'<rect x="{x}" y="{h - bh}" width="{bw}" height="{bh}" stroke-width="1.4"/>')
            for yy in range(h - bh + 8, h, 7):
                out.append(f'<line x1="{x + 3}" y1="{yy}" x2="{x + bw - 3}" y2="{yy}" stroke-width=".6" opacity=".55"/>')
            x += bw + rng.randint(2, 10)
    elif kind == "columns":
        n = 8
        gap = w / n
        out.append(f'<path d="M0 90 L{w / 2} 20 L{w} 90 Z" stroke-width="1.6"/>')
        for i in range(n):
            cx = gap * i + gap / 2
            out.append(f'<rect x="{cx - 22}" y="100" width="44" height="{h - 130}" stroke-width="1.5"/>')
            for k in range(-16, 17, 4):
                out.append(f'<line x1="{cx + k}" y1="104" x2="{cx + k}" y2="{h - 34}" stroke-width=".5" opacity=".6"/>')
        for yy in range(h - 26, h, 6):
            out.append(f'<line x1="0" y1="{yy}" x2="{w}" y2="{yy}" stroke-width="1"/>')
    else:  # circuit
        cx, cy, half = w / 2, h / 2, 70
        out.append(f'<rect x="{cx - half}" y="{cy - half}" width="{half * 2}" height="{half * 2}" stroke-width="2"/>')
        out.append(f'<rect x="{cx - half + 18}" y="{cy - half + 18}" width="{half * 2 - 36}" height="{half * 2 - 36}" stroke-width="1"/>')
        for i in range(14):
            off = -half + 10 + i * 10
            for side in range(4):
                length = rng.randint(60, 300)
                if side == 0:
                    x, y, x2, y2 = cx + off, cy - half, cx + off, cy - half - length
                elif side == 1:
                    x, y, x2, y2 = cx + off, cy + half, cx + off, cy + half + length
                elif side == 2:
                    x, y, x2, y2 = cx - half, cy + off, cx - half - length, cy + off
                else:
                    x, y, x2, y2 = cx + half, cy + off, cx + half + length, cy + off
                if rng.random() < .8:
                    jog = rng.choice((-1, 1)) * rng.randint(10, 40)
                    mx, my = (x2 + jog, y2) if side < 2 else (x2, y2 + jog)
                    out.append(f'<polyline points="{x:.0f},{y:.0f} {x2:.0f},{y2:.0f} {mx:.0f},{my:.0f}" stroke-width="1.1"/>')
                    out.append(f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="3" stroke-width="1.1"/>')
    out.append("</g></svg>")
    return "".join(out)


# ── the sealed (encrypted) back page ───────────────────────────────────────

def _keys(passphrase: str, salt: bytes):
    raw = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, PBKDF2_ITERS, 64)
    return raw[:32], raw[32:]


def seal(payload_html: str, passphrase: str) -> dict:
    salt, iv = os.urandom(16), os.urandom(16)
    enc_key, mac_key = _keys(passphrase, salt)
    proc = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-K", enc_key.hex(), "-iv", iv.hex()],
        input=payload_html.encode(), capture_output=True, check=True)
    ct = proc.stdout
    mac = hmac.new(mac_key, iv + ct, hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()
    return {"v": 1, "iter": PBKDF2_ITERS, "salt": b64(salt), "iv": b64(iv),
            "ct": b64(ct), "mac": b64(mac)}


def open_sealed(blob: dict, passphrase: str) -> str:
    """inverse of seal(); used by the self-test and for local debugging."""
    salt, iv = base64.b64decode(blob["salt"]), base64.b64decode(blob["iv"])
    ct, mac = base64.b64decode(blob["ct"]), base64.b64decode(blob["mac"])
    enc_key, mac_key = _keys(passphrase, salt)
    if not hmac.compare_digest(mac, hmac.new(mac_key, iv + ct, hashlib.sha256).digest()):
        raise ValueError("wrong passphrase")
    proc = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-K", enc_key.hex(), "-iv", iv.hex()],
        input=ct, capture_output=True, check=True)
    return proc.stdout.decode()


def private_html(priv: dict) -> str:
    """the personal panel — rendered to html, then sealed."""
    parts = []
    cal = priv.get("calendar", [])
    rows = []
    for ev in cal:
        note = f'<span class="ev-note">{inline(ev["note"])}</span>' if ev.get("note") else ""
        rows.append(f'<li><span class="ev-when"><b>{esc(ev["day"])}</b> {esc(ev.get("time", ""))}</span>'
                    f'<span class="ev-what">{inline(ev["title"])}{note}</span></li>')
    parts.append('<div class="priv-col"><h4>Your week &mdash; from your calendar</h4>'
                 + (f'<ul class="agenda">{"".join(rows)}</ul>' if rows
                    else '<p class="muted">Nothing on the calendar. Enjoy it.</p>') + '</div>')
    radar = []
    for it in priv.get("radar", []):
        title = inline(it["title"])
        if it.get("url"):
            title = f'<a href="{esc(it["url"])}" target="_blank" rel="noopener">{title}</a>'
        radar.append(f'<li><span class="tag">{esc(it.get("kind", "note"))}</span>'
                     f'<div><b>{title}</b>'
                     + (f' <span class="when">{esc(it["when"])}</span>' if it.get("when") else "")
                     + (f'<p>{inline(it["why"])}</p>' if it.get("why") else "")
                     + '</div></li>')
    parts.append('<div class="priv-col"><h4>On your radar</h4>'
                 f'<ul class="radar">{"".join(radar)}</ul></div>')
    note = priv.get("note")
    foot = f'<p class="priv-note">{inline(note)}</p>' if note else ""
    return f'<div class="priv-grid">{"".join(parts)}</div>{foot}'


def sealed_for(iso: str, root: pathlib.Path, passphrase):
    """returns the sealed blob for an edition, (re)sealing when a plaintext
    private file is present, otherwise reusing the committed ciphertext."""
    paper = root / "paper"
    plain, sealed = paper / f"{iso}.private.json", paper / f"{iso}.sealed.json"
    if plain.exists():
        if not passphrase:
            print(f"  ! {plain.name}: TIMES_PASSPHRASE not set — back page left unsealed")
        else:
            blob = seal(private_html(json.loads(plain.read_text(encoding="utf-8"))), passphrase)
            sealed.write_text(json.dumps(blob), encoding="utf-8")
    if sealed.exists():
        return json.loads(sealed.read_text(encoding="utf-8"))
    return None


# ── rendering the two pages ────────────────────────────────────────────────

def _figure(lead: dict, iso: str) -> str:
    img = lead.get("image") or {}
    if img.get("src"):
        inner = (f'<div class="halftone"><img src="{esc(img["src"])}" alt="{esc(img.get("alt", ""))}" '
                 f'loading="eager"></div>')
    else:
        inner = f'<div class="halftone art">{art_svg(img.get("art", "circuit"), iso)}</div>'
    cap = img.get("caption", "")
    credit = img.get("credit", "")
    return (f'<figure class="photo">{inner}<figcaption>{inline(cap)}'
            + (f' <span class="credit">{inline(credit)}</span>' if credit else "")
            + "</figcaption></figure>")


def inside_index(brief):
    rows = []
    back = "A3" if brief else "A2"
    if brief:
        n = sum(len(items) for _, items in brief["sections"])
        names = ", ".join(_title(name) for name, _ in brief["sections"])
        rows.append(("A2", "The Daily Brief", f"All {n} stories: {names}."))
    rows.append((back, "Three Sudokus", "Difficult, devilish and diabolical. Singles alone won't save you."))
    rows.append((back, "Your Week & Your Radar", "Calendar, deadlines and programs. Sealed, unlocks with your passphrase."))
    return rows


def _title(name: str) -> str:
    words = [("AI" if w == "ai" else w if w == "&" else w.capitalize()) for w in name.split()]
    return " ".join(words)


def render_brief(brief: dict, iso: str) -> str:
    cols = []
    for name, items in brief["sections"]:
        lis = "".join(f"<li>{inline(i)}</li>" for i in items)
        cols.append(f'<section class="bsec"><h3>{esc(_title(name))}</h3><ul>{lis}</ul></section>')
    n = sum(len(items) for _, items in brief["sections"])
    return f'''
<article class="sheet brief" id="a2">
	<header class="back-head"><span class="mini-flag">The Utku Times</span><span>The Daily Brief &middot; {n} stories</span><span>{esc(long_date(iso))}</span></header>
	<div class="brief-cols">{"".join(cols)}</div>
	<footer class="folio"><span>The Utku Times</span><span>{esc(long_date(iso))}</span><span>A2</span></footer>
</article>'''


def render_front(c: dict, iso: str, issue_no: int, brief) -> str:
    lead = c["lead"]
    body = "".join(f"<p>{inline(p)}</p>" for p in lead["body"])
    box = ""
    if lead.get("box"):
        items = "".join(f"<li>{inline(i)}</li>" for i in lead["box"]["items"])
        box = f'<aside class="box"><h4>{esc(lead["box"]["title"])}</h4><ol>{items}</ol></aside>'
    secondary = "".join(
        f'<article class="sec"><p class="kicker">{esc(s.get("kicker", ""))}</p>'
        f'<h3>{inline(s["headline"])}</h3>'
        + "".join(f"<p>{inline(p)}</p>" for p in s["body"]) + "</article>"
        for s in c.get("secondary", []))
    mk = "".join(
        f'<tr><th>{esc(m["name"])}</th><td>{esc(m["value"])}</td>'
        f'<td class="chg {"up" if str(m.get("change", "")).startswith("+") else "dn" if str(m.get("change", "")).startswith(("-", "−")) else ""}">'
        f'{esc(m.get("change", ""))}</td></tr>' for m in c.get("markets", []))
    wx = c.get("weather", {})
    days = "".join(f'<tr><th>{esc(d["d"])}</th><td>{esc(d["c"])}</td><td>{esc(d["t"])}</td></tr>'
                   for d in wx.get("days", []))
    inside = "".join(
        f'<li><b>{esc(page)}</b><div><strong>{esc(head)}</strong><span>{esc(blurb)}</span></div></li>'
        for page, head, blurb in inside_index(brief))
    stats = "".join(f'<div class="stat"><b>{esc(s["big"])}</b><span>{inline(s["text"])}</span></div>'
                    for s in c.get("stats", []))
    return f'''
<article class="sheet front" id="a1">
	<header class="flag">
		<p class="tagline">{esc(c.get("tagline", "All the news that fits in your pocket"))}</p>
		<h1 class="nameplate">The Utku Times</h1>
		<div class="folio-bar"><span>Vol. I &middot; No. {issue_no}</span><span>{esc(long_date(iso))}</span><span>Ankara &middot; Free</span></div>
	</header>
	<div class="cols">
		<div class="main">
			<p class="kicker">{esc(lead.get("kicker", ""))}</p>
			<h2 class="lead-h">{inline(lead["headline"])}</h2>
			<p class="deck">{inline(lead.get("deck", ""))}</p>
			{_figure(lead, iso)}
			<div class="lead-body">{body}{box}</div>
			<p class="src">{inline(lead.get("source", ""))}</p>
			<div class="secondary">{secondary}</div>
		</div>
		<aside class="side">
			<h5>Markets at a glance</h5>
			<table class="mkt">{mk}</table>
			<p class="small">{inline(c.get("markets_note", ""))}</p>
			<h5>Weather &middot; Ankara</h5>
			<p class="wx-now"><b>{esc(wx.get("now", ""))}</b> <span>{esc(wx.get("cond", ""))}</span></p>
			<p class="small">{inline(wx.get("summary", ""))}</p>
			<table class="wx">{days}</table>
			<h5>Inside</h5>
			<ul class="inside">{inside}</ul>
		</aside>
	</div>
	<div class="stats">{stats}</div>
	<footer class="folio"><span>The Utku Times</span><span>{esc(long_date(iso))}</span><span>A1</span></footer>
</article>'''


def render_back(iso: str, sealed, sd_html: str, key_html: str, page_no: str) -> str:
    if sealed:
        priv = ('<section class="private" id="private" data-state="locked">'
                '<div class="puz-head"><h3>For Utku&rsquo;s eyes only</h3><span>sealed &middot; unlocks in your browser</span></div>'
                '<form class="unlock" id="unlock"><label>passphrase '
                '<input type="password" id="pp" autocomplete="current-password" required></label>'
                '<label class="rem"><input type="checkbox" id="remember" checked> remember on this device</label>'
                '<button type="submit">Unlock</button><p class="err" id="pperr" role="alert"></p></form>'
                '<div id="privbody" hidden></div>'
                f'<script type="application/json" id="sealed">{json.dumps(sealed)}</script></section>')
    else:
        priv = ('<section class="private"><div class="puz-head"><h3>For Utku&rsquo;s eyes only</h3>'
                '<span>not published</span></div><p class="muted">No personal page was sealed for this edition.</p></section>')
    return f'''
<article class="sheet back" id="a-back">
	<header class="back-head"><span class="mini-flag">The Utku Times</span><span>Sudokus &amp; planner</span><span>{esc(long_date(iso))}</span></header>
	<div class="puz-head"><h3>Sudoku</h3><span>no mercy</span></div>
	<div class="sudoku-row">{sd_html}{priv}</div>
	{key_html}
	<footer class="folio"><span>The Utku Times</span><span>{esc(long_date(iso))}</span><span>{page_no}</span></footer>
</article>'''


def build_edition(path: pathlib.Path, root: pathlib.Path, passphrase, issue_no: int, brief=None) -> dict:
    iso = path.stem.split(".")[0]
    c = json.loads(path.read_text(encoding="utf-8"))

    s1, a1 = make_sudoku(iso, "hard", attempts=6)
    s2, a2 = make_sudoku(iso, "devilish", attempts=14)
    s3, a3 = make_sudoku(iso, "diabolical", attempts=30)
    sd_html = (sudoku_html(s1, "Difficult", "needs more than singles")
               + sudoku_html(s2, "Devilish", "few givens")
               + sudoku_html(s3, "Diabolical", "the fewest givens we could find"))
    key = ('<details class="key"><summary>answer key</summary>'
           f'<p><b>Difficult.</b> {sudoku_key(a1)}</p>'
           f'<p><b>Devilish.</b> {sudoku_key(a2)}</p>'
           f'<p><b>Diabolical.</b> {sudoku_key(a3)}</p></details>')
    sealed = sealed_for(iso, root, passphrase)
    page = (render_front(c, iso, issue_no, brief)
            + (render_brief(brief, iso) if brief else "")
            + render_back(iso, sealed, sd_html, key, "A3" if brief else "A2"))
    lead = c["lead"]
    plain_head = re.sub(r"[*\[\]]|\(https?://[^)]*\)", "", lead["headline"])
    return {"iso": iso, "issue": issue_no, "headline": plain_head, "page": page,
            "desc": re.sub(r"[*\[\]]|\(https?://[^)]*\)", "", lead.get("deck", ""))}


def issue_numbers(files):
    """edition number = days since the first issue + 1 (stable across rebuilds)."""
    return {p.stem.split(".")[0]: (dt.date.fromisoformat(p.stem.split(".")[0]) - FIRST_ISSUE).days + 1
            for p in files}
