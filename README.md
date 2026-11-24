# Christmas Gift Finder

A small website for Christmas shopping: gift ideas for ages 1 to 30, a Christmas list for each person you're buying for, and every big store's search one click away. It has 361 gift ideas in 80 product types (LEGO sets, Switch 2 games, squishies, stuffed animals, PlayStation, earbuds, beauty and more), 266 of them picked from this year's store top-toys lists, toy experts' lists and gift guides, and links to 28 stores, from Target, Walmart, Amazon and Best Buy to GameStop, LEGO.com, Pokémon Center, Five Below, Build-A-Bear, Sephora and Nike. On top of that come 2,350 of the stores' own best sellers, gift lists and holiday deals (1,199 from Walmart, 413 from Five Below, 319 from Barnes & Noble, 265 from GameStop, 154 from LEGO.com), read from their lists in a browser and sorted into the same product types and age groups. They count as gift ideas too: Find, Browse by type and the lists show all 2,672 (the same product at two stores is one idea), with the hand-picked gifts ranked first.

**Live site:** https://eviiius.github.io/ChristmasItemsListWebsite/

| Page | What it does |
| --- | --- |
| Find gifts | Set an age (1–30), a budget and interests to get ranked gift ideas, quick buttons (Under $25, On sale, Hot this year, Store best sellers) and an age guide with safety notes. Choose someone from your lists to use their age, interests and budget. |
| Lists | One Christmas list per person: name, age, color, budget and interests. Add gifts from anywhere on the site (they get circled in that person's color) or add your own with a link. Mark each gift Idea, Bought or Wrapped, note what you paid and watch the budget bar. The shopping trip view groups everything by store. Share, copy as text, print, back up. Starred gifts go to a shortlist. |
| Browse & search | The search box's results, and every gift sorted into 80 product types in 20 groups. Pick a type (Squishies & fidgets, LEGO sets, Switch 2 games…) or a whole group, then narrow by hot list, interest, age, price and store. A sortable table, or cards on phones. |
| Deals & dates | Countdown to Black Friday, Cyber Monday, Green Monday and Christmas Eve; Walmart's best sellers and deals, filtered by age group, product type, price, sale or best seller, and addable to anyone's list; gifts selling at least 8% under their usual price; the big-ticket gifts; the hot lists this year's picks come from; and the status of every tracked store link, grouped by store. |
| Shop every store | Type a search once and open it at any of the 28 stores, plus a directory of what each store is good for. |

Lists and settings are saved in each visitor's own browser. There are no accounts and no AI features, and nothing is sent anywhere.

## Searching and browsing

- **The search box at the top of every page** understands plain requests: "LEGO for an 8 year old under $50", "squishies under $10 at Five Below", "gift card for my boss", "books for a 3 year old", "switch games on sale", "stocking stuffers for a toddler". It picks out the age (numbers, "toddler", "teen", "my boss"), the price ("under $50", "$20-40", "cheap"), a store ("at Walmart"), "on sale" and "popular", and looks for the remaining words at the start of words in each gift's name, brand and type (descriptions and interests count only for a word none of those contain), with plurals, other words for the same thing (plushie → plush, PS5 → PlayStation) and the nearest spelling when a word matches nothing ("squishmellow" → squishmallow). The chips under the filters show what it understood; ✕ removes one. Results rank name matches first, then how well each gift fits the age and price. A search is a link (`#browse?q=...`), so it can be shared. Press `/` to jump to the box. It runs in the browser with no AI service.
- **Long lists load as you scroll**: Find shows 24 ideas, Browse 60 rows and Deals 24 best sellers, and the next batch is added as you near the end ("Show all" loads the rest at once). "Back to top" appears on long pages.
- **Browse's filters**: Type, Into, Age, Price, Store, Sort (best match, price, age, name), On sale and Hot this year. "Into" uses each gift's interests; for the stores' best sellers those come from the product name (a console only when the name says PlayStation, PS5, Xbox, Nintendo or Switch), so Xbox games don't show up under PlayStation.
- **Find** has quick buttons above the ideas: Everything, Under $25, On sale, Hot this year and Store best sellers, each with its count.
- **On phones** the sections are a tab bar at the bottom of the screen, and Browse's filters fold behind a Filters button.

## One-time setup

1. **Push this folder** to `main` on GitHub (GitHub Desktop: **Commit to main**, then **Push origin**). If GitHub Desktop says there are new commits on GitHub first (the price checker commits prices), click **Pull origin**, then push.
2. **Turn on Pages:** repo **Settings → Pages → Build and deployment → Source: GitHub Actions**. On a free account the repo has to be public for Pages to work.
   If the first workflow run failed at "configure-pages" because Pages wasn't on yet, open the run and press **Re-run all jobs**.
3. Wait a minute or two. The **Actions** tab shows "Check prices and publish site". When it's green, the site is live at the address above.
4. **First price check:** Actions → "Check prices and publish site" → **Run workflow**. Pushes only rebuild the site. Store prices come from the twice-daily run, this button or the site's Refresh prices button.

### The site's Refresh prices button

The button starts the same workflow through the GitHub API, so it needs a key:

1. GitHub → Settings → Developer settings → [Fine-grained tokens](https://github.com/settings/personal-access-tokens/new) → Generate new token.
2. Repository access: **only `EviIius/ChristmasItemsListWebsite`**. Permissions: **Actions: Read and write**, nothing else. Pick a short expiry.
3. Paste it into the site's Refresh prices dialog. It's stored in that browser's local storage only and never goes into the repo. Use **Forget saved key** on shared computers.

Without a key, the dialog still shows when prices were last checked, and the repo owner can always use **Run workflow** on GitHub.

## How prices work

- **Typical prices first.** Every gift has a typical price (its usual list price, in the catalog) and, for many, the usual range. The site shows the typical price until a store price has been read, and says which kind of price it is. 74 of the newer gifts have an *estimated* price instead (`price_est` in the catalog); the site labels those "Estimated price… Check the store."
- **Store prices.** Gifts with exact product pages (`offers` in the catalog) get the store's own price. 199 product links are tracked: Amazon 101, Target 41, Walmart 34, Best Buy 17, tonies 2, GameStop 2, LEGO 1 and PlayStation Direct 1. Walmart's are read in a browser on your computer (see "Walmart best sellers and deals" below). The others are read by the price checker on GitHub twice a day (11:43 and 23:43 UTC, about 6:45 AM and 6:45 PM Eastern), committed and republished; Amazon and Target links open the product but aren't price-checked (see the table below). Add more links with `add_link.py` or `hotlists.py` (below). To change the times, edit the `cron` line in `.github/workflows/scrape.yml` and the `schedule` text in `site/assets/config.js` to match.
- **What's read:** the schema.org Product data stores publish for search engines (Best Buy, LEGO, GameStop, Pokémon Center, Shopify shops like tonies and Five Below), Walmart's page data and Amazon's price block. With a `BESTBUY_API_KEY` secret, Best Buy prices come from Best Buy's official Products API instead.
- **Only the store's own price counts.** Marketplace sellers are ignored. A price under a quarter or over four times the typical price is treated as a misread and dropped.
- **Deals** need a store price checked in the last 72 hours that's at least 8% under the typical price.
- **Politeness:** one request at a time, 3–6 seconds apart per store, robots.txt respected, an honest user agent (`ChristmasGiftFinder`), and a store is skipped for the rest of the run after 3 failures in a row.
- **When a page can't be read,** the last known price stays up, labeled with when it was checked. Price history keeps one point per day (that day's low) for 120 days.

### Which stores can be read

What each store gave the price checker on GitHub's servers (the November 21 probe and the November 22 run) and what it gave Claude browsing for you in the Claude app's browser on your Mac (November 22):

| Store | From GitHub | From a browser on your Mac | Result |
| --- | --- | --- | --- |
| Walmart | A bot check (PerimeterX) | Lists, best sellers, deals and product pages, no bot check; no rule against AI assistants in its robots.txt | **Read in a browser:** 1,199 best sellers and deals (pages 1–4 of every age group, trending toys, stocking stuffers, toy, video game, electronics and sports deals), and prices for its 34 links |
| GameStop | The product page (prices for the catalog's links) | Best Sellers, Black Friday deals, top-selling toys and collectibles; its product grid is drawn in the browser, so only a browser sees it. No rule against AI assistants in its robots.txt | Prices read on GitHub; **265 best sellers and deals read in a browser** |
| PlayStation Direct, tonies | The product page | Not needed | Prices read on GitHub |
| Target | A product page with no price in it | Its robots.txt has no rule against AI assistants, but its bot defense refuses the prices and product lists (HTTP 435), and on Nov 23 the Top Toys page said "This page is currently unavailable" | **Link only.** Target links open the right product |
| Amazon | Pages without the product on them | An "Access restricted" page saying continued access by an unauthorized AI agent breaks Amazon's Conditions of Use | **Link only.** Amazon links open the right product |
| Best Buy | No answer at all | Since about Nov 23 its robots.txt allows `Claude-User` (the name Claude uses when it browses for someone) on `/site/` pages. Claude's own safety check stopped the first attempt to read its lists, so they aren't read yet | Not read. The Best Buy API key or a self-hosted runner (below) are the other ways in |
| LEGO.com | A Cloudflare challenge | Best Sellers, New sets and Sales & deals pages, no challenge; no rule against AI assistants in its robots.txt | **154 sets read in a browser** |
| Kohl's | Not tried | Pages load, but its bot defense refused a scripted product request (HTTP 403) on Nov 23 | Not read |
| Five Below | Not tried for lists | Top Toy Gifts, its best sellers (toys, tech, beauty), the gift finder (kids, her, him, under $5), stocking stuffers, gift guides and new arrivals. Its robots.txt has no rule against AI assistants but disallows `/frontastic`, where the "Load more" button gets the next pages, so only each list's first page (24 products) is read | **413 read in a browser** from 29 lists (Nov 24) |
| Barnes & Noble | Not tried | Best Toys & Games of 2026, toys by age (0–2 up to teens), building toys, plush, collectibles, Funko, games, puzzles, advent calendars, gifts and bestselling books (kids' books by age, teen, manga, boxed sets). No rule against AI assistants in its robots.txt (a standard Shopify one); only first pages, since `?page=2` isn't supported | **319 read in a browser** from 24 lists (Nov 24) |

**What the checker won't do:** solve CAPTCHAs, disguise itself as a person's browser, rotate through proxy addresses, or call a store's private price service with borrowed keys. Those are the ways botnets get around bot checks. They break the stores' terms and turn into an arms race, and they get your address blocked. The browser reading follows the same rules: it doesn't click past Amazon's "access restricted" page, ignore Best Buy's robots.txt, or switch to another browser to slip past Target's bot defense. A bot-check page is detected and reported, and that store is skipped. The site falls back to the last known price or the typical price and says so.

What to do instead:

1. **See which stores answer:** Actions → Run workflow → tick **probe**. It reads one page per store and writes `scraper/probe-results.json`. To test your own connection instead, run `python3 scraper/scrape.py --probe` on your computer.
2. **Run the price check from home (for LEGO and Best Buy):** stores block cloud servers far more often than home connections, and the price checker identifies itself as `ChristmasGiftFinder`, which Best Buy's robots.txt allows. Settings → Actions → Runners → **New self-hosted runner**, run the commands it shows on a computer that's on at check times, then `./svc.sh install && ./svc.sh start` so it survives restarts. A runner belongs to one repository, so if Victor's site already has one, set this one up in its own folder (for example `~/actions-runner-christmas`). Then add a repository variable (Settings → Secrets and variables → Actions → **Variables**) named `SCRAPER_RUNNER` with the value `self-hosted`. Only the price check moves to your computer; building and publishing stay on GitHub. Since the repo is public, also set Settings → Actions → General → fork pull request approval to **Require approval for all external contributors**, so strangers' pull requests can't run code on your machine. Run **probe** afterwards to see what your connection gets.
3. **Best Buy API key:** sign up at [developer.bestbuy.com](https://developer.bestbuy.com/) (Best Buy asks for a work email, not a personal one) and add the key as a repo secret named `BESTBUY_API_KEY`. Best Buy prices then come from Best Buy's own API, which is meant for this.
4. **Run it by hand:** `python3 scraper/scrape.py`, then commit and push `site/data/gifts.json`.

## Store best sellers and deals (Walmart, GameStop, LEGO.com, Five Below, Barnes & Noble)

The stores publish their own hot lists, and their pages carry clean product data, so a browser on a home computer can read them. The Deals page shows them (filter by age group, product type, price, "on sale" or "best seller"), the Find page shows the stores' best sellers for the chosen age, and Browse by type links to the picks in the chosen type. Anything can go on a person's list. The November 22 and 23 readings cover:

- **Hot lists:** Walmart's Top 100 Gifts, Top Toys, Trending Toys and best-selling stocking stuffers
- **Best sellers for each age group:** baby, toddlers, little kids, big kids, teens, her and him
- **Deals:** Walmart's toy, video game, electronics and sports deal pages, sorted by best sellers
- **GameStop:** its Best Sellers and Black Friday deals (new items only; each game's ESRB rating comes from its product page)
- **LEGO.com:** its Best Sellers, with LEGO's age rating for each set
- **Five Below:** the first 24 products of 29 of its lists and gift guides, read from the page's own search results (`InstantSearchInitialResults`); its aisle sorts products the name doesn't, and candy aisles are left out
- **Barnes & Noble:** the first page of 24 collections, read from the page's data as the site's own links open them; book formats (hardcover, paperback, board book) and the age lists sort books into picture, kids', teen and adult books and manga
- **Prices** for the 34 Walmart links in the catalog, which feed the gifts' prices and the "Below the usual price" deals

Each product keeps Walmart's badges (Best seller, Deal, Rollback, Reduced price, Clearance, Low stock), its rating and its place on each list. Sponsored placements are skipped. Marketplace sellers are labeled, and only Walmart's own price counts for the catalog's gifts. Things this site doesn't cover are left out: groceries, TVs, big appliances, tools, phones on carrier plans, decorations, bedding, and open-box or refurbished items. `scraper/store_picks.py` sorts each product into the site's product types and works out who it's for, in this order: ages printed in the name ("Ages 9+"), the Walmart age-group list it's on, words like "Toddler" or "Women's", then the usual ages for its product type. Gifts the catalog already has keep the catalog's ages. Video games carry Walmart's ESRB rating: Mature games show for 17 and up, Teen games for 13 and up, and a game whose rating is still pending counts as Teen, or Mature if it's in a Mature series like Grand Theft Auto or Call of Duty.

The site says when the reading happened. After three days it warns that some deals have likely ended, and captures more than 10 days old are left out the next time the import runs.

### Refreshing it

Deals change daily this week, so refresh before Black Friday and again before Cyber Monday:

1. **Ask Claude** in the Claude desktop app on your Mac: "Refresh the store best sellers and deals for the Christmas site." It reads the pages in its built-in browser, one at a time, and writes capture files in `scraper/captures/` (one or more per store, such as `walmart.txt`, `walmart-2026-11-23.txt`, `gamestop.txt`, `lego.txt`). When two files have the same page of a list, the newer reading counts, so a later visit can add pages without reading everything again. Or **do it by hand** in Chrome or Safari: the steps are at the top of `scraper/browser/walmart-capture.js`.
2. Run `python3 scraper/store_picks.py`. It writes `site/data/store-picks.json` and `scraper/captures/<store>-observations.json` (prices for the gifts the catalog links to), and rebuilds `gifts.json` with those prices.
3. Commit and push. The rebuild after the push merges the new Walmart prices on GitHub too, so it doesn't matter if `gifts.json` changed there in the meantime.

If Walmart ever shows a "press and hold" check or a captcha, the reading stops there; it never tries to get past one. `python3 scraper/store_picks.py --unsorted` lists products no product-type rule matched, so the rules in `store_picks.py` can be improved.

## Hot lists

Gifts on this year's lists name them in `lists`, and each gift's details link to the lists it's on. The sources are in `hot_lists` at the top of the catalog:

- **Store lists** (`retailer`): Target's Bullseye's Top Toys, Amazon's Top 100+ Toys, Walmart's Top Toys, Macy's Top Toys
- **Expert lists** (`expert`): The Toy Insider's Hot 20, STEM 10, 12 Under $20 and holiday gift guide; TODAY's Best Toy Awards
- **Trend reports** (`trend`): Good Morning America's top trending toys
- **Gift guides** (`guide`): NBC Select and Reviewed guides for teens, tech lovers, women and men

Store, expert and trend lists give a gift the "Hot this year" seal automatically. Gift guides are cited, but don't add the seal on their own, since they're an editor's picks rather than what's selling. On Browse by type, the **Hot list** filter shows one list at a time.

### Finding more hot gifts with `hotlists.py`

Top-toys lists and gift guides link every pick to its product page. `hotlists.py` reads a list, finds every store product link (it decodes affiliate redirects like goto.target.com and go.skimresources.com back to the real page) and matches each one to a gift in the catalog:

```bash
python3 scraper/hotlists.py "https://www.aboutamazon.com/news/retail/best-gifts-kids-amazon-toys-we-love-list-2026"
python3 scraper/hotlists.py URL --new-only          # only links the catalog doesn't track yet
python3 scraper/hotlists.py --file ~/Downloads/top-toys.html
```

It prints an `add_link.py` command for each link; copy the ones you want. Nothing is added on its own. If a page won't load from a script, save it from your browser (Chrome: File → Save Page As → **Webpage, Complete**) and pass the file with `--file`.

## Adding gifts and store links

Everything lives in `site/data/catalog.json`. To start tracking a store price, find the gift's id, then add the product page:

```bash
python3 scraper/add_link.py --find squish
python3 scraper/add_link.py squishmallows-12 "https://www.amazon.com/dp/B0XXXXXXXX" --label "Pink cow"
```

The store is worked out from the link, the product number is pulled out when the store puts one in the URL, and tracking parameters are removed. Push, and the next price check reads it. Target links can be added too; they open the product but aren't price-checked.

To add a gift, copy an existing entry in `items` and change it:

- `id` (unique), `name`, `brand`, `emoji`, `blurb` and an optional `note` (safety or buying tips)
- `type`: a key from `types` (for example `squishies`, `lego`, `switch-games`), and `category`: that type's group
- `interests`: keys from the `interests` list
- `ages`: `[youngest, oldest]`, within 1–30
- `typical`: the usual price, optionally `range`: `[low, high]`, and `price_est: true` if the price is your estimate rather than the store's list price
- `lists`: keys from `hot_lists` for the lists it's on
- `tags`: `new` for the "New this year" seal. Gifts on a store, expert or trend list get the "Hot this year" seal automatically; add `hot` only for a gift that's hot without being on a list.
- `search`: the words used for each store's search button, and `stores`: which stores get a button
- `offers`: exact product pages (easiest through `add_link.py`)

To add a product type, add it to `types` with a `label`, an `emoji` and its `category`. To add a hot list, add it to `hot_lists` with a `name`, a `short` name, its `kind` (`retailer`, `expert`, `trend` or `guide`), the `url` and the `date` it came out.

`python3 -B scraper/test_scrape.py` checks the catalog: valid ages, interests, types, lists and stores, at least 12 ideas for each age band, store links on the right sites and no store link listed twice. The workflow runs it on every push, so a broken catalog stops the publish instead of breaking the live site.

## Lists and share links

- Lists are kept in the browser's local storage on that device. Clearing the site's data deletes them, so use **Back up** to save a file and **Restore** to load it on another device.
- A share link carries the list inside the link itself, compressed. Nothing is uploaded, so anyone who has the link can read the list. Tick **Hide what's been bought or wrapped** before sharing with the person the list is for.
- Opening a share link shows the list and lets you save it to your own lists, or add it to the matching person's list if you already have one.

## Run it locally

Python 3.9 or later (the version macOS includes is fine), standard library only. The site checks need Node.js 22 or later; the workflow installs it.

```bash
python3 -B scraper/scrape.py --offline         # rebuild site/data/gifts.json from the catalog (keeps the last prices)
python3 -m http.server -d site 8000            # then open http://localhost:8000
python3 -B scraper/test_scrape.py              # parser, robots.txt, merge, hot list, store picks and catalog checks
node site/test_app.cjs                         # matching, lists, sharing, types, store picks and page rendering checks
python3 scraper/scrape.py --limit 3 --dry-run  # read 3 store pages, print, write nothing
python3 scraper/scrape.py --only amazon        # check one store
python3 scraper/scrape.py                      # full price check, rewrites site/data/gifts.json
python3 scraper/scrape.py --probe              # which stores answer this computer?
python3 scraper/store_picks.py                 # import scraper/captures/ (Walmart read in a browser)
python3 scraper/store_picks.py --check         # what the import would keep, writing nothing
```

## Files

```
site/                       the website (plain HTML, CSS and JavaScript; no build step)
  index.html
  test_app.cjs              site checks (Node.js)
  assets/app.js             gift matching, product types, lists, sharing, pages, refresh button
  assets/app.css
  assets/config.js          repo name, schedule text, site address
  data/catalog.json         the gifts, product types, hot lists, stores and interests (edit this)
  data/gifts.json           generated by the scraper (don't edit by hand)
  data/store-picks.json     Walmart's best sellers and deals, generated by store_picks.py
scraper/
  scrape.py                 the price checker
  add_link.py               adds a store product link to a gift
  hotlists.py               pulls product links out of a top-toys list or gift guide
  store_picks.py            imports store pages read in a browser: picks, product types, ages and prices
  browser/walmart-capture.js  the snippet that reads Walmart's pages in a browser
  captures/                 what the browser read (walmart*.txt, gamestop.txt, lego.txt) and the prices it found
  test_scrape.py            offline parser, merge, hot list, store picks and catalog checks
  fixtures/                 saved page snippets the checks read
  probe-results.json        which stores answered the last probe (written by the workflow)
.github/workflows/scrape.yml   twice-daily price check, commit and publish
```

Prices change constantly, so check the store before buying. Not affiliated with any store or brand.
