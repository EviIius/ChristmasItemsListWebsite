#!/usr/bin/env python3
"""Turn store pages read in a browser into the site's store picks and store prices.

Walmart blocks GitHub's servers, so its hot lists, best sellers and deals are read in a real browser on a home
computer (see "Reading Walmart in your browser" in the README) and saved as a capture file:
scraper/captures/walmart.txt. This script:

  1. reads every capture file in scraper/captures/
  2. writes site/data/store-picks.json: each product on the store's hot lists and deal pages, sorted into the
     site's product types, with an age range and the store's own badges (best seller, deal, rollback...)
  3. writes scraper/captures/<store>-observations.json: store prices for the gifts the catalog already links to
  4. runs scrape.py --offline, which merges those prices into site/data/gifts.json (on GitHub, the rebuild after
     every push does the same, so pushing the capture files is enough)

Usage:
  python3 scraper/store_picks.py             # import every capture file
  python3 scraper/store_picks.py --check     # print what would be imported, write nothing
  python3 scraper/store_picks.py --unsorted  # list products no product-type rule matched (to improve RULES)

Capture file format (one product per line, written by the browser snippet in the README):
  #run walmart 2026-11-22T19:20:23Z
  #list wm-top-toys page=1 count=83 maxPage=2
  id|price|was|seller|category path|flags|rating|reviews|name
  id|price|was|seller|category path|flags|rating|reviews|photo|name   (newer files: with the product photo)
  ^id|price|was|flags|photo   (a product an earlier file of the same store has: new price, badges and photo)
  =id          (the same product again, on another list)
  ~N           (N products left out here: already in an earlier file, or not gifts this site covers)
The photo is the part of the store's image address that changes from product to product (see STORES "img").
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "scraper" / "captures"
CATALOG = ROOT / "site" / "data" / "catalog.json"
OUT = ROOT / "site" / "data" / "store-picks.json"
MATCHES = ROOT / "scraper" / "photo_matches.json"  # hand-checked photos for catalog gifts no tracked link covers
MAX_AGE_DAYS = 10  # captures older than this are left out of store-picks.json (deals end)

STORES = {
    "walmart": {
        "name": "Walmart",
        "site": "walmart.com",
        "url": lambda sku: f"https://www.walmart.com/ip/{sku}",
        "own_seller": "Walmart.com",
        # Product photos: the photo's id (a UUID; captures write it without dashes). {w} is the width the site asks for.
        "img": "https://i5.walmartimages.com/asr/{id}.jpeg?odnHeight={w}&odnWidth={w}&odnBg=FFFFFF",
    },
    # GameStop draws its product grid in the browser; /products/<id>.html redirects to the full product page.
    "gamestop": {
        "name": "GameStop",
        "site": "gamestop.com",
        "url": lambda sku: f"https://www.gamestop.com/products/{sku}.html",
        "own_seller": "GameStop",
        "img": "https://media.gamestop.com/i/gamestop/{id}?h={w}&w={w}&sm=clamp&fmt=auto",  # id: GameStop's photo name (its SKU)
    },
    # LEGO.com: /en-us/product/<set number> redirects to the set's page.
    "lego": {
        "name": "LEGO.com",
        "site": "lego.com",
        "url": lambda sku: f"https://www.lego.com/en-us/product/{sku}",
        "own_seller": "LEGO",
        "img": "https://www.lego.com/cdn/cs/set/assets/{id}?format=jpg&width={w}",  # id: "blt.../<file>.png"
    },
    # Five Below: /products/<slug>; the slug ends in Five Below's style number.
    "fivebelow": {
        "name": "Five Below",
        "site": "fivebelow.com",
        "url": lambda sku: f"https://www.fivebelow.com/products/{sku}",
        "own_seller": "Five Below",
    },
    # Barnes & Noble: the id is "<work id>-<EAN>"; /w/<work id>?ean=<EAN> redirects to the product page.
    "barnesnoble": {
        "name": "Barnes & Noble",
        "site": "barnesandnoble.com",
        "url": lambda sku: "https://www.barnesandnoble.com/w/{}?ean={}".format(*sku.split("-", 1)),
        "own_seller": "Barnes & Noble",
        "img": "https://cdn.shopify.com/s/files/1/0674/5433/7265/files/{id}_p0.jpg?width={w}",  # id: the EAN
    },
}


def photo_id(store: str, sku: str, token: str | None) -> str | None:
    """The photo id the site puts into STORES[store]["img"], from the captured token (or the product id)."""
    if store == "barnesnoble":
        m = re.search(r"(\d{13})$", sku)
        return m.group(1) if m else None  # B&N names its photos by EAN
    token = (token or "").strip()
    if not token:
        return None
    if store == "walmart":
        h = token.replace("-", "").lower()
        if not re.fullmatch(r"[0-9a-f]{32}", h):
            return None
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if store == "gamestop":  # "11204090", "20023062-2e0ec255", "11184368_black"
        return token if re.fullmatch(r"\d[\w-]*", token) else None
    if store == "lego":
        return token if re.fullmatch(r"blt[0-9a-f]{16}/[\w.%()-]+\.(?:png|jpe?g|webp)", token, re.I) else None
    return None

# Product ids are numbers, except Five Below's (the product's URL slug) and Barnes & Noble's ("<work id>-<EAN>").
SKU_FORMS = {"fivebelow": r"[a-z0-9][a-z0-9-]*", "barnesnoble": r"\d+-\d{13}"}

# key: (name, short name, url, kind, ages). kind: "hot" (the store's own best-seller and top lists),
# "age" (the store's best sellers for an age group), "deals" (the store's deal pages), "tracked" (gifts the
# catalog links to). ages: the age group the store made the list for, or None.
LISTS = {
    "wm-top100": ("Walmart Top 100 Gifts", "Top 100 Gifts", "https://www.walmart.com/shop/gifting/holiday/top-100-gifts", "hot", None),
    "wm-top-toys": ("Walmart Top Toys", "Top Toys", "https://www.walmart.com/shop/toy-shop/toptoys", "hot", (2, 12)),
    "wm-trending-toys": ("Walmart Trending Toys", "Trending toys", "https://www.walmart.com/shop/toy-shop/trendingtoys", "hot", (2, 12)),
    "wm-stocking-stuffers": ("Walmart best-selling stocking stuffers", "Stocking stuffers", "https://www.walmart.com/shop/gifts/holiday/stocking-stuffer-gifts?sort=best_seller", "hot", None),
    "wm-gifts-baby": ("Walmart best sellers: gifts for babies", "Baby best sellers", "https://www.walmart.com/shop/gifts/holiday/baby?sort=best_seller", "age", (1, 2)),
    "wm-gifts-toddlers": ("Walmart best sellers: gifts for toddlers", "Toddler best sellers", "https://www.walmart.com/shop/gifts/holiday/toddlers?sort=best_seller", "age", (1, 3)),
    "wm-gifts-little-kids": ("Walmart best sellers: gifts for little kids", "Little kids best sellers", "https://www.walmart.com/shop/gifts/holiday/little-kids?sort=best_seller", "age", (3, 7)),
    "wm-gifts-big-kids": ("Walmart best sellers: gifts for big kids", "Big kids best sellers", "https://www.walmart.com/shop/gifts/holiday/big-kids?sort=best_seller", "age", (8, 12)),
    "wm-gifts-teens": ("Walmart best sellers: gifts for teens", "Teen best sellers", "https://www.walmart.com/shop/gifts/holiday/teens?sort=best_seller", "age", (13, 17)),
    "wm-gifts-her": ("Walmart best sellers: gifts for her", "Gifts for her", "https://www.walmart.com/shop/gifts/holiday/her?sort=best_seller", "age", (18, 30)),
    "wm-gifts-him": ("Walmart best sellers: gifts for him", "Gifts for him", "https://www.walmart.com/shop/gifts/holiday/him?sort=best_seller", "age", (18, 30)),
    "wm-deals-toys": ("Walmart toy deals", "Toy deals", "https://www.walmart.com/shop/deals?catId=4171&sort=best_seller", "deals", None),
    "wm-deals-video-games": ("Walmart video game deals", "Video game deals", "https://www.walmart.com/shop/deals?catId=2636&sort=best_seller", "deals", None),
    "wm-deals-electronics": ("Walmart electronics deals", "Electronics deals", "https://www.walmart.com/shop/deals?catId=3944&sort=best_seller", "deals", None),
    "wm-deals-sports": ("Walmart sports & outdoors deals", "Sports deals", "https://www.walmart.com/shop/deals?catId=4125&sort=best_seller", "deals", None),
    "wm-cyber-monday": ("Walmart Cyber Monday deals", "Cyber Monday deals", "https://www.walmart.com/shop/deals/cyber-monday?sort=best_seller", "deals", None),
    "wm-cm-toys": ("Walmart Cyber Monday toy deals", "Cyber Monday toys", "https://www.walmart.com/shop/deals/cyber-monday?catId=4171&sort=best_seller", "deals", None),
    "wm-cm-video-games": ("Walmart Cyber Monday video game deals", "Cyber Monday games", "https://www.walmart.com/shop/deals/cyber-monday?catId=2636&sort=best_seller", "deals", None),
    "wm-cm-electronics": ("Walmart Cyber Monday electronics deals", "Cyber Monday tech", "https://www.walmart.com/shop/deals/cyber-monday?catId=3944&sort=best_seller", "deals", None),
    "gs-best-sellers": ("GameStop Best Sellers", "GameStop best sellers", "https://www.gamestop.com/best-sellers", "hot", None),
    "gs-deals": ("GameStop Black Friday deals", "GameStop deals", "https://www.gamestop.com/deals", "deals", None),
    "gs-bf-games-20": ("GameStop Black Friday: games $19.99 or less", "Games $19.99 or less", "https://www.gamestop.com/links/select-video-games-20-under?pmax=20", "deals", None),
    "gs-bf-games-30": ("GameStop Black Friday: games $29.99 or less", "Games $29.99 or less", "https://www.gamestop.com/links/select-video-games-30-under?pmax=30", "deals", None),
    "gs-bf-games-40": ("GameStop Black Friday: games $39.99 or less", "Games $39.99 or less", "https://www.gamestop.com/links/select-video-games-40-under?pmax=40", "deals", None),
    "lego-black-friday": ("LEGO.com Black Friday deals", "LEGO Black Friday", "https://www.lego.com/en-us/black-friday-deals", "deals", None),
    "lego-cyber-monday": ("LEGO.com Cyber Monday deals", "LEGO Cyber Monday", "https://www.lego.com/en-us/cyber-monday-deals", "deals", None),
    "bn-50off": ("Barnes & Noble 50% off books", "B&N 50% off books", "https://www.barnesandnoble.com/collections/books/50off", "deals", None),
    "lego-bestsellers": ("LEGO.com Best Sellers", "LEGO best sellers", "https://www.lego.com/en-us/categories/bestsellers", "hot", None),
    "lego-new": ("LEGO.com new sets", "New LEGO sets", "https://www.lego.com/en-us/categories/new-sets-and-products", "new", None),
    "lego-deals": ("LEGO.com sales & deals", "LEGO deals", "https://www.lego.com/en-us/categories/sales-and-deals", "deals", None),
    "gs-toys": ("GameStop top-selling toys & games", "GameStop toys", "https://www.gamestop.com/toys-games?srule=top-sellers", "hot", None),
    "gs-collectibles": ("GameStop top-selling collectibles", "GameStop collectibles", "https://www.gamestop.com/collectibles?srule=top-sellers", "hot", None),
    "fb-top-toys": ("Five Below Top Toy Gifts", "Five Below top toys", "https://www.fivebelow.com/categories/holiday/top-toy-gifts", "hot", None),
    "fb-best-toys": ("Five Below best-selling games & toys", "Five Below best-selling toys", "https://www.fivebelow.com/categories/toys-and-games/best-selling-games-and-toys", "hot", None),
    "fb-best-tech": ("Five Below best-selling tech", "Five Below best-selling tech", "https://www.fivebelow.com/categories/tech/best-selling-electronics-and-accessories", "hot", None),
    "fb-best-beauty": ("Five Below best-selling beauty", "Five Below best-selling beauty", "https://www.fivebelow.com/categories/beauty/best-selling-beauty-products", "hot", None),
    "fb-gifts-kids": ("Five Below gift finder: gifts for kids", None, "https://www.fivebelow.com/categories/holiday/gift-finder/for-kids", "age", (4, 12)),
    "fb-gifts-her": ("Five Below gift finder: gifts for her", None, "https://www.fivebelow.com/categories/holiday/gift-finder/for-her", "age", (13, 30)),
    "fb-gifts-him": ("Five Below gift finder: gifts for him", None, "https://www.fivebelow.com/categories/holiday/gift-finder/for-him", "age", (13, 30)),
    "fb-under-5": ("Five Below gifts under $5", "Five Below gifts under $5", "https://www.fivebelow.com/categories/holiday/gift-finder/gifts-under-5-dollars", "hot", None),
    "fb-stocking-stuffers": ("Five Below stocking stuffers", "Five Below stocking stuffers", "https://www.fivebelow.com/categories/holiday/stocking-stuffers", "hot", None),
    "fb-gamer-gifts": ("Five Below top gamer gifts", None, "https://www.fivebelow.com/categories/gift-guide/top-gamer-gifts", "hot", None),
    "fb-beauty-gifts": ("Five Below beauty gift sets", None, "https://www.fivebelow.com/categories/beauty/beauty-gift-sets", "hot", None),
    "fb-squishies": ("Five Below squishy & fidget toys", "Five Below squishies", "https://www.fivebelow.com/categories/toys-and-games/squishy-and-fidget-toys", "hot", None),
    "fb-plush": ("Five Below stuffed animals", None, "https://www.fivebelow.com/categories/toys-and-games/stuffed-animals", "hot", None),
    "fb-blind-bags": ("Five Below blind bags & collectibles", None, "https://www.fivebelow.com/categories/toys-and-games/blind-bags-and-collectibles", "hot", None),
    "fb-collector-gifts": ("Five Below gift guide: collector gifts", None, "https://www.fivebelow.com/categories/gift-guide/toy-gifts/collector-gifts", "hot", None),
    "fb-cute-gifts": ("Five Below gift guide: cute gifts", None, "https://www.fivebelow.com/categories/gift-guide/toy-gifts/cute-gifts", "hot", None),
    "fb-craft-gifts": ("Five Below gift guide: craft kit gifts", None, "https://www.fivebelow.com/categories/gift-guide/toy-gifts/craft-kit-gifts", "hot", None),
    "fb-sensory-gifts": ("Five Below gift guide: squishy & sensory gifts", None, "https://www.fivebelow.com/categories/gift-guide/toy-gifts/squishy-sensory-gifts", "hot", None),
    "fb-fan-gifts": ("Five Below gift guide: fan shop", None, "https://www.fivebelow.com/categories/gift-guide/fan-shop-wonderland", "hot", None),
    "fb-kpop": ("Five Below KPop Demon Hunters shop", None, "https://www.fivebelow.com/categories/fan-shop/k-pop-demon-hunters", "hot", (6, 17)),
    "fb-girls-night": ("Five Below gift guide: girls' night in", None, "https://www.fivebelow.com/categories/gift-guide/girls-night-in", "hot", (13, 30)),
    "fb-glow": ("Five Below gift guide: ready, set, glow", None, "https://www.fivebelow.com/categories/gift-guide/ready-set-glow", "hot", (13, 30)),
    "fb-cozy": ("Five Below gift guide: cozy loungewear", None, "https://www.fivebelow.com/categories/gift-guide/cozy-loungewear", "hot", (13, 30)),
    "fb-headphones": ("Five Below headphones", None, "https://www.fivebelow.com/categories/tech/headphone-shop", "hot", None),
    "fb-gaming-acc": ("Five Below gaming accessories", None, "https://www.fivebelow.com/categories/tech/gaming-accessories", "hot", None),
    "fb-board-games": ("Five Below board games", None, "https://www.fivebelow.com/categories/toys-and-games/board-games-and-more", "hot", None),
    "fb-new-toys": ("Five Below new toys & games", None, "https://www.fivebelow.com/categories/new-and-now/new-toys-games", "new", None),
    "fb-new-tech": ("Five Below new tech", None, "https://www.fivebelow.com/categories/new-and-now/new-tech-electronics", "new", None),
    "fb-new-beauty": ("Five Below new beauty", None, "https://www.fivebelow.com/categories/new-and-now/new-beauty", "new", None),
    "bn-best-toys": ("Barnes & Noble Best Toys & Games of 2026", "B&N best toys of 2026", "https://www.barnesandnoble.com/collections/toys-games/best-toys-games-of-the-year", "hot", None),
    "bn-toys-0-2": ("Barnes & Noble toys for ages 0-2", None, "https://www.barnesandnoble.com/collections/toys-games/ages-0-2", "age", (1, 2)),
    "bn-toys-3-5": ("Barnes & Noble toys for ages 3-5", None, "https://www.barnesandnoble.com/collections/toys-games/ages-3-5", "age", (3, 5)),
    "bn-toys-6-8": ("Barnes & Noble toys for ages 6-8", None, "https://www.barnesandnoble.com/collections/toys-games/ages-6-8", "age", (6, 8)),
    "bn-toys-9-12": ("Barnes & Noble toys for ages 9-12", None, "https://www.barnesandnoble.com/collections/toys-games/ages-9-12", "age", (9, 12)),
    "bn-toys-teens": ("Barnes & Noble toys & games for teens", None, "https://www.barnesandnoble.com/collections/toys-games/teens", "age", (13, 17)),
    "bn-lego": ("Barnes & Noble building toys & LEGO", None, "https://www.barnesandnoble.com/collections/toys-games/building-lego", "hot", None),
    "bn-plush": ("Barnes & Noble dolls & stuffed animals", None, "https://www.barnesandnoble.com/collections/toys-games/dolls-stuffed-animals", "hot", None),
    "bn-collectibles": ("Barnes & Noble collectibles", None, "https://www.barnesandnoble.com/collections/toys-games/collectibles", "hot", None),
    "bn-funko": ("Barnes & Noble Funko", None, "https://www.barnesandnoble.com/collections/toys-games/special-collections/funko", "hot", None),
    "bn-games": ("Barnes & Noble games", "B&N games", "https://www.barnesandnoble.com/collections/toys-games/games", "hot", None),
    "bn-tcg": ("Barnes & Noble collectible card games", None, "https://www.barnesandnoble.com/collections/toys-games/games/collectible-card-games-1", "hot", None),
    "bn-puzzles": ("Barnes & Noble puzzles", None, "https://www.barnesandnoble.com/collections/toys-games/puzzles", "hot", None),
    "bn-advent": ("Barnes & Noble advent calendars", None, "https://www.barnesandnoble.com/collections/toys-games/advent-calendars", "hot", None),
    "bn-gifts": ("Barnes & Noble gift ideas", None, "https://www.barnesandnoble.com/collections/stationery-gifts/gift-giving", "hot", None),
    "bn-best-books": ("Barnes & Noble bestselling books", "B&N bestselling books", "https://www.barnesandnoble.com/collections/books/bestselling-books", "hot", None),
    "bn-books-of-year": ("Barnes & Noble best books of the year", None, "https://www.barnesandnoble.com/collections/books/awards/best-books-of-the-year", "hot", None),
    "bn-kids-books-0-2": ("Barnes & Noble books for ages 0-2", None, "https://www.barnesandnoble.com/collections/books/kids/ages-0-2", "age", (1, 2)),
    "bn-kids-books-3-5": ("Barnes & Noble books for ages 3-5", None, "https://www.barnesandnoble.com/collections/books/kids/ages-3-5", "age", (3, 5)),
    "bn-kids-books-6-8": ("Barnes & Noble books for ages 6-8", None, "https://www.barnesandnoble.com/collections/books/kids/ages-6-8", "age", (6, 8)),
    "bn-kids-books-9-12": ("Barnes & Noble books for ages 9-12", None, "https://www.barnesandnoble.com/collections/books/kids/ages-9-12", "age", (9, 12)),
    "bn-teen-books": ("Barnes & Noble teen & YA books", "B&N teen books", "https://www.barnesandnoble.com/collections/books/teens-ya", "age", (13, 17)),
    "bn-manga": ("Barnes & Noble manga & graphic novels", None, "https://www.barnesandnoble.com/collections/books/graphic-novels-comics-manga", "hot", (13, 30)),
    "bn-boxed-sets": ("Barnes & Noble kids' boxed sets", None, "https://www.barnesandnoble.com/collections/books/kids-boxed-sets", "hot", (5, 12)),
    "wm-tracked": ("Gifts this site tracks at Walmart", None, None, "tracked", None),
    "gs-tracked": ("Gifts this site tracks at GameStop", None, None, "tracked", None),
    "lego-tracked": ("Gifts this site tracks at LEGO.com", None, None, "tracked", None),
}

FLAGS = {"B": "best-seller", "H": "deal", "R": "rollback", "P": "reduced", "C": "clearance", "L": "low-stock",
         "E": "event", "O": "sold-out"}

# Walmart's data drops some accented letters; put the common ones back.
NAME_FIXES = {"Pokmon": "Pokémon", "Pok?mon": "Pokémon", "J?ADORE": "J'ADORE", "World’S": "World's", "Ragnark": "Ragnarök", "Mbapp ": "Mbappé ", "Smarwatch": "Smartwatch",
              # LEGO.com's theme names: "Other" isn't a theme, and some names repeat the brand
              "LEGO Other LEGO® ": "LEGO ", "LEGO Other ": "LEGO ", "LEGO ǀ ": "LEGO ", "LEGO Minifigures LEGO® ": "LEGO Minifigures ", "LEGO Icons LEGO® ": "LEGO Icons "}

# Not gifts this site covers: groceries, big appliances, TVs, phones on carrier plans, tools, holiday decorations,
# bedding, furniture and baby gear. Checked before the product-type rules.
DROP_TERMS = [
    r"christmas tree", r"xmas tree", r"artificial .*tree", r"freezer", r"refrigerator", r"mini fridge", r"range oven",
    r"wall oven", r"gas range", r"vacuum cleaner", r"upright vacuum", r"deep cleaner", r"cake mix", r"biscuit mix",
    r"olive oil", r"cooking oil", r"waffles", r"gummy(?!.*(?:squish|slime|toy))", r"ring pop", r"lollipop", r"candy filled", r"chocolate kisses",
    r"energy drink", r"red bull", r"meat & cheese", r"charcuterie", r"gourmet", r"holiday treats", r"spices",
    r"iphone \d+", r"iphone duo", r"prepaid smartphone", r"straight talk", r"verizon", r"t-mobile",
    r"smart tv", r"\d+[″\"]? class", r"\d+ class", r"qled", r"crystal uhd", r"mini led", r"soundbar",
    r"drill", r"circular saw", r"recip saw", r"rotary tool", r"tool storage", r"screwdriver", r"dewalt", r"greenworks",
    r"griddle", r"electric grill", r"gas grill", r"fire ?pit", r"chest cooler", r"ice chest", r"hard cooler", r"dome tent",
    r"camping tent", r"hand sanitizer", r"meat thermometer", r"bar cart", r"vanity table", r"comforter", r"bed set",
    r"twin bed", r"toddler bed", r"pillowcase", r"throw pillow", r"upholstered", r"washcloths?", r"towel",
    r"e-?bike", r"electric bike", r"electric tricycle", r"electric dirt bike", r"echomap", r"transducer",
    r"cookware set", r"fry pan", r"dutch oven", r"pots (?:&|and) pans", r"kitchen tool set", r"ornament",
    r"stocking with", r"phone case", r"wired earbuds", r"over ear headphones with microphone", r"baby monitor",
    r"video monitor", r"essential oil", r"dj controller", r"acoustic electric guitar", r"acoustic guitar",
    r"electric guitar", r"pre-?lit", r"\(open box\)", r"open box", r"restored", r"refurbished", r"renewed",
    r"chocolate candy", r"baby food", r"electrolyte", r"flavor cartridge", r"whitestrips", r"baking kit", r"soda crafter",
    r"syrups?\b", r"hex key", r"tool pad", r"shop-vac", r"wet/dry vac", r"folding table", r"power station", r"seatpost",
    r"garden statue", r"slumberpod", r"sleep tent",
    r"halloween", r"\bcostume\b(?! accessory)", r"terrifier", r"bloody", r"ghost ?face", r"reading sunglasses", r"deodorant", r"antiperspirant",
    r"period underwear", r"diaper", r"stroller", r"\bjuice\b", r"cookies", r"crackers", r"spices", r"^(?!.*gift set).*\b(?:body wash|shampoo)\b",
    r"washcloths?", r"humidifier", r"hdmi cable", r"\btights\b", r"pajama shorts", r"area rug", r"christmas tree", r"wreath",
    r"tool set", r"toolbox", r"tool cabinet", r"spotlight", r"flashlight", r"storage (?:organizer|cabinet)", r"air purifier",
    r"robot vacuum", r"tea kettle", r"corkscrew", r"milk frother", r"treadmill", r"sauna", r"playpen", r"play yard", r"swaddle",
    r"wash cloths", r"gummies", r"mini jars", r"popcorn", r"hershey", r"cocoa set", r"bottles of", r"fish ?finder|humminbird",
    r"luggage|carry on|checked\)", r"gps\b",
    r"hot cocoa (?:bomb|mix)", r"cocoa bomb", r"mini drinks", r"alani nu", r"candy slime", r"gumm(?:y|i) candy", r"handheld vacuum",
    r"storage chair", r"desktop fan", r"heated car cushion", r"cable end protectors", r"exfoliating gloves", r"cocoa butter formula",
    r"puzzle glue", r"\d+ ?pc pdq", r"count display$",
    # Black Friday pages mix in household and car gear
    r"jump starter", r"jump box", r"tire inflator", r"air compressor", r"leaf (?:dust )?(?:air )?(?:blaster|blower)", r"snow (?:blower|thrower)",
    r"ice maker", r"dresser\b", r"space heater", r"security camera", r"surveillance", r"doorbell", r"dash ?cam", r"bulb cam",
    r"surge protector", r"outlet extender", r"driveway alarm", r"solar (?:outdoor |flood |motion )?lights?", r"flood light",
    r"(?:permanent|outdoor) christmas lights", r"\btv antenna\b", r"(?:smart|outdoor|portable) (?:outdoor |portable )?tv\b",
    r"knife set", r"kitchen tool", r"steam mop", r"rice (?:and grain )?cooker", r"slow cooker", r"pressure cooker", r"cat food",
    r"wagon cart", r"collapsible (?:folding )?wagon", r"hot tub", r"hot tent", r"bike cases?", r"\bjeans\b", r"sleep mask",
    r"dog food", r"wet cat", r"drip coffee maker",
]
DROP = re.compile(r"\b(?:" + "|".join(DROP_TERMS) + r")", re.I)
# Gifts a drop term would catch: craft kits that make ornaments or wreaths, puzzles of cookies, Funko figures.
KEEP = re.compile(r"\b(?:diy|make your own|decorate your own|paint your own|digital photo|diamond art|puzzle(?! glue| conserver)|funko)\b", re.I)

# (product type, pattern) — first match wins, so specific rules come before general ones.
RULES = [
    ("tcg", r"pok[eé]mon tcg|trading card game|elite trainer box|booster"),
    ("lego", r"\blego\b(?!.*\b(?:guide|duplo)\b)"),
    ("blocks", r"\bduplo\b|brickcraft|building kit|mega bloks|building blocks"),
    ("magnetic-tiles", r"magna-?tiles|magnetic tiles|connetix"),
    ("lip", r"lip gloss|lip balm|lip treatment|lip tint|lip oil|\blips?\b"),
    ("blind-boxes", r"blind box|blind ball|mystery box|surprise toy|surprise collectible|happy haul|miniverse|mystery plush|fugg nuggets"),
    ("figures", r"\bfunko\b|\bpop!|vinyl figure"),
    ("charms", r"bag charms?|keychain|keyring"),
    ("squishies", r"nee ?doh|squish|stress ball|fidget|sensory squeeze"),
    ("slime", r"\bslime\b|gui gui|kinetic sand"),
    ("gift-cards", r"gift card|egift"),
    ("clothing", r"\brobes?\b|bathrobe|pajama"),
    ("accessories", r"beanie|hat and glove|scarf|watch hat|hair bow|bow clip|headwrap|accessories set"),
    ("cozy", r"\bthrow\b|blanket"),
    ("decor", r"bean ?bag"),
    ("interactive-plush", r"tickle me elmo|furreal|interactive plush|speak & sing|smart stages|giggle max|puppetronic|grow & roar|sleep soother|shusher"),
    ("plush", r"plush|stuffed animal|squishmallow|warmies|buttercups|lovey|palm pals"),
    ("ride-ons", r"ride-?on|cozy coupe|activity walker|push walker|roadster|kart ride"),
    ("bikes-scooters", r"\bbike\b|scooter|pocket mod|\brider\b"),
    ("blasters", r"\bnerf\b|blaster|foam blade|foam sword|x-?shot|laser x"),
    ("active-games", r"nex playground|gymnastics mat|rebounder|bouncer"),
    ("kids-tech", r"toniebox|tonies|\byoto\b|kids tablet|kids karaoke|kidizoom|itech jr|alarm clock for kid"),
    ("science-kits", r"science kit|chemistry|dissection|stem toy|lab science"),
    ("pretend-play", r"pretend|first aid|cash register|kitchen set|play kitchen|ice cream cart|dress up|dress-up|role ?play|fx mask|easy bake|baking toy|doctor kit"),
    ("toddler-playsets", r"little people|take-along|toddler learning toy"),
    ("craft-kits", r"craft kit|crafts kit|bracelet kit|friendship bracelet|water globes|rock painting|blooms by play-doh|flower bouquet|cricut|sticker maker|smart sketcher"),
    ("dough", r"play-?doh|modeling clay"),
    ("playsets", r"playset|dollhouse|play set|cruise ship|garage|volcano|track set|copter|firetruck|adventure plane|dream camper|dream plane"),
    ("vehicles", r"hot wheels|monster jam|monster truck|\brc\b|radio control|remote control|dig rig|motorized|school bus|race cars|toy cars|drone|vehicle"),
    ("dolls", r"\bdolls?\b|barbie|polly pocket|my life as"),
    ("action-figures", r"action figure|titan series|figure battle|feature figure|beyblade|grogu animatronic|actionverse|buzz lightyear|toy story 5"),
    ("baby-activity", r"\bbaby\b.*\b(?:gym|playmat|toy|teether|tub tester)|teether|playmat|sorting barn|barn buddies|whack game|story dream machine|leapreader|learn-to-read"),
    ("musical-toys", r"kidi star|dj mixer|guitar|karaoke|xylophone|piano|sing along microphone|record player musical"),
    ("interactive", r"tamagotchi|bitzee|digital pet|pets alive|robo alive|interactive|hatching egg|primal hatch|leapmove|crunchinator|animatronic"),
    ("engineering", r"crunchlabs|engineering|robot kit|marble run"),
    ("3d-pens", r"3d pen|3d printing pen|3d printer"),
    ("art-supplies", r"crayola|crayons|markers|sticker book|art set|coloring"),
    ("board-games", r"board game|monopoly(?! deal)|mahjong|chess"),
    ("card-games", r"card game|\buno\b|monopoly deal|word game"),
    ("puzzles", r"puzzle|jigsaw"),
    ("pc-gaming", r"gaming keyboard|gaming mouse|gaming chair|gaming monitor|gaming pc|gaming laptop|stream deck|quadcast|usb microphone|curved gaming|tuf gaming|\bomen\b|monitor"),
    ("consoles", r"(?:playstation [45]|xbox (?:series [xs]|one)|nintendo switch)\b[^|]*\bconsole\b(?![^|]*(?:charging|stand|skin|case|cover|controller))|playstation portal|switch oled"),
    ("consoles", r"switch 2 system|switch 2 \+|switch 2 bundle|mario kart world bundle|playstation 5 console|xbox series [xs] console|game system"),
    ("controllers", r"controller|dualsense"),
    ("vr", r"meta quest|vr headset|virtual reality"),
    ("switch-games", r"nintendo switch"),
    ("headphones", r"gaming headsets?\b|\bheadset\b(?![^|]*\bvr\b)"),
    ("ps-xbox-games", r"playstation 5|playstation 4|\bps5\b|xbox series x game|\bps4\b"),
    ("headphones", r"headphones|headset|kraken|barracuda|arctis|airpods max|beats solo"),
    ("earbuds", r"airpods|earbuds|linkbuds"),
    ("chargers", r"airtag|item tracker|popsockets|phone grip|charger|power bank|magsafe"),
    ("smart-home", r"google home|homeview|echo dot|smart speaker|skylight|digital calendar"),
    ("speakers", r"speaker|record player|sonos|turntable"),
    ("cameras", r"camera|instax|polaroid|photo printer|now gen 3"),
    ("tablets", r"\bipad\b|tablet|kindle|e-?reader|galaxy tab|\btab\b"),
    ("computers", r"macbook|laptop|chromebook"),
    ("wearables", r"apple watch|smartwatch|smart watch|oura ring|smart ring|garmin|fitbit|ray-ban meta|\bwatch\b"),
    ("vinyl", r"\bvinyl\b(?!.*(?:plush|figure))|splatter|\blp\b"),
    ("picture-books", r"board book|sound book|padded board|little golden books|picture book|electronic book"),
    ("kids-books", r"wimpy kid|dog man|advent christmas countdown.*books|lego make your own movie"),
    ("kids-books", r"dog man|diary of a wimpy kid|cat kid comic|captain underpants|baby-sitters club|magic tree house|junie b\. jones|amelia bedelia|wild robot|bob books"),
    ("manga", r"\bmanga\b|graphic novel"),
    ("ya-books", r"court of|new moon|sixth faction|raven boys|nothing like the movies"),
    ("adult-books", r"a novel|mamba mentality|dungeon crawler"),
    ("journals", r"journal|planner|notebook|letters to my baby"),
    ("appliances", r"ninja|creami|slushi|air fryer|espresso|coffee maker|nespresso|keurig|kitchenaid|crispi|ice cream maker|frozen drink|stand mixer|slow cooker|multi-cooker|crock-pot|pasta press"),
    ("hair-tools", r"hair dryer|flat iron|curling|flexstyle|airwrap|glossi|styling tool|speedstyle|supersonic|halo ?ring"),
    ("kids-makeup", r"makeup kit for kids|kid-safe makeup|tween beauty|go glo|u-glow"),
    ("makeup", r"makeup|mascara|nail polish|nail color|press on nails|gel nail|beauty advent|advent calendar.*women"),
    ("skincare", r"skincare|skin care|acne|face wash|cleanser|salicylic|moisturizer|\bmasks?\b|toner|serum|pore pad|cream|spf|patches|red light therapy|face spray"),
    ("fragrance", r"eau de|parfum|cologne|perfume|body mist|hair mist|fragrance|\bedp\b|\bedt\b|\bmist\b"),
    ("bath-body", r"bath|body wash|spa set|body care|gift set|gift pack"),
    ("shoes", r"boots?\b|sneakers|slippers|clogs|crocs|heels|shoes|\bugg\b|tasman|bungee lace|timberland"),
    ("outerwear", r"jacket|coat|puffer|shacket"),
    ("bags", r"crossbody|tote|satchel|handbag|shoulder bag|backpack|wristlet|luggage"),
    ("jewelry", r"necklace|earring|bracelet|jewelry|(?:gold|silver|diamond|stackable|signet|birthstone) ring\b|ring set|pendant"),
    ("accessories", r"\bhat\b|gloves|socks?\b|sunglass"),
    ("clothing", r"sweater|hoodie|cardigan|joggers|jeans|skirt|t-shirt|dress set|sweatpants|matching"),
    ("lighting", r"string lights|lamp|night light|candle warmer"),
    ("decor", r"diffuser|candle"),
    ("drinkware", r"water bottle|tumbler|owala|stanley|freesip|vacuum bottle|\bmug\b"),
    ("fitness", r"dumbbell|smartbell|massage gun|theragun|yoga|resistance band"),
    ("sports-gear", r"soccer ball|basketball|football|tee ball|glove with ball|golf|fishing|lure kit|volleyball|baseball"),
    ("outdoor-play", r"snow|sled|outdoor|backyard|trampoline|swing set|floats|\bpool\b"),
]
RULES = [(t, re.compile(p, re.I)) for t, p in RULES]

# Ages written in product names: "Ages 4-7", "Ages 9+", "for Kids 5 and up", "Ages 8 Years and Up", "Ages 6".
AGE_RANGE = re.compile(r"\bages?\s*(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\b", re.I)
AGE_MIN = re.compile(r"\b(?:ages?|kids|children|child)\s*(\d{1,2})\s*(?:\+|and up|years and up|years old and up|& up|years\+?)", re.I)
AGE_BARE = re.compile(r"\bages?\s*(\d{1,2})\b", re.I)
# Words that hint at an age group. Weaker than the store's own age-group lists ("Women's" sizes fit teens too).
ADULT = re.compile(r"\b(adults?|women'?s|men'?s|womens|for women|for men)\b", re.I)
TEEN = re.compile(r"\bteens?\b", re.I)
TODDLER = re.compile(r"\btoddlers?\b|\bpreschool", re.I)
BABY = re.compile(r"\bnewborns?\b|\binfants?\b|\b\d{1,2}\s*months?\b|\bbaby (?:boy|girl|toy|gift)s?\b|for babies", re.I)
KID = re.compile(r"\b(kids?|kids'|boys'?|girls'?|youth|children|child)\b", re.I)


def fix_name(name: str) -> str:
    for a, b in NAME_FIXES.items():
        name = name.replace(a, b)
    return re.sub(r"\s+", " ", name).strip()


def clean_name(name: str) -> str:
    name = fix_name(name).strip(" ,-–")
    if len(name) >= 79:  # the capture cuts names at 80 characters: end on a whole word
        name = re.sub(r"[\s,;:–-]+\S*$", "", name).rstrip(" ,-–(") + "…"
    return name


BOOK_PATHS = ("3920", "5440")  # Walmart's Books departments


def classify(name: str, path: str = "", ages: list | None = None) -> str | None:
    if (DROP.search(name) and not KEEP.search(name)) or FIVEBELOW_DROP.match(path or ""):
        return "drop"
    if (path or "").startswith("bnbook:") and not re.search(r"\b(?:puzzle|game|kit|deck|journal|notebook|tarot|plush|desktop|wacky waving|talking button|crystal ball|lucky cat|mood lamp|sticker book)\b", name, re.I):
        return book_type(name, ages)  # Barnes & Noble says it's a book (hardcover, paperback, board book)
    if re.match(r"[a-z-]+:", path or ""):
        for rx, t in GAMESTOP_PATHS:
            if re.match(rx, path):
                return t
    for t, rx in RULES:
        if rx.search(name):
            return t
    if (path or "").startswith("fb:"):  # Five Below's aisle, when the name alone doesn't say
        for rx, t in FIVEBELOW_PATHS:
            if re.match(rx, path):
                return t
    if path.split(":")[0] in BOOK_PATHS or re.search(r"\((?:hardcover|paperback|board book)\)", name, re.I):
        return book_type(name, ages)
    return None


def book_type(name: str, ages: list | None) -> str:
    if re.search(r"\bmanga\b|graphic novel|, vol\. \d", name, re.I):
        return "manga" if not ages or ages[0] >= 13 else "kids-books"
    lo = (ages or [18])[0]
    return "picture-books" if lo <= 5 else "kids-books" if lo <= 12 else "ya-books" if lo <= 17 else "adult-books"


def ages_from_name(name: str) -> tuple[int, int | None] | None:
    """Ages the name states in numbers: (youngest, oldest or None for "and up")."""
    m = AGE_RANGE.search(name)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 <= lo <= hi <= 99:
            return max(lo, 1), min(hi, 30)
    m = AGE_MIN.search(name) or AGE_BARE.search(name)
    if m and 0 < int(m.group(1)) <= 30:
        return int(m.group(1)), None
    return None


def ages_from_words(name: str) -> tuple[int, int] | None:
    """A rough age group from words like Women's, Teen, Toddler or Newborn."""
    kid, adult = KID.search(name), ADULT.search(name)
    if kid and adult:
        return 6, 30
    if adult:
        return 18, 30
    if TEEN.search(name):
        return 13, 17
    if TODDLER.search(name):
        return 1, 4
    if BABY.search(name):
        return 1, 2
    return None


RULES += [(t, re.compile(rx, re.I)) for t, rx in [
    ("ps-xbox-games", r"xbox series x(?:/s)?\b(?![^|]*(?:console|controller|headset|batter|charg|storage|card))|xbox one\b(?![^|]*(?:console|controller))"),
    ("tcg", r"\btopps\b|hobby box|mega box|value box"),
    ("bath-body", r"advent calendar[^|]*(?:adults|beauty|bath|body|spa)|grooming set"),
    ("figures", r"advent calendar"),
    ("action-figures", r"marvel legends|mcfarlane|\d-in(?:ch)? (?:action )?figure"),
    ("blind-boxes", r"blind (?:pack|bag)|mystery capsule"),
    ("squishies", r"squeeze ball|squishy"),
    ("kids-makeup", r"beauty set[^|]*age"),
    ("craft-kits", r"arts? (?:&|and) crafts|making kit|bird ?house kit"),
    ("science-kits", r"steam kit|terrarium"),
    ("ride-ons", r"\btrike\b|tricycle"),
    ("bikes-scooters", r"hoverboard|hovertrax|dirt rocket"),
    ("sports-gear", r"pickleball|\bskates?\b"),
    ("fitness", r"power cage|squat rack"),
    ("baby-activity", r"activity cube|play gym|soother|rattle|jingle & shake"),
    ("kids-tech", r"walkie talkies?|learn & go|learning toy"),
    ("musical-toys", r"sing-along microphone"),
    ("pretend-play", r"tea set|teapot|glam vanity|get ready with me"),
    ("playsets", r"headquarters|\bplayset\b"),
    ("board-games", r"party game"),
    ("cameras", r"fujifilm mini|instax"),
    ("wearables", r"\bmeta (?:adventurer|wayfarer|skyler)|smart glasses"),
    ("controllers", r"motionplus|controller grip"),
    ("chargers", r"rechargeable batter|ac adapter"),
    ("vr", r"head strap for (?:oculus|meta) quest|quest 2|quest 3"),
    ("hair-tools", r"detangling brush"),
    ("accessories", r"hair clips?|claw clip|headband|ponytail|scrunchie"),
    ("bags", r"cosmetic (?:travel )?case|beauty bag|\bwallet\b"),
    ("drinkware", r"water jug|tumbler"),
    ("decor", r"floor mirror|foam chair|wooden block"),
    ("journals", r"memory book|baby books?\b"),
    ("shoes", r"sneakers?\b|\bclogs?\b"),
    ("clothing", r"pullover|quarter zip|half zip|sweatshirt|\bshorts\b|crew neck|sleep 'n play|romper|outfit|onesie|sleep pants|fleece"),
    ("action-figures", r"jurassic world|imaginext|ghidorah|spartan collection|\bfigures?\b|freddy's|slap bands|web slinger"),
    ("plush", r"flopsie|plush|deddy bear"),
    ("blind-boxes", r"surprise eggs|bitty pop|l\.o\.l\. surprise|blind pdq"),
    ("puzzles", r"rubik"),
    ("card-games", r"playing cards"),
    ("vehicles", r"go kart|race to celebrate|rescue cruiser"),
    ("blocks", r"\bbldr\b"),
    ("baby-activity", r"baby einstein|melissa & doug multi-sensory|montessori|pikler|sit n spin|spin along|rubber ducks|bright starts"),
    ("kids-tech", r"claw game|learning systems"),
    ("pretend-play", r"play coin"),
    ("outdoor-play", r"soccer goal|axe throwing|lawn darts|balance beam|gymnastics bar"),
    ("bikes-scooters", r"mountain bicycle|\bbicycle\b"),
    ("musical-toys", r"drum,|drum set"),
    ("art-supplies", r"gel pens|diamond (?:dotz|painting)|cozy stickers|easy-doodle|crochet"),
    ("craft-kits", r"water pets|footprint kit"),
    ("journals", r"letters to my"),
    ("hair-tools", r"thermal brush|detangler"),
    ("accessories", r"hair pin|pin set|earmuff|mittens|caps with ears"),
    ("skincare", r"medicube|ice roller|depuffi"),
    ("speakers", r"homepod|cd player|boombox"),
    ("headphones", r"\bheadphones?\b"),
    ("pc-gaming", r"huntsman|keyboard"),
    ("lighting", r"light projector|led strip|selfie light"),
    ("decor", r"saucer chair|flip-out chair|table lamp|velvet fringe|cell phone stand|desk mirror|vanity desk"),
    ("fragrance", r"collector's edition christmas holiday gift|every man jack"),
    ("shoes", r"slippers?\b|\bboots?\b|\bshoes?\b"),
    ("clothing", r"pants|shirt|dress|jogger|sleep top|footed sleep|crew &"),
]]
# Barnes & Noble and Five Below names (Nov 24): games, plush, puppets, putty and the like.
RULES += [(t, re.compile(rx, re.I)) for t, rx in [
    ("board-games", r"exploding kittens|gloomhaven|wingspan|sushi go|rummikub|kanoodle|guess who|what do you meme|happy little dinosaurs"
                    r"|boardgame|game of the (?:year|season)|magical athlete|monkey around|forbidden legacy|endearment|midnight on the christmas express|qboid|mah ?jong"),
    ("slime", r"thinking putty|scentsory putty|\bslimy\b"), ("dough", r"playfoam|kiddough"),
    ("squishies", r"squeeze toy|slimygloop"), ("pretend-play", r"puppet|critter clinic|lightsaber"),
    ("baby-activity", r"leapfrog|geared to steer|activity soft cube|soft book|pop & surprise"),
    ("plush", r"soft toy|cuteeze|barnsie bear|tuxedo kitten|fuggler|fuggs\b"), ("vehicles", r"tracktors|char car|matchbox|\bmoto asst"),
    ("action-figures", r"schleich|lava scorpion"), ("science-kits", r"i dig it|thames & kosmos|gyroscope"),
    ("craft-kits", r"illustory|diamond (?:art|painting)"), ("blocks", r"build(?:able)? blocks"), ("dolls", r"styling head|fashion dol"),
    ("kids-tech", r"handheld gaming console|microphone"), ("kids-makeup", r"cosmetic set"), ("accessories", r"tripod|hand warmers"),
    ("active-games", r"ping pong|billiards|desktop arcade"), ("charms", r"trinket charms|gacha"), ("bags", r"duffel|duffle"),
    ("pc-gaming", r"wireless mouse|gaming mouse|wrist rest"), ("lighting", r"book light|table lamp|portable table l"),
    ("figures", r"\bhippers\b"), ("sports-gear", r"glove, ball|bat kit"), ("drinkware", r"tritan|double-wall insul"),
]]
# Checked before every other rule: names the general rules sort wrongly (sports-card boxes aren't sports gear, a Funko
# "POP Television" figure isn't a coat, a Ghibli plush beanbag isn't furniture).
RULES[:0] = [(t, re.compile(rx, re.I)) for t, rx in [
    ("tcg", r"panini|topps|bowman|mega box|blaster box"), ("active-games", r"desktop arcade|tabletop arcade"),
    ("kids-tech", r"portable video gaming console|minimobile"),
    ("board-games", r"rock 'em sock 'em|santa cookie elf candy snowman|karaoke chaos"),
    ("craft-kits", r"make your own snow globe|crochet .*set|crochet kit"), ("decor", r"snow globe"), ("lighting", r"string light"),
    ("plush", r"fluffy beanbag|plush .*beanbag"),
    ("figures", r"\bpop (?:television|movies|animation|tv|rocks|games|books|premium|jumbo)\b|pocket pop"),
    # Black Friday deal names
    ("ride-ons", r"\bride[- ]on (?:car|truck|toy|utv|dump)|powered ride"), ("blasters", r"foam (?:dart|ball) (?:launcher|target)|dart launchers"),
    ("pc-gaming", r"gaming desktop|desktop pc"), ("controllers", r"game control\b|cooling (?:stand|fan)|charging station for (?:xbox|ps5)"),
    ("magnetic-tiles", r"magnetic building"), ("pretend-play", r"tea party set|tea time toys"), ("craft-kits", r"bedazzler"),
    ("active-games", r"claw machine|bounce house|ball pit"), ("musical-toys", r"instruments toy|musical toys for"),
    ("cameras", r"compact digital|digital camera"), ("decor", r"alarm clock|picture frame"),
]]
# Lists whose unsorted products are books (Barnes & Noble's exclusive editions don't carry a format).
BOOK_LISTS = {"bn-best-books", "bn-books-of-year", "bn-kids-books-0-2", "bn-kids-books-3-5", "bn-kids-books-6-8",
              "bn-kids-books-9-12", "bn-teen-books", "bn-boxed-sets"}

# GameStop's department and aisle (the first two parts of its product address) say what a product is.
GAMESTOP_PATHS = [
    (r"^video-games:nintendo-switch", "switch-games"), (r"^video-games:", "ps-xbox-games"),
    (r"^consoles-hardware:", "consoles"), (r"^gaming-accessories:gaming-headsets", "headphones"),
    (r"^gaming-accessories:chargers", "chargers"), (r"^gaming-accessories:", "controllers"),
    (r"^toys-games:trading-cards", "tcg"), (r"^toys-games:blind", "blind-boxes"), (r"^collectibles:funko", "figures"),
    (r"^collectibles:", "action-figures"), (r"^gift-cards:", "gift-cards"), (r"^clothing:t-shirts", "clothing"),
    (r"^clothing:", "accessories"),
]

# Five Below's aisles (the last part of its category path), used when the product name doesn't match a rule.
FIVEBELOW_DROP = re.compile(r"fb:(?:chocolate|christmas-candy|gummy-candy|candy|cleaning|hand-soaps-and-sanitizers|personal-care|bins-and-boxes|desk-supplies|cables)$")
FIVEBELOW_PATHS = [
    (r"fb:(?:squishy-and-fidget|a-mart-snacks-toys-and-more)$", "squishies"), (r"fb:slime-kits$", "slime"),
    (r"fb:(?:squishmallows|plush|other-plush|character-plush|stuffed-animals-and-plush-toys)$", "plush"),
    (r"fb:(?:blind-bags|clips)$", "blind-boxes"), (r"fb:(?:vinyl|funko-vinyl-action-figures)$", "figures"),
    (r"fb:(?:action-figures|spiderman-toys-and-sets)$", "action-figures"), (r"fb:dolls$", "dolls"), (r"fb:toy-cars$", "vehicles"),
    (r"fb:(?:construction|lego)$", "blocks"), (r"fb:(?:board-games|games)$", "board-games"), (r"fb:(?:cards|trading-cards)$", "card-games"),
    (r"fb:puzzles$", "puzzles"), (r"fb:science-kits$", "science-kits"), (r"fb:journals$", "journals"),
    (r"fb:(?:painting-kits|craft-kits-and-sets|crochet-kits|jewelry-kits|beauty-kits|branded-kits|craft-basket|crafts-and-activities)$", "craft-kits"),
    (r"fb:(?:coloring-supplies|children-s-coloring|stickers|1-supplies)$", "art-supplies"),
    (r"fb:(?:bluetooth-speakers-headphones-and-earbuds|speakers)$", "speakers"), (r"fb:earbuds$", "earbuds"),
    (r"fb:(?:bluetooth-headphones-and-earbuds|wired-headphones|kid-safe-headphones)$", "headphones"),
    (r"fb:(?:cables-and-chargers|wall-chargers)$", "chargers"), (r"fb:(?:gaming-gear|gamer-basket)$", "controllers"),
    (r"fb:(?:phone-accessories|phone-cases|earbud-cases|computer-accessories|iphone-15-models|hats|bag-charms-and-more)$", "accessories"),
    (r"fb:bags-and-wallets$", "bags"), (r"fb:(?:lip-gloss|lip-balm-and-lip-gloss)$", "lip"),
    (r"fb:perfume-cologne-and-body-mist$", "fragrance"), (r"fb:(?:makeup|palettes|fake-nails)$", "makeup"),
    (r"fb:(?:bath-and-body|body-care|skin-care|skincare-and-beauty|beauty-gift-sets|best-selling-beauty|amora-glow|travel-care)$", "skincare"),
    (r"fb:(?:graphic-tees|lounge-tops|lounge-bottoms|other-tops|young-men-s-tops-and-tees|apparel-and-accessories)$", "clothing"),
    (r"fb:(?:slippers-and-cozy-socks|throw-blankets|throw-pillows|bedding)$", "cozy"), (r"fb:(?:decor-and-lighting|home-decor)$", "decor"),
    (r"fb:tumblers-and-bottles$", "drinkware"), (r"fb:(?:footballs|basketballs|outdoor)$", "sports-gear"),
    (r"fb:(?:toning-and-conditioning|recovery)$", "fitness"), (r"fb:smart-home$", "kids-tech"),
]
# When neither the name nor the aisle sorts a product, the store list it came from can (Barnes & Noble's aisles).
LIST_TYPES = {"bn-plush": "plush", "bn-puzzles": "puzzles", "bn-games": "board-games", "bn-tcg": "tcg", "bn-funko": "figures",
              "bn-collectibles": "figures", "bn-lego": "blocks", "fb-squishies": "squishies", "fb-plush": "plush",
              "fb-blind-bags": "blind-boxes", "fb-board-games": "board-games", "fb-headphones": "headphones"}

GAME_TYPES = {"switch-games", "ps-xbox-games", "any-console-games"}
ESRB_MIN = {"E": 1, "E10": 10, "T": 13, "M": 17, "RP-M": 17, "AO": 18}
# Series that are rated Mature, for new games whose rating is still pending.
MATURE_SERIES = re.compile(r"grand theft auto|\bgta\b|call of duty|ghost of y|mortal kombat|resident evil|the last of us|god of war", re.I)


def esrb_ages(ages: list, code: str | None, name: str) -> tuple[list, str | None]:
    """Raise a video game's youngest age to its ESRB rating. A pending rating counts as Teen, or Mature for a Mature series.
    When the rating raises the youngest age, the game suits every age above it too."""
    if not code:
        return ages, None
    if code == "RP" and MATURE_SERIES.search(name):
        code = "RP-M"
    floor = ESRB_MIN.get(code, 13)  # pending or unknown ratings: Teen
    if floor <= ages[0]:
        return list(ages), code
    return [floor, 30], code


def open_ended(lo: int, type_hi: int) -> int:
    """The oldest age for an "Ages X+" product: teen and adult products go to 30, toys about a dozen years past X."""
    return 30 if lo >= 13 else max(lo, min(type_hi, lo + 12))


def type_ages(catalog: dict) -> dict:
    spans: dict = {}
    for it in catalog["items"]:
        lo, hi = it["ages"]
        s = spans.setdefault(it["type"], [lo, hi])
        s[0], s[1] = min(s[0], lo), max(s[1], hi)
    return spans


def parse_capture(path: Path, later_files: bool = False) -> dict:
    """Read one capture file: {store, captured_at, lists: {key: {"pages": [...], "rows": [(rank, id)], "by_page": {page: [id]}}},
    products: {id: row}}."""
    store, captured_at, cur, page = None, None, None, 1
    lists: dict = {}
    products: dict = {}
    problems: list = []
    esrb: dict = {}
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#format"):
            continue
        if line.startswith("#run "):
            _, store, captured_at = line.split()[:3]
            continue
        if line.startswith("#note"):
            continue
        if line.startswith("#esrb "):  # video game ratings: "#esrb id:M id:T ..."
            for pair in line.split()[1:]:
                pid, _, code = pair.partition(":")
                if code:
                    esrb[pid] = code
            continue
        if line.startswith("#list "):
            parts = line.split()
            cur = parts[1]
            meta = dict(p.split("=", 1) for p in parts[2:] if "=" in p)
            lists.setdefault(cur, {"rows": [], "pages": [], "by_page": {}})["pages"].append(meta)
            page = int(meta["page"]) if str(meta.get("page", "")).isdigit() else 1
            continue
        if line.startswith("!") or line.startswith("#"):
            problems.append(f"{path.name}:{n}: {line[:80]}")
            continue
        if cur is None:
            raise ValueError(f"{path.name}:{n}: product line before any #list line")
        if line.startswith("~"):  # "~N": N products already captured in an earlier file; they keep their places
            if cur is None or not line[1:].strip().isdigit():
                raise ValueError(f"{path.name}:{n}: bad skip line {line!r}")
            for _ in range(int(line[1:])):
                lists[cur]["rows"].append((len(lists[cur]["rows"]) + 1, None))
                lists[cur]["by_page"].setdefault(page, []).append(None)
            continue
        if line.startswith("="):
            pid = line[1:].split()[0]
            if pid not in products and not later_files:
                raise ValueError(f"{path.name}:{n}: repeat of {pid}, which wasn't listed before")
        elif line.startswith("^"):  # an update: "^id|price|was|flags|photo" for a product an earlier file has
            f = line[1:].split("|")
            if len(f) != 5:
                raise ValueError(f"{path.name}:{n}: expected 5 fields in an update line, found {len(f)}")
            pid = f[0].strip()
            if not re.fullmatch(SKU_FORMS.get(store, r"\d+"), pid):
                raise ValueError(f"{path.name}:{n}: product id {pid!r} isn't a {store} product id")
            products[pid] = {"update": True, "price": num(f[1]), "was": num(f[2]), "flags": f[3], "img": f[4].strip() or None}
        else:
            f = line.split("|")
            if len(f) not in (9, 10):
                raise ValueError(f"{path.name}:{n}: expected 9 or 10 fields, found {len(f)}")
            img = (f[8].strip() or None) if len(f) == 10 else None
            name = f[-1]
            pid = f[0].split()[0]
            if not re.fullmatch(SKU_FORMS.get(store, r"\d+"), pid):
                raise ValueError(f"{path.name}:{n}: product id {pid!r} isn't a {store} product id")
            products[pid] = {"price": num(f[1]), "was": num(f[2]), "seller": f[3], "path": f[4], "flags": f[5],
                             "rating": num(f[6]), "reviews": int(f[7]) if f[7].isdigit() else None, "name": name.split(" ~asked=")[0]}
            if img:
                products[pid]["img"] = img
            if f[0] != pid or "~asked=" in name:
                products[pid]["note"] = "the store answered with a different product number"
        rows = lists[cur]["rows"]
        rows.append((len(rows) + 1, pid))
        lists[cur]["by_page"].setdefault(page, []).append(pid)
    if not store or not captured_at:
        raise ValueError(f"{path.name}: missing the '#run <store> <time>' line")
    for pid, code in esrb.items():
        if pid in products:
            products[pid]["esrb"] = code
    if store not in STORES:
        raise ValueError(f"{path.name}: unknown store {store!r}")
    return {"store": store, "captured_at": captured_at, "lists": lists, "products": products, "problems": problems}


def num(s: str) -> float | None:
    s = (s or "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def build(catalog: dict, captures: list[dict], now: dt.datetime | None = None,
          matches: dict | None = None) -> tuple[dict, dict, dict]:
    """Return (store_picks, observations by store, stats). matches: photo_matches.json ({"same": {gift id: "store:id"},
    "examples": {...}})."""
    now = now or dt.datetime.now(dt.timezone.utc)
    spans = type_ages(catalog)
    types = catalog["types"]
    tracked = {}  # (store, sku) -> [(item, offer)]
    for it in catalog["items"]:
        for o in it.get("offers", []):
            if o["retailer"] in STORES and o.get("sku"):
                tracked.setdefault((o["retailer"], str(o["sku"])), []).append((it, o))
    picks, lists_out, obs_by_store = [], {}, {}
    photos: dict = {}  # catalog gift id -> [store, photo id]: product photos for the hand-picked gifts
    stats = {"products": 0, "kept": 0, "dropped": 0, "unsorted": [], "marketplace_dropped": 0, "observations": 0, "old_captures": 0}
    # Several capture files can hold pages of the same list (a later visit reads more pages, or reads a page again).
    # Combine them page by page, the newest reading of each page and of each product winning.
    fresh = []
    for cap in captures:
        when = dt.datetime.fromisoformat(cap["captured_at"].replace("Z", "+00:00"))
        if (now - when).days > MAX_AGE_DAYS:
            stats["old_captures"] += 1
        else:
            fresh.append(cap)
    pages: dict = {}     # (store, list) -> {page: (captured_at, [product ids])}
    products: dict = {}  # (store, product id) -> (captured_at, row)
    # An update line ("^id|price|was|flags|photo") keeps the name, aisle, seller and reviews of the newest full reading of
    # the product, even one from a capture too old to list (names don't go stale the way prices do).
    bases: dict = {}
    for cap in sorted(captures, key=lambda c: c["captured_at"]):
        for pid, p in cap["products"].items():
            if not p.get("update"):
                bases[(cap["store"], pid)] = p
    for cap in sorted(fresh, key=lambda c: c["captured_at"]):
        for key, lst in cap["lists"].items():
            if key not in LISTS:
                raise ValueError(f"unknown list {key!r}; add it to LISTS in store_picks.py")
            for page, pids in (lst.get("by_page") or {1: [pid for _, pid in lst["rows"]]}).items():
                pages.setdefault((cap["store"], key), {})[page] = (cap["captured_at"], pids)
        for pid, p in cap["products"].items():
            if p.get("update"):
                base = (products.get((cap["store"], pid)) or (None, None))[1] or bases.get((cap["store"], pid))
                if not base:
                    stats["no_base"] = stats.get("no_base", 0) + 1
                    continue
                p = dict(base, price=p["price"], was=p["was"], flags=p["flags"], img=p["img"] or base.get("img"))
                p.pop("update", None)
            else:  # a full reading keeps the photo, rating and aisle an earlier reading found when it has none
                old = (products.get((cap["store"], pid)) or (None, None))[1] or bases.get((cap["store"], pid)) or {}
                fill = {k: old[k] for k in ("img", "rating", "reviews", "path", "esrb") if not p.get(k) and old.get(k)}
                if fill:
                    p = dict(p, **fill)
            products[(cap["store"], pid)] = (cap["captured_at"], p)
    member: dict = {}  # (store, product id) -> {list: rank}
    for (store, key), by_page in pages.items():
        name, short, url, kind, ages = LISTS[key]
        rank = 0
        for page in sorted(by_page):
            for pid in by_page[page][1]:
                rank += 1
                if pid is None:  # a "~N" skip: a product another capture file already has
                    continue
                if (store, pid) not in products:  # a repeat of a product only an expired capture had
                    stats["missing"] = stats.get("missing", 0) + 1
                    continue
                member.setdefault((store, pid), {}).setdefault(key, rank)
        if kind != "tracked":
            lists_out[key] = {k: v for k, v in {"store": store, "name": name, "short": short, "url": url, "kind": kind,
                                                "ages": list(ages) if ages else None, "count": rank,
                                                "captured_at": max(v[0] for v in by_page.values())}.items() if v is not None}
    for (store, pid), (captured_at, p) in products.items():
        obs = obs_by_store.setdefault(store, [])
        stats["products"] += 1
        raw = fix_name(p["name"])  # the full captured name: classify on this, show the tidied one
        name = clean_name(p["name"])
        in_lists = {k: r for k, r in member.get((store, pid), {}).items() if LISTS[k][3] != "tracked"}
        for it, off in tracked.get((store, pid), []):
            obs.append(observation(it, off, p, captured_at, STORES[store]))
            stats["observations"] += 1
            photo = photo_id(store, pid, p.get("img"))
            if photo:
                photos.setdefault(it["id"], [store, photo])
        if not in_lists:
            continue
        gift_items = [it for it, _ in tracked.get((store, pid), [])]
        hint = age_hint(raw, in_lists)
        t = gift_items[0]["type"] if gift_items else classify(raw, p["path"], hint)
        if t == "drop":
            stats["dropped"] += 1
            continue
        if t is None:
            t = next((LIST_TYPES[k] for k in in_lists if k in LIST_TYPES), None)
        if t is None and set(in_lists) & BOOK_LISTS and not re.search(r"\b(?:puzzle|game|kit|deck|plush)\b", raw, re.I):
            t = book_type(raw, hint)
        if t is None:
            stats["unsorted"].append(name)
            continue
        curated = any(LISTS[k][3] == "hot" for k in in_lists)
        if p["seller"] == "M" and (p["reviews"] or 0) < 25 and not curated:
            stats["marketplace_dropped"] += 1
            continue
        if not p["price"] and not p["was"]:
            stats["dropped"] += 1
            continue
        lo_hi, ages_from = age_range(raw, in_lists, t, spans)
        if gift_items:  # a gift the catalog already describes: use its curated ages
            lo_hi, ages_from = list(gift_items[0]["ages"]), "catalog"
        rating = None
        if t in GAME_TYPES:
            if p.get("esrb") == "AO":
                stats["dropped"] += 1
                continue
            lo_hi, rating = esrb_ages(lo_hi, p.get("esrb"), raw)
        gift = gift_items[0]["id"] if gift_items else None
        was = p["was"] if p["was"] and p["price"] and p["was"] > p["price"] else None
        flags = [FLAGS[c] for c in p["flags"] if c in FLAGS]
        if was and not set(flags) & {"deal", "rollback", "reduced", "clearance"}:
            flags.append("reduced")
        pick = {"id": f"{store}-{pid}", "store": store, "sku": pid, "name": name, "url": STORES[store]["url"](pid),
                "img": photo_id(store, pid, p.get("img")),
                "price": p["price"], "was": was, "pct": int((was - p["price"]) / was * 100 + 0.5) if was else None,  # half up, like the site
                "seller": "store" if p["seller"] == "W" else "marketplace", "rating": p["rating"], "reviews": p["reviews"],
                "flags": flags, "lists": sorted(in_lists, key=lambda k: list(LISTS).index(k)), "rank": in_lists,
                "type": t, "category": types[t]["category"], "ages": lo_hi, "ages_from": ages_from, "esrb": rating, "gift": gift,
                "checked_at": captured_at}
        picks.append({k: v for k, v in pick.items() if v not in (None, [], {})})
        if gift and pick["img"]:
            photos.setdefault(gift, [store, pick["img"]])
        stats["kept"] += 1
    # Hand-picked gifts a store sells by EAN (Barnes & Noble) get that store's photo even when no list had them.
    for (store, sku), pairs in tracked.items():
        if store == "barnesnoble":
            for it, _ in pairs:
                if photo_id(store, sku, None):
                    photos.setdefault(it["id"], [store, photo_id(store, sku, None)])
    # Hand-checked matches: "same" (the same product; it wins over a tracked link's photo) and "examples" (one version
    # of a gift idea that comes in many; the site labels the photo "Example").
    gift_ids = {it["id"] for it in catalog["items"]}
    stats["match_problems"] = []
    for kind in ("same", "examples"):
        for gid, ref in sorted(((matches or {}).get(kind) or {}).items()):
            store, _, pid = ref.partition(":")
            if gid not in gift_ids or store not in STORES:
                stats["match_problems"].append(f"{gid} ({ref}): no such catalog gift or store")
                continue
            p = (products.get((store, pid)) or (None, None))[1] or bases.get((store, pid)) or {}
            photo = photo_id(store, pid, p.get("img"))
            if not photo:
                stats["match_problems"].append(f"{gid} ({ref}): no capture has a photo of that product")
                continue
            if kind == "same":
                photos[gid] = [store, photo]
            else:
                photos.setdefault(gid, [store, photo, "example"])
    picks.sort(key=lambda x: (min(x["rank"].values()), x["name"]))
    stats["photos"] = sum(1 for x in picks if x.get("img"))
    newest = max((c["captured_at"] for c in fresh), default=None)
    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "captured_at": newest,
           "stores": {s: {k: v for k, v in {"name": STORES[s]["name"], "img": STORES[s].get("img")}.items() if v}
                      for s in sorted({c["store"] for c in fresh}, key=lambda s: (-sum(x["store"] == s for x in picks), s))},
           "lists": lists_out, "items": picks, "photos": dict(sorted(photos.items()))}
    return out, obs_by_store, stats


def age_hint(name: str, in_lists: dict) -> list | None:
    """Ages from the name or the store's lists, before the product type is known (used to sort books)."""
    named = ages_from_name(name)
    if named:
        return [named[0], named[1] or 30]
    groups = [LISTS[k][4] for k in in_lists if LISTS[k][4]]
    if groups:
        return [min(g[0] for g in groups), max(g[1] for g in groups)]
    words = ages_from_words(name)
    return list(words) if words else None


def age_range(name: str, in_lists: dict, t: str, spans: dict) -> tuple[list, str]:
    """Best guess at who a product is for, strongest evidence first: ages printed in the name, the store's age-group
    lists, words in the name (Women's, Toddler), the store's kids' lists, then the usual ages for the product type."""
    tlo, thi = spans.get(t, (1, 30))
    named = ages_from_name(name)
    if named:
        lo, hi = named
        return [lo, hi if hi is not None else open_ended(lo, thi)], "name"
    groups = [LISTS[k][4] for k in in_lists if LISTS[k][3] == "age" and LISTS[k][4]]
    if groups:
        return [min(g[0] for g in groups), max(g[1] for g in groups)], "list"
    words = ages_from_words(name)
    if words:
        return list(words), "name"
    hinted = [LISTS[k][4] for k in in_lists if LISTS[k][4]]
    if hinted:
        lo, hi = min(g[0] for g in hinted), max(g[1] for g in hinted)
        lo2, hi2 = max(lo, tlo), min(hi, thi)
        return ([lo2, hi2] if lo2 <= hi2 else [lo, hi]), "list"
    return [tlo, thi], "type"


def observation(it: dict, off: dict, p: dict, checked_at: str, store: dict) -> dict:
    rec = {"item_id": it["id"], "retailer": off["retailer"], "url": off["url"], "sku": off.get("sku"), "checked_at": checked_at,
           "source": f"{store['site']}, read in a browser", "verification_method": "browser"}
    if not p["price"]:
        rec.update(ok=False, reason="parse", error=f"{store['name']} didn't show a price (it may need a size or color picked first)")
        return rec
    rec.update(ok=True, price=p["price"], in_stock="O" not in p["flags"], name=clean_name(p["name"]))
    if p["was"] and p["was"] > p["price"]:
        rec["regular"] = p["was"]
        rec["on_sale"] = True
    if p["seller"] != "W":
        rec["marketplace_only"] = True
        rec["seller"] = "a marketplace seller"
    if p["rating"]:
        rec["rating"] = p["rating"]
    if p["reviews"]:
        rec["reviews"] = p["reviews"]
    sys.path.insert(0, str(ROOT / "scraper"))
    from scrape import check_sane  # noqa: E402  (same sanity rule as the price checker)
    check_sane(rec, it)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="print what would be imported, write nothing")
    ap.add_argument("--unsorted", action="store_true", help="list products that no product-type rule matched")
    args = ap.parse_args()
    catalog = json.loads(CATALOG.read_text())
    files = sorted(p for p in CAPTURES.glob("*.txt"))
    if not files:
        print("No capture files in scraper/captures/. See 'Reading Walmart in your browser' in the README.")
        return 1
    captures = [parse_capture(p, later_files=True) for p in files]
    matches = json.loads(MATCHES.read_text()) if MATCHES.exists() else None
    out, obs_by_store, stats = build(catalog, captures, matches=matches)
    for c in captures:
        for p in c["problems"]:
            print("note:", p)
    print(f"{stats['products']} products read; {stats['kept']} store picks kept, {stats['dropped']} not gifts this site covers, "
          f"{stats['marketplace_dropped']} marketplace listings with few reviews left out, {len(stats['unsorted'])} with no product type.")
    print(f"{stats['observations']} prices for gifts the catalog links to. {stats.get('photos', 0)} store picks have a product photo, "
          f"plus {len(out['photos'])} hand-picked gifts.")
    for problem in stats["match_problems"]:
        print("photo match:", problem)
    if stats.get("no_base"):
        print(f"{stats['no_base']} update lines skipped: no earlier reading of the product to update.")
    if stats["old_captures"]:
        print(f"{stats['old_captures']} capture file(s) older than {MAX_AGE_DAYS} days were skipped.")
    if args.unsorted:
        print("\n".join(sorted(stats["unsorted"])))
    if args.check:
        return 0
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out['items'])} store picks from {len(out['lists'])} lists")
    for store, obs in obs_by_store.items():
        if not obs:
            continue
        path = CAPTURES / f"{store}-observations.json"
        when = max(o["checked_at"] for o in obs)
        path.write_text(json.dumps({"checked_at": when, "observations": obs,
                                    "note": f"{STORES[store]['name']} prices read in a browser on "
                                            f"{when[:10]} (scraper/captures/{store}.txt)."}, indent=1) + "\n")
        print(f"wrote {path.relative_to(ROOT)}: {sum(1 for o in obs if o.get('ok'))} of {len(obs)} tracked links read")
    if obs_by_store:  # the offline rebuild merges the observation files into gifts.json
        return subprocess.run([sys.executable, "-B", str(ROOT / "scraper" / "scrape.py"), "--offline"]).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
