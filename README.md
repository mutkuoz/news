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

## one-time setup (already done or in progress)

1. **github pages** — settings → pages → deploy from branch → `main` / root.
2. **custom domain** — settings → pages → custom domain: `news.utku.space`,
   then tick *enforce https* once the certificate is issued.
3. **dns** — at the `utku.space` dns provider, add:
   `CNAME  news  →  mutkuoz.github.io.`
4. **routine** — the "daily news → news.utku.space" trigger in claude code
   (claude.ai/code) does the rest each morning.
