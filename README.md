# utku's news — the daily brief

a machine-written morning paper at **[news.utku.space](https://news.utku.space)**.
every day at 09:00 (gmt+3) a scheduled [claude code](https://claude.com/claude-code)
routine researches the day's news, writes 20–30 bullets, and publishes them here.
the design mirrors [utku.space](https://utku.space) — same serif newspaper look,
same background artwork, same day/night themes.

## how it works

```
09:00 gmt+3 (06:00 utc)
  └─ claude code routine (fresh session)
       ├─ websearch: international politics · ai & computing · business & tech · other
       ├─ writes content/YYYY-MM-DD.md          (bullet list, format below)
       ├─ runs python3 generate.py              (rebuilds all html)
       └─ commits & pushes to main              → github pages redeploys
```

| path                   | what it is                                        |
| ---------------------- | ------------------------------------------------- |
| `content/*.md`         | one markdown file per edition — the only inputs   |
| `template.html`        | the page shell (style lives here)                 |
| `generate.py`          | stdlib-only builder: content → html               |
| `times.py`, `times.html` | the utku times (see below)                      |
| `index.html`           | generated — latest edition                        |
| `archive/*.html`       | generated — permalink per edition                 |
| `archive.html`         | generated — list of all editions                  |
| `CNAME`                | `news.utku.space` (github pages custom domain)    |

## content format (the contract the routine follows)

`content/YYYY-MM-DD.md`, named for the edition date in europe/istanbul:

```markdown
# 31 july 2026

## international politics
- one concise sentence per story — [source](https://example.com/article)

## ai & computing
- …
```

rules: first line is `# <human date>`; sections are `## <name>`; items are `- ` bullets;
inline `[text](url)`, `**bold**` and `*italic*` are supported. everything else is ignored.
end each bullet with an em-dash and a lowercase `[source](url)` link.

## build locally

```bash
python3 generate.py   # no dependencies
```

then open `index.html`. never edit the generated html by hand — edit
`content/` or `template.html` and regenerate.

## the utku times — a two-page paper (`/times/`)

a print-style front page and a puzzles-and-planner back page, built by the same
`generate.py` from `paper/*.json` (code lives in `times.py`, shell in `times.html`).
prints as exactly two a4 sheets (ctrl/cmd-p).

| path                              | what it is                                                       |
| --------------------------------- | ---------------------------------------------------------------- |
| `paper/YYYY-MM-DD.json`           | public content: lead story, markets, weather, crossword entries  |
| `paper/YYYY-MM-DD.private.json`   | calendar + personal radar. **gitignored**, never committed       |
| `paper/YYYY-MM-DD.sealed.json`    | the private page, encrypted. this is what gets committed         |
| `paper_data.py`                   | real markets / weather / commons photo, so numbers aren't recalled from memory |
| `times/*.html`                    | generated, like the rest                                         |

**the sealed back page.** the site is public, so the calendar and personal radar are
encrypted at build time (PBKDF2 → AES-256-CBC + HMAC-SHA256, needs the `openssl`
binary) with the passphrase in the `TIMES_PASSPHRASE` environment variable, and
decrypted in the browser with WebCrypto. without the variable the build still works but
leaves the panel out, and past editions keep their committed ciphertext.

**public json** (`paper/YYYY-MM-DD.json`) — write plain text, not html entities:

```json
{
  "tagline": "…",
  "lead": { "kicker": "", "headline": "", "deck": "", "body": ["para", "para"],
            "image": { "src": "/assets/times/x.jpg", "alt": "", "caption": "", "credit": "" },
            "box": { "title": "What Utku should do", "items": ["", ""] }, "source": "" },
  "secondary": [{ "kicker": "", "headline": "", "body": ["para"] }],
  "markets": [], "markets_note": "", "weather": {},
  "inside": [{ "page": "A6", "head": "", "blurb": "" }],
  "stats": [{ "big": "229%", "text": "" }],
  "crossword": { "entries": [{ "answer": "WORD", "clue": "…" }] }
}
```

`image` is either a photo (`python3 paper_data.py image "<terms>"`, freely licensed from
wikimedia commons) or `{"art": "skyline|columns|circuit", "caption": "…"}` for a generated
engraving. `markets` and `weather` come straight from `paper_data.py markets|weather`.
give the crossword 25–30 entries; the generator fits what it can and reports the rest.
both sudokus are generated per date (unique solution; the "difficult" one needs more than
singles) — nothing to write.

**private json** (`paper/YYYY-MM-DD.private.json`):

```json
{ "calendar": [{ "day": "Thu 22 Oct", "time": "all day", "title": "", "note": "" }],
  "radar": [{ "kind": "deadline|funding|program|event|test", "title": "", "when": "", "why": "", "url": "" }],
  "note": "" }
```

the daily routine does, after the brief: write `paper/…json` and `paper/…private.json`,
run `python3 generate.py` with `TIMES_PASSPHRASE` set, then commit `paper/`, `times/` and
`assets/times/` (never the `.private.json`). the personal profile (what to look for) lives
in the routine's own prompt, not in this public repo.

## one-time setup (already done or in progress)

1. **github pages** — settings → pages → deploy from branch → `main` / root.
2. **custom domain** — settings → pages → custom domain: `news.utku.space`,
   then tick *enforce https* once the certificate is issued.
3. **dns** — at the `utku.space` dns provider, add:
   `CNAME  news  →  mutkuoz.github.io.`
4. **routine** — the "daily news → news.utku.space" trigger in claude code
   (claude.ai/code) does the rest each morning.
