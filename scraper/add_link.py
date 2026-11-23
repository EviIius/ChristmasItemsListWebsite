#!/usr/bin/env python3
"""Add a store product link to a gift in site/data/catalog.json, so the scraper starts tracking its price.

Usage:
  python3 scraper/add_link.py ITEM_ID URL [--label "Pink, 12 inch"] [--sku 12345]
  python3 scraper/add_link.py --find squish           # look up item ids by name

The store is worked out from the link (Target, Walmart, Amazon, Best Buy, LEGO, GameStop and the rest of the stores in the
catalog), and the product number is pulled from the link when the store puts one there. Push the change and the next scrape
reads the price.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CATALOG = Path(__file__).resolve().parent.parent / "site" / "data" / "catalog.json"

SKU_PATTERNS = {
    "target": [r"/A-(\d+)"],
    "walmart": [r"/ip/(?:[^/]+/)?(\d+)"],
    "amazon": [r"/(?:dp|gp/product)/([A-Z0-9]{10})"],
    "bestbuy": [r"/sku/(\d+)", r"/(\d{7})\.p"],
    "lego": [r"-(\d{4,6})(?:$|[/?])"],
    "gamestop": [r"/(\d+)(?:-[0-9a-f]+)?\.html"],
    "macys": [r"[?&]ID=(\d+)"],
}


def store_for(url: str, retailers: dict) -> str | None:
    host = urlparse(url).netloc.lower()
    for rid, r in retailers.items():
        if any(host == h or host.endswith("." + h) for h in r.get("hosts", [])):
            return rid
    return None


def sku_for(url: str, retailer: str) -> str | None:
    q = parse_qs(urlparse(url).query)
    if retailer == "bestbuy" and q.get("skuId"):
        return q["skuId"][0]
    for rx in SKU_PATTERNS.get(retailer, []):
        m = re.search(rx, url)
        if m:
            return m.group(1)
    return None


def clean(url: str, retailer: str) -> str:
    """Drop tracking parameters; keep the ones that pick a product variant. Amazon links become amazon.com/dp/ASIN."""
    u = urlparse(url)
    if retailer == "amazon" and sku_for(url, "amazon"):
        return f"https://www.amazon.com/dp/{sku_for(url, 'amazon')}"
    keep = {"variant", "skuId", "preselect", "ID"}
    query = "&".join(f"{k}={v[0]}" for k, v in parse_qs(u.query).items() if k in keep)
    return f"{u.scheme}://{u.netloc}{u.path}" + (f"?{query}" if query else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item_id", nargs="?")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--label", help="what this listing is, e.g. a color or character")
    ap.add_argument("--sku", help="the store's product number, when it isn't in the link")
    ap.add_argument("--find", help="list gifts whose name or id contains this text")
    args = ap.parse_args()
    catalog = json.loads(CATALOG.read_text())
    if args.find:
        q = args.find.lower()
        for it in catalog["items"]:
            if q in it["id"] or q in it["name"].lower():
                n = len(it.get("offers", []))
                print(f"{it['id']:<36} {it['name']}  ({n} store link{'' if n == 1 else 's'})")
        return
    if not args.item_id or not args.url:
        ap.error("give an item id and a product link (or use --find)")
    item = next((i for i in catalog["items"] if i["id"] == args.item_id), None)
    if not item:
        sys.exit(f"No gift with id '{args.item_id}'. Try: python3 scraper/add_link.py --find <word>")
    retailer = store_for(args.url, catalog["retailers"])
    if not retailer:
        sys.exit("That store isn't in the catalog yet. Add it under 'retailers' in site/data/catalog.json first (name, home, search, parser, hosts).")
    url = clean(args.url, retailer)
    if any(o["url"] == url for o in item.get("offers", [])):
        sys.exit("That link is already tracked for this gift.")
    offer = {"retailer": retailer, "url": url}
    sku = args.sku or sku_for(url, retailer)
    if sku:
        offer["sku"] = sku
    if args.label:
        offer["label"] = args.label
    item.setdefault("offers", []).append(offer)
    CATALOG.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
    print(f"Added {catalog['retailers'][retailer]['name']} link to {item['name']}" + (f" (product number {sku})" if sku else "") + ".")
    print("Push the change; the next scrape reads the price. To check it now: python3 scraper/scrape.py --only " + retailer + " --dry-run")


if __name__ == "__main__":
    main()
