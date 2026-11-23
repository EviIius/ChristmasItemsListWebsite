#!/usr/bin/env python3
"""Pull the store product links out of a gift guide or a store's top-toys list.

Top-toys lists and gift guides (Amazon's Top 100+ Toys, The Toy Insider, news gift guides) link every gift to its
product page. This finds those links, decodes affiliate redirects (goto.target.com, goto.walmart.com, bestbuy.7tiv.net,
go.skimresources.com, anrdoezrs.net) to the real product page, and matches each one to a gift in the catalog, so it
can be added with add_link.py and get a live price.

Usage:
  python3 scraper/hotlists.py URL [URL ...]        # list every product link on the page(s)
  python3 scraper/hotlists.py --file page.html     # read a page saved from your browser instead
  python3 scraper/hotlists.py URL --new-only       # only links the catalog doesn't track yet

The page is fetched once, politely (robots.txt respected, honest user agent). Nothing is added to the catalog;
copy the add_link.py commands it prints for the links you want.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from add_link import CATALOG, clean, sku_for, store_for  # noqa: E402

REDIRECT_PARAMS = ("u", "url", "murl", "destination", "dest")
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
LABEL = re.compile(r"""(?:aria-label|title)\s*=\s*["']([^"']+)["']""", re.I)
STOP = {"the", "and", "with", "for", "set", "of", "a", "an", "toy", "toys", "kids", "pack", "edition", "by", "in", "to", "on", "new"}


def real_url(url: str) -> str:
    """Follow affiliate redirect wrappers that carry the real URL inside the link (no network needed)."""
    url = htmllib.unescape(url.strip())
    for _ in range(4):
        u = urlparse(url)
        q = parse_qs(u.query)
        inner = next((q[k][0] for k in REDIRECT_PARAMS if q.get(k) and q[k][0].startswith("http")), None)
        if not inner:
            m = re.search(r"/(https?://.+)$", u.path + ("?" + u.query if u.query else ""))
            inner = m.group(1) if m and u.netloc and not u.netloc.endswith(("amazon.com", "target.com", "walmart.com")) else None
        if not inner:
            return url
        url = unquote(inner)
    return url


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower().replace("é", "e")) if t not in STOP and len(t) > 1}


def best_match(name: str, items: list[dict]) -> tuple[dict | None, float]:
    want = tokens(name)
    best, score = None, 0.0
    for it in items:
        have = tokens(f"{it['name']} {it.get('brand', '')}")
        if not want or not have:
            continue
        s = len(want & have) / len(want | have) ** 0.5 / len(want) ** 0.5
        if s > score:
            best, score = it, s
    return best, score


def extract(page: str, retailers: dict) -> list[dict]:
    """Every distinct store product link on the page, with the best name the page gives it."""
    found: dict[tuple[str, str], dict] = {}
    for attrs, inner in ANCHOR.findall(page):
        m = HREF.search(attrs)
        if not m:
            continue
        url = real_url(m.group(1))
        store = store_for(url, retailers)
        if not store:
            continue
        sku = sku_for(url, store)
        if not sku:
            continue
        name = text_of(inner)
        if not name or len(name) < 3:
            lab = LABEL.search(attrs)
            name = htmllib.unescape(lab.group(1)) if lab else ""
        key = (store, sku)
        row = found.setdefault(key, {"store": store, "sku": sku, "url": clean(url, store), "name": ""})
        if len(name) > len(row["name"]) and not re.fullmatch(r"(?i)(shop|buy|see|view)( it| now| deal| at [\w .&']+)?|\$[\d,.]+", name):
            row["name"] = name[:140]
    return list(found.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="gift guide or top-toys pages")
    ap.add_argument("--file", action="append", default=[], help="a saved HTML page (repeatable)")
    ap.add_argument("--new-only", action="store_true", help="hide links the catalog already tracks")
    ap.add_argument("--json", help="also write the links found to this JSON file")
    args = ap.parse_args()
    if not args.urls and not args.file:
        ap.error("give at least one page URL or --file")
    catalog = json.loads(CATALOG.read_text())
    retailers, items = catalog["retailers"], catalog["items"]
    tracked = {(o["retailer"], str(o.get("sku"))) for it in items for o in it.get("offers", [])}
    pages = [(f, Path(f).read_text(errors="replace")) for f in args.file]
    if args.urls:
        from scrape import PoliteFetcher  # standard library only; respects robots.txt
        fetcher = PoliteFetcher(delay=(1.0, 2.0))
        for url in args.urls:
            status, page, _ = fetcher.get(url)
            if status != 200:
                print(f"{url}: HTTP {status}, skipped", file=sys.stderr)
                continue
            pages.append((url, page))
    rows = []
    for source, page in pages:
        links = extract(page, retailers)
        print(f"\n{source}: {len(links)} product links")
        for r in links:
            r["source"] = source
            known = (r["store"], r["sku"]) in tracked
            if args.new_only and known:
                continue
            match, score = best_match(r["name"], items)
            r["match"] = match["id"] if match and score >= 0.45 else None
            label = r["name"] or "(no link text)"
            line = f"  {retailers[r['store']]['name']:<12} {r['sku']:<12} {label[:70]}"
            if known:
                line += "  [already tracked]"
            elif r["match"]:
                line += f"\n      -> python3 scraper/add_link.py {r['match']} '{r['url']}'"
            else:
                line += "\n      -> not in the catalog yet (add the gift first, then add_link.py)"
            print(line)
            rows.append(r)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
