#!/usr/bin/env python3
"""build news.utku.space — turns content/*.md into the static site.

usage: python3 generate.py          (run from the repo root)

inputs : content/YYYY-MM-DD.md      one file per edition
         template.html              the page shell
outputs: index.html                 newest edition
         archive/YYYY-MM-DD.html    permalink for every edition
         archive.html               list of all editions

content format (strict — the daily routine writes this):
  line 1        # 31 july 2026            human date, becomes the dateline
  sections      ## international politics
  items         - one sentence per story — [source](https://…)
  inline        [text](url), **bold**, *italic*

stdlib only. no dependencies.
"""
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SITE = "https://news.utku.space"
PREV_ON_INDEX = 10  # how many past editions the front page lists


# ── parsing ────────────────────────────────────────────────────────────────

def parse(path: pathlib.Path) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
        raise ValueError(f"{path.name}: filename must be YYYY-MM-DD.md")
    title, sections = None, []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.startswith("# ") and title is None:
            title = ln[2:].strip()
        elif ln.startswith("## "):
            sections.append((ln[3:].strip(), []))
        elif ln.startswith("- "):
            if not sections:
                raise ValueError(f"{path.name}: bullet before any '## section'")
            sections[-1][1].append(ln[2:].strip())
    if title is None:
        raise ValueError(f"{path.name}: first line must be '# <human date>'")
    sections = [(name, items) for name, items in sections if items]
    if not sections:
        raise ValueError(f"{path.name}: no '- ' items found")
    return {"iso": path.stem, "title": title, "sections": sections}


# ── inline markdown → html ─────────────────────────────────────────────────

LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
ITAL = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = BOLD.sub(r"<strong>\1</strong>", out)
    out = ITAL.sub(r"<em>\1</em>", out)
    return out


# ── rendering ──────────────────────────────────────────────────────────────

def render_sections(ed: dict) -> str:
    parts = []
    for name, items in ed["sections"]:
        parts.append('\t<section class="section reveal">')
        parts.append(f'\t\t<div class="rule-head"><h2 class="rule-head-label">{inline(name)}</h2></div>')
        parts.append('\t\t<ul class="briefs">')
        parts.extend(f"\t\t\t<li>{inline(item)}</li>" for item in items)
        parts.append("\t\t</ul>")
        parts.append("\t</section>")
    return "\n".join(parts)


def prev_links(editions: list, skip_iso: str, limit: int) -> str:
    rows = [
        f'\t\t\t<a class="prev-link" href="/archive/{ed["iso"]}.html">'
        f'<span class="d">{ed["iso"]}</span><span class="t">the {inline(ed["title"])} edition</span></a>'
        for ed in editions if ed["iso"] != skip_iso
    ]
    if not rows:
        rows = ['\t\t\t<p class="more-note">none yet — this is the first edition.</p>']
    return "\n".join(rows[:limit])


def fill(template: str, **tokens: str) -> str:
    out = template
    for key, val in tokens.items():
        out = out.replace("{{" + key + "}}", val)
    leftover = re.search(r"\{\{[A-Z_]+\}\}", out)
    if leftover:
        raise ValueError(f"unfilled template token: {leftover.group(0)}")
    return out


def meta_desc(ed: dict) -> str:
    n = sum(len(items) for _, items in ed["sections"])
    topics = ", ".join(name for name, _ in ed["sections"])
    return f"{n} stories in brief — {topics}. the {ed['title']} edition."


def main() -> None:
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    files = sorted((ROOT / "content").glob("*.md"), reverse=True)
    if not files:
        sys.exit("no content/*.md files found")
    editions = [parse(p) for p in files]  # newest first
    (ROOT / "archive").mkdir(exist_ok=True)

    latest = editions[0]

    # front page — the latest edition
    (ROOT / "index.html").write_text(fill(
        template,
        PAGE_TITLE=f"utku's news — the daily brief, {latest['title']}",
        META_DESC=meta_desc(latest),
        CANONICAL=f"{SITE}/",
        DATE_HUMAN=latest["title"],
        SUBLINE="fresh every morning at 09:00 gmt+3",
        CONTENT=render_sections(latest),
        PREVIOUS=prev_links(editions, latest["iso"], PREV_ON_INDEX),
        ARCHIVE_NOTE='<a href="/archive.html">full archive →</a>',
    ), encoding="utf-8")

    # permalink for every edition (including the latest)
    for ed in editions:
        (ROOT / "archive" / f"{ed['iso']}.html").write_text(fill(
            template,
            PAGE_TITLE=f"utku's news — the daily brief, {ed['title']}",
            META_DESC=meta_desc(ed),
            CANONICAL=f"{SITE}/archive/{ed['iso']}.html",
            DATE_HUMAN=ed["title"],
            SUBLINE='an earlier edition — <a href="/">read today&rsquo;s →</a>'
                    if ed is not latest else "fresh every morning at 09:00 gmt+3",
            CONTENT=render_sections(ed),
            PREVIOUS=prev_links(editions, ed["iso"], PREV_ON_INDEX),
            ARCHIVE_NOTE='<a href="/archive.html">full archive →</a>',
        ), encoding="utf-8")

    # the archive index
    (ROOT / "archive.html").write_text(fill(
        template,
        PAGE_TITLE="utku's news — archive",
        META_DESC=f"every edition of the daily brief — {len(editions)} so far.",
        CANONICAL=f"{SITE}/archive.html",
        DATE_HUMAN=latest["title"],
        SUBLINE=f"{len(editions)} edition{'s' if len(editions) != 1 else ''} and counting",
        CONTENT='\t<section class="section reveal">\n'
                '\t\t<div class="rule-head"><h2 class="rule-head-label">all editions</h2></div>\n'
                '\t\t<div class="prev-list">\n'
                + prev_links(editions, "", 100000) +
                "\n\t\t</div>\n\t</section>",
        PREVIOUS=prev_links(editions, latest["iso"], PREV_ON_INDEX),
        ARCHIVE_NOTE="you are reading the full archive.",
    ), encoding="utf-8")

    n = sum(len(items) for _, items in latest["sections"])
    print(f"built: index.html ({latest['iso']}, {n} items), "
          f"{len(editions)} archive page(s), archive.html")


if __name__ == "__main__":
    main()
