#!/usr/bin/env python3
"""data helpers for the utku times — real numbers instead of remembered ones.

usage:
  python3 paper_data.py markets                 → json for the "markets" block
  python3 paper_data.py weather                 → json for the "weather" block (ankara)
  python3 paper_data.py image "<search terms>"  → finds a freely licensed photo on
        wikimedia commons, saves a 1400px copy under assets/times/ and prints the
        "image" block (src, alt, caption, credit). prints nothing and exits 1 when
        nothing suitable is found — use {"art": "skyline|columns|circuit"} instead.

stdlib only. sources: yahoo finance chart api, wttr.in, commons api.
"""
import datetime
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
UA = {"User-Agent": "UtkuTimes/1.0 (https://news.utku.space; utku@kalitte.com.tr) python-urllib"}

MARKETS = [  # (label, yahoo symbol, decimals, prefix)
    ("S&P 500", "^GSPC", 2, ""), ("Nasdaq", "^IXIC", 2, ""), ("Dow", "^DJI", 2, ""),
    ("Nvidia", "NVDA", 2, "$"), ("Intel", "INTC", 2, "$"),
    ("BIST 100", "XU100.IS", 0, ""), ("USD / TRY", "USDTRY=X", 2, ""),
    ("Brent crude", "BZ=F", 2, "$"), ("Gold", "GC=F", 0, "$"), ("Bitcoin", "BTC-USD", 0, "$"),
]


def get(url: str, timeout: int = 20) -> bytes:
    for attempt in range(4):  # commons and yahoo both rate-limit; back off politely
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 3:
                raise
            time.sleep(3 * 2 ** attempt)


def markets() -> list:
    out = []
    for label, sym, dec, pre in MARKETS:
        try:
            d = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=7d&interval=1d"))
            closes = [c for c in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
            last, prev = closes[-1], closes[-2]
            pct = (last / prev - 1) * 100
            out.append({"name": label, "value": f"{pre}{last:,.{dec}f}",
                        "change": f"{'+' if pct >= 0 else '−'}{abs(pct):.2f}%"})
        except Exception as e:  # a missing row beats a made-up one
            print(f"  ! {label}: {e}", file=sys.stderr)
    return out


def weather() -> dict:
    d = json.loads(get("https://wttr.in/Ankara?format=j1"))
    cur = d["current_condition"][0]
    days = []
    for w in d["weather"]:
        noon = w["hourly"][4]["weatherDesc"][0]["value"].strip()
        day = datetime.date.fromisoformat(w["date"]).strftime("%a").upper()
        days.append({"d": day, "c": noon, "t": f"{w['maxtempC']}° / {w['mintempC']}°"})
    t0 = d["weather"][0]
    return {"now": f"{t0['maxtempC']}° / {t0['mintempC']}°", "cond": cur["weatherDesc"][0]["value"].strip().lower(),
            "summary": f"Now {cur['temp_C']}°C, feels like {cur['FeelsLikeC']}°C, humidity {cur['humidity']}%.",
            "days": days}


def commons_image(query: str):
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
           f"&gsrlimit=12&gsrsearch={urllib.parse.quote(query + ' filetype:bitmap')}"
           "&prop=imageinfo&iiprop=url|extmetadata|size&iiurlwidth=1400")
    pages = json.loads(get(api)).get("query", {}).get("pages", {})
    ok_license = re.compile(r"^(cc0|cc[- ]by(-sa)?|public domain|pd)", re.I)
    for p in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if (not ok_license.match(lic) or info.get("width", 0) < 1000 or not info.get("thumburl")
                or info.get("width", 0) < info.get("height", 1) * 1.2):  # landscape only
            continue
        if not re.search(r"\.(jpe?g|png)$", urllib.parse.urlparse(info["url"]).path, re.I):
            continue
        author = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "unknown")).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40]
        dest = ROOT / "assets" / "times" / f"{slug}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(get(re.sub(r"/\d+px-", "/1280px-", info["thumburl"]), 60))
        title = re.sub(r"^File:|\.\w+$", "", p["title"])
        return {"src": f"/assets/times/{dest.name}", "alt": title,
                "caption": title.replace("_", " "),
                "credit": f"Photo: {author}, {lic}, via Wikimedia Commons"}
    return None


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "markets":
        print(json.dumps(markets(), ensure_ascii=False, indent=1))
    elif cmd == "weather":
        print(json.dumps(weather(), ensure_ascii=False, indent=1))
    elif cmd == "image" and len(sys.argv) > 2:
        res = commons_image(" ".join(sys.argv[2:]))
        if not res:
            sys.exit(1)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
