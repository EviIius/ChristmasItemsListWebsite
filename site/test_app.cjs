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
    get items() { return ITEMS; }, get byId() { return BYID; },
  };
})();`), context);

const data = JSON.parse(fs.readFileSync(path.join(site, 'data/gifts.json'), 'utf8'));
const { app } = context;
app.load(data);

let checks = 0;
async function check(label, fn) { await fn(); console.log('PASS ' + label); checks += 1; }
const base = { who: '', age: 10, budget: 100, interests: [], hot: false, deals: false, live: false };
const withLive = (id, price, extra = {}) => Object.assign(app.byId[id], { price, price_status: 'live', price_retailer: 'target', price_url: 'https://www.target.com/p/x/-/A-1', price_checked_at: new Date().toISOString() }, extra);

(async () => {
  await check('every gift has the fields the site needs', () => {
    for (const it of app.items) {
      assert(it.id && it.name && it.emoji && it.blurb && it.search, it.id);
      assert(it.ages[0] >= 1 && it.ages[1] <= 30 && it.ages[0] <= it.ages[1], it.id);
      assert(it.typical > 0 && it.stores.length >= 2, it.id);
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
    const it = app.byId['needoh-nice-cube'];
    assert.equal(app.priceInfo(it).kind, 'typical');
    withLive('needoh-nice-cube', 7.49);
    assert.equal(app.priceInfo(it).kind, 'live');
    assert(app.dealInfo(it) && Math.abs(app.dealInfo(it).save - 2.5) < 1e-9);
    withLive('needoh-nice-cube', 9.79);
    assert.equal(app.dealInfo(it), null, 'a 2% dip is not a deal');
    withLive('needoh-nice-cube', 7.49, { price_checked_at: new Date(Date.now() - 5 * 864e5).toISOString() });
    assert.equal(app.dealInfo(it), null, 'old prices are not deals');
    assert(app.findResults(Object.assign({}, base, { deals: true })).every((x) => app.dealInfo(x)));
    delete it.price; it.price_status = 'typical';
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
    app.state.browse.q = 'needoh'; app.renderBrowse(); assert(element('#browse-sub').textContent.startsWith('3 of') && element('#browse-table tbody').innerHTML.includes('data-open="needoh-shapes"'));
    app.state.browse.q = '';
    app.renderDeals(); assert(element('#dates').innerHTML.includes('Black Friday'));
    app.state.storeQ = 'squishmallow'; app.renderStores(); assert(element('#store-results').innerHTML.includes('searchTerm=squishmallow'));
    app.openDrawer('gta-vi'); assert(element('#drawer').innerHTML.includes('Rated M (Mature 17+)'));
    app.renderFreshness(); assert(element('#freshness-text').textContent.includes('typical prices'));
    assert(app.statusHtml().includes('exact product pages'));
    app.state.lists = app.normalizeLists(null); app.state.listView = null; app.renderLists();
    assert(element('#list-main').innerHTML.includes('Start from an example'));
    app.sharedModal({ v: 1, n: 'Eve', items: [{ n: 'Prize', u: 'javascript:alert(1)' }] });
    assert(element('#modal').innerHTML.includes('Prize') && !element('#modal').innerHTML.includes('javascript:'), 'no script links in the shared-list preview');
  });
  await check('names are escaped everywhere they are shown', () => {
    app.state.lists = app.normalizeLists(null);
    const p = app.addPerson({ name: '<img src=x onerror=alert(1)>' });
    app.addGift(p.id, 'needoh-nice-cube');
    app.state.listView = p.id; app.renderLists();
    assert(!element('#list-main').innerHTML.includes('<img src=x'));
    assert(!app.giftCard(app.byId['needoh-nice-cube']).includes('<img src=x'));
  });
  console.log(`\n${checks} checks passed.`);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
