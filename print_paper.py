#!/usr/bin/env python3
"""print today's utku times — meant to run from a home computer at 07:00.

  python3 print_paper.py                       wait for today's edition, print it
  python3 print_paper.py --no-print --out x.pdf   only make the pdf
  python3 print_paper.py --printer HP_LaserJet --duplex

what it does
  1. polls https://news.utku.space/times/ until the page carries today's date
     (europe/istanbul), up to --wait minutes — the routine publishes ~06:30-06:50.
  2. if the private planner is sealed, decrypts it on this machine with your
     passphrase (env TIMES_PASSPHRASE, or the first line of ~/.utku-times-passphrase)
     and bakes it into the page. the passphrase never leaves this computer.
     pass --public to skip that and print only the public pages.
  3. headless chrome/chromium/edge renders the three a4 sheets to a pdf.
  4. sends the pdf to the printer with `lp` (mac/linux) or SumatraPDF (windows).

needs: python 3.9+, the `openssl` binary (only for the private page), and one of
chrome / chromium / edge. uses times.py from this repo to decrypt, so run it from a
clone of mutkuoz/news. stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zoneinfo

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import times  # noqa: E402  (decrypt + the long_date format)

CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge"]
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def log(msg: str) -> None:
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def find_chrome() -> str:
    env = os.environ.get("CHROME")
    if env:
        return env
    for name in CHROME_NAMES:
        if shutil.which(name):
            return shutil.which(name)
    for path in CHROME_PATHS:
        if os.path.exists(path):
            return path
    sys.exit("no chrome/chromium/edge found — install one or set CHROME=/path/to/it")


def passphrase():
    if os.environ.get("TIMES_PASSPHRASE"):
        return os.environ["TIMES_PASSPHRASE"]
    f = pathlib.Path.home() / ".utku-times-passphrase"
    if f.exists():
        return f.read_text(encoding="utf-8").splitlines()[0].strip()
    return None


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "utku-times-printer/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def wait_for_edition(site: str, wait_min: int) -> str:
    today = dt.datetime.now(zoneinfo.ZoneInfo("Europe/Istanbul")).date().isoformat()
    want = times.long_date(today)
    deadline = time.time() + wait_min * 60
    while True:
        try:
            page = fetch(f"{site}/times/?t={int(time.time())}")
            if want in page:
                log(f"found today's edition ({want})")
                return page
            log(f"site still shows an older edition, waiting for {want} …")
        except Exception as e:  # network blips at 07:00 should not kill the job
            log(f"fetch failed: {e}")
        if time.time() > deadline:
            sys.exit(f"gave up after {wait_min} min: today's edition ({want}) is not published")
        time.sleep(60)


def unlock(page: str, pw) -> str:
    m = re.search(r'<script type="application/json" id="sealed">(.*?)</script>', page, re.S)
    if not m:
        log("no sealed page in this edition")
        return page
    if not pw:
        log("sealed page found but no passphrase (TIMES_PASSPHRASE or ~/.utku-times-passphrase) — printing it locked")
        return page
    try:
        inner = times.open_sealed(json.loads(m.group(1)), pw)
    except Exception as e:
        log(f"could not open the sealed page ({e}) — printing it locked")
        return page
    log("private planner decrypted")
    return page.replace('<div id="privbody" hidden></div>', f'<div id="privbody">{inner}</div>', 1)


def to_pdf(page: str, site: str, out: pathlib.Path) -> None:
    page = page.replace("<head>", f'<head>\n<base href="{site}/">', 1)
    with tempfile.TemporaryDirectory() as tmp:
        html = pathlib.Path(tmp) / "times.html"
        html.write_text(page, encoding="utf-8")
        cmd = [find_chrome(), "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
               "--virtual-time-budget=15000", f"--print-to-pdf={out}", html.as_uri()]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not out.exists() or out.stat().st_size < 10_000:
        sys.exit("chrome did not produce a pdf")
    log(f"pdf ready: {out} ({out.stat().st_size // 1024} KB)")


def send_to_printer(pdf: pathlib.Path, printer, duplex: bool) -> None:
    if shutil.which("lp"):
        cmd = ["lp", "-o", "media=A4", "-o", "fit-to-page"]
        if printer:
            cmd += ["-d", printer]
        if duplex:
            cmd += ["-o", "sides=two-sided-long-edge"]
        out = subprocess.run(cmd + [str(pdf)], capture_output=True, text=True)
        if out.returncode:
            sys.exit(f"lp failed: {out.stderr.strip()}")
        log(out.stdout.strip() or "sent to printer")
        return
    sumatra = shutil.which("SumatraPDF") or next((p for p in [r"C:\Program Files\SumatraPDF\SumatraPDF.exe"] if os.path.exists(p)), None)
    if sumatra:
        settings = "fit" + (",duplexlong" if duplex else "")
        target = ["-print-to", printer] if printer else ["-print-to-default"]
        subprocess.run([sumatra, *target, "-print-settings", settings, "-silent", str(pdf)], check=True)
        log("sent to printer via SumatraPDF")
        return
    sys.exit(f"no `lp` or SumatraPDF found — the pdf is at {pdf}; print it by hand")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default="https://news.utku.space", help="site to fetch from")
    ap.add_argument("--wait", type=int, default=45, help="minutes to wait for today's edition (default 45)")
    ap.add_argument("--printer", help="printer name (default: system default). list with `lpstat -p`")
    ap.add_argument("--duplex", action="store_true", help="print double-sided")
    ap.add_argument("--public", action="store_true", help="do not decrypt the private planner")
    ap.add_argument("--no-print", action="store_true", help="make the pdf only")
    ap.add_argument("--out", type=pathlib.Path, help="where to keep the pdf (default: ~/utku-times/YYYY-MM-DD.pdf)")
    args = ap.parse_args()

    site = args.site.rstrip("/")
    page = wait_for_edition(site, args.wait)
    page = page if args.public else unlock(page, passphrase())
    today = dt.datetime.now(zoneinfo.ZoneInfo("Europe/Istanbul")).date().isoformat()
    out = args.out or pathlib.Path.home() / "utku-times" / f"{today}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    to_pdf(page, site, out)
    if not args.no_print:
        send_to_printer(out, args.printer, args.duplex)


if __name__ == "__main__":
    main()
