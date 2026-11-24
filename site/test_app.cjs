// Run with: node site/test_app.cjs. Exercises the site's matching, lists, sharing and rendering without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const site = __dirname;
const source = fs.readFileSync(path.join(site, 'assets/app.js'), 'utf8');
const elements = new Map();
const classes = () => { const set = new Set(); return { add: (c) => set.add(c), remove: (...c) => c.forEach((x) => set.delete(x)), toggle: (c, on) => ((on ?? !set.has(c)) ? set.add(c) : set.delete(c)), contains: (c) => set.has(c) }; };
const element = (selector) => {
  if (!elements.has(selector)) {
    elements.set(selector, {
      innerHTML: '', textContent: '', hidden: true, isConnected: true, value: '', dataset: {}, style: { setProperty() {} },
      classList: classes(), attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      addEventListener() {}, insertAdjacentHTML(_, html) { this.innerHTML += html; }, querySelector: element, querySelectorAll: () => [],
      getBoundingClientRect: () => ({ top: 0, left: 0, bottom: 0, right: 0 }), getClientRects: () => [{}], contains: () => false,
      focus() { context.document.activeElement = this; }, offsetHeight: 0, offsetWidth: 0,
    });
  }
  return elements.get(selector);
};
const storage = new Map();
const context = vm.createContext({
  window: { SITE_CONFIG: { repo: 'EviIius/ChristmasItemsListWebsite', christmas: { month: 12, day: 25 } }, matchMedia: () => ({ matches: false }), addEventListener() {} },
  document: { querySelector: element, querySelectorAll: () => [], documentElement: { style: { setProperty() {} }, dataset: {} }, addEventListener() {}, activeElement: null, hidden: false },
  localStorage: { getItem: (k) => (storage.has(k) ? storage.get(k) : null), setItem: (k, v) => storage.set(k, String(v)), removeItem: (k) => storage.delete(k) },
  location: { hash: '', href: 'https://eviiius.github.io/ChristmasItemsListWebsite/', pathname: '/ChristmasItemsListWebsite/', search: '' },
  history: { replaceState() {} },
  matchMedia: () => ({ matches: false }), innerWidth: 1200, innerHeight: 800,
  console, setTimeout, clearTimeout, TextEncoder, TextDecoder, Blob, Response, btoa, atob, URL,
  CompressionStream: globalThis.CompressionStream, DecompressionStream: globalThis.DecompressionStream,
});
context.window.SITE_CONFIG && (context.SITE_CONFIG = context.window.SITE_CONFIG);
assert(source.includes('  init();\n})();'), 'test hook must replace the startup call');
vm.runInContext(source.replace('  init();\n})();', `
  globalThis.app = {
    load(d) { DATA = d; boot(true); },
    state, findResults, sharedModal, scoreGift, priceInfo, dealInfo, ageFit, ageText, ageLabel, normalizeLists, addPerson, addGift, removeGift,
    toggleShortlist, addCustom, totals, itemInfo, sharePayload, encodeShare, decodeShare, fromShare, listText, searchUrl, keyDates,
    christmasDate, daysUntil, interestNames, giftCard, renderFindPrefs, renderFind, renderLists, renderBrowse, renderFilters, renderDeals,
    renderStores, openDrawer, statusHtml, renderFreshness, profileOf, person, onLists,
    prepPicks, pickRows, renderPicksPanel, renderPicks, renderStoreHot, togglePick, offerStatus, get picks() { return PICKS; },
    get items() { return ITEMS; }, get byId() { return BYID; },
    parseQuery, matchWords, browseRows, loadMore, setMoreRow, get findView() { return FIND_RES; }, get browseView() { return BROWSE_RES; },
  };
})();`), context);

const data = JSON.parse(fs.readFileSync(path.join(site, 'data/gifts.json'), 'utf8'));
const picksDataForInto = JSON.parse(fs.readFileSync(path.join(site, 'data/store-picks.json'), 'utf8'));
const { app } = context;
app.load(data);

let checks = 0;
async function check(label, fn) { await fn(); console.log('PASS ' + label); checks += 1; }
const base = { who: '', age: 10, budget: 100, interests: [], hot: false, deals: false, live: false };
const withLive = (id, price, extra = {}) => Object.assign(app.byId[id], { price, price_status: 'live', price_retailer: 'target', price_url: 'https://www.target.com/p/x/-/A-1', price_checked_at: new Date().toISOString() }, extra);
// Checks that need a gift at its typical price clear whatever store price the data has, then put it back,
// so they pass whichever prices the price checker found.
const PRICE_KEYS = ['price', 'price_status', 'price_retailer', 'price_url', 'price_checked_at', 'regular'];
const asTypical = (id) => {
  const it = app.byId[id]; const saved = {};
  for (const k of PRICE_KEYS) { saved[k] = it[k]; delete it[k]; }
  it.price_status = 'typical';
  return () => { for (const k of PRICE_KEYS) { if (saved[k] === undefined) delete it[k]; else it[k] = saved[k]; } };
};

(async () => {
  await check('every gift has the fields the site needs', () => {
    for (const it of app.items) {
      assert(it.id && it.name && it.emoji && it.blurb && it.search, it.id);
      assert(it.ages[0] >= 1 && it.ages[1] <= 30 && it.ages[0] <= it.ages[1], it.id);
      assert(it.typical > 0 && it.stores.length >= 1, it.id);
    }
  });
  await check('matching respects age, budget and interests', () => {
    const p = Object.assign({}, base, { interests: ['squishies'] });
    const res = app.findResults(p);
    assert(res.length >= 5);
    for (const it of res) {
      assert(it.interests.includes('squishies'), it.id);
      assert(app.ageFit(it, 10) > 0, it.id);
      assert(app.priceInfo(it).value <= 100, it.id);
    }
  });
  await check('M-rated games stay out until 17', () => {
    const ids = (age) => app.findResults(Object.assign({}, base, { age, budget: 700, interests: ['playstation'] })).map((it) => it.id);
    assert(!ids(15).includes('gta-vi') && !ids(15).includes('marvels-wolverine'));
    assert(ids(17).includes('gta-vi'));
    assert(!app.findResults(Object.assign({}, base, { age: 2, budget: 700 })).some((it) => it.ages[0] > 3), 'toddler ideas only for a 2-year-old');
  });
  await check('"any amount" budget includes the big gifts; a $25 budget only stocking stuffers', () => {
    assert(app.findResults(Object.assign({}, base, { age: 16, budget: 700 })).some((it) => it.id === 'ps5-disc'));
    assert(app.findResults(Object.assign({}, base, { age: 16, budget: 25 })).every((it) => app.priceInfo(it).value <= 25));
  });
  await check('store prices replace typical prices, and deals need a fresh price well below typical', () => {
    const it = app.byId['needoh-nice-cube']; const restore = asTypical(it.id);
    assert.equal(app.priceInfo(it).kind, 'typical');
    withLive('needoh-nice-cube', 7.49);
    assert.equal(app.priceInfo(it).kind, 'live');
    assert(app.dealInfo(it) && Math.abs(app.dealInfo(it).save - 2.5) < 1e-9);
    withLive('needoh-nice-cube', 9.79);
    assert.equal(app.dealInfo(it), null, 'a 2% dip is not a deal');
    withLive('needoh-nice-cube', 7.49, { price_checked_at: new Date(Date.now() - 5 * 864e5).toISOString() });
    assert.equal(app.dealInfo(it), null, 'old prices are not deals');
    assert(app.findResults(Object.assign({}, base, { deals: true })).every((x) => app.dealInfo(x)));
    restore();
  });
  await check('lists: add people, circle gifts once, shortlist, custom items and totals', () => {
    app.state.lists = app.normalizeLists(null);
    const mia = app.addPerson({ name: 'Mia', age: 10, budget: 150, interests: ['squishies', 'lego'] });
    assert(app.addGift(mia.id, 'lego-pokemon-pikachu-house'));
    assert(!app.addGift(mia.id, 'lego-pokemon-pikachu-house'), 'no duplicates');
    assert(!app.addGift(mia.id, 'not-a-gift'));
    assert.deepEqual([...app.onLists('lego-pokemon-pikachu-house').map((p) => p.name)], ['Mia']);
    assert(app.toggleShortlist('needoh-nice-cube') && !app.toggleShortlist('needoh-nice-cube'));
    app.toggleShortlist('squishy-dumplings');
    app.addGift(mia.id, 'squishy-dumplings');
    assert(!app.state.lists.shortlist.includes('squishy-dumplings'), 'circling a gift takes it off the shortlist');
    const x = app.addCustom(mia.id, { name: 'Hello Kitty dumpling', url: 'https://www.target.com/p/hello-kitty/-/A-123', price: '5' });
    assert.equal(x.store, 'target');
    assert.equal(app.itemInfo(x).url, 'https://www.target.com/p/hello-kitty/-/A-123');
    mia.items[0].status = 'bought'; mia.items[0].paid = 60;
    const t = app.totals(mia);
    assert.equal(t.count, 3); assert.equal(t.done, 1); assert.equal(t.spent, 60);
    assert(Math.abs(t.planned - (60 + 5 + 5)) < 1e-9);
    assert(app.removeGift(mia.id, 'squishy-dumplings') && app.totals(mia).count === 2);
    const ideas = app.findResults(app.profileOf(mia));
    assert(ideas.every((it) => it.interests.some((i) => ['squishies', 'lego'].includes(i))));
  });
  await check('stored lists are cleaned up when loaded', () => {
    const l = app.normalizeLists({ people: [{ name: 'X'.repeat(80), age: 99, color: 'javascript:alert(1)', items: [{ gift: 'needoh-nice-cube', status: 'stolen' }, { name: 'Thing', url: 'javascript:alert(1)' }, {}] }, { age: 3 }], shortlist: ['a', 4] });
    assert.equal(l.people.length, 1);
    const p = l.people[0];
    assert.equal(p.name.length, 40); assert.equal(p.age, 30); assert(p.color.startsWith('#'));
    assert.equal(p.items.length, 2); assert.equal(p.items[0].status, 'idea'); assert.equal(p.items[1].url, undefined);
    assert.deepEqual([...l.shortlist], ['a']);
  });
  await check('share links round-trip, with and without compression, and can hide spoilers', async () => {
    const mia = app.state.lists.people[0];
    const plain = app.sharePayload(mia, false);
    const z = await app.encodeShare(plain);
    assert(z.startsWith(typeof CompressionStream === 'function' ? 'z' : 'j'));
    const back = app.fromShare(await app.decodeShare(z));
    assert.equal(back.name, 'Mia'); assert.equal(back.items.length, 2);
    assert.equal(back.items[0].status, 'bought');
    assert.equal(back.items[1].name, 'Hello Kitty dumpling'); assert.equal(back.items[1].url, 'https://www.target.com/p/hello-kitty/-/A-123');
    const hidden = app.fromShare(await app.decodeShare(await app.encodeShare(app.sharePayload(mia, true))));
    assert(hidden.items.every((x) => x.status === 'idea'), 'no spoilers');
    const saved = context.CompressionStream; context.CompressionStream = undefined;
    const j = await app.encodeShare(plain); context.CompressionStream = saved;
    assert(j.startsWith('j') && app.fromShare(await app.decodeShare(j)).items.length === 2);
    await assert.rejects(() => app.decodeShare('jbm90IGEgbGlzdA'));
    const evil = await app.encodeShare({ v: 1, n: 'Eve', c: 'red;background:url(x)', items: [{ n: 'Prize', u: 'javascript:alert(1)' }, { g: 'needoh-nice-cube', st: 'b' }] });
    const cleaned = app.normalizeLists({ people: [app.fromShare(await app.decodeShare(evil))] }).people[0];
    assert(cleaned.items[0].url === undefined && cleaned.color.startsWith('#') && cleaned.items[1].status === 'bought', 'shared lists are cleaned before showing or saving');
    assert(app.listText(mia, false).includes("Mia's Christmas list (age 10)") && app.listText(mia, false).includes('[Bought]'));
    assert(!app.listText(mia, true).includes('[Bought]'));
  });
  await check('store search links are encoded', () => {
    assert.equal(app.searchUrl('target', 'LEGO Pokémon & friends'), 'https://www.target.com/s?searchTerm=LEGO%20Pok%C3%A9mon%20%26%20friends');
    assert.equal(app.searchUrl('playstation', 'ps5'), 'https://direct.playstation.com/en-us/', 'stores without search go home');
  });
  await check('sale dates for 2026 and the Christmas countdown', () => {
    const now = new Date(2026, 10, 20, 21, 30);
    const d = Object.fromEntries(app.keyDates(now).map((x) => [x.label, x.date.toDateString()]));
    assert.equal(d['Black Friday'], new Date(2026, 10, 27).toDateString());
    assert.equal(d['Cyber Monday'], new Date(2026, 10, 30).toDateString());
    assert.equal(d['Green Monday'], new Date(2026, 11, 14).toDateString());
    assert.equal(app.daysUntil(app.christmasDate(now), now), 35);
    assert.equal(app.daysUntil(app.christmasDate(new Date(2026, 11, 25, 8)), new Date(2026, 11, 25, 8)), 0);
    assert.equal(app.christmasDate(new Date(2026, 11, 26)).getFullYear(), 2027);
  });
  await check('wording helpers', () => {
    assert.equal(app.ageLabel(8), 'an 8-year-old'); assert.equal(app.ageLabel(9), 'a 9-year-old'); assert.equal(app.ageLabel(18), 'an 18-year-old');
    assert.equal(app.interestNames(['lego', 'switch', 'playstation']), 'LEGO, Switch games and PlayStation');
    assert.equal(app.ageText({ ages: [1, 30] }), 'any age'); assert.equal(app.ageText({ ages: [12, 30] }), 'ages 12+');
  });
  await check('every page renders, including empty and filled lists', () => {
    app.state.find = Object.assign({}, base, { who: app.state.lists.people[0].id });
    app.renderFindPrefs(); app.renderFind();
    assert(element('#top-picks').innerHTML.includes('class="gift"'));
    assert(element('#find-h').textContent === 'Ideas for Mia');
    assert(element('#top-picks').innerHTML.includes('class="marker'), 'gifts on the selected list are circled');
    for (const v of [null, 'shortlist', 'trip']) { app.state.listView = v; app.renderLists(); assert(element('#list-main').innerHTML.length > 100, String(v)); }
    app.state.listView = app.state.lists.people[0].id; app.renderLists();
    assert(element('#list-main').innerHTML.includes("Mia's list"));
    app.renderFilters(); app.renderBrowse(); assert(element('#browse-table tbody').innerHTML.includes('data-open'));
    const needoh = app.items.filter((it) => /(^|[^a-z0-9])nee-?doh/i.test(`${it.name} ${it.brand}`)).length; // search looks at names, brands and types first
    app.state.browse.q = 'needoh'; app.renderBrowse(); assert(needoh >= 3 && element('#browse-sub').innerHTML.startsWith(`${needoh} of`) && element('#browse-table tbody').innerHTML.includes('data-open="needoh-shapes"'));
    app.state.browse.q = '';
    app.renderDeals(); assert(element('#dates').innerHTML.includes('Black Friday'));
    app.state.storeQ = 'squishmallow'; app.renderStores(); assert(element('#store-results').innerHTML.includes('searchTerm=squishmallow'));
    app.openDrawer('gta-vi'); assert(element('#drawer').innerHTML.includes('Rated M (Mature 17+)'));
    app.renderFreshness(); assert(element('#freshness-text').textContent.includes(data.live_prices ? 'store price' : 'typical prices'));
    assert(app.statusHtml().includes('exact product pages'));
    app.state.lists = app.normalizeLists(null); app.state.listView = null; app.renderLists();
    assert(element('#list-main').innerHTML.includes('Start from an example'));
    app.sharedModal({ v: 1, n: 'Eve', items: [{ n: 'Prize', u: 'javascript:alert(1)' }] });
    assert(element('#modal').innerHTML.includes('Prize') && !element('#modal').innerHTML.includes('javascript:'), 'no script links in the shared-list preview');
  });
  await check('product types: every gift has one, and Browse filters by type, group and hot list', () => {
    const types = data.types; const cats = data.categories;
    assert(Object.keys(types).length >= 60, 'a real product-type taxonomy');
    for (const it of app.items) assert(types[it.type] && types[it.type].category === it.category && cats[it.category], it.id);
    app.state.browse = Object.assign(app.state.browse, { q: '', interest: '', age: '', max: '', store: '', hot: false, live: false, list: '', type: 'lego' });
    app.renderFilters(); app.renderBrowse();
    const lego = app.items.filter((it) => it.type === 'lego');
    assert(lego.length >= 10 && element('#browse-sub').innerHTML.startsWith(`${lego.length} of`) && element('#browse-sub').innerHTML.includes('in LEGO sets'));
    assert(element('#type-browser').innerHTML.includes('data-type="lego" aria-pressed="true"'), 'chosen type is pressed');
    assert(element('#filters').innerHTML.includes('<optgroup label="Building sets">'), 'type select is grouped');
    app.state.browse.type = 'cat:beauty'; app.renderBrowse();
    const beauty = app.items.filter((it) => it.category === 'beauty').length;
    assert(element('#browse-sub').innerHTML.startsWith(`${beauty} of`));
    app.state.browse.type = ''; app.state.browse.list = 'amazon'; app.renderBrowse();
    const onAmazon = app.items.filter((it) => it.lists.includes('amazon')).length;
    assert(onAmazon >= 30 && element('#browse-sub').innerHTML.startsWith(`${onAmazon} of`));
    app.state.browse.list = ''; app.state.typesOpen = false; app.renderBrowse();
    assert(!element('#type-browser').innerHTML.includes('class="tchip"') && element('#type-browser').innerHTML.includes('Choose a type'), 'type browser folds away');
    app.state.typesOpen = true; app.renderBrowse();
  });
  await check('hot seals come from 2026 store and expert lists; gift-guide picks are cited without a seal', () => {
    assert(app.byId['target-toy-basket'].tags.includes('hot'), 'Target list item gets the seal');
    assert(app.byId['little-live-pets-puppy'].tags.includes('hot'));
    const guideOnly = app.items.find((it) => it.lists.length && it.lists.every((l) => data.hot_lists[l].kind === 'guide') && !(data.items.find((x) => x.id === it.id).tags || []).includes('hot'));
    assert(guideOnly && !guideOnly.tags.includes('hot'), 'gift-guide-only pick has no seal');
    app.openDrawer('little-live-pets-puppy');
    assert(element('#drawer').innerHTML.includes('On these 2026 lists') && element('#drawer').innerHTML.includes('Top Toys 2026'));
    assert(element('#drawer').innerHTML.includes('data-type="interactive"'), 'drawer links to its product type');
    assert(element('#drawer').innerHTML.includes("link only; Target isn't price-checked automatically"), 'Target links are marked link-only');
    app.renderDeals();
    assert(element('#hot-sources').innerHTML.includes('data-show-list="target"') && element('#tracked-list').innerHTML.includes('<details class="store-links">'));
  });
  await check('estimated prices are labeled as estimates, confirmed ones as typical', () => {
    const est = app.items.find((it) => it.price_est && app.priceInfo(it).kind === 'typical'); const sure = app.byId['lego-upscaled-vader'];
    assert(est && app.giftCard(est).includes('Estimated price') && !app.giftCard(est).includes('Typical price'));
    const restore = asTypical(sure.id);
    assert(!sure.price_est && app.giftCard(sure).includes('Typical price'));
    restore();
  });
  const picksData = JSON.parse(fs.readFileSync(path.join(site, 'data/store-picks.json'), 'utf8'));
  app.prepPicks(JSON.parse(JSON.stringify(picksData)));
  const pickReset = () => Object.assign(app.state.picks, { band: '', type: '', show: '', max: '', sort: 'rank', q: '', shown: 24 });
  const PICK_URL = { walmart: (s) => `https://www.walmart.com/ip/${s}`, gamestop: (s) => `https://www.gamestop.com/products/${s}.html`, lego: (s) => `https://www.lego.com/en-us/product/${s}`, fivebelow: (s) => `https://www.fivebelow.com/products/${s}`, barnesnoble: (s) => { const [w, e] = s.split('-'); return `https://www.barnesandnoble.com/w/${w}?ean=${e}`; } };
  await check('smart search reads ages, prices, stores, "on sale" and the words to look for', () => {
    const q1 = app.parseQuery('LEGO for an 8 year old under $50');
    assert(q1.ageLo === 8 && q1.ageHi === 8 && q1.max === 50 && q1.words.length === 1 && q1.words[0].w === 'lego', JSON.stringify(q1));
    const q2 = app.parseQuery('squishies between $5 and $15 at five below for my 10yo nephew');
    assert(q2.min === 5 && q2.max === 15 && q2.store === 'fivebelow' && q2.ageLo === 10 && q2.words.map((w) => w.w).join() === 'squishies', JSON.stringify(q2));
    const q3 = app.parseQuery('gift card for my boss');
    assert(q3.ageLo === 18 && q3.words.map((w) => w.w).join() === 'gift card', JSON.stringify(q3));
    const q4 = app.parseQuery('teen deals 8-12');
    assert(q4.ageLo === 8 && q4.ageHi === 12 && q4.sale, JSON.stringify(q4));
    const q5 = app.parseQuery('stocking stuffers for a toddler');
    assert(q5.max === 25 && q5.ageLo === 1 && q5.ageHi === 3 && !q5.words.length, JSON.stringify(q5));
    const q6 = app.parseQuery('lego nintendo');
    assert(!q6.store && q6.words.length === 2, 'brand names are words, not stores');
  });
  await check('smart search: results fit what was asked, rank name matches first, fix a misspelling, and load 60 at a time', () => {
    app.state.browse.sort = 'match'; app.state.browse.dir = 1;
    app.state.browse.q = 'lego for an 8 year old under $50'; app.state.browse.shown = 60; app.renderBrowse();
    const rows = app.browseView;
    assert(rows.length >= 2 && rows.every((it) => it.ages[0] <= 8 && it.ages[1] >= 8 && !(app.priceInfo(it).value > 50) && /lego/i.test(it._s)), `${rows.length} rows`);
    assert(/lego/i.test(rows[0].name) && element('#browse-understood').innerHTML.includes('Age 8') && element('#browse-understood').innerHTML.includes('Up to $50'));
    app.state.browse.q = 'squishmellow'; app.renderBrowse();
    assert(app.browseView.length && app.browseView.every((it) => /squishmallow/i.test(it._s)) && element('#browse-understood').innerHTML.includes('for “squishmellow”'));
    app.state.browse.q = ''; app.state.browse.shown = 60; app.renderBrowse();
    const shownRows = (element('#browse-table tbody').innerHTML.match(/data-open=/g) || []).length;
    assert(shownRows === 60 && element('#browse-more').innerHTML.includes('data-browse-more') && element('#browse-more').innerHTML.includes(`Show all ${app.items.length.toLocaleString('en-US')}`), `${shownRows} rows`);
    app.loadMore('browse'); assert.equal((element('#browse-table tbody').innerHTML.match(/data-open=/g) || []).length, 120);
    app.state.browse.q = '';
  });
  await check('"Into" is precise: consoles come from product names, and squishy toys are not LEGO', () => {
    app.prepPicks(JSON.parse(JSON.stringify(picksDataForInto))); app.load(JSON.parse(JSON.stringify(data)));
    const plat = { playstation: /playstation|\bps[45]\b|psvr|dualsense|dualshock/i, xbox: /\bxbox\b/i, switch: /nintendo|\bswitch\b|joy-?cons?|amiibo/i };
    const wrong = app.items.filter((it) => it.pick && Object.entries(plat).some(([i, rx]) => it.interests.includes(i) && !rx.test(it.name) && !(i === 'switch' && it.type === 'switch-games')));
    assert(!wrong.length, wrong.slice(0, 4).map((it) => `${it.name} [${it.interests}]`).join(' | '));
    assert(!app.items.some((it) => it.category === 'squish' || it.type === 'squishies' ? it.interests.includes('lego') : false), 'a squishy toy is tagged LEGO');
    app.state.browse = Object.assign(app.state.browse, { q: 'lego at target', interest: '', type: '', store: '', sort: 'match', shown: 60 }); app.renderBrowse();
    assert(app.browseView.length && app.browseView.every((it) => /\blego\b/i.test(`${it.name} ${it.brand} ${it.type}`) && (it.stores.includes('target') || it.offers.some((o) => o.retailer === 'target'))), app.browseView.filter((it) => !/lego/i.test(it.name)).map((it) => it.name).slice(0, 3).join(' | '));
    app.state.browse = Object.assign(app.state.browse, { q: '', interest: 'playstation' }); app.renderBrowse();
    assert(app.browseView.length && !app.browseView.some((it) => it.pick && /\bxbox\b/i.test(it.name) && !plat.playstation.test(it.name)), 'Xbox-only store items under PlayStation');
    app.state.browse.interest = ''; app.prepPicks(null); app.load(JSON.parse(JSON.stringify(data))); app.prepPicks(JSON.parse(JSON.stringify(picksDataForInto)));
  });
  await check('Find: quick buttons narrow the ideas, and the list grows in place 24 at a time', () => {
    app.state.find = Object.assign({}, app.state.find, { who: '', age: 9, budget: 100, interests: [], hot: false, deals: false, live: false });
    app.state.findQuick = 'u25'; app.state.shown = 24; app.renderFind();
    assert(app.findView.length > 24 && app.findView.every((it) => app.priceInfo(it).value <= 25), `${app.findView.length}`);
    assert(element('#find-quick').innerHTML.includes('data-find-quick="u25"') && element('#find-quick').innerHTML.includes('aria-pressed="true"'));
    const before = (element('#top-picks').innerHTML.match(/class="gift"/g) || []).length;
    app.loadMore('find');
    assert.equal((element('#top-picks').innerHTML.match(/class="gift"/g) || []).length, before + 24);
    app.state.findQuick = ''; app.state.shown = 24; app.renderFind();
  });
  await check("store picks: every pick is typed, aged and links to the store's product page", () => {
    const P = app.picks;
    assert(P.items.length >= 300, `${P.items.length} picks`);
    for (const x of P.items) {
      assert(data.types[x.type] && data.types[x.type].category === x.category, x.id);
      assert(x.ages[0] >= 1 && x.ages[1] <= 30 && x.ages[0] <= x.ages[1], x.id);
      assert(x.url === PICK_URL[x.store](x.sku) && x.id === `${x.store}-${x.sku}` && P.stores[x.store], x.id);
      assert(x.price == null || x.price > 0, x.id);
      if (x.was) assert(x.was > x.price && x.pct === Math.round((x.was - x.price) / x.was * 100), x.id);
      assert(x.lists.length && x.lists.every((l) => P.lists[l]) && Object.keys(x.rank).sort().join() === x.lists.slice().sort().join(), x.id);
      assert(!/open box|christmas tree|freezer|refrigerator|smart tv/i.test(x.name), x.name);
      if (x.gift) assert(app.byId[x.gift], x.gift);
    }
  });
  await check('store picks filter by age group, type, sale, best sellers, store list, price and search', () => {
    pickReset(); app.state.picks.band = '9-12';
    assert(app.pickRows(app.state.picks).length > 20 && app.pickRows(app.state.picks).every((x) => x.ages[1] >= 9 && x.ages[0] <= 12));
    const kidsGames = app.pickRows(app.state.picks).filter((x) => x.esrb);
    assert(kidsGames.length && kidsGames.every((x) => !['M', 'RP-M', 'AO'].includes(x.esrb)), 'no Mature games for ages 9-12');
    pickReset(); app.state.picks.type = 'lego';
    assert(app.pickRows(app.state.picks).length >= 5 && app.pickRows(app.state.picks).every((x) => x.type === 'lego'));
    pickReset(); app.state.picks.type = 'cat:beauty';
    assert(app.pickRows(app.state.picks).every((x) => x.category === 'beauty'));
    pickReset(); app.state.picks.show = 'sale';
    assert(app.pickRows(app.state.picks).every((x) => x.was || x.flags.some((f) => ['deal', 'rollback', 'reduced', 'clearance'].includes(f))));
    pickReset(); app.state.picks.show = 'flag:best-seller';
    assert(app.pickRows(app.state.picks).length > 50 && app.pickRows(app.state.picks).every((x) => x.flags.includes('best-seller')));
    pickReset(); app.state.picks.show = 'list:wm-top-toys';
    assert(app.pickRows(app.state.picks).every((x) => x.lists.includes('wm-top-toys')));
    pickReset(); app.state.picks.max = '25';
    assert(app.pickRows(app.state.picks).every((x) => x.price != null && x.price <= 25));
    pickReset(); app.state.picks.q = 'barbie';
    assert(app.pickRows(app.state.picks).length >= 3 && app.pickRows(app.state.picks).every((x) => /barbie/i.test(x.name)));
    pickReset(); app.state.picks.sort = 'pct';
    const pcts = app.pickRows(app.state.picks).map((x) => x.pct || 0); assert(pcts.every((v, i) => i === 0 || pcts[i - 1] >= v));
    pickReset(); app.state.picks.sort = 'low';
    const lows = app.pickRows(app.state.picks).filter((x) => x.price != null).map((x) => x.price); assert(lows.every((v, i) => i === 0 || lows[i - 1] <= v));
    pickReset();
  });
  await check("store picks show on Deals and Find, and go on a person's list", () => {
    app.renderDeals();
    assert.equal(element('#picks-panel').hidden, false);
    assert(element('#picks-h').textContent.includes('Walmart'));
    assert(element('#picks').innerHTML.includes('data-add-pick=') && element('#picks-filters').innerHTML.includes('data-pick-band="13-17"'));
    app.state.picks.q = 'grand theft auto'; app.renderPicks();
    assert(element('#picks').innerHTML.includes('rated M (Mature 17+)') && element('#picks').innerHTML.includes('ages 17+'));
    app.state.picks.q = ''; app.renderPicks();
    assert(element('#picks-more').innerHTML.includes('data-picks-more'));
    app.renderStoreHot({ age: 9, budget: 50, interests: [] });
    assert.equal(element('#store-hot').hidden, false);
    assert(element('#store-hot').innerHTML.includes('9-year-olds') && element('#store-hot').innerHTML.includes('data-picks-goto="9-12"'));
    const shown = [...element('#store-hot').innerHTML.matchAll(/data-add-pick="([^"]+)"/g)].map((m) => app.picks.items.find((x) => x.id === m[1]));
    assert(shown.length && shown.every((x) => x.price <= 50 && x.ages[0] <= 9 && x.ages[1] >= 9));
    const kid = app.addPerson({ name: 'Theo', age: 9, interests: [] });
    const pk = shown[0];
    app.togglePick(pk.id, kid.id);
    const added = kid.items.find((i) => i.url === pk.url);
    assert(added && added.gift === null && added.name === pk.name && added.store === pk.store && added.price === pk.price);
    app.togglePick(pk.id, kid.id);
    assert(!kid.items.some((i) => i.url === pk.url), 'a second click takes it back off the list');
    app.openDrawer('paw-patrol-megasaurus');
    assert(element('#drawer').innerHTML.includes("On Walmart's lists") && element('#drawer').innerHTML.includes('Walmart Top Toys'));
    app.state.browse = Object.assign(app.state.browse, { type: 'lego', q: '', list: '' }); app.renderBrowse();
    assert(element('#browse-sub').innerHTML.includes('data-picks-type="lego"'));
    app.state.browse.type = '';
  });
  await check('browser-read and link-only store prices say where they came from', () => {
    const wm = app.items.flatMap((it) => it.offers).find((o) => o.retailer === 'walmart' && o.price && !o.stale);
    assert(wm && app.offerStatus(wm).includes('read in a browser'));
    const amz = app.items.flatMap((it) => it.offers).find((o) => o.retailer === 'amazon' && !o.price);
    assert(amz && app.offerStatus(amz).includes("isn't price-checked automatically"));
    app.renderStores();
    assert(element('#store-directory').innerHTML.includes('priced in a browser') && element('#store-directory').innerHTML.includes('no price check'));
    app.renderDeals();
    assert(element('#tracked-list').innerHTML.includes('read in a browser'));
  });
  await check('without a store picks file every page still works', () => {
    app.prepPicks(null);
    app.renderDeals(); assert.equal(element('#picks-panel').hidden, true);
    app.renderStoreHot({ age: 9, budget: 100, interests: [] }); assert.equal(element('#store-hot').hidden, true);
    app.renderFind(); app.renderBrowse();
    app.prepPicks({ items: [] }); app.renderDeals(); assert.equal(element('#picks-panel').hidden, true);
    app.prepPicks(JSON.parse(JSON.stringify(picksData)));
  });
  await check('store best sellers count as gift ideas: one idea per product, linked to every store that has it', () => {
    app.prepPicks(JSON.parse(JSON.stringify(picksData)));
    app.load(JSON.parse(JSON.stringify(data)));
    const picks = app.items.filter((it) => it.pick);
    const linked = new Set(app.picks.items.filter((x) => x.gift).map((x) => x.id));
    assert(picks.length >= 300 && app.items.length === data.items.length + picks.length, `${picks.length} store ideas`);
    assert(new Set(app.items.map((it) => it.id)).size === app.items.length, 'ids are unique');
    for (const it of picks) {
      assert(!linked.has(it.pick) && app.picks.items.some((x) => x.id === it.pick), it.id);
      assert(data.types[it.type] && data.types[it.type].category === it.category && it.ages[0] <= it.ages[1], it.id);
      assert(it.offers.length && it.offers.every((o) => /^https:\/\//.test(o.url) && app.picks.stores[o.retailer]), it.id);
      assert(/^#\d+ on |^On /.test(it.blurb), it.id);
    }
    app.state.browse.type = ''; app.renderBrowse();
    assert(element('#browse-sub').innerHTML.includes(` of ${app.items.length.toLocaleString('en-US')} gift ideas`));
    const one = picks.find((it) => it.offers.length === 1);
    const kid = app.addPerson({ name: 'Pick Test', age: 9, interests: [] });
    assert(app.addGift(kid.id, one.id));
    const entry = app.person(kid.id).items.find((x) => x.gift === one.id);
    assert(entry.name === one.name && entry.url === one.offers[0].url, 'a store idea on a list keeps its name and link');
    app.openDrawer(one.id);
    app.prepPicks(null); app.load(JSON.parse(JSON.stringify(data)));
    assert(app.items.length === data.items.length);
    app.prepPicks(JSON.parse(JSON.stringify(picksData)));
  });

  await check('store best sellers get interests from their names, and the "Store best sellers" button on Find shows only them', () => {
    app.load(JSON.parse(JSON.stringify(data)));
    const sw = app.items.filter((it) => it.pick && /star wars/i.test(it.name));
    assert(sw.length && sw.every((it) => it.interests.includes('characters') && !it.interests.includes('room')), sw.map((it) => it.name + ':' + it.interests).slice(0, 3).join(' | '));
    const nd = app.items.filter((it) => it.pick && /needoh/i.test(it.name));
    assert(nd.length && nd.every((it) => it.interests.includes('squishies')));
    app.state.find = Object.assign({}, app.state.find, { who: '', age: 9, budget: 100, interests: [] });
    app.state.findQuick = 'store'; app.state.shown = 24; app.renderFind();
    assert(app.findView.length && app.findView.every((it) => it.pick), 'the "Store best sellers" button shows only store best sellers');
    app.state.findQuick = ''; app.renderFind();
    app.prepPicks(null); app.load(JSON.parse(JSON.stringify(data))); app.prepPicks(JSON.parse(JSON.stringify(picksData)));
  });
  await check('the Walmart browser snippet writes lines store_picks.py can read', () => {
    const snippet = fs.readFileSync(path.join(site, '../scraper/browser/walmart-capture.js'), 'utf8');
    const ss = new Map();
    const nd = { props: { pageProps: { initialData: { searchResult: { aggregatedCount: 3, paginationV2: { maxPage: 1 }, itemStacks: [{ items: [
      { usItemId: '111', name: 'LEGO "Cozy" Plants | Ages 9+', sellerName: 'Walmart.com', priceInfo: { linePrice: '$22.96', wasPrice: '$29.99' }, badges: { flags: [{ key: 'BESTSELLER' }], groups: [{ members: [{ key: 'LOW_INVENTORY' }] }] }, annualEventV2: true, averageRating: 4.7, numberOfReviews: 150, category: { categoryPathId: '0:4171:4186:9' } },
      { usItemId: '222', name: 'Sponsored Thing', isSponsoredFlag: true, priceInfo: { linePrice: '$5.00' } },
      { usItemId: '333', name: 'Marketplace Doll', sellerName: 'Some Shop', priceInfo: { linePrice: '$1,049.00' } },
      { usItemId: '444', name: 'Some Game - PlayStation 5', sellerName: 'Walmart.com', esrb: 'Mature 17+', priceInfo: { linePrice: '$29.00' } }] }] } } } } };
    const ctx = vm.createContext({ document: { getElementById: () => ({ textContent: JSON.stringify(nd) }) }, location: { href: 'https://www.walmart.com/shop/toy-shop/toptoys?page=2' },
      sessionStorage: { getItem: (k) => (ss.has(k) ? ss.get(k) : null), setItem: (k, v) => ss.set(k, String(v)) }, URL, JSON });
    vm.runInContext(snippet, ctx);
    const first = vm.runInContext("walmartCapture('wm-top-toys')", ctx).split('\n');
    assert.equal(first[0], '#list wm-top-toys page=2 count=3 maxPage=1');
    assert.equal(first.length, 5, 'sponsored listings are skipped');
    assert.equal(first[4], '#esrb 444:M', 'video game ratings are written on their own line');
    assert.equal(first[1], '111|22.96|29.99|W|4171:4186|BLE|4.7|150|LEGO ″Cozy″ Plants Ages 9+');
    assert.equal(first[2], '333|1049.00||M|||||Marketplace Doll');
    assert(first.slice(1, 4).every((l) => l.split('|').length === 9));
    assert.deepEqual(vm.runInContext("walmartCapture('wm-deals-toys')", ctx).split('\n').slice(1), ['=111', '=333', '=444', '#esrb 444:M'], 'products are saved once, then repeated by id');
  });
  await check('names are escaped everywhere they are shown', () => {
    app.state.lists = app.normalizeLists(null);
    const p = app.addPerson({ name: '<img src=x onerror=alert(1)>' });
    app.addGift(p.id, 'needoh-nice-cube');
    app.state.listView = p.id; app.renderLists();
    assert(!element('#list-main').innerHTML.includes('<img src=x'));
    assert(!app.giftCard(app.byId['needoh-nice-cube']).includes('<img src=x'));
  });
  await check('data from before product types and hot lists still renders every page', () => {
    // A gifts.json written by the older scraper: no types, no hot lists, no estimates.
    const old = JSON.parse(fs.readFileSync(path.join(site, 'data/gifts.json'), 'utf8'));
    delete old.types; delete old.hot_lists;
    old.items.forEach((it) => { delete it.type; delete it.lists; delete it.price_est; });
    app.load(old);
    app.state.browse = Object.assign(app.state.browse, { type: '', list: '', q: '' });
    app.renderFindPrefs(); app.renderFind(); app.renderLists(); app.renderFilters(); app.renderBrowse(); app.renderDeals(); app.renderStores();
    assert.equal(element('#type-browser').innerHTML, '');
    assert.equal(element('#type-browser').hidden, true, 'no empty type panel');
    assert(!element('#filters').innerHTML.includes('id="f-list"'), 'no hot-list filter without hot lists');
    assert(element('#browse-table tbody').innerHTML.includes('data-open'));
    app.openDrawer(old.items[0].id);
    assert(!element('#drawer').innerHTML.includes('On these 2026 lists'));
    app.load(JSON.parse(fs.readFileSync(path.join(site, 'data/gifts.json'), 'utf8')));
  });
  console.log(`\n${checks} checks passed.`);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
