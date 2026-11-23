"""Offline checks for the store parsers, robots.txt rules, merging and the catalog: python3 -B scraper/test_scrape.py"""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scrape import (BlockedError, CATALOG, Robots, check_sane, merge, parse_product_page)  # noqa: E402
from add_link import clean, sku_for, store_for  # noqa: E402

failures = 0


def check(cond, label):
    global failures
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        failures += 1


def raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def ld(*nodes):
    return "".join('<script type="application/ld+json">%s</script>' % json.dumps(n) for n in nodes)


# --------------------------------------------------------------- schema.org (Best Buy, LEGO, GameStop, Shopify)
BESTBUY = "<html><head>" + ld([{"@type": "BreadcrumbList"}, {
    "@type": "Product", "name": "The Legend of Zelda: Ocarina of Time - Nintendo Switch 2", "sku": "6691853",
    "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.96, "reviewCount": 145},
    "offers": [
        {"@type": "Offer", "price": 74.99, "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/NewCondition", "seller": {"name": "GameDealsUSA"}},
        {"@type": "Offer", "price": 69.99, "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/NewCondition", "seller": {"name": "Best Buy"}},
        {"@type": "Offer", "price": 54.99, "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/UsedCondition", "seller": {"name": "Best Buy"}},
    ]}]) + "</head></html>"
r = parse_product_page(BESTBUY, "bestbuy", "bestbuy", "6691853")
check(r["price"] == 69.99 and r["in_stock"] is True, "Best Buy: Best Buy's own new price wins")
check(r["marketplace"] == {"price": 74.99, "seller": "GameDealsUSA"}, "Best Buy: marketplace seller recorded separately")
check(r["open_box"] == 54.99 and r["rating"] == 5.0 and r["reviews"] == 145, "Best Buy: open-box price and rating")

MKT_ONLY = "<html>" + ld({"@type": "Product", "name": "Switch 2 + Mario Kart World Bundle", "sku": "6689812", "offers": [
    {"@type": "Offer", "price": 649.0, "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/NewCondition", "seller": {"name": "Tech Resale"}}]}) + "</html>"
r = parse_product_page(MKT_ONLY, "bestbuy", "bestbuy", "6689812")
check(r.get("marketplace_only") and r["price"] == 649.0, "Best Buy: marketplace-only listing is flagged, not used as Best Buy's price")

LEGO = "<html>" + ld({"@context": "https://schema.org", "@type": "Product", "name": "SMART Play: Training House with Pikachu", "sku": "72164",
                      "offers": {"@type": "Offer", "priceCurrency": "USD", "price": 69.99, "availability": "https://schema.org/InStock"}}) + "</html>"
r = parse_product_page(LEGO, "jsonld", "lego", "72164")
check(r["price"] == 69.99 and r["in_stock"] is True, "LEGO: single offer object")

GAMESTOP = "<html>" + ld({"@type": "VideoGame", "name": "Grand Theft Auto VI", "offers": [
    {"name": "New", "price": "79.99", "priceCurrency": "USD", "availability": "https://schema.org/InStock"},
    {"name": "Pre-Owned", "price": "64.99", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}]}) + "</html>"
r = parse_product_page(GAMESTOP, "jsonld", "gamestop", "448295")
check(r["price"] == 79.99 and r["open_box"] == 64.99, "GameStop: VideoGame type; pre-owned kept out of the new price")

SHOPIFY = "<html>" + ld({"@type": "ProductGroup", "name": "Toniebox 2 Starter Set", "productGroupID": "777", "hasVariant": [
    {"@type": "Product", "sku": "TB2-PINK", "offers": {"@type": "Offer", "price": "139.99", "availability": "http://schema.org/OutOfStock"}},
    {"@type": "Product", "sku": "TB2-BLUE", "offers": {"@type": "Offer", "price": "139.99", "availability": "http://schema.org/InStock"}},
]}) + "</html>"
r = parse_product_page(SHOPIFY, "jsonld", "tonies")
check(r["price"] == 139.99 and r["in_stock"] is True and r["name"] == "Toniebox 2 Starter Set", "Shopify: product group variants, in-stock variant preferred")

LISTPRICE = "<html>" + ld({"@type": "Product", "name": "Kindle", "offers": {"@type": "Offer", "price": 129.99, "availability": "InStock",
                           "priceSpecification": [{"@type": "UnitPriceSpecification", "priceType": "https://schema.org/ListPrice", "price": 159.99}]}}) + "</html>"
r = parse_product_page(LISTPRICE, "jsonld", "kohls")
check(r["price"] == 129.99 and r["regular"] == 159.99, "schema.org list price becomes the regular price")

MANY = "<html>" + ld({"@type": "Product", "name": "A", "sku": "1", "offers": {"price": 10}}, {"@type": "Product", "name": "B", "sku": "2", "offers": {"price": 20}}) + "</html>"
check(raises(ValueError, lambda: parse_product_page(MANY, "jsonld", "kohls", "3")), "several products and no SKU match: refuse rather than guess")
check(parse_product_page(MANY, "jsonld", "kohls", "2")["price"] == 20, "several products: SKU picks the right one")

# --------------------------------------------------------------- Walmart
def walmart_page(products):
    return '<html><script id="__NEXT_DATA__" type="application/json">%s</script></html>' % json.dumps({"props": {"pageProps": {"initialData": {"data": products}}}})

WALMART = walmart_page({"related": [{"usItemId": "111", "name": "Some other toy", "priceInfo": {"currentPrice": {"price": 5.0}}}],
                        "product": {"usItemId": "1107995384", "name": "NeeDoh Nice Cube", "sellerDisplayName": "Walmart.com", "availabilityStatus": "IN_STOCK",
                                    "averageRating": 4.3, "numberOfReviews": 2262, "priceInfo": {"currentPrice": {"price": 7.97}, "wasPrice": {"price": 9.99}}}})
r = parse_product_page(WALMART, "walmart", "walmart", "1107995384")
check(r["price"] == 7.97 and r["regular"] == 9.99 and r["in_stock"] and not r.get("marketplace_only"), "Walmart: the linked item, not a related one")
r = parse_product_page(WALMART.replace("Walmart.com", "ToyFlipper"), "walmart", "walmart", "1107995384")
check(r.get("marketplace_only") and r["seller"] == "ToyFlipper", "Walmart: outside seller flagged")
WALMART_BLOCK = '<html><head><title>Robot or human?</title></head><body><div id="px-captcha"></div></body></html>'
check(raises(BlockedError, lambda: parse_product_page(WALMART_BLOCK, "walmart", "walmart", "1")), "Walmart: bot check reported as blocked")

# --------------------------------------------------------------- Target
TARGET = ('<html><script>window.__TGT_DATA__ = JSON.parse("{\\"product\\":{\\"tcin\\":\\"1006663864\\",\\"price\\":{\\"current_retail\\":16.99,'
          '\\"reg_retail\\":19.99,\\"formatted_current_price\\":\\"$16.99\\"},\\"fulfillment\\":{\\"availability_status\\":\\"IN_STOCK\\"}}}")</script></html>')
r = parse_product_page(TARGET, "target", "target", "1006663864")
check(r["price"] == 16.99 and r["regular"] == 19.99 and r["in_stock"] is True, "Target: embedded product data (escaped JSON)")
TARGET_FMT = '<html><script>{"tcin":"55","formatted_current_price":"$24.99","availability_status":"OUT_OF_STOCK"}</script></html>'
r = parse_product_page(TARGET_FMT, "target", "target", "55")
check(r["price"] == 24.99 and r["in_stock"] is False, "Target: formatted price and sold-out status")
TARGET_PLUS = TARGET.replace("</html>", "<div>Sold &amp; shipped by Toynk</div></html>")
check(parse_product_page(TARGET_PLUS, "target", "target", "1006663864").get("marketplace_only"), "Target: Target Plus partner seller flagged")
check(parse_product_page("<html>" + ld({"@type": "Product", "name": "x", "offers": {"price": "12.00", "availability": "InStock"}}) + "</html>",
                         "target", "target")["price"] == 12.0, "Target: schema.org data used when present")

# --------------------------------------------------------------- Amazon
AMAZON = ('<html><div id="corePriceDisplay_desktop_feature_div"><span class="a-price"><span class="a-offscreen">$69.99</span></span></div>'
          '<span>List Price: </span><span class="a-text-price"><span class="a-offscreen">$79.99</span></span>'
          '<div id="availability"><span class="a-size-medium a-color-success"> In Stock </span></div>'
          '<span class="a-icon-alt">4.8 out of 5 stars</span><span id="acrCustomerReviewText">1,204 ratings</span>'
          '<input type="hidden" name="ASIN" value="B0GHYFH499"></html>')
r = parse_product_page(AMAZON, "amazon", "amazon", "B0GHYFH499")
check(r["price"] == 69.99 and r["regular"] == 79.99 and r["in_stock"] is True and r["reviews"] == 1204, "Amazon: buy-box price, list price, stock, reviews")
check(raises(ValueError, lambda: parse_product_page(AMAZON, "amazon", "amazon", "B000000000")), "Amazon: wrong ASIN refused")
AMAZON_3P = AMAZON.replace("</html>", '<a id="sellerProfileTriggerId" href="#">Toy Kingdom LLC</a></html>')
check(parse_product_page(AMAZON_3P, "amazon", "amazon", "B0GHYFH499").get("marketplace_only"), "Amazon: third-party seller flagged")
AMAZON_WHOLE = '<html><span class="a-price-whole">9<span class="a-price-decimal">.</span></span><span class="a-price-fraction">99</span> B0BQZFVJTB <div id="availability"><span>Currently unavailable.</span></div></html>'
r = parse_product_page(AMAZON_WHOLE, "amazon", "amazon", "B0BQZFVJTB")
check(r["price"] == 9.99 and r["in_stock"] is False, "Amazon: split whole/fraction price and unavailable stock")
CAPTCHA = '<html><title>Amazon.com</title><form action="/errors/validateCaptcha">Type the characters you see in this image</form></html>'
check(raises(BlockedError, lambda: parse_product_page(CAPTCHA, "amazon", "amazon")), "Amazon: captcha page reported as blocked")

# --------------------------------------------------------------- fallbacks
META = '<html><meta property="og:price:amount" content="24.00"><meta property="og:price:currency" content="USD"></html>'
check(parse_product_page(META, "jsonld", "sephora")["price"] == 24.0, "price meta tag fallback")
check(raises(ValueError, lambda: parse_product_page("<html><p>hello</p></html>", "jsonld", "kohls")), "a page with no price is an error, not a zero")

# --------------------------------------------------------------- robots.txt
ROBOTS = """User-agent: GPTBot
Disallow: /

User-agent: *
Allow: /~assets/
Disallow: /cart
Disallow: /s?*
Disallow: *cp=1*
Crawl-delay: 2

User-agent: ChristmasGiftFinder
Disallow: /secret/
"""
rb = Robots(ROBOTS, agent="SomeBot")
check(rb.allowed("https://www.target.com/p/squishmallows/-/A-1006663864"), "robots: product page allowed")
check(not rb.allowed("https://www.target.com/s?searchTerm=lego"), "robots: search pages disallowed with wildcard")
check(not rb.allowed("https://x.com/list?cp=1&x=2") and rb.crawl_delay == 2, "robots: leading wildcard and crawl-delay")
mine = Robots(ROBOTS)
check(mine.allowed("https://x.com/cart") and not mine.allowed("https://x.com/secret/a"), "robots: our own group replaces the * group")
check(Robots("").allowed("https://x.com/a") and not Robots("User-agent: *\nDisallow: /").allowed("https://x.com/a"), "robots: empty file vs disallow-all")

# --------------------------------------------------------------- merge
CAT = {"retailers": {"target": {"name": "Target"}, "walmart": {"name": "Walmart"}},
       "items": [{"id": "cube", "name": "Cube", "typical": 9.99, "offers": [
           {"retailer": "target", "url": "https://t/1"}, {"retailer": "walmart", "url": "https://w/1"}]},
           {"id": "plain", "name": "No links", "typical": 20.0, "offers": []}]}
meta1 = {"finished": "2026-11-20T12:00:00Z"}
obs1 = [{"item_id": "cube", "retailer": "target", "url": "https://t/1", "ok": True, "price": 8.99, "in_stock": True, "checked_at": "2026-11-20T11:59:00Z"},
        {"item_id": "cube", "retailer": "walmart", "url": "https://w/1", "ok": True, "price": 7.49, "in_stock": True, "marketplace_only": True, "checked_at": "2026-11-20T11:58:00Z"}]
d1 = merge(CAT, None, obs1, meta1)
cube = d1["items"][0]
check(cube["price"] == 8.99 and cube["price_retailer"] == "target" and cube["price_status"] == "live", "merge: cheapest first-party offer shown, marketplace ignored")
check(cube["history"] == [["2026-11-20", 8.99]] and d1["live_prices"] == 1 and d1["prices_as_of"] == "2026-11-20T11:59:00Z", "merge: history and freshness")
check(d1["items"][1]["price_status"] == "typical" and "price" not in d1["items"][1], "merge: gifts without links fall back to the typical price")
obs2 = [{"item_id": "cube", "retailer": "target", "url": "https://t/1", "ok": False, "error": "HTTP 503", "blocked": True, "checked_at": "2026-11-21T12:00:00Z"}]
d2 = merge(CAT, d1, obs2, {"finished": "2026-11-21T12:00:00Z"})
off = d2["items"][0]["offers"][0]
check(off["price"] == 8.99 and off["stale"] and off["blocked"] and d2["items"][0]["price_status"] == "stale", "merge: failed read keeps the last price, flagged stale")
check(d2["items"][0]["history"] == [["2026-11-20", 8.99]] and d2["prices_as_of"] is None, "merge: stale prices don't add history or count as live")
d3 = merge(CAT, d2, [], {"finished": "2026-11-22T12:00:00Z"})
check(d3["items"][0]["offers"][0].get("error") == "HTTP 503" and d3["items"][0]["offers"][0]["stale"], "merge: untouched links carry over unchanged")
obs4 = [{"item_id": "cube", "retailer": "target", "url": "https://t/1", "ok": True, "price": 6.99, "in_stock": True, "checked_at": "2026-11-22T13:00:00Z"},
        {"item_id": "cube", "retailer": "target", "url": "https://t/1", "ok": True, "price": 7.99, "in_stock": True, "checked_at": "2026-11-22T13:00:00Z"}]
d4 = merge(CAT, d3, obs4[1:], {"finished": "2026-11-22T13:00:00Z"})
d4 = merge(CAT, d4, obs4[:1], {"finished": "2026-11-22T20:00:00Z"})
check(d4["items"][0]["history"][-1] == ["2026-11-22", 6.99] and len(d4["items"][0]["history"]) == 2, "merge: one history point per day, the day's low")
rec = {"ok": True, "price": 59.99}
check_sane(rec, {"typical": 9.99})
check(not rec["ok"] and "far from" in rec["error"], "a price far from typical (likely the wrong product) is not used")

# --------------------------------------------------------------- catalog
catalog = json.loads(CATALOG.read_text())
items = catalog["items"]
ids = [i["id"] for i in items]
check(len(ids) == len(set(ids)), f"catalog: {len(ids)} unique gift ids")
check(all(i["interests"] and set(i["interests"]) <= set(catalog["interests"]) for i in items), "catalog: every interest is defined")
check(all(1 <= i["ages"][0] <= i["ages"][1] <= 30 for i in items), "catalog: ages within 1-30")
check(all(i["typical"] > 0 and (not i.get("range") or i["range"][0] <= i["typical"] <= i["range"][1]) for i in items), "catalog: typical price inside its range")
check(all(i["stores"] and set(i["stores"]) <= set(catalog["retailers"]) for i in items), "catalog: every gift links to known stores")
single = [i["id"] for i in items if len(i["stores"]) == 1]
check(len(single) <= len(items) // 4, f"catalog: single-store gifts stay the exception ({len(single)}, mostly store exclusives)")
T = catalog.get("types", {})
check(T and all(i.get("type") in T and T[i["type"]]["category"] == i["category"] for i in items), f"catalog: every gift has a product type in its category ({len(T)} types)")
check(all(t["category"] in catalog["categories"] and t["label"] and t["emoji"] for t in T.values()), "catalog: product types are labeled and grouped")
used = {i["type"] for i in items}
check(not (set(T) - used), "catalog: every product type has at least one gift" + (f" (empty: {sorted(set(T) - used)})" if set(T) - used else ""))
H = catalog.get("hot_lists", {})
check(H and all(set(i.get("lists", [])) <= set(H) for i in items), f"catalog: every hot list a gift cites is defined ({len(H)} lists)")
check(all(h["name"] and h["short"] and h["kind"] in ("retailer", "expert", "trend", "guide") and h["url"].startswith("https://") for h in H.values()),
      "catalog: hot lists have a name, kind and source link")
check(all(isinstance(i.get("price_est", False), bool) for i in items), "catalog: estimated-price flags are true/false")
dups = [(i["id"], o["retailer"], o.get("sku")) for i in items for n, o in enumerate(i["offers"])
        if any((o["retailer"], o.get("sku")) == (p["retailer"], p.get("sku")) for p in i["offers"][:n])]
check(not dups, "catalog: no store link listed twice on a gift" + (f" {dups}" if dups else ""))
check(all(i["category"] in catalog["categories"] for i in items), "catalog: every category is defined")
bad = [o["url"] for i in items for o in i["offers"]
       if not any(urlparse(o["url"]).netloc.endswith(h) for h in catalog["retailers"][o["retailer"]]["hosts"])]
check(not bad, "catalog: store links point at their store's site" + (f" (bad: {bad})" if bad else ""))
check(all(r["search"] is None or "{q}" in r["search"] for r in catalog["retailers"].values()), "catalog: store search links have a {q} slot")
for lo, hi in [(1, 2), (3, 5), (6, 8), (9, 12), (13, 17), (18, 24), (25, 30)]:
    n = sum(1 for i in items if i["ages"][0] <= hi and i["ages"][1] >= lo)
    check(n >= 12, f"catalog: ages {lo}-{hi} have at least 12 ideas ({n})")

# --------------------------------------------------------------- add_link helpers
R = catalog["retailers"]
check(store_for("https://www.target.com/p/x/-/A-1006663864", R) == "target" and sku_for("https://www.target.com/p/x/-/A-1006663864", "target") == "1006663864", "add_link: Target TCIN")
check(sku_for("https://www.amazon.com/LEGO-Pokemon/dp/B0GHYFH499?th=1", "amazon") == "B0GHYFH499", "add_link: Amazon ASIN")
check(sku_for("https://www.walmart.com/ip/Nee-Doh-Nice-Cube/1107995384?athbdg=L1600", "walmart") == "1107995384", "add_link: Walmart item id")
check(sku_for("https://www.bestbuy.com/product/x/J7GSL57WWG/sku/6689812", "bestbuy") == "6689812", "add_link: Best Buy SKU")
check(store_for("https://us.tonies.com/products/x", R) == "tonies" and store_for("https://example.com/x", R) is None, "add_link: store from host")
check(clean("https://www.walmart.com/ip/x/1?athbdg=L1600&from=/search", "walmart") == "https://www.walmart.com/ip/x/1", "add_link: tracking parameters removed")

check(clean("https://www.macys.com/shop/product/x?ID=26970766&cm_mmc=aff", "macys") == "https://www.macys.com/shop/product/x?ID=26970766"
      and sku_for("https://www.macys.com/shop/product/x?ID=26970766", "macys") == "26970766", "add_link: Macy's product id kept")

# --------------------------------------------------------------- Target pages without prices, probe hints, link-only stores
from scrape import page_hints, run_live  # noqa: E402
NO_PRICE_TGT = '<html><script id="__NEXT_DATA__">{"props":{"pageProps":{"isProductDetailServerSideRenderPriceEnabled":false}}}</script></html>'
try:
    parse_product_page(NO_PRICE_TGT, "target", "target", "1006663864")
    msg = ""
except ValueError as e:
    msg = str(e)
check("no longer puts prices" in msg, "Target: a page with server-side prices turned off says so plainly")
h = page_hints('<script type="application/ld+json">{}</script><span class="a-offscreen">$19.99</span>')
check(h["json_ld"] and h["dollar_amounts"] == 1 and "a-offscreen" in h["price_keys"], "probe: hints describe what a page holds")
lo_cat = {"retailers": {"target": {"name": "Target", "price_check": False, "price_note": "prices load in the browser"}},
          "items": [{"id": "x", "offers": [{"retailer": "target", "url": "https://www.target.com/p/-/A-1", "sku": "1"}]}]}
obs, extra = run_live(lo_cat, None, None)
check(obs == [] and any("aren't price-checked" in n for n in extra["notes"]), "live run: link-only stores are skipped with a note, no requests made")
mcat = {"retailers": {}, "interests": {}, "categories": {}, "types": {"lego": {"label": "LEGO sets"}}, "hot_lists": {"amazon": {"name": "A"}},
        "items": [{"id": "g", "typical": 10, "offers": []}]}
md = merge(mcat, None, [], {"finished": "2026-11-21T00:00:00Z"})
check(md["types"] == mcat["types"] and md["hot_lists"] == mcat["hot_lists"], "merge: product types and hot lists reach gifts.json")

# --------------------------------------------------------------- hotlists.py: product links out of gift guides
from hotlists import best_match, extract, real_url  # noqa: E402
check(real_url("https://goto.target.com/c/1/2/3?subId1=x&u=https%3A%2F%2Fwww.target.com%2Fp%2Fgui-gui%2F-%2FA-94991898") ==
      "https://www.target.com/p/gui-gui/-/A-94991898", "hotlists: Target affiliate redirect decoded")
check(real_url("https://www.anrdoezrs.net/links/9260995/type/dlg/sid/x/https://www.macys.com/shop/product/elmo?ID=27355097") ==
      "https://www.macys.com/shop/product/elmo?ID=27355097", "hotlists: path-style redirect decoded")
check(real_url("https://go.skimresources.com?id=1&url=https%3A%2F%2Fwww.walmart.com%2Fip%2FX%2F19555206231&xcust=y") ==
      "https://www.walmart.com/ip/X/19555206231", "hotlists: skimlinks redirect decoded")
GUIDE = """<p><a href="https://www.amazon.com/Klutz-Lego/dp/1338137204?tag=abc-20">Lego Make Your Own Movie</a>
<a href="https://www.amazon.com/dp/1338137204?tag=abc-20"><img alt=""></a>
<a href="https://goto.walmart.com/c/1/2/3?u=https%3A%2F%2Fwww.walmart.com%2Fip%2FCRUNCH%2F18879462675">The Crunchinator</a>
<a href="https://bestbuy.7tiv.net/c/1/2/3?u=https%3A%2F%2Fwww.bestbuy.com%2Fproduct%2Fps-portal%2FJXHQ3C2CHX%2Fsku%2F6562576">Shop at Best Buy</a>
<a href="https://www.amazon.com/s?k=lego">Amazon search (not a product)</a>
<a href="https://example.com/p/123">Some other shop</a></p>"""
links = {(r["store"], r["sku"]): r for r in extract(GUIDE, R)}
check(set(links) == {("amazon", "1338137204"), ("walmart", "18879462675"), ("bestbuy", "6562576")}, "hotlists: product links found, searches and unknown shops ignored")
check(links[("amazon", "1338137204")]["name"] == "Lego Make Your Own Movie" and links[("amazon", "1338137204")]["url"] == "https://www.amazon.com/dp/1338137204",
      "hotlists: link text kept as the name, tracking removed")
check(links[("bestbuy", "6562576")]["name"] == "", "hotlists: 'Shop at Best Buy' isn't mistaken for a product name")
m, score = best_match("CrunchLabs by Mark Rober The Crunchinator", items)
check(m and m["id"] == "crunchlabs-crunchinator" and score >= 0.45, "hotlists: guide names match catalog gifts")
real = extract((Path(__file__).parent / "fixtures" / "amazon-toys-2026-links.html").read_text(), R)
owner = {(o["retailer"], str(o.get("sku"))): i["id"] for i in items for o in i["offers"]}
right = [r for r in real if best_match(r["name"], items)[0]["id"] == owner.get((r["store"], r["sku"]))]
check(len(real) == 10 and len(right) == len(real), f"hotlists: real Amazon list markup -> 10 products, each matched to the right gift ({len(right)}/{len(real)})")
m, score = best_match("Completely unrelated garden hose", items)
check(score < 0.45, "hotlists: unrelated names don't match")

# --------------------------------------------------------------- store_picks.py: store lists read in a browser
import datetime as dt  # noqa: E402
import tempfile  # noqa: E402
import store_picks as sp  # noqa: E402
from scrape import capture_observations  # noqa: E402

TYPE_CASES = {
    "LEGO Botanicals Cozy Plants - Building Toy for Girls & Boys, Ages 9+": "lego",
    "LEGO DUPLO Disney Frozen Creative Box with Elsa and Olaf": "blocks",
    "Joyspun Women's Plush Robe, Sizes S to 3X": "clothing",
    "Taste Beauty Dumpling Squishy Lip Gloss Keychain, Strawberry, 0.14 oz": "lip",
    "Barbie Dream Camper Playset with Roof Tent, BBQ Grill with Color-Change Feature": "playsets",
    "Ninja Creami Scoop & Swirl Ice Cream Maker, Scoopable & Soft Serve": "appliances",
    "STANLEY Classic Vacuum Bottle, Green/Silver": "drinkware",
    "Pinkfong Baby Shark Inflatable Arm Ring Floats, Pair, Ages 2-4 Years": "outdoor-play",
    "Sweet Like Candy by Ariana Grande, 3.4 oz EDP Spray for Women": "fragrance",
    "Funko POP TV: Power Rangers Z - Zeo Ranger Yellow Collectible Vinyl Figure": "figures",
    "Nintendo Switch 2 System": "consoles",
    "Mario Kart 8 Deluxe racing video game (Nintendo Switch)": "switch-games",
    "PS5 DualSense® Wireless Controller - Gran Turismo Limited Edition": "controllers",
    "Grand Theft Auto VI, PlayStation 5 Game, (Code in Box)": "ps-xbox-games",
    "HALO Rise Above Jr Lil' Switch 2-in-1 Rider - Scooter for Ages 1+ - Red": "bikes-scooters",
    "Star Wars Imperial Remnant AT-RT RC Walker with Mandalorian and Grogu": "vehicles",
    "Barbie Chemistry Activity Lab Science Kit for Kids Age 5 and Up by Blue Marble": "science-kits",
    "The French Illusion: A Novel (Hardcover)": "adult-books",
    "Apple AirPods Max Over-Ear Headphones with USB-C, Blue": "headphones",
    "Apple AirPods Pro 3": "earbuds",
    "Carhartt Adult Acrylic Watch Hat (Carhartt Brown)": "accessories",
}
wrong = {n: (sp.classify(n), t) for n, t in TYPE_CASES.items() if sp.classify(n) != t}
check(not wrong, "store picks: product names land in the right product type" + (f" {wrong}" if wrong else ""))
DROPS = ["Best Choice Products 6ft Pre-Lit Flocked Artificial Aspen Noble Fir Christmas Tr", "(Open Box) Apple AirPods Max Over-Ear Headphones",
         "Samsung 55 Class U8000H Series Crystal UHD 4K UHD Smart TV", "Frigidaire 5.0 Cu. ft. Garage Ready Chest Freezer",
         "Verizon iPhone 18 Pro 256GB Burgundy", "Greenworks Pro PowerAll 24V Drill, Driver Bundle", "Restored Premium Dyson Supersonic Hair Dryer",
         "Hickory Farms $9.97 Meat & Cheese Gift Box Gourmet Charcuterie Set", "Haribo Holiday Filled Tube Goldbears 2.53oz Gummy Candy"]
check(all(sp.classify(n) == "drop" for n in DROPS), "store picks: groceries, TVs, appliances, tools, phones and open-box items are left out")
check(sp.classify("Bluey: Little Library 4-Book Box Set (Hardcover)", "3920:582053", [1, 3]) == "picture-books"
      and sp.classify("Some Novel Title (Hardcover)", "3920:1233541", [13, 17]) == "ya-books", "store picks: books are sorted by the ages they're for")
check(sp.ages_from_name("LeapFrog LeapMove, Ages 4-7 Years Old") == (4, 7) and sp.ages_from_name("LEGO set, Ages 9+") == (9, None)
      and sp.ages_from_name("Squishy Cheese for Kids 5 and up") == (5, None) and sp.ages_from_name("Advent Calendar for Kids, Ages 6") == (6, None)
      and sp.ages_from_name("Apple AirPods Pro 3") is None, "store picks: ages printed in product names are read")
spans = {"clothing": [1, 30], "vehicles": [2, 30]}
check(sp.age_range("No Boundaries Icon Sweater, Women's and Women's Plus", {"wm-gifts-teens": 1}, "clothing", spans)[0] == [13, 17]
      and sp.age_range("No Boundaries Icon Sweater, Women's and Women's Plus", {"wm-top100": 1}, "clothing", spans)[0] == [18, 30],
      "store picks: the store's age-group list beats words like Women's; words beat the product type")
check(sp.age_range("PAW Patrol Megasaurus Dino Vehicle, Ages 3+", {"wm-top-toys": 3}, "vehicles", spans)[0] == [3, 15],
      "store picks: 'Ages 3+' on a toy doesn't stretch to age 30")
check(sp.clean_name("Pokmon " + "x" * 74 + " tail") == "Pokémon " + "x" * 74 + "…" and sp.clean_name("Short name") == "Short name",
      "store picks: names cut at 80 characters end on a whole word, and dropped accents come back")

now = dt.datetime(2026, 11, 22, 20, 0, tzinfo=dt.timezone.utc)
CAP = """#run walmart 2026-11-22T19:20:23Z
#list wm-top-toys page=1 count=4 maxPage=1
111|19.97|29.99|W|4171:4186|BH|4.7|150|LEGO Botanicals Cozy Plants - Building Toy, Ages 9+
222|89.99||M|4171:4187|B|4.7|717|KPop Demon Hunters Mira Singing Doll
333|4.97||M|4171:4187||4.0|3|Mystery Doll From A Marketplace Shop
444|149.00||W|3944:1060825|B|4.4|7617|VIZIO 55 Class Mini LED 4K QLED Smart TV
#list wm-deals-toys page=1 count=2 maxPage=1
=111
555|5.00||M|4171:4187|R|4.0|3|Tiny Doll Sold By A Marketplace Shop
#list wm-tracked page=1 count=2 maxPage=1
666|300.00||W|||4.6|58|Magical Birthday Surprises Winnie the Pooh Doll
777|24.88||W||O|4.5|70|Barbie Chemistry Activity Lab Science Kit
"""
with tempfile.TemporaryDirectory() as td:
    f = Path(td) / "walmart.txt"
    f.write_text(CAP)
    cap = sp.parse_capture(f)
    check(cap["store"] == "walmart" and cap["lists"]["wm-deals-toys"]["rows"] == [(1, "111"), (2, "555")] and len(cap["products"]) == 7,
          "store picks: capture files are read, repeats point back to the first listing")
    bad = Path(td) / "bad.txt"
    bad.write_text("#run walmart 2026-11-22T19:20:23Z\n#list wm-top-toys page=1\n=999\n")
    check(raises(ValueError, lambda: sp.parse_capture(bad)), "store picks: a repeat of a product that wasn't listed is an error")
    bad.write_text("#run walmart 2026-11-22T19:20:23Z\n#list wm-top-toys page=1\n111|1|2|W\n")
    check(raises(ValueError, lambda: sp.parse_capture(bad)), "store picks: a line with the wrong number of fields is an error")
    mini = {"types": {"lego": {"category": "building"}, "dolls": {"category": "toys"}, "science-kits": {"category": "stem"}},
            "items": [{"id": "lego-cozy", "type": "lego", "ages": [9, 30], "typical": 29.99,
                       "offers": [{"retailer": "walmart", "url": "https://www.walmart.com/ip/111", "sku": "111"}]},
                      {"id": "kpdh-mira", "type": "dolls", "ages": [4, 12], "typical": 24.99,
                       "offers": [{"retailer": "walmart", "url": "https://www.walmart.com/ip/222", "sku": "222"}]},
                      {"id": "pooh", "type": "dolls", "ages": [2, 6], "typical": 49.97,
                       "offers": [{"retailer": "walmart", "url": "https://www.walmart.com/ip/666", "sku": "666"}]},
                      {"id": "barbie-lab", "type": "science-kits", "ages": [5, 10], "typical": 24.88,
                       "offers": [{"retailer": "walmart", "url": "https://www.walmart.com/ip/777", "sku": "777"}]}]}
    out, obs, st = sp.build(mini, [cap], now)
    by = {x["sku"]: x for x in out["items"]}
    check(set(by) == {"111", "222", "333"}, "store picks: TVs and few-review marketplace listings on deal pages are left out; the store's own top lists keep theirs")
    lego = by["111"]
    check(lego["gift"] == "lego-cozy" and lego["type"] == "lego" and lego["was"] == 29.99 and lego["pct"] == 33
          and lego["flags"] == ["best-seller", "deal"] and lego["lists"] == ["wm-top-toys", "wm-deals-toys"]
          and lego["ages"] == [9, 30] and lego["ages_from"] == "catalog",
          "store picks: a pick keeps the store's badges, lists, discount and the catalog gift it matches")
    check(by["222"]["seller"] == "marketplace" and "was" not in by["222"], "store picks: marketplace sellers are labeled")
    o = {x["item_id"]: x for x in obs["walmart"]}
    check(o["lego-cozy"]["ok"] and o["lego-cozy"]["price"] == 19.97 and o["lego-cozy"]["regular"] == 29.99 and o["lego-cozy"]["on_sale"]
          and o["lego-cozy"]["verification_method"] == "browser" and o["lego-cozy"]["checked_at"] == "2026-11-22T19:20:23Z",
          "store picks: prices for gifts the catalog tracks become price-checker observations")
    check(o["kpdh-mira"]["marketplace_only"] and o["barbie-lab"]["in_stock"] is False,
          "store picks: marketplace-only and sold-out readings are marked as such")
    check(o["pooh"]["ok"] is False and o["pooh"]["reason"] == "sanity", "store picks: a price far from the usual one is rejected like any other reading")
    old, _, st2 = sp.build(mini, [cap], now + dt.timedelta(days=sp.MAX_AGE_DAYS + 1))
    check(old["items"] == [] and st2["old_captures"] == 1, f"store picks: captures older than {sp.MAX_AGE_DAYS} days are skipped")
    ob = Path(td) / "walmart-observations.json"
    ob.write_text(json.dumps({"observations": obs["walmart"]}))
    cat2 = {"retailers": {"walmart": {"name": "Walmart"}}, "items": mini["items"]}
    fresh = capture_observations(cat2, None, Path(td))
    prev = {"items": [{"id": "lego-cozy", "offers": [{"url": "https://www.walmart.com/ip/111", "checked_at": "2026-11-22T19:20:23Z"}]}]}
    again = capture_observations(cat2, prev, Path(td))
    check(len(fresh) == 4 and {x["item_id"] for x in again} == {"kpdh-mira", "pooh", "barbie-lab"},
          "price checker: browser-read prices are merged once, then gifts.json carries them")

real = [sp.parse_capture(p) for p in sorted(sp.CAPTURES.glob("*.txt"))]
if real:
    rout, robs, rst = sp.build(json.loads(CATALOG.read_text()), real, dt.datetime.fromisoformat(max(c["captured_at"] for c in real).replace("Z", "+00:00")))
    shipped = json.loads((sp.OUT).read_text()) if sp.OUT.exists() else {"items": []}
    check(len(rout["items"]) >= 300 and {x["id"] for x in rout["items"]} == {x["id"] for x in shipped["items"]},
          f"store picks: site/data/store-picks.json is up to date with scraper/captures ({len(rout['items'])} picks)")
    tps = json.loads(CATALOG.read_text())["types"]
    check(all(x["type"] in tps and tps[x["type"]]["category"] == x["category"] and 1 <= x["ages"][0] <= x["ages"][1] <= 30 for x in rout["items"]),
          "store picks: every pick has a known product type and an age range within 1-30")
check(sp.esrb_ages([6, 30], "M", "Some Game") == ([17, 30], "M") and sp.esrb_ages([8, 12], "T", "x") == ([13, 30], "T")
      and sp.esrb_ages([6, 30], "E", "x") == ([6, 30], "E") and sp.esrb_ages([13, 17], "RP", "Grand Theft Auto VI") == ([17, 30], "RP-M")
      and sp.esrb_ages([7, 30], "RP", "Madden NFL 27") == ([13, 30], "RP"), "store picks: ESRB ratings set the youngest age for video games")
if real:
    rated = [x for x in rout["items"] if x["type"] in sp.GAME_TYPES]
    check(rated and all(x["ages"][0] >= 17 for x in rated if x.get("esrb") in ("M", "RP-M"))
          and any(x.get("esrb") == "M" for x in rated) and all(x.get("esrb") for x in rated),
          f"store picks: every video game has an ESRB rating, and Mature ones are 17 and up ({len(rated)} games)")
rcat = {"retailers": {"walmart": {"name": "Walmart"}, "amazon": {"name": "Amazon"}}, "items": [{"id": "g", "typical": 30, "offers": [
    {"retailer": "walmart", "url": "https://www.walmart.com/ip/1", "sku": "1"}, {"retailer": "amazon", "url": "https://www.amazon.com/dp/B0X", "sku": "B0X"}]}]}
run1 = merge(rcat, None, [{"item_id": "g", "retailer": "walmart", "url": "https://www.walmart.com/ip/1", "ok": True, "price": 20.0,
                           "checked_at": "2026-11-22T19:20:23Z"}], {"finished": "2026-11-22T20:00:00Z"})
run2 = merge(rcat, run1, [], {"finished": "2026-11-22T20:00:00Z"})
check(json.dumps(run1["items"]) == json.dumps(run2["items"]), "merge: rebuilding unchanged data gives the same file, byte for byte")
bcat = {"retailers": {"walmart": {"name": "Walmart", "price_check": "browser", "price_note": "read at home"}},
        "items": [{"id": "x", "offers": [{"retailer": "walmart", "url": "https://www.walmart.com/ip/1", "sku": "1"}]}]}
obs3, extra3 = run_live(bcat, None, None)
check(obs3 == [] and any("priced from a browser" in n for n in extra3["notes"]), "live run: stores priced in a browser are skipped on GitHub, no requests made")
rets = json.loads(CATALOG.read_text())["retailers"]
check(rets["walmart"].get("price_check") == "browser" and rets["amazon"].get("price_check") is False and rets["target"].get("price_check") is False,
      "catalog: Walmart is priced in a browser; Amazon and Target links aren't price-checked")

# A price an older version of the checker read from a store that is now links only doesn't stay up.
lcat = {"retailers": {"amazon": {"name": "Amazon", "price_check": False}, "gamestop": {"name": "GameStop"}},
        "items": [{"id": "cube", "typical": 9.99, "offers": [{"retailer": "amazon", "url": "https://www.amazon.com/dp/B0Q", "sku": "B0Q"}]},
                  {"id": "game", "typical": 70, "offers": [{"retailer": "gamestop", "url": "https://www.gamestop.com/x/1.html", "sku": "1"}]}]}
lprev = {"items": [{"id": "cube", "price": 14.99, "price_retailer": "amazon", "price_status": "live", "history": [["2026-11-22", 14.99]],
                    "offers": [{"retailer": "amazon", "url": "https://www.amazon.com/dp/B0Q", "price": 14.99, "checked_at": "2026-11-22T23:45:55Z", "stale": False}]},
                   {"id": "game", "price": 69.99, "price_retailer": "gamestop", "price_status": "live", "history": [["2026-11-22", 69.99]],
                    "offers": [{"retailer": "gamestop", "url": "https://www.gamestop.com/x/1.html", "price": 69.99, "checked_at": "2026-11-22T23:45:00Z", "stale": False}]}]}
lout = {i["id"]: i for i in merge(lcat, lprev, [], {"finished": "2026-11-23T06:20:00Z"})["items"]}
check("price" not in lout["cube"]["offers"][0] and lout["cube"]["price_status"] == "typical" and lout["cube"]["history"] == []
      and lout["game"]["offers"][0]["price"] == 69.99 and lout["game"]["history"] == [["2026-11-22", 69.99]],
      "merge: link-only stores never show a price, even one an older checker read; other stores keep theirs")

# A failed attempt on GitHub after a browser reading doesn't hold that reading back, and history uses the reading's day.
with tempfile.TemporaryDirectory() as td2:
    wurl = "https://www.walmart.com/ip/9"
    wcat = {"retailers": {"walmart": {"name": "Walmart", "price_check": "browser"}},
            "items": [{"id": "sw", "typical": 499, "offers": [{"retailer": "walmart", "url": wurl, "sku": "9"}]}]}
    wob = {"item_id": "sw", "retailer": "walmart", "url": wurl, "ok": True, "price": 449.0, "checked_at": "2026-11-22T19:20:23Z"}
    (Path(td2) / "walmart-observations.json").write_text(json.dumps({"observations": [wob]}))
    wprev = {"items": [{"id": "sw", "offers": [{"retailer": "walmart", "url": wurl, "blocked": True, "error": "bot check",
                                                 "last_attempt": "2026-11-22T23:46:01Z", "stale": True}]}]}
    got = capture_observations(wcat, wprev, Path(td2))
    wout = merge(wcat, wprev, got, {"finished": "2026-11-23T06:20:00Z"})["items"][0]
    check(len(got) == 1 and wout["price"] == 449.0 and wout["price_status"] == "live" and wout["history"] == [["2026-11-22", 449.0]],
          "price checker: a later failed attempt doesn't hold back a browser reading; history is dated by the reading")

print(f"\n{'All checks passed.' if not failures else f'{failures} check(s) failed.'}")
sys.exit(1 if failures else 0)
