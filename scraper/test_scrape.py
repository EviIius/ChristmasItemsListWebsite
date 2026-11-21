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
check(all(len(i["stores"]) >= 2 and set(i["stores"]) <= set(catalog["retailers"]) for i in items), "catalog: every gift links to 2+ known stores")
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

print(f"\n{'All checks passed.' if not failures else f'{failures} check(s) failed.'}")
sys.exit(1 if failures else 0)
