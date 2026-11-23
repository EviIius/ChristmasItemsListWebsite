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
  =id          (the same product again, on another list)
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
MAX_AGE_DAYS = 10  # captures older than this are left out of store-picks.json (deals end)

STORES = {
    "walmart": {
        "name": "Walmart",
        "url": lambda sku: f"https://www.walmart.com/ip/{sku}",
        "own_seller": "Walmart.com",
    },
}

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
    "wm-tracked": ("Gifts this site tracks at Walmart", None, None, "tracked", None),
}

FLAGS = {"B": "best-seller", "H": "deal", "R": "rollback", "P": "reduced", "C": "clearance", "L": "low-stock",
         "E": "event", "O": "sold-out"}

# Walmart's data drops some accented letters; put the common ones back.
NAME_FIXES = {"Pokmon": "Pokémon", "Ragnark": "Ragnarök", "Mbapp ": "Mbappé ", "Smarwatch": "Smartwatch"}

# Not gifts this site covers: groceries, big appliances, TVs, phones on carrier plans, tools, holiday decorations,
# bedding, furniture and baby gear. Checked before the product-type rules.
DROP_TERMS = [
    r"christmas tree", r"xmas tree", r"artificial .*tree", r"freezer", r"refrigerator", r"mini fridge", r"range oven",
    r"wall oven", r"gas range", r"vacuum cleaner", r"upright vacuum", r"deep cleaner", r"cake mix", r"biscuit mix",
    r"olive oil", r"cooking oil", r"waffles", r"gummy", r"ring pop", r"lollipop", r"candy filled", r"chocolate kisses",
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
]
DROP = re.compile(r"\b(?:" + "|".join(DROP_TERMS) + r")", re.I)

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
    ("consoles", r"switch 2 system|switch 2 \+|switch 2 bundle|mario kart world bundle|playstation 5 console|xbox series [xs] console|game system"),
    ("controllers", r"controller|dualsense"),
    ("vr", r"meta quest|vr headset|virtual reality"),
    ("switch-games", r"nintendo switch"),
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
    if DROP.search(name):
        return "drop"
    for t, rx in RULES:
        if rx.search(name):
            return t
    if path.split(":")[0] in BOOK_PATHS or re.search(r"\((?:hardcover|paperback|board book)\)", name, re.I):
        lo = (ages or [18])[0]
        return "picture-books" if lo <= 5 else "kids-books" if lo <= 12 else "ya-books" if lo <= 17 else "adult-books"
    return None


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


def parse_capture(path: Path) -> dict:
    """Read one capture file: {store, captured_at, lists: {key: {"pages": [...], "rows": [(rank, id)]}}, products: {id: row}}."""
    store, captured_at, cur = None, None, None
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
            lists.setdefault(cur, {"rows": [], "pages": []})["pages"].append(meta)
            continue
        if line.startswith("!") or line.startswith("#"):
            problems.append(f"{path.name}:{n}: {line[:80]}")
            continue
        if cur is None:
            raise ValueError(f"{path.name}:{n}: product line before any #list line")
        if line.startswith("="):
            pid = line[1:].split()[0]
            if pid not in products:
                raise ValueError(f"{path.name}:{n}: repeat of {pid}, which wasn't listed before")
        else:
            f = line.split("|")
            if len(f) != 9:
                raise ValueError(f"{path.name}:{n}: expected 9 fields, found {len(f)}")
            pid = f[0].split()[0]
            if not pid.isdigit():
                raise ValueError(f"{path.name}:{n}: product id {pid!r} isn't a number")
            products[pid] = {"price": num(f[1]), "was": num(f[2]), "seller": f[3], "path": f[4], "flags": f[5],
                             "rating": num(f[6]), "reviews": int(f[7]) if f[7].isdigit() else None, "name": f[8].split(" ~asked=")[0]}
            if f[0] != pid or "~asked=" in f[8]:
                products[pid]["note"] = "the store answered with a different product number"
        rows = lists[cur]["rows"]
        rows.append((len(rows) + 1, pid))
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


def build(catalog: dict, captures: list[dict], now: dt.datetime | None = None) -> tuple[dict, dict, dict]:
    """Return (store_picks, observations by store, stats)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    spans = type_ages(catalog)
    types = catalog["types"]
    tracked = {}  # (store, sku) -> [(item, offer)]
    for it in catalog["items"]:
        for o in it.get("offers", []):
            if o["retailer"] in STORES and o.get("sku"):
                tracked.setdefault((o["retailer"], str(o["sku"])), []).append((it, o))
    picks, lists_out, obs_by_store = [], {}, {}
    stats = {"products": 0, "kept": 0, "dropped": 0, "unsorted": [], "marketplace_dropped": 0, "observations": 0, "old_captures": 0}
    for cap in captures:
        store = cap["store"]
        when = dt.datetime.fromisoformat(cap["captured_at"].replace("Z", "+00:00"))
        if (now - when).days > MAX_AGE_DAYS:
            stats["old_captures"] += 1
            continue
        member: dict = {}
        for key, lst in cap["lists"].items():
            if key not in LISTS:
                raise ValueError(f"unknown list {key!r}; add it to LISTS in store_picks.py")
            name, short, url, kind, ages = LISTS[key]
            if kind != "tracked":
                lists_out[key] = {k: v for k, v in {"store": store, "name": name, "short": short, "url": url, "kind": kind,
                                                    "ages": list(ages) if ages else None, "count": len(lst["rows"]),
                                                    "captured_at": cap["captured_at"]}.items() if v is not None}
            for rank, pid in lst["rows"]:
                member.setdefault(pid, {})
                member[pid].setdefault(key, rank)
        obs = []
        for pid, p in cap["products"].items():
            stats["products"] += 1
            raw = fix_name(p["name"])  # the full captured name: classify on this, show the tidied one
            name = clean_name(p["name"])
            in_lists = {k: r for k, r in member.get(pid, {}).items() if LISTS[k][3] != "tracked"}
            for it, off in tracked.get((store, pid), []):
                obs.append(observation(it, off, p, cap["captured_at"], STORES[store]))
            if not in_lists:
                continue
            gift_items = [it for it, _ in tracked.get((store, pid), [])]
            hint = age_hint(raw, in_lists)
            t = gift_items[0]["type"] if gift_items else classify(raw, p["path"], hint)
            if t == "drop":
                stats["dropped"] += 1
                continue
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
                    "price": p["price"], "was": was, "pct": round((was - p["price"]) / was * 100) if was else None,
                    "seller": "store" if p["seller"] == "W" else "marketplace", "rating": p["rating"], "reviews": p["reviews"],
                    "flags": flags, "lists": sorted(in_lists, key=lambda k: list(LISTS).index(k)), "rank": in_lists,
                    "type": t, "category": types[t]["category"], "ages": lo_hi, "ages_from": ages_from, "esrb": rating, "gift": gift,
                    "checked_at": cap["captured_at"]}
            picks.append({k: v for k, v in pick.items() if v not in (None, [], {})})
            stats["kept"] += 1
        obs_by_store.setdefault(store, []).extend(obs)
        stats["observations"] += len(obs)
    picks.sort(key=lambda x: (min(x["rank"].values()), x["name"]))
    newest = max((c["captured_at"] for c in captures), default=None)
    out = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "captured_at": newest,
           "stores": {s: {"name": STORES[s]["name"]} for s in {c["store"] for c in captures}},
           "lists": lists_out, "items": picks}
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
           "source": f"{store['name']}.com, read in a browser", "verification_method": "browser"}
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
    captures = [parse_capture(p) for p in files]
    out, obs_by_store, stats = build(catalog, captures)
    for c in captures:
        for p in c["problems"]:
            print("note:", p)
    print(f"{stats['products']} products read; {stats['kept']} store picks kept, {stats['dropped']} not gifts this site covers, "
          f"{stats['marketplace_dropped']} marketplace listings with few reviews left out, {len(stats['unsorted'])} with no product type.")
    print(f"{stats['observations']} prices for gifts the catalog links to.")
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
