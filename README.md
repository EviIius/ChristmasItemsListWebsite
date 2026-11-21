# Christmas Gift Finder

A small website for Christmas shopping: gift ideas for ages 1 to 30, a Christmas list for each person you're buying for, and every big store's search one click away. It has 161 gift ideas across 27 interests (squishies, plush, LEGO, Switch, PlayStation, Pokémon, K-pop and more) and links to 24 stores, from Target, Walmart, Amazon and Best Buy to GameStop, LEGO.com, Pokémon Center, Five Below and Build-A-Bear.

**Live site:** https://eviiius.github.io/ChristmasItemsListWebsite/ (once the setup below is done)

| Page | What it does |
| --- | --- |
| Find gifts | Set an age (1–30), a budget and interests to get ranked gift ideas, stocking stuffers ($25 and under) and an age guide with safety notes. Choose someone from your lists to use their age, interests and budget. |
| Lists | One Christmas list per person: name, age, color, budget and interests. Add gifts from anywhere on the site (they get circled in that person's color) or add your own with a link. Mark each gift Idea, Bought or Wrapped, note what you paid and watch the budget bar. The shopping trip view groups everything by store. Share, copy as text, print, back up. Starred gifts go to a shortlist. |
| Browse all | Every gift in one sortable, filterable table (cards on phones). |
| Deals & dates | Countdown to Black Friday, Cyber Monday, Green Monday and Christmas Eve, gifts selling at least 8% under their usual price, the big-ticket gifts, and the status of every tracked store link. |
| Shop every store | Type a search once and open it at any of the 24 stores, plus a directory of what each store is good for. |

Lists and settings are saved in each visitor's own browser. There are no accounts and no AI features, and nothing is sent anywhere.

## One-time setup

1. **Push this folder** to `main` on GitHub (GitHub Desktop: **Commit to main**, then **Push origin**).
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

- **Typical prices first.** Every gift has a typical price (its usual list price, in the catalog) and, for many, the usual range. The site shows the typical price until a store price has been read, and says which kind of price it is.
- **Store prices.** Gifts with exact product pages (`offers` in the catalog) get the store's own price read twice a day (11:43 and 23:43 UTC, about 6:45 AM and 6:45 PM Eastern), committed, and republished. 18 product pages at 8 stores are tracked so far; add more with `add_link.py` (below). Change the `cron` line in `.github/workflows/scrape.yml`, and the `schedule` text in `site/assets/config.js` to match.
- **What's read:** the schema.org Product data stores publish for search engines (Best Buy, LEGO, GameStop, Pokémon Center, Shopify shops like tonies and Five Below), Walmart's page data, Target's embedded product data and Amazon's price block. With a `BESTBUY_API_KEY` secret, Best Buy prices come from Best Buy's official Products API instead.
- **Only the store's own price counts.** Marketplace sellers are ignored. A price under a quarter or over four times the typical price is treated as a misread and dropped.
- **Deals** need a store price checked in the last 72 hours that's at least 8% under the typical price.
- **Politeness:** one request at a time, 3–6 seconds apart per store, robots.txt respected, an honest user agent (`ChristmasGiftFinder`), and a store is skipped for the rest of the run after 3 failures in a row. Bot-check pages are detected and reported, never bypassed.
- **When a page can't be read,** the last known price stays up, labeled with when it was checked. Price history keeps one point per day (that day's low) for 120 days.

### If stores block the price check

Big stores often refuse requests from cloud servers like GitHub's. On Victor's laptop site, Best Buy never answered GitHub at all and Walmart showed a bot check. Expect the same here: the site still works on typical prices and store searches, but live prices need a better connection. Options:

1. **See which stores answer:** Actions → Run workflow → tick **probe**. It reads one page per store and writes `scraper/probe-results.json`. To test your own connection instead, run `python3 scraper/scrape.py --probe` on your computer.
2. **Run the price check from home (recommended):** Settings → Actions → Runners → **New self-hosted runner**, run the commands it shows on a computer that's on at check times, then `./svc.sh install && ./svc.sh start` so it survives restarts. A runner belongs to one repository, so if Victor's site already has one, set this one up in its own folder (for example `~/actions-runner-christmas`). Then add a repository variable (Settings → Secrets and variables → Actions → **Variables**) named `SCRAPER_RUNNER` with the value `self-hosted`. Only the price check moves to your computer; building and publishing stay on GitHub. Since the repo is public, also set Settings → Actions → General → fork pull request approval to **Require approval for all external contributors**, so strangers' pull requests can't run code on your machine.
3. **Run it by hand:** `python3 scraper/scrape.py`, then commit and push `site/data/gifts.json`.
4. **Best Buy API key:** if you can get one from [developer.bestbuy.com](https://developer.bestbuy.com/), add it as a repo secret named `BESTBUY_API_KEY`.

## Adding gifts and store links

Everything lives in `site/data/catalog.json`. To start tracking a store price, find the gift's id, then add the product page:

```bash
python3 scraper/add_link.py --find squish
python3 scraper/add_link.py squishmallows-12 "https://www.target.com/p/.../-/A-12345678" --label "Pink cow"
```

The store is worked out from the link, the product number is pulled out when the store puts one in the URL, and tracking parameters are removed. Push, and the next price check reads it.

To add a gift, copy an existing entry in `items` and change it:

- `id` (unique), `name`, `brand`, `emoji`, `blurb` and an optional `note` (safety or buying tips)
- `category` and `interests`: keys from the `categories` and `interests` lists at the top of the file
- `ages`: `[youngest, oldest]`, within 1–30
- `typical`: the usual price, and optionally `range`: `[low, high]`
- `tags`: `hot` and/or `new` for the "Hot this year" and "New this year" seals
- `search`: the words used for each store's search button, and `stores`: which stores get a button
- `offers`: exact product pages (easiest through `add_link.py`)

`python3 -B scraper/test_scrape.py` checks the catalog (valid ages, interests and stores, at least 12 gifts for each age band, store links on the right sites). The workflow runs it on every push, so a broken catalog stops the publish instead of breaking the live site.

## Lists and share links

- Lists are kept in the browser's local storage on that device. Clearing the site's data deletes them, so use **Back up** to save a file and **Restore** to load it on another device.
- A share link carries the list inside the link itself, compressed. Nothing is uploaded, so anyone who has the link can read the list. Tick **Hide what's been bought or wrapped** before sharing with the person the list is for.
- Opening a share link shows the list and lets you save it to your own lists, or add it to the matching person's list if you already have one.

## Run it locally

Python 3.9 or later (the version macOS includes is fine), standard library only. The site checks need Node.js 22 or later; the workflow installs it.

```bash
python3 -m http.server -d site 8000            # then open http://localhost:8000
python3 -B scraper/test_scrape.py              # parser, robots.txt, merge and catalog checks
node site/test_app.cjs                         # matching, lists, sharing and page rendering checks
python3 scraper/scrape.py --limit 3 --dry-run  # read 3 store pages, print, write nothing
python3 scraper/scrape.py --only target        # check one store
python3 scraper/scrape.py                      # full price check, rewrites site/data/gifts.json
python3 scraper/scrape.py --offline            # rebuild gifts.json from catalog.json without contacting stores
```

## Files

```
site/                     the website (plain HTML, CSS and JavaScript; no build step)
  index.html
  test_app.cjs            site checks (Node.js)
  assets/app.js           gift matching, lists, sharing, pages, refresh button
  assets/app.css
  assets/config.js        repo name, schedule text, site address
  data/catalog.json       the gifts, stores and interests (edit this)
  data/gifts.json         generated by the scraper (don't edit by hand)
scraper/
  scrape.py               the price checker
  add_link.py             adds a store product link to a gift
  test_scrape.py          offline parser, merge and catalog checks
.github/workflows/scrape.yml   twice-daily price check, commit and publish
```

Prices change constantly, so check the store before buying. Not affiliated with any store or brand.
