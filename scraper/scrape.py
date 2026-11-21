#!/usr/bin/env python3
"""Refresh store prices for the gifts in site/data/catalog.json and write site/data/gifts.json.

Gifts can list exact product pages ("offers"). For each one the scraper reads the price the store itself publishes:
  - schema.org Product data (JSON-LD) that most stores publish for search engines: Best Buy, LEGO, GameStop,
    Pokémon Center, Shopify shops like tonies and Five Below, and many more
  - Walmart's page data (__NEXT_DATA__), Target's embedded product data and Amazon's price blocks
  - Best Buy's official Products API instead of its pages when BESTBUY_API_KEY is set
Requests are slow and polite: one at a time, several seconds apart per site, robots.txt respected, an honest user
agent, and a site is skipped for the rest of the run after 3 failures in a row. Bot-check pages are detected and
reported, never bypassed. If a page can't be read, the last known price is kept and marked stale.

Usage:
  python3 scraper/scrape.py                      # live run (standard library only, nothing to install)
  python3 scraper/scrape.py --limit 3 --dry-run  # quick test: read 3 pages, print, write nothing
  python3 scraper/scrape.py --only target        # one store only
  python3 scraper/scrape.py --probe              # which stores answer this machine? writes scraper/probe-results.json
  python3 scraper/scrape.py --offline            # rebuild gifts.json from the catalog without contacting stores
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import http.cookiejar
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
CATALOG = DATA / "catalog.json"
OUTPUT = DATA / "gifts.json"
PROBE_OUT = ROOT / "scraper" / "probe-results.json"
HISTORY_DAYS = 120
DEFAULT_UA = "Mozilla/5.0 (compatible; ChristmasGiftFinder/1.0; +https://github.com/EviIius/ChristmasItemsListWebsite)"
UA = os.environ.get("SCRAPER_USER_AGENT", DEFAULT_UA)
ROBOTS_AGENT = "ChristmasGiftFinder"  # the product token robots.txt rules are matched against
SANITY = (0.25, 4.0)  # a read price outside typical x this range is probably the wrong product, so it isn't used


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def money(value) -> float | None:
    """'$1,299.99', '1299.99', 1299.99 -> 1299.99; anything else -> None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        m = re.search(r"\d[\d,]*(?:\.\d+)?", value)
        if m:
            v = float(m.group(0).replace(",", ""))
            return v if v > 0 else None
    return None


# --------------------------------------------------------------------------- fetching

class Robots:
    """robots.txt rules, including the * and $ wildcards most retailers use (urllib.robotparser ignores those)."""

    def __init__(self, text: str, agent: str = ROBOTS_AGENT):
        groups: list[dict] = []
        cur = None
        in_agents = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not in_agents:
                    cur = {"agents": [], "rules": [], "delay": None}
                    groups.append(cur)
                cur["agents"].append(val.lower())
                in_agents = True
            elif cur is not None and key in ("allow", "disallow"):
                cur["rules"].append((key == "allow", val.split()[0] if val else ""))
                in_agents = False
            elif cur is not None and key == "crawl-delay":
                try:
                    cur["delay"] = float(val)
                except ValueError:
                    pass
                in_agents = False
        name = agent.lower()
        mine = [g for g in groups if any(a != "*" and a in name for a in g["agents"])]
        chosen = mine or [g for g in groups if "*" in g["agents"]]
        self.rules = [r for g in chosen for r in g["rules"]]
        delays = [g["delay"] for g in chosen if g["delay"]]
        self.crawl_delay = max(delays) if delays else None

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        rx = "".join(".*" if c == "*" else ("$" if c == "$" and i == len(pattern) - 1 else re.escape(c))
                     for i, c in enumerate(pattern))
        return re.match(rx, path) is not None

    def allowed(self, url: str) -> bool:
        u = urlparse(url)
        path = (u.path or "/") + ("?" + u.query if u.query else "")
        best = None  # (pattern length, allow): the longest matching rule wins, Allow wins ties
        for allow, pattern in self.rules:
            if pattern and self._matches(pattern, path):
                if best is None or len(pattern) > best[0] or (len(pattern) == best[0] and allow):
                    best = (len(pattern), allow)
        return True if best is None else best[1]


def http_get(opener, url: str, headers: dict, timeout: float) -> tuple[int, str, str]:
    """GET with the standard library. Returns (status, text, final_url); HTTP errors come back as a status."""
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    with resp:
        try:
            body = resp.read()
        except Exception:
            body = b""
        if (resp.headers.get("Content-Encoding") or "").lower() == "gzip" and body:
            body = gzip.decompress(body)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.getcode(), body.decode(charset, "replace"), resp.geturl() or url


class PoliteFetcher:
    """One request at a time, a few seconds apart per host, robots.txt respected, gives up on a host after repeated failures."""

    def __init__(self, delay=(3.0, 6.0), timeout=25, max_host_failures=3):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        }
        self.delay, self.timeout = delay, timeout
        self.max_host_failures = max_host_failures
        self.last_hit: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self.robots: dict[str, Robots | None] = {}
        self.robots_error: dict[str, str] = {}

    def _robots(self, url: str) -> Robots | None:
        u = urlparse(url)
        if u.netloc not in self.robots:
            try:
                status, text, _ = http_get(self.opener, f"{u.scheme}://{u.netloc}/robots.txt", self.headers, self.timeout)
                # RFC 9309: a missing robots.txt (4xx) allows everything; a server error means "assume disallowed".
                self.robots[u.netloc] = Robots(text) if status == 200 else (Robots("") if 400 <= status < 500 else None)
                if self.robots[u.netloc] is None:
                    self.robots_error[u.netloc] = f"HTTP {status}"
            except Exception as e:
                self.robots[u.netloc] = None
                reason = getattr(e, "reason", None) or e
                self.robots_error[u.netloc] = f"{reason.__class__.__name__}: {str(reason)[:140]}"
                if "CERTIFICATE_VERIFY_FAILED" in str(reason) and sys.platform == "darwin":
                    self.robots_error[u.netloc] += " (on a Mac, run 'Install Certificates.command' in your Python folder under Applications)"
        return self.robots[u.netloc]

    def host_blocked(self, url: str) -> bool:
        return self.failures.get(urlparse(url).netloc, 0) >= self.max_host_failures

    def note_failure(self, url: str) -> None:
        host = urlparse(url).netloc
        self.failures[host] = self.failures.get(host, 0) + 1

    def get(self, url: str) -> tuple[int, str, str]:
        host = urlparse(url).netloc
        rules = self._robots(url)
        if rules is None:
            self.failures[host] = self.max_host_failures
            raise PermissionError(f"robots.txt unreachable ({self.robots_error.get(host, 'no response')}), so the site is skipped this run")
        if not rules.allowed(url):
            raise PermissionError("robots.txt disallows this page")
        low, high = self.delay
        floor = rules.crawl_delay or 0
        wait = max(random.uniform(low, high), floor) - (time.time() - self.last_hit.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.last_hit[host] = time.time()
        try:
            status, text, final = http_get(self.opener, url, self.headers, self.timeout)
        except Exception:
            self.note_failure(url)
            raise
        self.failures[host] = self.failures.get(host, 0) + 1 if status >= 400 else 0
        return status, text, final


# --------------------------------------------------------------------------- parsing

class BlockedError(Exception):
    """The store answered with a bot check or captcha page instead of the product."""


BOT_MARKERS = ("px-captcha", "robot or human", "/errors/validatecaptcha", "type the characters you see",
               "cf-chl-", "challenge-platform", "pardon our interruption", "_incapsula_resource",
               "verify you are human", "are you a human", "unusual traffic from your computer")


def bot_check(html: str) -> list[str]:
    """Markers of a bot-check page. Only consulted when no price was found, so a normal page that loads a captcha script elsewhere is fine."""
    low = html[:300000].lower()
    hits = [m for m in BOT_MARKERS if m in low]
    title = re.search(r"<title[^>]*>(.*?)</title>", html[:30000], re.S | re.I)
    if title and re.search(r"access denied|attention required|just a moment|robot", title.group(1), re.I):
        hits.append("title: " + title.group(1).strip()[:40])
    return hits


LD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
PRODUCT_TYPES = {"Product", "VideoGame", "Book", "IndividualProduct", "ProductModel", "Vehicle"}


def _types(node: dict) -> set:
    t = node.get("@type")
    return set(t) if isinstance(t, list) else {t}


def jsonld_products(html: str) -> list[dict]:
    """Product-like nodes from every JSON-LD block. ProductGroup variants (Shopify) are expanded and tagged with their group."""
    found = []
    for n, raw in enumerate(LD_RE.findall(html)):
        try:
            data = json.loads(raw.strip(), strict=False)
        except ValueError:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            if node.get("@graph"):
                stack.append(node["@graph"])
            types = _types(node)
            if "ProductGroup" in types:
                for v in node.get("hasVariant") or []:
                    if isinstance(v, dict):
                        v = dict(v)
                        v.setdefault("name", node.get("name"))
                        v["_group"] = f"{n}:{node.get('productGroupID') or node.get('name')}"
                        found.append(v)
                if node.get("offers"):
                    found.append(node)
                continue
            if types & PRODUCT_TYPES:
                found.append(node)
            elif isinstance(node.get("mainEntity"), (dict, list)):
                stack.append(node["mainEntity"])
    return [p for p in found if p.get("offers")]


def _flat_offers(offers) -> list[dict]:
    out, stack = [], [offers]
    while stack:
        o = stack.pop()
        if isinstance(o, list):
            stack.extend(o)
        elif isinstance(o, dict):
            if isinstance(o.get("offers"), (list, dict)):  # AggregateOffer wrapping individual offers
                stack.append(o["offers"])
            else:
                out.append(o)
    return out


def _cond(o: dict) -> str:
    text = " ".join(str(o.get(k, "")) for k in ("itemCondition", "name", "description")).lower()
    if "refurb" in text or "renewed" in text:
        return "refurbished"
    if any(w in text for w in ("used", "pre-owned", "preowned", "open-box", "open box")):
        return "used"
    return "new"


def _avail(o: dict) -> bool | None:
    a = str(o.get("availability", "")).lower()
    if not a:
        return None
    return any(w in a for w in ("instock", "limitedavailability", "preorder", "presale", "backorder"))


def _seller(o: dict) -> str:
    s = o.get("seller")
    if isinstance(s, dict):
        return str(s.get("name") or "").strip()
    return str(s or "").strip()


FIRST_PARTY = {"bestbuy": ("best buy",), "walmart": ("walmart",), "target": ("target",), "amazon": ("amazon",),
               "gamestop": ("gamestop",), "lego": ("lego",)}


def _first_party(retailer: str | None, seller: str) -> bool:
    names = FIRST_PARTY.get(retailer or "")
    return not names or not seller or any(n in seller.lower() for n in names)


def _regular(o: dict) -> float | None:
    specs = o.get("priceSpecification")
    for s in (specs if isinstance(specs, list) else [specs] if isinstance(specs, dict) else []):
        if re.search(r"ListPrice|Strikethrough|MSRP", str(s.get("priceType", "")), re.I):
            return money(s.get("price"))
    return None


def _identifiers(p: dict) -> set:
    keys = ("sku", "mpn", "productID", "model", "gtin", "gtin12", "gtin13", "gtin14")
    return {str(p[k]).strip().casefold() for k in keys if isinstance(p.get(k), (str, int))}


def _pick_product(products: list[dict], sku: str | None) -> dict:
    if sku:
        s = str(sku).strip().casefold()
        hit = [p for p in products if s in _identifiers(p)
               or re.search(r"(?<![\w-])" + re.escape(str(sku)) + r"(?![\w-])", str(p.get("name") or "") + " " + str(p.get("url") or ""), re.I)]
        if len(hit) == 1:
            return hit[0]
        if len(hit) > 1 and len({p.get("_group") for p in hit}) == 1 and hit[0].get("_group"):
            return {"_variants": hit}
    if len(products) == 1:
        return products[0]
    groups = {p.get("_group") for p in products}
    if len(groups) == 1 and None not in groups:
        return {"_variants": products}  # one Shopify product with several variants
    if sku and not any(_identifiers(p) for p in products):
        return products[0]
    raise ValueError("the page lists several products and none matches this link's SKU")


def parse_jsonld(html: str, retailer: str | None = None, sku: str | None = None) -> dict:
    """Price, stock, rating and marketplace offers from schema.org Product data."""
    products = jsonld_products(html)
    if not products:
        raise ValueError("no product price data found on the page (layout may have changed)")
    prod = _pick_product(products, sku)
    variants = prod.get("_variants") or [prod]
    news, used, mkt, regulars = [], [], [], []
    for p in variants:
        for o in _flat_offers(p.get("offers")):
            price = money(o.get("price")) or money(o.get("lowPrice")) or money((o.get("priceSpecification") or {}).get("price") if isinstance(o.get("priceSpecification"), dict) else None)
            if price is None:
                continue
            seller, cond = _seller(o), _cond(o)
            if cond == "new" and _first_party(retailer, seller):
                news.append((price, _avail(o)))
                r = _regular(o)
                if r:
                    regulars.append(r)
            elif cond == "new":
                mkt.append((price, seller))
            elif _first_party(retailer, seller):
                used.append(price)
    out: dict = {"name": str(variants[0].get("name") or "")[:160] or None}
    if news:
        available = [x for x in news if x[1] is True]
        price, avail = min(available or news, key=lambda x: x[0])
        out["price"], out["in_stock"] = price, avail
        if regulars and max(regulars) > price:
            out["regular"] = max(regulars)
    elif mkt:
        p, s = min(mkt)
        out.update(price=p, seller=s, marketplace_only=True, in_stock=True)
    else:
        out["in_stock"] = False
    if used:
        out["open_box"] = min(used)
    if mkt and not out.get("marketplace_only"):
        p, s = min(mkt)
        out["marketplace"] = {"price": p, "seller": s}
    first = variants[0]
    rating = first.get("aggregateRating") or {}
    if isinstance(rating, dict) and rating.get("ratingValue"):
        try:
            out["rating"] = round(float(rating["ratingValue"]), 1)
            out["reviews"] = int(float(rating.get("reviewCount") or rating.get("ratingCount") or 0))
        except (TypeError, ValueError):
            pass
    return out


NEXT_RE = re.compile(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _find_all(node, test, depth=0, out=None):
    out = [] if out is None else out
    if depth > 16:
        return out
    if isinstance(node, dict):
        if test(node):
            out.append(node)
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return out
    for child in children:
        _find_all(child, test, depth + 1, out)
    return out


def parse_walmart(html: str, retailer: str | None = "walmart", sku: str | None = None) -> dict:
    """Walmart product pages carry their data in the page's __NEXT_DATA__ JSON instead of schema.org markup."""
    m = NEXT_RE.search(html)
    if not m:
        return parse_jsonld(html, retailer, sku)
    try:
        data = json.loads(m.group(1))
    except ValueError:
        raise ValueError("Walmart page data could not be read")
    prods = _find_all(data, lambda d: isinstance(d.get("priceInfo"), dict) and ("usItemId" in d or "name" in d))
    if not prods:
        raise ValueError("no product price data in Walmart's page data")
    prod = next((p for p in prods if sku and str(p.get("usItemId")) == str(sku)), prods[0])
    pi = prod["priceInfo"]
    cur = money((pi.get("currentPrice") or {}).get("price"))
    if cur is None:
        raise ValueError("Walmart page data has no current price")
    was = money((pi.get("wasPrice") or {}).get("price"))
    seller = (prod.get("sellerDisplayName") or prod.get("sellerName") or "").strip()
    out: dict = {"name": prod.get("name"), "price": cur, "in_stock": str(prod.get("availabilityStatus", "")).upper() == "IN_STOCK",
                 "seller": seller or None}
    if seller and "walmart" not in seller.lower():
        out["marketplace_only"] = True  # sold by an outside seller through Walmart's marketplace
    if was and was > cur:
        out["regular"] = was
    if prod.get("averageRating"):
        out["rating"] = round(float(prod["averageRating"]), 1)
        out["reviews"] = int(prod.get("numberOfReviews") or 0)
    return out


Q = r'\\?"'  # a JSON quote that may be escaped inside a JavaScript string


def parse_target(html: str, retailer: str | None = "target", sku: str | None = None) -> dict:
    """Target: schema.org data when present, otherwise the product data embedded in the page's scripts."""
    try:
        return parse_jsonld(html, retailer, sku)
    except ValueError:
        pass
    seg = html
    if sku:
        i = html.find(str(sku))
        if i >= 0:
            seg = html[i:i + 80000]

    def grab(key, text, pattern=r'([0-9]+(?:\.[0-9]+)?)'):
        m = re.search(Q + key + Q + r'\s*:\s*' + pattern, text)
        return m.group(1) if m else None

    price = money(grab("current_retail", seg)) or money(grab("current_retail", html))
    if price is None:
        fmt = grab("formatted_current_price", seg, Q + r'\$([0-9,]+(?:\.[0-9]{2})?)') or grab("formatted_current_price", html, Q + r'\$([0-9,]+(?:\.[0-9]{2})?)')
        price = money(fmt)
    if price is None:
        raise ValueError("no product price data found on the Target page")
    out: dict = {"price": price}
    reg = money(grab("reg_retail", seg))
    if reg and reg > price:
        out["regular"] = reg
    status = grab("availability_status", seg, Q + r'([A-Z_]+)')
    out["in_stock"] = None if not status else status in ("IN_STOCK", "LIMITED_STOCK", "PRE_ORDER_SELLABLE", "BACKORDER_SELLABLE")
    seller = re.search(r'[Ss]old (?:&amp;|&|and) shipped by\s*(?:<[^>]+>\s*)*([^<"\\]{2,60})', html)
    if seller and "target" not in seller.group(1).lower():
        out.update(seller=seller.group(1).strip(), marketplace_only=True)
    return out


def parse_amazon(html: str, retailer: str | None = "amazon", sku: str | None = None) -> dict:
    """Amazon: the buy-box price, stock line and seller. Third-party sellers are flagged, not counted as Amazon's price."""
    if sku and str(sku) not in html:
        raise ValueError("page doesn't mention this link's ASIN (it may redirect to another product)")
    price = None
    for rx in (r'"priceAmount"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
               r'id="corePrice(?:Display_desktop)?_feature_div".{0,8000}?class="a-offscreen">\s*\$([0-9,]+\.[0-9]{2})',
               r'class="a-price-whole">([0-9,]+)<span class="a-price-decimal">\.</span></span><span class="a-price-fraction">([0-9]{2})',
               r'id="priceblock_(?:our|deal|sale)price"[^>]*>\s*\$([0-9,]+\.[0-9]{2})'):
        m = re.search(rx, html, re.S)
        if m:
            text = m.group(1).replace(",", "") + ("." + m.group(2) if m.lastindex and m.lastindex >= 2 else "")
            price = money(text)
            break
    if price is None:
        raise ValueError("no price on the Amazon page (it may be unavailable or need a seller choice)")
    out: dict = {"price": price}
    lp = re.search(r'(?:List Price|Typical price|List:)[^$]{0,400}?\$([0-9,]+\.[0-9]{2})', html, re.S)
    if lp and money(lp.group(1)) and money(lp.group(1)) > price:
        out["regular"] = money(lp.group(1))
    av = re.search(r'id="availability"(.{0,1500}?)</div>', html, re.S)
    text = re.sub(r"<[^>]+>", " ", av.group(1)).lower() if av else ""
    if "currently unavailable" in text or "out of stock" in text:
        out["in_stock"] = False
    elif any(w in text for w in ("in stock", "left in stock", "ships within", "usually ships", "available to ship", "pre-order")):
        out["in_stock"] = True
    else:
        out["in_stock"] = None
    seller = re.search(r'id="sellerProfileTriggerId"[^>]*>\s*([^<]+?)\s*<', html)
    if seller and "amazon" not in seller.group(1).lower():
        out.update(seller=seller.group(1).strip(), marketplace_only=True)
    rating = re.search(r'([0-5]\.[0-9]) out of 5 stars', html)
    count = re.search(r'id="acrCustomerReviewText"[^>]*>\s*([0-9,]+)', html)
    if rating:
        out["rating"] = float(rating.group(1))
        if count:
            out["reviews"] = int(count.group(1).replace(",", ""))
    return out


def parse_meta(html: str) -> dict | None:
    """Last resort: price meta tags many shops add for social previews."""
    m = re.search(r'<meta[^>]+(?:property|itemprop|name)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]+content=["\']([\d.,]+)', html) \
        or re.search(r'<meta[^>]+content=["\']([\d.,]+)["\'][^>]+(?:property|itemprop|name)=["\'](?:product:price:amount|og:price:amount|price)["\']', html)
    if m and money(m.group(1)):
        return {"price": money(m.group(1)), "in_stock": None}
    return None


PARSERS = {"jsonld": parse_jsonld, "bestbuy": parse_jsonld, "walmart": parse_walmart, "target": parse_target, "amazon": parse_amazon}


def parse_product_page(html: str, parser: str = "jsonld", retailer: str | None = None, sku: str | None = None) -> dict:
    fn = PARSERS.get(parser, parse_jsonld)
    try:
        return fn(html, retailer, sku)
    except ValueError:
        hits = bot_check(html)
        if hits:
            raise BlockedError("the store showed a bot check instead of the product (" + ", ".join(hits[:2]) + ")") from None
        meta = parse_meta(html)
        if meta:
            return meta
        raise


# --------------------------------------------------------------------------- Best Buy official API (optional)

def bestbuy_api(key: str, skus: list[str]) -> dict:
    show = "sku,name,salePrice,regularPrice,onSale,onlineAvailability,customerReviewAverage,customerReviewCount,url"
    prices: dict = {}
    for i in range(0, len(skus), 90):
        chunk = ",".join(skus[i:i + 90])
        url = ("https://api.bestbuy.com/v1/products" + quote(f"(sku in({chunk}))", safe="(),=&.") + "?"
               + urlencode({"apiKey": key, "format": "json", "show": show, "pageSize": 100}))
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            for p in json.loads(r.read().decode("utf-8")).get("products", []):
                prices[str(p["sku"])] = p
        time.sleep(0.5)
    return prices


# --------------------------------------------------------------------------- merge

KEEP = ("price", "regular", "in_stock", "open_box", "marketplace", "rating", "reviews", "checked_at", "source", "seller",
        "marketplace_only", "verification_method", "on_sale", "availability_checked_at", "note", "name")


def merge(catalog: dict, previous: dict | None, observations: list[dict], run_meta: dict) -> dict:
    """Combine the catalog, this run's observations and the previous output into gifts.json."""
    previous = previous or {}
    prev_items = {i["id"]: i for i in previous.get("items", [])}
    obs = {(o["item_id"], o["url"]): o for o in observations}
    retailers = catalog.get("retailers", {})
    today = run_meta["finished"][:10]
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=HISTORY_DAYS - 1)).isoformat()
    items, shown = [], []
    for it in catalog["items"]:
        prev = prev_items.get(it["id"], {})
        prev_offers = {o.get("url"): o for o in prev.get("offers", [])}
        offers = []
        for off in it.get("offers", []):
            ob = obs.get((it["id"], off["url"]))
            po = prev_offers.get(off["url"], {})
            o = {"retailer": off["retailer"], "retailer_name": retailers.get(off["retailer"], {}).get("name", off["retailer"]),
                 "url": off["url"], "sku": off.get("sku"), "label": off.get("label")}
            if ob and ob.get("ok"):  # read this run
                o.update({k: ob[k] for k in KEEP if ob.get(k) is not None})
                o["stale"], o["_fresh"] = False, True
                if ob.get("price") is None and po.get("price") is not None:  # stock-only check: keep the old price, flagged
                    o.update({k: po[k] for k in ("price", "regular", "checked_at", "source", "verification_method") if k in po})
                    o["availability_checked_at"] = ob.get("checked_at")
                    o["stale"], o["_fresh"] = True, False
            elif ob:  # tried and failed: keep the last known price, flagged
                o.update({k: po[k] for k in KEEP if po.get(k) is not None})
                o["stale"] = True
                o["error"] = ob.get("error") or "could not be read"
                o["last_attempt"] = ob.get("checked_at")
                if ob.get("blocked"):
                    o["blocked"] = True
            elif po:  # not attempted this run: carry over unchanged
                o.update({k: po[k] for k in KEEP + ("error", "last_attempt", "blocked") if po.get(k) is not None})
                o["stale"] = bool(po.get("stale", True))
            else:
                o["stale"] = True
                o["error"] = "not checked yet"
            if o.get("stale"):
                o["on_sale"] = False
            offers.append({k: v for k, v in o.items() if v is not None})
        priced = [o for o in offers if o.get("price") and not o.get("marketplace_only")]
        best = min(priced, key=lambda o: (bool(o.get("stale")), o.get("in_stock") is False, o["price"])) if priced else None
        history = [list(h) for h in prev.get("history", []) if h[0] >= cutoff]
        if best and best.get("_fresh") and best.get("in_stock") is not False:
            if history and history[-1][0] == today:
                history[-1][1] = min(history[-1][1], best["price"])
            else:
                history.append([today, best["price"]])
        if not best:
            status = "typical"
        elif best.get("in_stock") is False:
            status = "unavailable"
        elif best.get("stale"):
            status = "stale"
        else:
            status = "live"
            shown.append(best.get("checked_at"))
        item = dict(it)
        item["offers"] = offers
        item.update({"price": best["price"] if best else None,
                     "price_retailer": best["retailer"] if best else None,
                     "price_url": best["url"] if best else None,
                     "price_status": status,
                     "price_checked_at": best.get("checked_at") if best else None,
                     "regular": best.get("regular") if best and (best.get("regular") or 0) > best["price"] else None,
                     "history": history})
        items.append({k: v for k, v in item.items() if v is not None})
    for i in items:
        for o in i["offers"]:
            o.pop("_fresh", None)
    shown = [s for s in shown if s]
    out = {"generated_at": run_meta["finished"],
           "prices_as_of": min(shown) if shown else None,
           "live_prices": len(shown),
           "scrape": run_meta,
           "retailers": retailers,
           "interests": catalog.get("interests", {}),
           "categories": catalog.get("categories", {}),
           "items": items}
    return out


# --------------------------------------------------------------------------- live run

def offer_list(catalog: dict, only: str | None = None) -> list[tuple[dict, dict]]:
    return [(it, off) for it in catalog["items"] for off in it.get("offers", [])
            if not off.get("manual") and (not only or off["retailer"] == only)]


def check_sane(rec: dict, item: dict) -> None:
    typical = item.get("typical")
    price = rec.get("price")
    if rec.get("ok") and price and typical and not (typical * SANITY[0] <= price <= typical * SANITY[1]) and not rec.get("marketplace_only"):
        rec.update(ok=False, reason="sanity", error=f"Read ${price:,.2f}, far from the usual ${typical:,.2f}, so it wasn't used. Check that the link is the right product.")


def read_offer(fetcher: PoliteFetcher, catalog: dict, item: dict, off: dict) -> dict:
    parser = catalog["retailers"].get(off["retailer"], {}).get("parser", "jsonld")
    rec = {"item_id": item["id"], "retailer": off["retailer"], "url": off["url"], "sku": off.get("sku"), "checked_at": now_iso()}
    if fetcher.host_blocked(off["url"]):
        rec.update(ok=False, reason="skipped", error="skipped: the store kept refusing requests this run")
        return rec
    try:
        status, html, final = fetcher.get(off["url"])
        if status != 200:
            if bot_check(html):
                raise BlockedError(f"HTTP {status} with a bot-check page")
            rec["reason"] = "http"
            raise RuntimeError(f"HTTP {status}")
        rec.update(parse_product_page(html, parser, off["retailer"], off.get("sku")), ok=True,
                   source=f"{urlparse(final).netloc} product page", verification_method="retailer-html")
    except BlockedError as e:
        fetcher.note_failure(off["url"])
        rec.update(ok=False, blocked=True, reason="blocked", error=str(e))
    except PermissionError as e:
        rec.update(ok=False, reason="robots" if "disallows" in str(e) else "network", error=str(e))
    except ValueError as e:
        rec.update(ok=False, reason="parse", error=f"Couldn't find the price: {str(e)[:140]}")
    except Exception as e:
        rec.setdefault("reason", "network")
        rec.update(ok=False, error=f"{e.__class__.__name__}: {str(e)[:140]}")
    check_sane(rec, item)
    return rec


def run_live(catalog: dict, limit: int | None, only: str | None) -> tuple[list[dict], dict]:
    observations: list[dict] = []
    notes: list[str] = []
    todo = offer_list(catalog, only)
    random.shuffle(todo)
    if limit:
        todo = todo[:limit]
    api_key = os.environ.get("BESTBUY_API_KEY", "").strip()
    if api_key:
        bb = [(it, o) for it, o in todo if o["retailer"] == "bestbuy" and o.get("sku")]
        try:
            prices = bestbuy_api(api_key, sorted({o["sku"] for _, o in bb}))
            for it, o in bb:
                p = prices.get(str(o["sku"]))
                rec = {"item_id": it["id"], "retailer": "bestbuy", "url": o["url"], "sku": o["sku"], "checked_at": now_iso()}
                if p:
                    rec.update(ok=True, price=float(p["salePrice"]), regular=money(p.get("regularPrice")), on_sale=p.get("onSale") is True,
                               in_stock=bool(p.get("onlineAvailability")), rating=p.get("customerReviewAverage"),
                               reviews=p.get("customerReviewCount"), source="Best Buy Products API", verification_method="retailer-api")
                else:
                    rec.update(ok=False, error="not returned by the Best Buy API (discontinued?)")
                check_sane(rec, it)
                observations.append(rec)
            done = {id(o) for _, o in bb}
            todo = [(it, o) for it, o in todo if id(o) not in done]
            notes.append("Best Buy prices came from the official Products API.")
        except Exception as e:
            notes.append(f"Best Buy API failed ({e.__class__.__name__}); fell back to product pages.")
    fetcher = PoliteFetcher()
    for it, off in todo:
        rec = read_offer(fetcher, catalog, it, off)
        observations.append(rec)
        print(("ok   " if rec.get("ok") else "FAIL ") + f"{off['retailer']:<12} {it['id']:<34} " + (f"${rec['price']:,.2f}" if rec.get("ok") and rec.get("price") else rec.get("error", "")), flush=True)
    per: dict = {}
    for o in observations:
        d = per.setdefault(o["retailer"], {"ok": 0, "failed": 0, "blocked": 0})
        d["ok" if o.get("ok") else "failed"] += 1
        if o.get("blocked"):
            d["blocked"] += 1
    names = {k: v.get("name", k) for k, v in catalog["retailers"].items()}
    for r, d in per.items():
        if d["ok"] or not d["failed"]:
            continue
        reasons = [o.get("reason") for o in observations if o["retailer"] == r and not o.get("ok")]
        name = names.get(r, r)
        if "blocked" in reasons or reasons.count("skipped") + reasons.count("network") + reasons.count("http") == len(reasons):
            notes.append(f"{name} didn't give this machine any prices, most likely because it blocks automated traffic from cloud "
                         "servers. Last known prices kept. Running the scraper on a home computer usually helps (see README).")
        elif all(x == "robots" for x in reasons):
            notes.append(f"{name}'s robots.txt asks scripts not to read these pages, so they were skipped. Its search links still work.")
        else:
            notes.append(f"{name}: no prices read this run ({', '.join(sorted(set(x or 'error' for x in reasons)))}). Last known prices kept.")
    return observations, {"by_retailer": per, "notes": notes}


def probe(catalog: dict) -> dict:
    """Try one product page per store and report what answers. Nothing is bypassed; blocked is a valid answer."""
    fetcher = PoliteFetcher(delay=(1.0, 2.0), max_host_failures=99)
    seen, results = set(), []
    for it, off in offer_list(catalog):
        if off["retailer"] in seen:
            continue
        seen.add(off["retailer"])
        row = {"store": off["retailer"], "url": off["url"]}
        rules = fetcher._robots(off["url"])
        row["robots"] = "unreachable: " + fetcher.robots_error.get(urlparse(off["url"]).netloc, "") if rules is None else ("allowed" if rules.allowed(off["url"]) else "disallowed")
        if rules is not None and rules.allowed(off["url"]):
            t = time.time()
            try:
                status, html, final = fetcher.get(off["url"])
                row.update(status=status, seconds=round(time.time() - t, 1), kb=len(html) // 1024, bot_check=bot_check(html)[:3])
                try:
                    parsed = parse_product_page(html, catalog["retailers"][off["retailer"]].get("parser", "jsonld"), off["retailer"], off.get("sku"))
                    row["price"] = parsed.get("price")
                    row["in_stock"] = parsed.get("in_stock")
                except Exception as e:
                    row["parse_error"] = f"{e.__class__.__name__}: {str(e)[:140]}"
            except Exception as e:
                row["error"] = f"{e.__class__.__name__}: {str(e)[:140]}"
        row["readable"] = bool(row.get("price"))
        results.append(row)
        print(f"{'READABLE' if row['readable'] else 'no price':<9} {off['retailer']:<14} {row.get('price') or row.get('parse_error') or row.get('error') or row['robots']}", flush=True)
    return {"checked_at": now_iso(), "runner": os.environ.get("SCRAPER_RUNNER") or ("github-actions" if os.environ.get("GITHUB_ACTIONS") else "local"),
            "user_agent": UA, "results": results}


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="don't fetch anything; rebuild gifts.json from the catalog and previous data")
    ap.add_argument("--observations", help="merge observations from this JSON file (e.g. prices checked by hand)")
    ap.add_argument("--limit", type=int, help="only read N store links (testing)")
    ap.add_argument("--only", help="only read one store, e.g. target")
    ap.add_argument("--dry-run", action="store_true", help="print what was found but don't write gifts.json")
    ap.add_argument("--save-observations", help="also save this run's observations as reusable JSON")
    ap.add_argument("--probe", action="store_true", help="test one page per store and write scraper/probe-results.json")
    args = ap.parse_args()

    catalog = load_json(CATALOG)
    if args.probe:
        result = probe(catalog)
        PROBE_OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {PROBE_OUT.relative_to(ROOT)}: {sum(r['readable'] for r in result['results'])} of {len(result['results'])} stores readable")
        return
    previous = load_json(OUTPUT, {})
    started = now_iso()
    observations: list[dict] = []
    extra: dict = {"by_retailer": {}, "notes": []}
    if args.observations:
        obs_file = load_json(args.observations)
        valid = {(it["id"], o["url"]) for it, o in offer_list(catalog)}
        for o in obs_file["observations"]:
            if (o.get("item_id"), o.get("url")) not in valid:
                ap.error("observation does not match a catalog store link: " + str(o.get("item_id")))
            if o.get("ok") and not o.get("checked_at"):
                ap.error("successful observations need their actual checked_at timestamp")
        observations = obs_file["observations"]
        extra["notes"].append(obs_file.get("note") or f"Merged observations from {Path(args.observations).name}.")
    if not args.offline:
        live_obs, live_extra = run_live(catalog, args.limit, args.only)
        seen = {(o["item_id"], o["url"]) for o in live_obs}
        observations = [o for o in observations if (o["item_id"], o["url"]) not in seen] + live_obs
        extra = {"by_retailer": live_extra["by_retailer"], "notes": extra["notes"] + live_extra["notes"]}
    ok = sum(1 for o in observations if o.get("ok"))
    failed = sum(1 for o in observations if not o.get("ok"))
    by_retailer = {}
    for o in observations:
        d = by_retailer.setdefault(o["retailer"], {"ok": 0, "failed": 0, "blocked": 0})
        d["ok" if o.get("ok") else "failed"] += 1
        if o.get("blocked"):
            d["blocked"] += 1
    meta = {"started": started, "finished": now_iso(), "mode": "offline" if args.offline else "live",
            "runner": os.environ.get("SCRAPER_RUNNER") or ("github-actions" if os.environ.get("GITHUB_ACTIONS") else "local"),
            "ok": ok, "failed": failed, "tracked_links": len(offer_list(catalog)), "by_retailer": by_retailer,
            "notes": extra.get("notes", []), "api": bool(os.environ.get("BESTBUY_API_KEY"))}
    if args.offline and args.observations:
        meta["mode"] = "manual"
    elif args.offline and previous.get("scrape"):
        # A plain rebuild (e.g. after editing catalog.json) isn't a scrape: keep the last run's details and timestamp.
        meta = dict(previous["scrape"])
        meta["finished"] = previous.get("generated_at") or meta.get("finished") or now_iso()
        meta["tracked_links"] = len(offer_list(catalog))
    if not args.offline and observations and ok == 0:
        meta["notes"].append("No prices could be read this run, so the site keeps showing the last known prices.")
    data = merge(catalog, previous, observations, meta)
    if os.environ.get("GITHUB_STEP_SUMMARY") and not args.offline:
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as report:
            report.write(f"Price refresh: {ok} store links read, {failed} failed. Failed links keep their previous prices.\n\n")
            for r, d in sorted(by_retailer.items()):
                bots = f" ({d['blocked']} bot checks)" if d["blocked"] else ""
                report.write(f"- {r}: {d['ok']} ok, {d['failed']} failed{bots}\n")
    if args.save_observations and not args.dry_run:
        Path(args.save_observations).write_text(json.dumps({"checked_at": meta["finished"], "runner": meta["runner"],
                                                            "note": "Store price observations from the scraper.",
                                                            "observations": observations}, indent=1, ensure_ascii=False))
    if args.dry_run:
        print(f"dry run: {ok} prices read, {failed} failed; gifts.json not written")
    else:
        OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        what = "rebuilt from the catalog, no scraping" if args.offline and not args.observations else f"{ok} store links read, {failed} failed"
        print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(data['items'])} gifts, {data['live_prices']} with live prices, {what}")
    # Non-zero exit only when a live run read nothing at all, so the workflow can flag it.
    if not args.offline and observations and ok == 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
