/* Christmas Gift Finder: gift ideas for ages 1–30, store prices, and a Christmas list per person. No build step. */
(() => {
  'use strict';
  const CFG = window.SITE_CONFIG || {};
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const money = (n) => (n == null || !Number.isFinite(+n) ? '—' : '$' + (Math.round(n * 100) % 100 === 0
    ? Math.round(n).toLocaleString('en-US') : (+n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })));
  const uid = () => Math.random().toString(36).slice(2, 10);
  const store = {
    get(k, d) { try { const v = localStorage.getItem('xmas:' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('xmas:' + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
    del(k) { try { localStorage.removeItem('xmas:' + k); } catch (e) { /* ignore */ } },
  };

  // ------------------------------------------------------------------ constants
  const AGE_BANDS = [
    { id: '1-2', label: '1–2', lo: 1, hi: 2, age: 2 },
    { id: '3-5', label: '3–5', lo: 3, hi: 5, age: 4 },
    { id: '6-8', label: '6–8', lo: 6, hi: 8, age: 7 },
    { id: '9-12', label: '9–12', lo: 9, hi: 12, age: 10 },
    { id: '13-17', label: '13–17', lo: 13, hi: 17, age: 15 },
    { id: '18-24', label: '18–24', lo: 18, hi: 24, age: 21 },
    { id: '25-30', label: '25–30', lo: 25, hi: 30, age: 27 },
  ];
  const TILE = { baby: 'frost', toys: 'cranberry', plush: 'plum', squishy: 'frost', building: 'gold', videogames: 'pine', consoles: 'pine',
    cards: 'gold', tech: 'pine', arts: 'cranberry', stem: 'frost', books: 'cocoa', games: 'cocoa', outdoor: 'pine', beauty: 'plum',
    fashion: 'cocoa', room: 'plum', kitchen: 'cocoa', collectibles: 'gold', giftcards: 'cranberry' };
  const MARKS = ['#c4122f', '#1d7a4c', '#2a65b3', '#8b3fa3', '#cf6a0a', '#0e8585', '#b2367c', '#5f6b16'];
  const BUDGET_ANY = 700;
  const DEFAULT_FIND = { who: '', age: 9, budget: 100, interests: [], hot: false, deals: false, live: false };
  const STATUS = { idea: 'Idea', bought: 'Bought', wrapped: 'Wrapped' };
  const NEXT_STATUS = { idea: 'bought', bought: 'wrapped', wrapped: 'idea' };
  const MARK_PATH = 'M 18 8 C 60 2 150 2 186 7 C 197 9 199 24 198 50 C 197 80 196 92 182 95 C 130 99 60 99 16 94 C 3 91 1 75 2 50 C 3 22 5 11 22 6 C 40 2 62 3 80 6';
  const QUICK = ['NeeDoh', 'Squishmallows', 'squishy dumpling', 'LEGO Pokémon', 'Switch 2 games', 'PS5 games', 'Pokémon cards', 'KPop Demon Hunters', 'stocking stuffers', 'gift cards'];
  const GROUPS = [['big', 'The big four'], ['games', 'Games and Pokémon'], ['toys', 'Toys, LEGO and squishies'], ['books', 'Books, crafts and handmade'],
    ['style', 'Beauty, clothes, shoes and sports'], ['warehouse', 'Warehouse clubs']];
  const EXAMPLE = { name: '', age: 10, budget: 150, interests: ['squishies', 'plush', 'lego', 'switch', 'playstation'], note: '' };
  const GUIDE = {
    '1-2': ['Big, chunky toys only. Anything small enough to fit through a toilet-paper tube is a choking risk.',
      'Skip toys with loose button batteries or small magnets; check that battery doors screw shut.',
      'Board books, push toys, stacking toys and music toys get the most use. Look for a volume switch.'],
    '3-5': ['Toys marked 3+ often have small parts. If there\'s a baby in the house, keep those out of reach.',
      'Pretend play (kitchens, dollhouses, vehicles) and building (DUPLO, MAGNA-TILES) last the longest.',
      'Character toys from Bluey, PAW Patrol and Mario are safe bets this year.'],
    '6-8': ['Peak age for LEGO, Pokémon, interactive pets and squishies.',
      'Video games rated E (Everyone) fit this age. E10+ games are meant for 10 and up.',
      'Craft kits and science kits work best when there\'s a grown-up free to help on Christmas Day.'],
    '9-12': ['Tweens care about what\'s trending: NeeDoh and squishies, KPop Demon Hunters, Pokémon cards and Switch 2 games.',
      'E10+ games fit this age. T (Teen) games are rated for 13 and up.',
      'Two or three small trending things often land better than one big gift they didn\'t ask for.'],
    '13-17': ['Teens often prefer choosing for themselves: gift cards, earbuds and room upgrades are safe.',
      'M-rated games like Grand Theft Auto VI are rated for 17 and up; check with a parent first.',
      'Ask a sibling or friend what they\'ve been talking about. It beats guessing.'],
    '18-24': ['Practical upgrades land well: kitchen gear for a first apartment, better earbuds, a nicer version of something they use daily.',
      'Experiences (concert tickets, a class, a trip) and gift cards never go unused.'],
    '25-30': ['Think upgrades and hobbies: kitchen gear, display LEGO, a new game or console, cozy home things.',
      'If you\'re unsure, ask for their wish list; most adults have one.'],
  };

  // ------------------------------------------------------------------ data and state
  let DATA = null; let ITEMS = []; let BYID = {}; let RET = {}; let INT = {}; let TYPES = {}; let HOT = {}; let CATS = {};
  let PICKS = null; let PICK_BY_ID = {}; let PICKS_BY_GIFT = {};
  function normalizeLists(raw) {
    const out = { version: 1, people: [], shortlist: [] };
    if (!raw || typeof raw !== 'object') return out;
    out.shortlist = Array.isArray(raw.shortlist) ? raw.shortlist.filter((x) => typeof x === 'string') : [];
    out.people = (Array.isArray(raw.people) ? raw.people : []).filter((p) => p && p.name).map((p, i) => ({
      id: String(p.id || uid()), name: String(p.name).slice(0, 40), age: Number.isFinite(+p.age) && p.age !== null && p.age !== '' ? clamp(Math.round(+p.age), 1, 30) : null,
      budget: Number.isFinite(+p.budget) && p.budget !== null && p.budget !== '' ? Math.max(0, +p.budget) : null,
      interests: Array.isArray(p.interests) ? p.interests.filter((x) => typeof x === 'string') : [],
      color: MARKS.includes(p.color) ? p.color : MARKS[i % MARKS.length], note: String(p.note || '').slice(0, 500),
      items: (Array.isArray(p.items) ? p.items : []).filter((x) => x && (x.gift || x.name)).map((x) => ({
        uid: String(x.uid || uid()), gift: x.gift ? String(x.gift) : null, name: x.gift ? undefined : String(x.name).slice(0, 120),
        url: x.gift ? undefined : (/^https?:\/\//i.test(x.url || '') ? String(x.url) : undefined), store: x.gift ? undefined : (x.store || undefined),
        price: Number.isFinite(+x.price) && x.price !== null && x.price !== '' ? +x.price : undefined,
        paid: Number.isFinite(+x.paid) && x.paid !== null && x.paid !== '' ? +x.paid : null,
        status: STATUS[x.status] ? x.status : 'idea', note: String(x.note || '').slice(0, 300), added: x.added || new Date().toISOString(),
      })),
    }));
    return out;
  }
  const state = {
    find: Object.assign({}, DEFAULT_FIND, store.get('find', {})),
    lists: normalizeLists(store.get('lists', null)),
    listView: store.get('listView', null),
    browse: { q: '', interest: '', type: '', list: '', age: '', max: '', store: '', hot: false, live: false, sort: 'name', dir: 1 }, typesOpen: true,
    shown: 9,
    picks: { band: '', type: '', show: '', max: '', sort: 'rank', q: '', shown: 24 },
    storeQ: '',
    lastAdded: null,
  };
  state.find.interests = Array.isArray(state.find.interests) ? state.find.interests : [];
  const saveFind = () => store.set('find', state.find);
  function saveLists() { store.set('lists', state.lists); updateListCount(); }

  // ------------------------------------------------------------------ prices
  const retName = (r) => (RET[r] || {}).name || r || 'Store';
  function priceInfo(it) {
    if (it.price != null && ['live', 'stale', 'unavailable'].includes(it.price_status)) {
      return { value: it.price, kind: it.price_status, retailer: it.price_retailer, url: it.price_url, at: it.price_checked_at };
    }
    return { value: it.typical, kind: 'typical' };
  }
  const priceOf = (it) => priceInfo(it).value;
  function freshLive(it) {
    const p = priceInfo(it);
    if (p.kind !== 'live') return false;
    const age = Date.now() - new Date(p.at).getTime();
    return Number.isFinite(age) && age >= 0 && age <= 72 * 36e5;
  }
  function dealInfo(it) {
    if (!freshLive(it)) return null;
    const save = it.typical - it.price;
    if (save >= Math.max(1, it.typical * 0.08)) return { save, pct: save / it.typical };
    return null;
  }
  function searchUrl(retailer, q) {
    const r = RET[retailer];
    if (!r) return '#';
    return r.search ? r.search.replace('{q}', encodeURIComponent(q)) : r.home;
  }
  function ago(iso) {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (!Number.isFinite(s)) return '';
    if (s < 90) return 'just now';
    if (s < 5400) return `${Math.round(s / 60)} min ago`;
    if (s < 129600) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} days ago`;
  }
  function fmtDate(iso, withTime = true) {
    const d = new Date(iso);
    if (!Number.isFinite(d.getTime())) return '—';
    return d.toLocaleString('en-US', withTime ? { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' } : { month: 'short', day: 'numeric' });
  }

  // ------------------------------------------------------------------ matching
  const ageText = (it) => (it.ages[0] <= 1 && it.ages[1] >= 30 ? 'any age' : it.ages[1] >= 30 ? `ages ${it.ages[0]}+` : `ages ${it.ages[0]}–${it.ages[1]}`);
  const ageLabel = (a) => `${[8, 11, 18].includes(a) ? 'an' : 'a'} ${a}-year-old`;
  const budgetOf = (p) => (p.budget >= BUDGET_ANY ? Infinity : p.budget);
  function ageFit(it, age) {
    const [lo, hi] = it.ages;
    if (age >= lo && age <= hi) return 2;
    if (age >= lo - 1 && age <= hi + 1) return 1;
    return 0;
  }
  function scoreGift(it, p) {
    const fit = ageFit(it, p.age);
    if (!fit) return -1;
    const price = priceOf(it);
    const budget = budgetOf(p);
    if (price > budget) return -1;
    const deal = dealInfo(it);
    if (p.hot && !it.tags.includes('hot')) return -1;
    if (p.deals && !deal) return -1;
    if (p.live && priceInfo(it).kind !== 'live') return -1;
    let s = fit === 2 ? 20 : 4;
    s += Math.max(0, 10 - (it.ages[1] - it.ages[0]) / 3);
    if (p.interests.length) {
      const n = it.interests.filter((i) => p.interests.includes(i)).length;
      if (!n) return -1;
      s += 18 + 8 * Math.min(n, 3);
    } else if (it.category === 'giftcards') s -= 8;
    if (it.tags.includes('hot')) s += 9;
    if (it.pick) s -= 10; // store best sellers come after the hand-picked gifts that fit as well
    if (it.tags.includes('new')) s += 4;
    if (deal) s += 6 + Math.min(10, deal.pct * 40);
    if (Number.isFinite(budget)) s += 6 * Math.min(1, price / Math.max(budget, 1));
    return s;
  }
  function findResults(p = state.find) {
    return ITEMS.map((it) => ({ it, s: scoreGift(it, p) })).filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s || priceOf(a.it) - priceOf(b.it)).map((x) => x.it);
  }
  const profileOf = (person) => Object.assign({}, DEFAULT_FIND, { who: person.id, age: person.age || DEFAULT_FIND.age,
    budget: person.budget || BUDGET_ANY, interests: person.interests.slice() });

  // ------------------------------------------------------------------ lists
  const person = (id) => state.lists.people.find((p) => p.id === id);
  const onLists = (giftId) => state.lists.people.filter((p) => p.items.some((x) => x.gift === giftId));
  const inShortlist = (giftId) => state.lists.shortlist.includes(giftId);
  const initial = (name) => (String(name).trim()[0] || '?').toUpperCase();
  function addPerson(data) {
    const used = new Set(state.lists.people.map((p) => p.color));
    const p = normalizeLists({ people: [Object.assign({ color: MARKS.find((c) => !used.has(c)) || MARKS[state.lists.people.length % MARKS.length] }, data, { items: [] })] }).people[0];
    state.lists.people.push(p);
    saveLists();
    return p;
  }
  function addGift(personId, giftId) {
    const p = person(personId);
    if (!p || !BYID[giftId] || p.items.some((x) => x.gift === giftId)) return false;
    const g = BYID[giftId];
    p.items.push(Object.assign({ uid: uid(), gift: giftId, paid: null, status: 'idea', note: '', added: new Date().toISOString() },
      g.pick ? { name: g.name, url: g.price_url || (g.offers[0] || {}).url || '' } : {}));
    state.lastAdded = { gift: giftId, person: personId };
    state.lists.shortlist = state.lists.shortlist.filter((g) => g !== giftId);
    saveLists();
    return true;
  }
  function removeGift(personId, giftId) {
    const p = person(personId);
    if (!p) return false;
    const before = p.items.length;
    p.items = p.items.filter((x) => x.gift !== giftId);
    saveLists();
    return p.items.length < before;
  }
  function toggleShortlist(giftId) {
    const s = state.lists.shortlist;
    state.lists.shortlist = s.includes(giftId) ? s.filter((g) => g !== giftId) : s.concat(giftId);
    saveLists();
    return state.lists.shortlist.includes(giftId);
  }
  function addCustom(personId, d) {
    const p = person(personId);
    if (!p || !d.name) return null;
    const x = { uid: uid(), gift: null, name: String(d.name).slice(0, 120), url: /^https?:\/\//i.test(d.url || '') ? d.url : undefined,
      store: storeFromUrl(d.url) || undefined, price: Number.isFinite(+d.price) && d.price !== '' ? +d.price : undefined,
      paid: null, status: 'idea', note: String(d.note || '').slice(0, 300), added: new Date().toISOString() };
    p.items.push(x);
    saveLists();
    return x;
  }
  function storeFromUrl(url) {
    let host = '';
    try { host = new URL(url).hostname.toLowerCase(); } catch (e) { return null; }
    const hit = Object.entries(RET).find(([, r]) => (r.hosts || []).some((h) => host === h || host.endsWith('.' + h)));
    return hit ? hit[0] : null;
  }
  function itemInfo(x) {
    const g = x.gift ? BYID[x.gift] : null;
    if (g) {
      const p = priceInfo(g);
      const where = p.kind === 'live' ? g.price_retailer : (g.offers[0] || {}).retailer || g.stores[0];
      const url = p.kind === 'live' && g.price_url ? g.price_url : (g.offers.find((o) => o.retailer === where) || {}).url || searchUrl(where, g.search);
      return { name: g.name, emoji: g.emoji, tile: TILE[g.category] || 'pine', price: x.paid ?? p.value, current: p.value, kind: p.kind, store: where, url, gift: g };
    }
    let host = '';
    try { host = x.url ? new URL(x.url).hostname.replace(/^www\./, '') : ''; } catch (e) { host = ''; }
    return { name: x.name || 'Gift', emoji: '🎁', tile: 'cranberry', price: x.paid ?? x.price ?? null, current: x.price ?? null, kind: 'custom',
      store: x.store || (host ? 'host:' + host : 'other'), url: x.url || null, gift: null, host };
  }
  const storeLabel = (s, info) => (s && s.startsWith('host:') ? s.slice(5) : s === 'other' ? 'Any store' : retName(s)) || (info && info.host) || 'Store';
  function totals(p) {
    let planned = 0; let spent = 0; let done = 0;
    for (const x of p.items) {
      const v = itemInfo(x).price || 0;
      planned += v;
      if (x.status !== 'idea') { spent += v; done += 1; }
    }
    return { planned, spent, done, count: p.items.length };
  }
  const listCount = () => state.lists.people.reduce((n, p) => n + p.items.length, 0);

  // ------------------------------------------------------------------ sharing
  const b64 = {
    enc(bytes) { let s = ''; bytes.forEach((b) => { s += String.fromCharCode(b); }); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); },
    dec(str) { const s = atob(str.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((str.length + 3) % 4)); return Uint8Array.from(s, (c) => c.charCodeAt(0)); },
  };
  async function pipe(bytes, stream) {
    const out = new Response(new Blob([bytes]).stream().pipeThrough(stream));
    return new Uint8Array(await out.arrayBuffer());
  }
  function sharePayload(p, hideStatus) {
    const items = p.items.map((x) => {
      const o = x.gift ? { g: x.gift } : { n: x.name, u: x.url, p: x.price, s: x.store };
      if (!hideStatus && x.status !== 'idea') o.st = x.status[0];
      if (x.note) o.no = x.note;
      return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== ''));
    });
    return { v: 1, n: p.name, a: p.age, c: p.color, i: p.interests, items };
  }
  async function encodeShare(obj) {
    const bytes = new TextEncoder().encode(JSON.stringify(obj));
    if (typeof CompressionStream === 'function') {
      try { return 'z' + b64.enc(await pipe(bytes, new CompressionStream('deflate-raw'))); } catch (e) { /* fall through */ }
    }
    return 'j' + b64.enc(bytes);
  }
  async function decodeShare(str) {
    const kind = str[0]; let bytes = b64.dec(str.slice(1));
    if (kind === 'z') bytes = await pipe(bytes, new DecompressionStream('deflate-raw'));
    else if (kind !== 'j') throw new Error('unknown share format');
    const obj = JSON.parse(new TextDecoder().decode(bytes));
    if (!obj || obj.v !== 1 || !obj.n || !Array.isArray(obj.items)) throw new Error('not a Christmas list');
    return obj;
  }
  function fromShare(obj) {
    const full = { s: 'idea', b: 'bought', w: 'wrapped' };
    return {
      name: obj.n, age: obj.a, color: obj.c, interests: obj.i || [], note: '',
      items: obj.items.map((o) => ({ gift: o.g || null, name: o.n, url: o.u, price: o.p, store: o.s, status: full[o.st] || 'idea', note: o.no || '' })),
    };
  }
  function listText(p, hideStatus) {
    const lines = [`${p.name}'s Christmas list${p.age ? ` (age ${p.age})` : ''}`];
    for (const x of p.items) {
      const info = itemInfo(x);
      let line = `- ${info.name}`;
      if (info.price) line += `, about ${money(info.price)}`;
      if (!hideStatus && x.status !== 'idea') line += ` [${STATUS[x.status]}]`;
      if (x.note) line += ` (${x.note})`;
      lines.push(line);
      if (info.url && info.url !== '#') lines.push(`  ${info.url}`);
    }
    return lines.join('\n');
  }

  // ------------------------------------------------------------------ small components
  const markerSvg = (draw) => `<svg class="marker${draw ? ' draw' : ''}" viewBox="0 0 200 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="100" d="${MARK_PATH}"/></svg>`;
  function tile(it, cls = '') {
    const seal = it.tags.includes('hot') ? '<span class="seal">Hot this year</span>' : it.tags.includes('new') ? '<span class="seal new">New this year</span>' : '';
    return `<button class="tile ${cls}" type="button" data-open="${esc(it.id)}" data-c="${TILE[it.category] || 'pine'}" tabindex="-1" aria-hidden="true"><span class="tag">${esc(it.emoji)}</span>${seal}</button>`;
  }
  function priceBlock(it, size = '') {
    const p = priceInfo(it); const deal = dealInfo(it);
    let note;
    if (p.kind === 'live') note = `<div class="price-note live">${esc(retName(p.retailer))} price, ${esc(ago(p.at))}</div>`;
    else if (p.kind === 'stale') note = `<div class="price-note stale">${esc(retName(p.retailer))} price from ${esc(fmtDate(p.at, false))}. Check the store.</div>`;
    else if (p.kind === 'unavailable') note = `<div class="price-note stale">Sold out at ${esc(retName(p.retailer))} when last checked</div>`;
    else if (it.price_est) note = `<div class="price-note est">Estimated price${it.range ? `, about ${money(it.range[0])} to ${money(it.range[1])}` : ''}. Check the store.</div>`;
    else note = `<div class="price-note">${it.range ? `Typical price; usually ${money(it.range[0])} to ${money(it.range[1])}` : 'Typical price'}</div>`;
    const was = deal ? `<span class="save">${money(deal.save)} below usual</span>` : '';
    return `<div><div class="price-row"><span class="price ${size}">${money(p.value)}</span>${was}</div>${note}</div>`;
  }
  function storeButton(it) {
    const p = priceInfo(it);
    if (p.kind === 'live' && p.url) return `<a class="btn btn-sm btn-ghost store-link" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(retName(p.retailer))}</a>`;
    const r = (it.offers[0] || {}).retailer || it.stores[0];
    const url = (it.offers[0] || {}).url || searchUrl(r, it.search);
    return `<a class="btn btn-sm btn-ghost store-link" href="${esc(url)}" target="_blank" rel="noopener" title="Open ${esc(retName(r))}">${esc(retName(r))}</a>`;
  }
  function giftCard(it, opts = {}) {
    const people = onLists(it.id);
    const mark = (state.find.who && people.find((p) => p.id === state.find.who)) || people[0];
    const draw = mark && state.lastAdded && state.lastAdded.gift === it.id && state.lastAdded.person === mark.id;
    const star = inShortlist(it.id);
    const who = people.length ? `On ${people.map((p) => p.name).join(' and ')}'s list. ` : '';
    return `<article class="gift" data-gift="${esc(it.id)}"${mark ? ` style="--mark:${mark.color}"` : ''}>
      ${tile(it)}
      <div class="gift-body">
        <div class="circled">
          ${mark ? markerSvg(draw) : ''}
          ${people.length ? `<div class="on-list" aria-hidden="true">${people.slice(0, 4).map((p) => `<span class="initial" style="--mark:${p.color}">${esc(initial(p.name))}</span>`).join('')}</div>` : ''}
          <button class="gift-title" type="button" data-open="${esc(it.id)}">${esc(it.name)}</button>
          <div class="gift-meta">${who ? `<span class="visually-hidden">${esc(who)}</span>` : ''}${esc(brandAges(it))}${it.rating ? `, rated ${esc(it.rating)}` : ''}</div>
          ${priceBlock(it, opts.compact ? 'sm' : '')}
        </div>
        ${opts.compact ? '' : `<p class="gift-blurb">${esc(it.blurb)}</p>`}
        <div class="gift-actions">
          <button class="btn btn-sm btn-accent" type="button" data-add="${esc(it.id)}" aria-haspopup="menu">Add to list</button>
          <button class="btn btn-sm btn-ghost" type="button" data-star="${esc(it.id)}" aria-pressed="${star}" title="${star ? 'Remove from shortlist' : 'Save to shortlist'}" aria-label="${star ? 'Remove from shortlist' : 'Save to shortlist'}">${star ? '★' : '☆'}</button>
          ${opts.compact ? '' : storeButton(it)}
        </div>
      </div>
    </article>`;
  }
  const avatar = (p, cls = '') => `<span class="avatar ${cls}" style="--mark:${p.color}" aria-hidden="true">${esc(initial(p.name))}</span>`;
  const andList = (xs) => (xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`);
  function interestNames(ids, max = 4) {
    const names = ids.slice(0, max).map((i) => (INT[i] || {}).short || (INT[i] || {}).label || i);
    if (ids.length > max) names.push(`${ids.length - max} more`);
    return andList(names);
  }

  // ------------------------------------------------------------------ FIND
  function renderFindPrefs() {
    const f = state.find;
    $('#for-who').innerHTML = `<option value="">Anyone (set it below)</option>` + state.lists.people.map((p) =>
      `<option value="${esc(p.id)}" ${f.who === p.id ? 'selected' : ''}>${esc(p.name)}${p.age ? `, ${p.age}` : ''}</option>`).join('');
    const who = person(f.who);
    const using = $('#using');
    using.hidden = !who;
    if (who) using.textContent = `Using ${who.name}'s age, interests and budget. Changes here don't change ${who.name}'s list.`;
    $('#age').value = f.age;
    $('#age-out').textContent = f.age;
    $('#age-bands').innerHTML = AGE_BANDS.map((b) => `<button type="button" class="band ${f.age >= b.lo && f.age <= b.hi ? 'is-on' : ''}" data-band="${b.id}">${b.label}</button>`).join('');
    $('#budget').value = Math.min(f.budget, BUDGET_ANY);
    $('#budget-out').textContent = f.budget >= BUDGET_ANY ? 'Any amount' : money(f.budget);
    $('#interests').innerHTML = Object.entries(INT).map(([k, v], i) =>
      `<button type="button" class="ichip ${i >= 8 && !f.interests.includes(k) ? 'extra' : ''}" data-interest="${esc(k)}" aria-pressed="${f.interests.includes(k)}"><span class="e" aria-hidden="true">${esc(v.emoji)}</span>${esc(v.label)}</button>`).join('')
      + `<button type="button" class="btn btn-sm more-interests" data-more-interests>${$('.prefs').classList.contains('show-all') ? 'Fewer interests' : `More interests (${Object.keys(INT).length - 8 - f.interests.filter((k) => Object.keys(INT).indexOf(k) >= 8).length})`}</button>`;
    const bits = [`Age ${f.age}`, f.budget >= BUDGET_ANY ? 'any budget' : `up to ${money(f.budget)}`];
    if (f.interests.length) bits.push(`into ${interestNames(f.interests, 3)}`);
    $('#prefs-summary').textContent = bits.join(', ');
    $('#toggles').innerHTML = '<legend>Only show</legend>' + [['hot', 'Hot this year'], ['deals', 'Selling below the usual price'], ['live', 'Store price checked recently']]
      .map(([k, l]) => `<label class="check"><input type="checkbox" data-toggle="${k}" ${f[k] ? 'checked' : ''}> ${l}</label>`).join('');
  }
  function renderFind() {
    const f = state.find;
    const res = findResults(f);
    const who = person(f.who);
    $('#find-h').textContent = who ? `Ideas for ${who.name}` : `Gift ideas for ${ageLabel(f.age)}`;
    const bits = [`age ${f.age}`];
    if (f.budget < BUDGET_ANY) bits.push(`up to ${money(f.budget)}`);
    if (f.interests.length) bits.push(`into ${interestNames(f.interests, 3)}`);
    $('#find-sub').textContent = `${res.length} of ${ITEMS.length} ideas fit ${bits.join(', ')}. Gifts that are hot this year or on sale rank higher.`;
    const top = res.slice(0, state.shown);
    $('#top-picks').innerHTML = top.length ? top.map((it) => giftCard(it)).join('')
      : `<div class="empty"><strong>Nothing matches yet.</strong><span>Try a higher budget, fewer interests, or turn off the "Only show" filters.</span><button class="btn btn-sm" type="button" data-reset-find>Clear all filters</button></div>`;
    $('#more-ideas').innerHTML = res.length > state.shown ? `<button class="btn more-btn" type="button" data-more>Show ${Math.min(12, res.length - state.shown)} more ideas (${res.length - state.shown} left)</button>` : '';
    const topIds = new Set(top.map((it) => it.id));
    const stock = res.filter((it) => priceOf(it) <= 25 && !topIds.has(it.id)).slice(0, 8);
    $('#stocking-h').hidden = !stock.length;
    $('#stocking').innerHTML = stock.map((it) => giftCard(it, { compact: true })).join('');
    renderStoreHot(f);
    $('#age-guide').innerHTML = guideHtml(f.age, f.interests);
    state.lastAdded = null;
  }
  function guideHtml(age, interests) {
    const band = AGE_BANDS.find((b) => age >= b.lo && age <= b.hi);
    const tips = GUIDE[band.id] || [];
    const squish = (interests.includes('squishies') || age <= 12)
      ? '<li class="safety">Skip squishies and sensory toys filled with water beads; several have been recalled. Never microwave a squishy.</li>' : '';
    return `<h3>Shopping for ages ${band.label}</h3><ul>${tips.map((t) => `<li>${esc(t)}</li>`).join('')}${squish}</ul>`;
  }

  // ------------------------------------------------------------------ LISTS
  function renderLists() {
    const people = state.lists.people;
    if (state.listView && !['shortlist', 'trip'].includes(state.listView) && !person(state.listView)) state.listView = null;
    if (!state.listView && people.length) state.listView = people[0].id;
    const v = state.listView;
    $('#people').innerHTML = `<h3>People</h3>
      ${people.map((p) => { const t = totals(p); return `<button type="button" class="person-row ${v === p.id ? 'is-on' : ''}" data-view-list="${esc(p.id)}">${avatar(p)}<span class="who"><b>${esc(p.name)}</b><span>${p.age ? `Age ${p.age}` : 'No age set'}</span></span><span class="count">${t.done}/${t.count}</span></button>`; }).join('')}
      <button type="button" class="person-row" data-new-person><span class="avatar ghost" aria-hidden="true">+</span><span class="who"><b>Add a person</b><span>Kids, teens, adults</span></span></button>
      <div class="sep"></div>
      <button type="button" class="person-row ${v === 'shortlist' ? 'is-on' : ''}" data-view-list="shortlist"><span class="avatar ghost" aria-hidden="true">★</span><span class="who"><b>Shortlist</b><span>Saved, not assigned yet</span></span><span class="count">${state.lists.shortlist.length}</span></button>
      <button type="button" class="person-row ${v === 'trip' ? 'is-on' : ''}" data-view-list="trip"><span class="avatar ghost" aria-hidden="true">🛒</span><span class="who"><b>Shopping trip</b><span>Everything left to buy, by store</span></span></button>
      <div class="sep"></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;padding:0 4px"><button class="btn btn-sm" type="button" data-backup>Back up</button><button class="btn btn-sm" type="button" data-restore>Restore</button></div>`;
    const main = $('#list-main');
    if (v === 'shortlist') main.innerHTML = shortlistPane();
    else if (v === 'trip') main.innerHTML = tripPane();
    else if (person(v)) main.innerHTML = personPane(person(v));
    else main.innerHTML = welcomePane();
  }
  function welcomePane() {
    return `<div class="panel" style="display:grid;gap:14px;justify-items:start">
      <h3>Start a list for each person you're shopping for</h3>
      <p class="sub">Add their age and what they're into, and the site suggests gifts that fit. Circle gifts for them from any page with Add to list, then mark them bought and wrapped as you go.</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn btn-accent" type="button" data-new-person>Add a person</button>
      <button class="btn" type="button" data-example>Start from an example</button></div>
      <p class="hint">The example is a 10-year-old into squishies, plush, LEGO, Switch and PlayStation. You'll type their name.</p></div>`;
  }
  function personPane(p) {
    const t = totals(p);
    const budget = p.budget || 0;
    const scale = Math.max(budget, t.planned, 1);
    const over = budget && t.spent > budget;
    const ideas = findResults(profileOf(p)).filter((it) => !p.items.some((x) => x.gift === it.id)).slice(0, 6);
    const desc = [p.age ? `Age ${p.age}` : null, p.interests.length ? `into ${interestNames(p.interests, 5)}` : null].filter(Boolean).join(', ');
    return `<div class="list-head"><div class="ident">${avatar(p, 'lg')}<div><h2>${esc(p.name)}'s list</h2><p class="sub">${esc(desc || 'Add an age and interests to get matched ideas.')}${p.note ? `. ${esc(p.note)}` : ''}</p></div></div>
      <div class="list-actions"><button class="btn btn-sm" type="button" data-edit-person="${esc(p.id)}">Edit</button><button class="btn btn-sm" type="button" data-share="${esc(p.id)}">Share</button><button class="btn btn-sm" type="button" data-print>Print</button><button class="btn btn-sm btn-pine" type="button" data-find-for="${esc(p.id)}">Find ideas for ${esc(p.name)}</button></div></div>
      <div class="panel budget">
        <div class="budget-bar ${over ? 'over' : ''}" role="img" aria-label="${esc(`Bought ${money(t.spent)} of ${budget ? money(budget) + ' budget' : 'no set budget'}; ${money(t.planned)} planned`)}"><span class="planned" style="width:${(100 * t.planned / scale).toFixed(1)}%"></span><span class="spent" style="width:${(100 * t.spent / scale).toFixed(1)}%"></span></div>
        <div class="budget-legend"><span>Bought <b>${money(t.spent)}</b></span><span>Planned <b>${money(t.planned)}</b></span><span>${budget ? `Budget <b>${money(budget)}</b>${t.planned > budget ? ` <span class="chip bad">${money(t.planned - budget)} over</span>` : ` <span class="chip good">${money(budget - t.planned)} left</span>`}` : `<button class="linkish" type="button" data-edit-person="${esc(p.id)}">Set a budget</button>`}</span><span>${t.done} of ${t.count} bought</span></div>
      </div>
      <div class="list-rows">${p.items.length ? p.items.map((x) => listRow(p, x)).join('')
        : `<div class="empty"><strong>Nothing on ${esc(p.name)}'s list yet.</strong><span>Use Add to list on any gift, or add something from any store.</span></div>`}</div>
      <div class="no-print"><button class="btn" type="button" data-custom="${esc(p.id)}">Add something from any store</button></div>
      ${ideas.length ? `<div class="no-print" style="display:grid;gap:12px"><h3 class="section-h">Ideas for ${esc(p.name)} <small>matched to ${p.age ? `age ${p.age}` : 'any age'}${p.interests.length ? ' and interests' : ''}</small></h3><div class="gift-grid compact">${ideas.map((it) => giftCard(it, { compact: true })).join('')}</div></div>` : ''}`;
  }
  function listRow(p, x) {
    const info = itemInfo(x);
    const where = info.url && info.url !== '#' ? `<a href="${esc(info.url)}" target="_blank" rel="noopener">${esc(storeLabel(info.store, info))}</a>` : esc(storeLabel(info.store, info));
    const priceText = info.current != null ? `${info.kind === 'typical' ? 'about ' : ''}${money(info.current)}` : 'price not set';
    return `<div class="lrow ${x.status !== 'idea' ? 'is-done' : ''}" data-uid="${esc(x.uid)}">
      <div class="mini" style="--tile:var(--tile-${info.tile})"><span aria-hidden="true">${esc(info.emoji)}</span></div>
      <div class="what">${info.gift ? `<button class="gift-title" type="button" data-open="${esc(info.gift.id)}" style="font-size:0.98rem">${esc(info.name)}</button>` : `<b>${esc(info.name)}</b>`}
        <span class="gift-meta">${priceText} at ${where}${x.note ? `. ${esc(x.note)}` : ''}</span></div>
      <div class="right">
        <label class="visually-hidden" for="paid-${esc(x.uid)}">Price paid for ${esc(info.name)}</label>
        <input class="paid" id="paid-${esc(x.uid)}" type="number" min="0" step="0.01" inputmode="decimal" placeholder="Paid" value="${x.paid ?? ''}" data-paid="${esc(p.id)}|${esc(x.uid)}" title="What you paid (optional)">
        <button class="status" type="button" data-s="${x.status}" data-status="${esc(p.id)}|${esc(x.uid)}" title="Change status">${STATUS[x.status]}</button>
        <button class="x" type="button" data-remove="${esc(p.id)}|${esc(x.uid)}" aria-label="Remove ${esc(info.name)}">✕</button>
      </div></div>`;
  }
  function shortlistPane() {
    const items = state.lists.shortlist.map((g) => BYID[g]).filter(Boolean);
    return `<div class="list-head"><div class="ident"><span class="avatar lg ghost" aria-hidden="true">★</span><div><h2>Shortlist</h2><p class="sub">Gifts you've saved but haven't given to anyone yet.</p></div></div></div>
      ${items.length ? `<div class="gift-grid">${items.map((it) => giftCard(it)).join('')}</div>` : '<div class="empty"><strong>No saved gifts yet.</strong><span>Tap the star on any gift to save it here.</span></div>'}`;
  }
  function tripPane() {
    const groups = {};
    for (const p of state.lists.people) {
      for (const x of p.items) {
        if (x.status !== 'idea') continue;
        const info = itemInfo(x);
        (groups[info.store] = groups[info.store] || []).push({ p, x, info });
      }
    }
    const keys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length);
    const total = keys.reduce((n, k) => n + groups[k].reduce((m, r) => m + (r.info.price || 0), 0), 0);
    const body = keys.map((k) => {
      const rows = groups[k]; const sum = rows.reduce((m, r) => m + (r.info.price || 0), 0);
      const home = RET[k] ? `<a class="btn btn-sm" href="${esc(RET[k].home)}" target="_blank" rel="noopener">Open ${esc(RET[k].name)}</a>` : '';
      return `<div class="panel store-group"><h3>${esc(storeLabel(k, rows[0].info))} <small>${rows.length} gift${rows.length > 1 ? 's' : ''}, about ${money(sum)}</small></h3>
        <div class="rows">${rows.map((r) => `<div class="row"><div><b>${esc(r.info.name)}</b> <span class="for-tag" style="--mark:${r.p.color}">for ${esc(r.p.name)}</span><div class="cell-sub">${r.info.current != null ? `${r.info.kind === 'typical' ? 'about ' : ''}${money(r.info.current)}` : ''}${r.info.url && r.info.url !== '#' ? ` <a href="${esc(r.info.url)}" target="_blank" rel="noopener">Open listing</a>` : ''}</div></div>
          <button class="btn btn-sm" type="button" data-status="${esc(r.p.id)}|${esc(r.x.uid)}" data-s="idea">Mark bought</button></div>`).join('')}</div>${home}</div>`;
    }).join('');
    return `<div class="list-head"><div class="ident"><span class="avatar lg ghost" aria-hidden="true">🛒</span><div><h2>Shopping trip</h2><p class="sub">Everything still marked Idea, grouped by the store with the best known price${keys.length ? `: about ${money(total)} in all` : ''}.</p></div></div></div>
      ${keys.length ? body : '<div class="empty"><strong>Nothing left to buy.</strong><span>Gifts marked Idea on anyone\'s list show up here, grouped by store.</span></div>'}`;
  }

  // ------------------------------------------------------------------ BROWSE
  const BROWSE_COLS = [
    { key: 'name', label: 'Gift', sort: (it) => it.name.toLowerCase() },
    { key: 'type', label: 'Type', sort: (it) => typeLabel(it).toLowerCase() },
    { key: 'age', label: 'Ages', sort: (it) => it.ages[0] * 100 + it.ages[1] },
    { key: 'interests', label: 'Into' },
    { key: 'price', label: 'Price', sort: (it) => priceOf(it), cls: 'r' },
    { key: 'where', label: 'Where' },
    { key: 'add', label: '' },
  ];
  function typeOptions(cur) {
    const used = new Set(ITEMS.map((it) => it.type));
    return Object.entries(CATS).map(([ck, c]) => {
      const ts = Object.entries(TYPES).filter(([k, t]) => t.category === ck && used.has(k));
      if (!ts.length) return '';
      return `<optgroup label="${esc(c.label)}"><option value="cat:${esc(ck)}" ${cur === 'cat:' + ck ? 'selected' : ''}>All ${esc(c.label)}</option>${ts.map(([k, t]) => `<option value="${esc(k)}" ${cur === k ? 'selected' : ''}>${esc(t.label)}</option>`).join('')}</optgroup>`;
    }).join('');
  }
  function typeBrowserHtml() {
    const b = state.browse; const count = {}; const catCount = {};
    ITEMS.forEach((it) => { if (!TYPES[it.type]) return; count[it.type] = (count[it.type] || 0) + 1; catCount[it.category] = (catCount[it.category] || 0) + 1; });
    const nTypes = Object.keys(count).length; const nCats = Object.keys(catCount).length;
    if (!nTypes) return '';
    const cur = b.type.startsWith('cat:') ? (CATS[b.type.slice(4)] || {}).label : (TYPES[b.type] || {}).label;
    const head = `<div class="tb-head"><h3>Product types</h3><span class="hint">${plural(nTypes, 'type')} in ${plural(nCats, 'group')}</span>${b.type ? `<button type="button" class="btn btn-sm" data-type="">Show every type</button>` : ''}<button type="button" class="btn btn-sm btn-ghost tb-toggle" data-types-toggle aria-expanded="${state.typesOpen}">${state.typesOpen ? 'Hide types' : 'Choose a type'}</button></div>`;
    if (!state.typesOpen) return head + (cur ? `<p class="tb-current">Showing: <b>${esc(cur)}</b></p>` : '');
    return head + `<div class="tb-grid">${Object.entries(CATS).filter(([ck]) => catCount[ck]).map(([ck, c]) => {
      const ts = Object.entries(TYPES).filter(([k, t]) => t.category === ck && count[k]);
      return `<div class="tb-cat" data-c="${TILE[ck] || 'pine'}"><button type="button" class="tb-cat-title" data-type="cat:${esc(ck)}" aria-pressed="${b.type === 'cat:' + ck}">${esc(c.label)} <span class="n">${catCount[ck]}</span></button>
        <div class="tb-types">${ts.map(([k, t]) => `<button type="button" class="tchip" data-type="${esc(k)}" aria-pressed="${b.type === k}"><span aria-hidden="true">${esc(t.emoji)}</span>${esc(t.label)}<span class="n">${count[k]}</span></button>`).join('')}</div></div>`;
    }).join('')}</div>`;
  }
  function renderFilters() {
    const b = state.browse;
    const opts = (pairs, cur) => pairs.map(([v, l]) => `<option value="${esc(v)}" ${String(cur) === String(v) ? 'selected' : ''}>${esc(l)}</option>`).join('');
    $('#filters').innerHTML = `
      <div class="f"><label for="f-q">Search</label><input type="search" id="f-q" placeholder="NeeDoh, LEGO, Zelda…" value="${esc(b.q)}"></div>
      <div class="f"><label for="f-type">Type</label><select id="f-type"><option value="">Any type</option>${typeOptions(b.type)}</select></div>
      ${Object.keys(HOT).length ? `<div class="f"><label for="f-list">Hot list</label><select id="f-list"><option value="">Any gift</option>${opts([['hot', 'On any 2026 hot list']].concat(Object.entries(HOT).map(([k, h]) => [k, h.short])), b.list)}</select></div>` : ''}
      <div class="f"><label for="f-interest">Into</label><select id="f-interest"><option value="">Anything</option>${opts(Object.entries(INT).map(([k, v]) => [k, v.label]), b.interest)}</select></div>
      <div class="f"><label for="f-age">Age</label><input type="number" id="f-age" min="1" max="30" placeholder="Any" value="${esc(b.age)}"></div>
      <div class="f"><label for="f-max">Price</label><select id="f-max"><option value="">Any price</option>${opts([[10, 'Up to $10'], [25, 'Up to $25'], [50, 'Up to $50'], [100, 'Up to $100'], [250, 'Up to $250'], [500, 'Up to $500']], b.max)}</select></div>
      <div class="f"><label for="f-store">Store</label><select id="f-store"><option value="">Any store</option>${opts(Object.entries(RET).map(([k, v]) => [k, v.name]), b.store)}</select></div>
      <label class="check"><input type="checkbox" id="f-hot" ${b.hot ? 'checked' : ''}> Hot this year</label>
      <label class="check"><input type="checkbox" id="f-live" ${b.live ? 'checked' : ''}> Store price checked</label>`;
  }
  function browseRows() {
    const b = state.browse; const q = b.q.trim().toLowerCase();
    const rows = ITEMS.filter((it) => {
      if (q && !`${it.name} ${it.brand} ${it.blurb} ${typeLabel(it)} ${it.interests.map((i) => (INT[i] || {}).label).join(' ')}`.toLowerCase().includes(q)) return false;
      if (b.type && (b.type.startsWith('cat:') ? it.category !== b.type.slice(4) : it.type !== b.type)) return false;
      if (b.list && (b.list === 'hot' ? !it.tags.includes('hot') : !it.lists.includes(b.list))) return false;
      if (b.interest && !it.interests.includes(b.interest)) return false;
      if (b.age !== '' && Number.isFinite(+b.age) && !ageFit(it, +b.age)) return false;
      if (b.max && priceOf(it) > +b.max) return false;
      if (b.store && !it.stores.includes(b.store) && !it.offers.some((o) => o.retailer === b.store)) return false;
      if (b.hot && !it.tags.includes('hot')) return false;
      if (b.live && priceInfo(it).kind !== 'live') return false;
      return true;
    });
    const col = BROWSE_COLS.find((c) => c.key === b.sort && c.sort) || BROWSE_COLS[0];
    rows.sort((x, y) => { const a = col.sort(x); const c = col.sort(y); return (a > c ? 1 : a < c ? -1 : 0) * b.dir; });
    return rows;
  }
  function renderBrowse() {
    const rows = browseRows(); const b = state.browse;
    const tb = typeBrowserHtml(); $('#type-browser').innerHTML = tb; $('#type-browser').hidden = !tb;
    const what = b.type ? (b.type.startsWith('cat:') ? (CATS[b.type.slice(4)] || {}).label : (TYPES[b.type] || {}).label) : '';
    const inType = PICKS && b.type ? PICKS.items.filter((x) => (b.type.startsWith('cat:') ? x.category === b.type.slice(4) : x.type === b.type)).length : 0;
    $('#browse-sub').innerHTML = `${rows.length} of ${ITEMS.length} gift ideas${what ? ` in ${esc(what)}` : ''}. Select a row for details, prices and every store that sells it.`
      + (inType ? ` <button class="linkish" type="button" data-picks-type="${esc(b.type)}">See ${inType} best seller${inType > 1 ? 's' : ''} and deal${inType > 1 ? 's' : ''} from ${esc(andList(Object.values(PICKS.stores).map((x) => x.name)))} in this type</button>` : '');
    $('#browse-table thead').innerHTML = '<tr>' + BROWSE_COLS.map((c) => c.sort
      ? `<th class="${c.cls || ''}" aria-sort="${b.sort === c.key ? (b.dir > 0 ? 'ascending' : 'descending') : 'none'}"><button type="button" data-sort="${c.key}">${c.label}</button></th>`
      : `<th class="${c.cls || ''}">${c.label ? c.label : '<span class="visually-hidden">Add</span>'}</th>`).join('') + '</tr>';
    $('#browse-table tbody').innerHTML = rows.map((it) => {
      const p = priceInfo(it); const people = onLists(it.id);
      return `<tr class="is-clickable" data-open="${esc(it.id)}" tabindex="0" aria-label="${esc(it.name)}">
        <td><div class="cell-title"><span aria-hidden="true">${esc(it.emoji)}</span>${esc(it.name)}${it.tags.includes('hot') ? ` <span class="chip gold" title="${esc(it.lists.map((l) => HOT[l].short).join(', '))}">Hot</span>` : ''}${people.map((x) => ` <span class="initial" style="--mark:${x.color};font-size:.9rem">${esc(initial(x.name))}</span>`).join('')}</div><div class="cell-sub">${esc(it.brand)}</div></td>
        <td class="cell-sub type-cell">${esc(typeLabel(it))}</td>
        <td class="num" style="white-space:nowrap">${esc(ageText(it))}</td>
        <td class="cell-sub">${esc(it.interests.slice(0, 2).map((i) => (INT[i] || {}).label || i).join(', '))}</td>
        <td class="r"><div class="num" style="font-weight:700">${money(p.value)}</div><div class="cell-sub">${p.kind === 'live' ? `${esc(retName(p.retailer))}, ${esc(ago(p.at))}` : p.kind === 'typical' ? 'typical' : 'check store'}</div></td>
        <td class="cell-sub">${esc(it.stores.slice(0, 3).map(retName).join(', '))}</td>
        <td><button class="btn btn-sm" type="button" data-add="${esc(it.id)}" aria-haspopup="menu">Add</button></td></tr>`;
    }).join('') || '<tr><td colspan="7"><div class="empty">No gifts match. Clear a filter or two.</div></td></tr>';
    $('#browse-cards').innerHTML = rows.map((it) => giftCard(it, { compact: true })).join('');
  }

  // ------------------------------------------------------------------ DEALS & DATES
  function thanksgiving(year) { const d = new Date(year, 10, 1); return new Date(year, 10, 1 + ((4 - d.getDay() + 7) % 7) + 21); }
  function secondMonday(year, month) { const d = new Date(year, month, 1); return new Date(year, month, 1 + ((1 - d.getDay() + 7) % 7) + 7); }
  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const daysUntil = (date, now = new Date()) => Math.round((startOfDay(date) - startOfDay(now)) / 864e5);
  function christmasDate(now = new Date()) {
    const m = ((CFG.christmas || {}).month || 12) - 1; const day = (CFG.christmas || {}).day || 25;
    const x = new Date(now.getFullYear(), m, day);
    return daysUntil(x, now) < 0 ? new Date(now.getFullYear() + 1, m, day) : x;
  }
  function keyDates(now = new Date()) {
    const xmas = christmasDate(now); const y = xmas.getFullYear(); const tg = thanksgiving(y);
    return [
      { label: 'Black Friday', date: new Date(y, 10, tg.getDate() + 1), tip: 'Biggest sale day for toys, consoles and TVs.' },
      { label: 'Cyber Monday', date: new Date(y, 10, tg.getDate() + 4), tip: 'Online deals, often matching Black Friday.' },
      { label: 'Green Monday', date: secondMonday(y, 11), tip: 'A second wave of online sales, about when standard shipping gets tight.' },
      { label: 'Christmas Eve', date: new Date(y, 11, 24), tip: 'Last-minute pickup in store. Many stores close early.' },
      { label: 'Christmas', date: xmas, tip: 'The big day.', big: true },
    ];
  }
  function whenText(n) { return n === 0 ? 'Today' : n === 1 ? 'Tomorrow' : n < 0 ? 'Passed' : `In ${n} days`; }
  function renderDeals() {
    renderPicksPanel();
    const now = new Date();
    $('#dates').innerHTML = keyDates(now).map((d) => { const n = daysUntil(d.date, now);
      return `<div class="date-card ${d.big ? 'is-big' : ''} ${n >= 0 && n <= 7 && !d.big ? 'is-soon' : ''} ${n < 0 ? 'is-past' : ''}"><span class="when">${esc(d.label)}</span><span class="d">${esc(d.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }))}</span><span class="when">${whenText(n)}. ${esc(d.tip)}</span></div>`; }).join('');
    const deals = ITEMS.filter((it) => !isPick(it)).map((it) => ({ it, d: dealInfo(it) })).filter((x) => x.d).sort((a, b) => b.d.pct - a.d.pct);
    const live = DATA.live_prices || 0;
    const bf = daysUntil(keyDates(now)[0].date, now);
    const bfNote = bf === 0 ? ' Black Friday is today.' : bf === 1 ? ' Black Friday is tomorrow.' : bf > 1 && bf <= 21 ? ` Black Friday is in ${bf} days.` : '';
    $('#deal-list').innerHTML = deals.length ? `<div class="rows">${deals.map(({ it, d }) => `<div class="row"><div><button class="gift-title" type="button" data-open="${esc(it.id)}">${esc(it.emoji)} ${esc(it.name)}</button><div class="cell-sub">${esc(retName(it.price_retailer))} has it for ${money(it.price)}, ${money(d.save)} (${Math.round(d.pct * 100)}%) below the usual ${money(it.typical)}${it.regular ? `; the store lists it as was ${money(it.regular)}` : ''}.</div></div><button class="btn btn-sm btn-accent" type="button" data-add="${esc(it.id)}" aria-haspopup="menu">Add to list</button></div>`).join('')}</div>`
      : `<div class="empty"><strong>${live ? 'No tracked gift is below its usual price right now.' : 'No store prices have been read yet.'}</strong><span>${live ? `The price checker read ${live} store price${live > 1 ? 's' : ''}; none are at least 8% under the usual price.${bfNote}` : 'Every price on the site is a typical price until the price checker runs. It runs on its own twice a day; you can also start it now.'}</span>${live ? '' : '<button class="btn btn-sm btn-accent" type="button" data-rescrape>Refresh prices</button>'}</div>`;
    const big = ITEMS.filter((it) => !isPick(it) && it.typical >= 150).sort((a, b) => b.typical - a.typical);
    $('#big-list').innerHTML = `<div class="rows">${big.map((it) => { const p = priceInfo(it); return `<div class="row"><div><button class="gift-title" type="button" data-open="${esc(it.id)}">${esc(it.emoji)} ${esc(it.name)}</button><div class="cell-sub">${p.kind === 'live' ? `${esc(retName(p.retailer))} ${money(p.value)}, ${esc(ago(p.at))}; usually ${money(it.typical)}` : `Usually ${money(it.typical)}${it.range ? ` (${money(it.range[0])} to ${money(it.range[1])})` : ''}`}</div></div><span class="price sm">${money(p.value)}</span></div>`; }).join('')}</div>`;
    const tracked = ITEMS.filter((it) => !isPick(it)).flatMap((it) => it.offers.map((o) => ({ it, o })));
    const byStore = {}; tracked.forEach((t) => { (byStore[t.o.retailer] = byStore[t.o.retailer] || []).push(t); });
    const sc = (DATA.scrape || {}).by_retailer || {};
    $('#tracked-list').innerHTML = `<p class="hint" style="margin:-6px 0 8px">${tracked.length} store links across ${Object.keys(byStore).length} stores. Add more with <code>scraper/add_link.py</code> or find them with <code>scraper/hotlists.py</code> (see README).</p>`
      + Object.entries(byStore).sort((a, b) => b[1].length - a[1].length).map(([r, ts]) => {
        const s = sc[r]; const linkOnly = RET[r] && RET[r].price_check === false; const byBrowser = RET[r] && RET[r].price_check === 'browser';
        const read = ts.map((x) => x.o.checked_at).filter(Boolean).sort().pop();
        const status = linkOnly ? 'links only, no price check' : byBrowser ? (read ? `read in a browser ${ago(read)}` : 'read in a browser, not yet') : s && s.ok ? `${s.ok} read last run` : s && s.blocked ? 'blocked last run' : s ? 'none read last run' : 'not checked yet';
        return `<details class="store-links"><summary><b>${esc(retName(r))}</b> <span class="cell-sub">${ts.length} link${ts.length > 1 ? 's' : ''}, ${esc(status)}</span></summary><div class="rows">${ts.map(({ it, o }) => `<div class="row"><div><button class="gift-title" type="button" data-open="${esc(it.id)}" style="font-size:.95rem">${esc(it.name)}</button><div class="cell-sub">${o.label ? `${esc(o.label)}: ` : ''}${offerStatus(o)}</div></div><a class="btn btn-sm" href="${esc(o.url)}" target="_blank" rel="noopener">Open</a></div>`).join('')}</div></details>`;
      }).join('');
    const listCount = {}; ITEMS.forEach((it) => it.lists.forEach((l) => { listCount[l] = (listCount[l] || 0) + 1; }));
    $('#hot-sources').innerHTML = `<div class="rows">${Object.entries(HOT).filter(([k]) => listCount[k]).map(([k, h]) => `<div class="row"><div><a href="${esc(h.url)}" target="_blank" rel="noopener"><b>${esc(h.name)}</b></a><div class="cell-sub">${listCount[k]} gift${listCount[k] > 1 ? 's' : ''} in this catalog${h.kind === 'guide' ? ', from a 2026 gift guide' : ''}</div></div><button class="btn btn-sm" type="button" data-show-list="${esc(k)}">Show them</button></div>`).join('')}</div>`;
  }
  function offerStatus(o) {
    if (!o.price && RET[o.retailer] && RET[o.retailer].price_check === false) return `<span title="${esc(RET[o.retailer].price_note || '')}">link only; ${esc(RET[o.retailer].name)} isn't price-checked automatically</span>`;
    if (o.price && !o.stale) return `<span style="color:var(--good);font-weight:600">${money(o.price)}${o.in_stock === false ? ', sold out' : ''}</span>, ${esc(ago(o.checked_at))}${o.verification_method === 'browser' ? ', read in a browser' : ''}${o.marketplace_only ? ' (outside seller only)' : ''}`;
    if (o.price) return `last read ${money(o.price)} on ${esc(fmtDate(o.checked_at, false))}${o.error ? `; latest try: ${esc(shortError(o))}` : ''}`;
    return esc(o.error === 'not checked yet' ? 'not checked yet' : shortError(o));
  }
  const shortError = (o) => (o.blocked ? 'the store showed a bot check' : String(o.error || 'not read').replace(/^\w+Error: /, '').slice(0, 90));

  // ------------------------------------------------------------------ STORE PICKS (store lists read in a browser)
  const PICK_FLAGS = { 'best-seller': ['Best seller', 'gold'], deal: ['Holiday deal', 'red'], rollback: ['Rollback', 'red'],
    reduced: ['Reduced price', 'red'], clearance: ['Clearance', 'red'], 'low-stock': ['Low stock', 'warn'] };
  const ESRB_TEXT = { E: 'rated E for Everyone', E10: 'rated E10+', T: 'rated T for Teen', M: 'rated M (Mature 17+)', 'RP-M': 'rating pending, likely M (17+)', RP: 'ESRB rating pending', AO: 'rated AO (18+)' };
  const PICK_SORTS = [['rank', "Store's ranking"], ['pct', 'Biggest discount'], ['low', 'Lowest price'], ['reviews', 'Most reviews']];
  const PICK_MAX = [['', 'Any price'], ['10', '$10 and under'], ['25', '$25 and under'], ['50', '$50 and under'], ['100', '$100 and under'], ['200', '$200 and under']];
  const optionList = (pairs, cur) => pairs.map(([v, l]) => `<option value="${esc(v)}"${String(cur) === String(v) ? ' selected' : ''}>${esc(l)}</option>`).join('');
  function prepPicks(data) {
    PICKS = data && Array.isArray(data.items) && data.items.length ? data : null;
    PICK_BY_ID = {}; PICKS_BY_GIFT = {};
    if (!PICKS) return;
    PICKS.lists = PICKS.lists || {}; PICKS.stores = PICKS.stores || {};
    PICKS.items = PICKS.items.filter((x) => x && x.id && x.name && x.url && /^https:\/\//.test(x.url) && Array.isArray(x.ages));
    PICKS.items.forEach((x) => {
      const ranks = Object.values(x.rank || {});
      x.score = (ranks.length ? Math.min(...ranks) : 999) - Math.min(4, (x.lists || []).length) * 2;
      PICK_BY_ID[x.id] = x;
      if (x.gift) (PICKS_BY_GIFT[x.gift] = PICKS_BY_GIFT[x.gift] || []).push(x);
    });
  }
  const pickList = (k) => (PICKS && PICKS.lists[k]) || {};
  // Store best sellers count as gift ideas too. A pick that is already one of the catalog's gifts stays with that gift;
  // the rest become gift ideas of their own, and the same product at several stores becomes one idea with each store's link.
  function pickItems() {
    if (!PICKS) return [];
    const typeInt = {};
    DATA.items.forEach((it) => (it.interests || []).forEach((i) => { const m = (typeInt[it.type] = typeInt[it.type] || {}); m[i] = (m[i] || 0) + 1; }));
    const groups = new Map();
    PICKS.items.forEach((x) => {
      if (x.gift || !TYPES[x.type]) return;
      const key = x.name.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
      if (groups.has(key)) groups.get(key).push(x); else groups.set(key, [x]);
    });
    return [...groups.values()].map((xs) => {
      xs.sort((a, b) => (a.price ?? 1e9) - (b.price ?? 1e9));
      const x = xs[0]; const t = TYPES[x.type];
      const best = xs.flatMap((q) => Object.entries(q.rank || {}).map(([k, n]) => ({ q, k, n }))).sort((a, b) => a.n - b.n)[0];
      const where = best ? `#${best.n} on ${pickStore(best.q)}'s ${pickList(best.k).short || pickList(best.k).name || 'list'}` : `On ${pickStore(x)}'s lists`;
      const stars = x.rating ? ` ${x.rating} stars${x.reviews ? ` from ${Number(x.reviews).toLocaleString('en-US')} reviews` : ''}.` : '';
      const id = 'pick:' + x.id;
      PICKS_BY_GIFT[id] = xs;
      return {
        id, pick: x.id, name: x.name, emoji: t.emoji || '🎁', category: x.category, type: x.type,
        interests: Object.entries(typeInt[x.type] || {}).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([i]) => i),
        ages: x.ages.slice(), typical: x.was || x.price || 0, tags: ['store'], blurb: `${where}.${stars}`, search: x.name,
        stores: [...new Set(xs.map((q) => q.store))],
        offers: xs.map((q) => ({ retailer: q.store, retailer_name: pickStore(q), url: q.url, sku: q.sku, price: q.price, checked_at: q.checked_at, label: 'Store best seller' })),
        price: x.price, price_retailer: x.store, price_url: x.url, price_status: x.price ? 'live' : 'typical', price_checked_at: x.checked_at,
        regular: x.was || undefined, history: [], lists: [],
      };
    });
  }
  const isPick = (it) => !!it.pick;
  const brandAges = (it) => (it.brand ? `${it.brand}, ${ageText(it)}` : ageText(it).replace(/^./, (c) => c.toUpperCase()));
  const pickStore = (x) => ((PICKS && PICKS.stores[x.store]) || {}).name || retName(x.store);
  const pickOnSale = (x) => !!x.was || (x.flags || []).some((f) => ['deal', 'rollback', 'reduced', 'clearance'].includes(f));
  const pickAges = (x) => (x.ages[0] <= 1 && x.ages[1] >= 30 ? 'any age' : x.ages[1] >= 30 ? `ages ${x.ages[0]}+` : x.ages[0] === x.ages[1] ? `age ${x.ages[0]}` : `ages ${x.ages[0]}–${x.ages[1]}`);
  const pickHolders = (x) => state.lists.people.filter((pp) => pp.items.some((i) => i.url === x.url));
  function pickRows(f) {
    if (!PICKS) return [];
    const band = AGE_BANDS.find((b) => b.id === f.band);
    const q = String(f.q || '').trim().toLowerCase();
    const max = f.max ? +f.max : Infinity;
    const rows = PICKS.items.filter((x) => {
      if (band && (x.ages[1] < band.lo || x.ages[0] > band.hi)) return false;
      if (f.type && (f.type.startsWith('cat:') ? x.category !== f.type.slice(4) : x.type !== f.type)) return false;
      if (f.show === 'sale' && !pickOnSale(x)) return false;
      if (f.show.startsWith('list:') && !(x.lists || []).includes(f.show.slice(5))) return false;
      if (f.show.startsWith('flag:') && !(x.flags || []).includes(f.show.slice(5))) return false;
      if (max < Infinity && !(x.price != null && x.price <= max)) return false;
      if (q && !`${x.name} ${(TYPES[x.type] || {}).label || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
    const by = { rank: (a, b) => a.score - b.score, pct: (a, b) => (b.pct || 0) - (a.pct || 0) || a.score - b.score,
      low: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9), reviews: (a, b) => (b.reviews || 0) - (a.reviews || 0) };
    return rows.sort(by[f.sort] || by.rank);
  }
  function pickCard(x) {
    const t = TYPES[x.type] || {};
    const top = Object.entries(x.rank || {}).filter(([k]) => pickList(k).short).sort((a, b) => a[1] - b[1])[0];
    const flags = (x.flags || []).filter((f) => PICK_FLAGS[f]).map((f) => `<span class="chip ${PICK_FLAGS[f][1]}">${esc(PICK_FLAGS[f][0])}</span>`).join('');
    const holders = pickHolders(x);
    const meta = [pickAges(x)];
    if (x.esrb) meta.push(ESRB_TEXT[x.esrb] || `ESRB ${x.esrb}`);
    if (x.rating) meta.push(`${x.rating} stars${x.reviews ? ` from ${x.reviews.toLocaleString('en-US')} reviews` : ''}`);
    if (x.seller === 'marketplace') meta.push('sold by a marketplace seller');
    return `<article class="pick" data-c="${esc(TILE[x.category] || 'pine')}">
      <div class="pick-top">${top ? `<span class="pick-rank" title="${esc(pickList(top[0]).name || '')}">#${esc(top[1])} ${esc(pickList(top[0]).short || '')}</span>` : ''}<span class="pick-type">${esc(t.emoji || '🎁')} ${esc(t.label || x.type)}</span></div>
      <a class="pick-name" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>
      <div class="gift-meta">${esc(meta.join(', '))}</div>
      <div class="price-row">${x.price != null ? `<span class="price sm">${money(x.price)}</span>` : '<span class="price-note">Price shown at the store</span>'}${x.was ? `<span class="was">${money(x.was)}</span><span class="save">${esc(x.pct)}% off</span>` : ''}</div>
      ${flags ? `<div class="chips">${flags}</div>` : ''}
      <div class="pick-actions">
        <button class="btn btn-sm btn-accent" type="button" data-add-pick="${esc(x.id)}" aria-haspopup="menu">${holders.length ? `On ${esc(holders[0].name)}'s list` : 'Add to list'}</button>
        ${x.gift && BYID[x.gift] ? `<button class="btn btn-sm" type="button" data-open="${esc(x.gift)}">Details</button>` : ''}
        <a class="btn btn-sm btn-ghost" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(pickStore(x))}</a>
      </div>
    </article>`;
  }
  function renderPicksPanel() {
    const panel = $('#picks-panel'); if (!panel) return;
    panel.hidden = !PICKS;
    if (!PICKS) return;
    const f = state.picks;
    const reads = Object.values(PICKS.lists).map((l) => l.captured_at).filter(Boolean).sort();
    const when = reads[0] || PICKS.captured_at; const days = (Date.now() - new Date(when).getTime()) / 864e5;
    const stores = Object.values(PICKS.stores).map((x) => x.name);
    const readOn = fmtDate(when) === fmtDate(PICKS.captured_at) ? fmtDate(when) : `${fmtDate(when)} to ${fmtDate(PICKS.captured_at)}`;
    $('#picks-h').textContent = `${andList(stores)} best sellers and deals`;
    $('#picks-sub').innerHTML = `${PICKS.items.length} gifts from ${stores.length > 1 ? `the stores' own lists: ${esc(andList(stores))} best sellers, top gifts and toys, best sellers for each age group, and deal pages. Read from the stores ${esc(readOn)}` : `${esc(stores[0])}'s own lists: its top gifts and top toys, best sellers for each age group and its deal pages. Read from the store ${esc(readOn)}`}${days > 3 ? `, <b class="stale-note">${Math.round(days)} days ago, so some of these deals have likely ended</b>` : ''}. Prices change fast this week, so check the store before you buy.`;
    const types = {}; const cats = {};
    PICKS.items.forEach((x) => { types[x.type] = (types[x.type] || 0) + 1; cats[x.category] = (cats[x.category] || 0) + 1; });
    const typeOpts = Object.keys(CATS).filter((c) => cats[c]).map((c) => `<optgroup label="${esc(CATS[c].label)}"><option value="cat:${esc(c)}"${f.type === `cat:${c}` ? ' selected' : ''}>All ${esc(CATS[c].label.toLowerCase())} (${cats[c]})</option>${Object.entries(TYPES).filter(([k, t]) => t.category === c && types[k]).map(([k, t]) => `<option value="${esc(k)}"${f.type === k ? ' selected' : ''}>${esc(t.label)} (${types[k]})</option>`).join('')}</optgroup>`).join('');
    const lists = Object.entries(PICKS.lists).filter(([, l]) => l.kind !== 'tracked' && l.short);
    const show = [['', 'Everything'], ['sale', 'On sale'], ['flag:best-seller', 'Best sellers'], ['flag:deal', 'Holiday deals']]
      .concat(lists.map(([k, l]) => [`list:${k}`, `${l.short} list`]));
    $('#picks-filters').innerHTML = `
      <div class="picks-who" role="group" aria-label="Who it's for">${[['', 'Every age']].concat(AGE_BANDS.map((b) => [b.id, `Ages ${b.label}`])).map(([v, l]) => `<button type="button" class="band ${f.band === v ? 'is-on' : ''}" data-pick-band="${esc(v)}" aria-pressed="${f.band === v}">${esc(l)}</button>`).join('')}</div>
      <div class="filters picks-f">
        <div class="f f-wide"><label for="pk-q">Search</label><input id="pk-q" type="search" value="${esc(f.q)}" placeholder="LEGO, Barbie, AirPods…" autocomplete="off"></div>
        <div class="f"><label for="pk-type">Type</label><select id="pk-type"><option value="">Every type</option>${typeOpts}</select></div>
        <div class="f"><label for="pk-show">Show</label><select id="pk-show">${optionList(show, f.show)}</select></div>
        <div class="f"><label for="pk-max">Price</label><select id="pk-max">${optionList(PICK_MAX, f.max)}</select></div>
        <div class="f"><label for="pk-sort">Sort</label><select id="pk-sort">${optionList(PICK_SORTS, f.sort)}</select></div>
      </div>`;
    renderPicks();
  }
  function renderPicks() {
    if (!PICKS || !$('#picks')) return;
    const rows = pickRows(state.picks);
    const shown = rows.slice(0, state.picks.shown);
    $('#picks-count').textContent = `${rows.length} of ${PICKS.items.length} shown`;
    $('#picks').innerHTML = shown.length ? shown.map(pickCard).join('')
      : '<div class="empty"><strong>Nothing here matches.</strong><span>Try another age group or type, or a higher price.</span><button class="btn btn-sm" type="button" data-picks-reset>Clear the filters</button></div>';
    $('#picks-more').innerHTML = rows.length > shown.length ? `<button class="btn more-btn" type="button" data-picks-more>Show ${Math.min(24, rows.length - shown.length)} more (${rows.length - shown.length} left)</button>` : '';
  }
  function renderStoreHot(f) {
    const box = $('#store-hot'); if (!box) return;
    const budget = f.budget < BUDGET_ANY ? f.budget : Infinity;
    const age = f.age;
    const forAge = (x) => {
      const r = Object.entries(x.rank || {}).filter(([k]) => { const l = pickList(k); return l.kind === 'age' && l.ages && age >= l.ages[0] && age <= l.ages[1]; }).map(([, n]) => n);
      return r.length ? Math.min(...r) : 1000 + x.score;
    };
    const rows = PICKS ? PICKS.items.filter((x) => x.ages[0] <= age && x.ages[1] >= age && x.price != null && x.price <= budget)
      .sort((a, b) => forAge(a) - forAge(b)).slice(0, 8) : [];
    box.hidden = !rows.length;
    if (!rows.length) { box.innerHTML = ''; return; }
    const band = AGE_BANDS.find((b) => age >= b.lo && age <= b.hi);
    const stores = andList(Object.values(PICKS.stores).map((x) => x.name));
    box.innerHTML = `<div class="store-hot-head"><h3 class="section-h">${esc(stores)}'s best sellers for ${esc(String(age))}-year-olds <small>from ${esc(stores)}'s own lists${budget < Infinity ? `, up to ${money(budget)}` : ''}</small></h3>
      <button class="btn btn-sm" type="button" data-picks-goto="${esc(band.id)}">See all for ages ${esc(band.label)}</button></div>
      <div class="pick-grid compact">${rows.map(pickCard).join('')}</div>`;
  }
  function openPickMenu(pickId, anchor) {
    const x = PICK_BY_ID[pickId]; if (!x) return;
    const m = $('#menu');
    menuTrigger = anchor;
    const ps = state.lists.people;
    m.innerHTML = `<div class="menu-title">Add ${esc(x.name.length > 34 ? x.name.slice(0, 32) + '…' : x.name)} to</div>
      ${ps.map((pp) => { const on = pp.items.some((i) => i.url === x.url);
        return `<button class="menu-item" role="menuitemcheckbox" aria-checked="${on}" type="button" data-pick-to="${esc(x.id)}|${esc(pp.id)}" style="--mark:${pp.color}">${avatar(pp)}${esc(pp.name)}${on ? '<span class="tick" aria-hidden="true">✓</span>' : ''}</button>`; }).join('')}
      ${ps.length ? '<div class="sep"></div>' : ''}
      <button class="menu-item" role="menuitem" type="button" data-new-person-pick="${esc(x.id)}"><span class="avatar ghost" aria-hidden="true">+</span>${ps.length ? 'New person…' : 'Add the first person…'}</button>`;
    placeMenu(m, anchor);
  }
  function togglePick(pickId, personId) {
    const x = PICK_BY_ID[pickId]; const pp = person(personId); if (!x || !pp) return;
    const idx = pp.items.findIndex((i) => i.url === x.url);
    if (idx >= 0) {
      const [gone] = pp.items.splice(idx, 1); saveLists();
      toast(`Removed from ${pp.name}'s list`, () => { pp.items.splice(idx, 0, gone); saveLists(); refresh(); });
    } else {
      addCustom(pp.id, { name: x.name, url: x.url, price: x.price ?? '', note: `${pickStore(x)} ${x.was ? `deal, usually ${money(x.was)}` : 'best seller'}` });
      toast(`Added to ${pp.name}'s list`);
    }
    refresh();
  }

  // ------------------------------------------------------------------ STORES
  function renderStores() {
    $('#store-quick').innerHTML = QUICK.map((q) => `<button class="chip frost" type="button" data-quick="${esc(q)}">${esc(q)}</button>`).join('');
    const q = state.storeQ.trim();
    $('#store-results').innerHTML = q ? GROUPS.map(([g, label]) => {
      const rs = Object.entries(RET).filter(([, r]) => r.group === g);
      if (!rs.length) return '';
      return `<div><h4>${esc(label)}</h4><div class="store-buttons">${rs.map(([k, r]) => `<a class="store-btn" href="${esc(searchUrl(k, q))}" target="_blank" rel="noopener">${esc(r.name)}${r.search ? '' : ' <span class="cell-sub">(store home)</span>'}</a>`).join('')}</div></div>`;
    }).join('') : '';
    const sc = (DATA.scrape || {}).by_retailer || {};
    const counts = {};
    ITEMS.forEach((it) => { if (!isPick(it)) it.offers.forEach((o) => { counts[o.retailer] = (counts[o.retailer] || 0) + 1; }); });
    $('#store-directory').innerHTML = GROUPS.map(([g, label]) => {
      const rs = Object.entries(RET).filter(([, r]) => r.group === g);
      return `<div class="dir-group"><h3>${esc(label)}</h3><div class="dir-grid">${rs.map(([k, r]) => {
        const s = sc[k]; const n = counts[k] || 0;
        const status = !n ? '<span class="chip">Search links</span>' : r.price_check === false ? `<span class="chip" title="${esc(r.price_note || '')}">${n} product links, no price check</span>` : r.price_check === 'browser' ? `<span class="chip good" title="${esc(r.price_note || '')}">${n} links, priced in a browser</span>` : s && s.ok ? `<span class="chip good">${s.ok} price${s.ok > 1 ? 's' : ''} read last run</span>` : s && s.blocked ? '<span class="chip warn">Blocked the last price check</span>' : s ? '<span class="chip warn">No prices read last run</span>' : `<span class="chip frost">${n} link${n > 1 ? 's' : ''} tracked</span>`;
        return `<div class="store-card"><h4>${esc(r.name)}</h4><p>${esc(r.good_for)}</p><div class="foot">${status}<a class="btn btn-sm" href="${esc(q ? searchUrl(k, q) : r.home)}" target="_blank" rel="noopener">${q && r.search ? 'Search' : 'Visit'}</a></div></div>`;
      }).join('')}</div></div>`;
    }).join('');
  }

  // ------------------------------------------------------------------ gift details drawer
  let drawerTrigger = null; let modalTrigger = null;
  function sparkline(hist, w = 280, h = 60) {
    if (!hist || hist.length < 2) return '';
    const ps = hist.map((x) => x[1]); const lo = Math.min(...ps); const hi = Math.max(...ps); const span = hi - lo || 1;
    const X = (i) => 4 + (i * (w - 8)) / (hist.length - 1); const Y = (p) => h - 6 - ((p - lo) * (h - 14)) / span;
    const d = hist.map((x, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(x[1]).toFixed(1)}`).join(' ');
    const last = hist[hist.length - 1];
    return `<div class="panel"><h3>Price history</h3><svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Lowest daily price from ${esc(hist[0][0])} to ${esc(last[0])}: low ${money(lo)}, high ${money(hi)}"><path class="area" d="${d} L${X(hist.length - 1)},${h} L${X(0)},${h} Z"/><path class="line" d="${d}"/><circle cx="${X(hist.length - 1)}" cy="${Y(last[1])}" r="3"/></svg><div class="cell-sub">Low ${money(lo)}, high ${money(hi)}, over ${hist.length} days with a price check</div></div>`;
  }
  function personToggles(it) {
    const ps = state.lists.people;
    return `<div class="person-toggles">${ps.map((p) => { const on = p.items.some((x) => x.gift === it.id);
      return `<button type="button" class="ptoggle" style="--mark:${p.color}" data-toggle-gift="${esc(it.id)}" data-person="${esc(p.id)}" aria-pressed="${on}">${avatar(p)}${esc(p.name)}${on ? ' ✓' : ''}</button>`; }).join('')}
      <button type="button" class="ptoggle plain" data-new-person-for="${esc(it.id)}">+ New person</button>
      <button type="button" class="ptoggle plain" data-star="${esc(it.id)}" aria-pressed="${inShortlist(it.id)}">${inShortlist(it.id) ? '★ On shortlist' : '☆ Shortlist'}</button></div>`;
  }
  function openDrawer(id) {
    const it = BYID[id]; if (!it) return;
    const dr = $('#drawer');
    if (dr.hidden) drawerTrigger = document.activeElement;
    const tracked = new Set(it.offers.map((o) => o.retailer));
    const others = it.stores.filter((s) => !tracked.has(s));
    dr.innerHTML = `<button class="btn btn-sm drawer-close" type="button" data-close-drawer>Close</button>
      ${tile(it, 'drawer-tile')}
      <div class="drawer-body">
        <div class="drawer-head"><h2 id="drawer-title">${esc(it.name)}</h2>
          <div class="gift-meta">${esc(brandAges(it))}${it.platforms ? `, for ${esc(it.platforms.join(', '))}` : ''}</div>
          <div class="chips" style="display:flex;gap:5px;flex-wrap:wrap">${it.type ? `<button type="button" class="chip frost" data-type="${esc(it.type)}" title="Browse every gift of this type">${esc((TYPES[it.type] || {}).emoji || '')} ${esc(typeLabel(it))}</button>` : ''}${it.rating ? `<span class="chip ${it.rating === 'M' ? 'bad' : 'frost'}">ESRB ${esc(it.rating)}</span>` : ''}${it.interests.map((i) => `<span class="chip">${esc((INT[i] || {}).label || i)}</span>`).join('')}</div>
        </div>
        ${priceBlock(it, 'lg')}
        <p>${esc(it.blurb)}</p>
        ${it.note ? `<div class="note-box">${esc(it.note)}</div>` : ''}
        ${it.lists.length ? `<div class="panel"><h3>On these 2026 lists</h3><ul class="cites">${it.lists.map((l) => `<li><a href="${esc(HOT[l].url)}" target="_blank" rel="noopener">${esc(HOT[l].name)}</a>${HOT[l].kind === 'guide' ? ' <span class="cell-sub">(gift guide)</span>' : ''}</li>`).join('')}</ul></div>` : ''}
        ${(PICKS_BY_GIFT[it.id] || []).map((x) => `<div class="panel"><h3>On ${esc(pickStore(x))}'s lists</h3><ul class="cites">${Object.entries(x.rank || {}).filter(([k]) => pickList(k).name).sort((a, b) => a[1] - b[1]).map(([k, n]) => `<li><a href="${esc(pickList(k).url || x.url)}" target="_blank" rel="noopener">${esc(pickList(k).name)}</a> <span class="cell-sub">#${esc(n)}</span></li>`).join('')}</ul>${(x.flags || []).filter((f) => PICK_FLAGS[f]).length ? `<div class="chips" style="margin-top:6px">${x.flags.filter((f) => PICK_FLAGS[f]).map((f) => `<span class="chip ${PICK_FLAGS[f][1]}">${esc(PICK_FLAGS[f][0])}</span>`).join('')}</div>` : ''}</div>`).join('')}
        <div class="panel"><h3>Put it on a list</h3>${personToggles(it)}</div>
        <div class="panel"><h3>Where to buy</h3>
          ${it.offers.length ? it.offers.map((o) => `<div class="offer"><div><b>${esc(o.retailer_name || retName(o.retailer))}</b>${o.label ? ` <span class="cell-sub">${esc(o.label)}</span>` : ''}<div class="cell-sub">${offerStatus(o)}</div>${o.marketplace ? `<div class="cell-sub">Outside seller ${esc(o.marketplace.seller)}: ${money(o.marketplace.price)}; returns can be harder</div>` : ''}${o.open_box ? `<div class="cell-sub">Open-box or used from ${money(o.open_box)}</div>` : ''}</div>
            <div class="right">${o.price ? `<span class="price sm">${money(o.price)}</span>` : ''}<a class="btn btn-sm" href="${esc(o.url)}" target="_blank" rel="noopener">Open</a></div></div>`).join('') : `<p class="hint">No exact product link is tracked yet, so the price above is the ${it.price_est ? 'estimated' : 'typical'} price.</p>`}
          ${others.length ? `<h4 style="margin:14px 0 6px">Search ${it.offers.length ? 'other stores' : 'the stores'}</h4><div class="store-buttons">${others.map((s) => `<a class="store-btn" href="${esc(searchUrl(s, it.search))}" target="_blank" rel="noopener">${esc(retName(s))}</a>`).join('')}</div>` : ''}
          <details style="margin-top:12px"><summary class="hint" style="cursor:pointer">Track this gift's price at another store</summary><p class="hint" style="margin-top:6px">Copy the product page link, then run <code>python3 scraper/add_link.py ${esc(it.id)} "LINK"</code> in the repository and push. The next price check reads it.</p></details>
        </div>
        ${sparkline(it.history)}
      </div>`;
    dr.hidden = false; $('#drawer-backdrop').hidden = false; dr.scrollTop = 0;
    $('.drawer-close', dr).focus();
  }
  function closeDrawer() {
    const was = !$('#drawer').hidden;
    $('#drawer').hidden = true; $('#drawer-backdrop').hidden = true;
    if (was && drawerTrigger && drawerTrigger.isConnected) drawerTrigger.focus();
  }

  // ------------------------------------------------------------------ menu, modal, toast
  let menuTrigger = null;
  function openAddMenu(giftId, anchor) {
    const it = BYID[giftId]; if (!it) return;
    const m = $('#menu');
    menuTrigger = anchor;
    const ps = state.lists.people;
    m.innerHTML = `<div class="menu-title">Add ${esc(it.name.length > 34 ? it.name.slice(0, 32) + '…' : it.name)} to</div>
      ${ps.map((p) => { const on = p.items.some((x) => x.gift === giftId);
        return `<button class="menu-item" role="menuitemcheckbox" aria-checked="${on}" type="button" data-toggle-gift="${esc(giftId)}" data-person="${esc(p.id)}" style="--mark:${p.color}">${avatar(p)}${esc(p.name)}${on ? '<span class="tick" aria-hidden="true">✓</span>' : ''}</button>`; }).join('')}
      ${ps.length ? '<div class="sep"></div>' : ''}
      <button class="menu-item" role="menuitem" type="button" data-new-person-for="${esc(giftId)}"><span class="avatar ghost" aria-hidden="true">+</span>${ps.length ? 'New person…' : 'Add the first person…'}</button>
      <button class="menu-item" role="menuitemcheckbox" aria-checked="${inShortlist(giftId)}" type="button" data-star="${esc(giftId)}"><span class="avatar ghost" aria-hidden="true">${inShortlist(giftId) ? '★' : '☆'}</span>${inShortlist(giftId) ? 'On the shortlist' : 'Shortlist, decide later'}</button>`;
    placeMenu(m, anchor);
  }
  function placeMenu(m, anchor) {
    m.hidden = false;
    const r = anchor.getBoundingClientRect(); const mw = m.offsetWidth || 240; const mh = m.offsetHeight || 200;
    let top = r.bottom + 6; if (top + mh > innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    m.style.top = `${top}px`; m.style.left = `${clamp(r.left, 8, innerWidth - mw - 8)}px`;
    const first = $('.menu-item', m); if (first) first.focus();
  }
  function closeMenu(refocus = true) {
    const m = $('#menu'); if (m.hidden) return;
    m.hidden = true;
    if (refocus && menuTrigger && menuTrigger.isConnected) menuTrigger.focus();
  }
  function modal(html) {
    if ($('#modal-backdrop').hidden) modalTrigger = document.activeElement;
    $('#modal').innerHTML = html; $('#modal-backdrop').hidden = false;
    const f = $('#modal [autofocus]') || $('#modal input, #modal button'); if (f) f.focus();
  }
  function closeModal() {
    const was = !$('#modal-backdrop').hidden;
    $('#modal-backdrop').hidden = true;
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
    if (was && modalTrigger && modalTrigger.isConnected) modalTrigger.focus();
  }
  let toastTimer = null;
  function toast(text, undo) {
    const t = $('#toast');
    t.innerHTML = `<span>${esc(text)}</span>${undo ? '<button type="button" data-undo>Undo</button>' : ''}`;
    t.hidden = false; toastUndo = undo || null;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; toastUndo = null; }, 4500);
  }
  let toastUndo = null;

  function personModal(p, opts = {}) {
    const d = p || Object.assign({}, opts.prefill || {});
    const chosen = new Set(d.interests || []);
    const used = new Set(state.lists.people.map((x) => x.color));
    const color = d.color || MARKS.find((c) => !used.has(c)) || MARKS[0];
    modal(`<h3 id="modal-title">${p ? `Edit ${esc(p.name)}` : 'Add a person'}</h3>
      <form id="person-form" data-id="${p ? esc(p.id) : ''}" data-for-gift="${esc(opts.forGift || '')}" data-for-pick="${esc(opts.forPick || '')}" style="display:grid;gap:14px">
        <div class="field"><label for="pf-name">Name</label><input type="text" id="pf-name" maxlength="40" required value="${esc(d.name || '')}" placeholder="Who's this list for?" autofocus></div>
        <div class="grid2"><div class="field"><label for="pf-age">Age</label><input type="number" id="pf-age" min="1" max="30" value="${esc(d.age ?? '')}" placeholder="1 to 30"></div>
          <div class="field"><label for="pf-budget">Budget ($)</label><input type="number" id="pf-budget" min="0" step="5" value="${esc(d.budget ?? '')}" placeholder="Optional"></div></div>
        <fieldset><legend>Into</legend><div class="interest-chips">${Object.entries(INT).map(([k, v]) => `<button type="button" class="ichip" data-pick-interest="${esc(k)}" aria-pressed="${chosen.has(k)}"><span class="e" aria-hidden="true">${esc(v.emoji)}</span>${esc(v.label)}</button>`).join('')}</div></fieldset>
        <fieldset><legend>Marker color</legend><div class="swatches">${MARKS.map((c) => `<button type="button" class="swatch" style="--mark:${c}" data-swatch="${c}" aria-pressed="${c === color}" aria-label="Color ${c}"></button>`).join('')}</div></fieldset>
        <div class="field"><label for="pf-note">Notes</label><textarea id="pf-note" maxlength="500" placeholder="Sizes, favorite colors, what they already have">${esc(d.note || '')}</textarea></div>
        <div class="modal-actions">${p ? `<button class="btn btn-ghost" type="button" data-delete-person="${esc(p.id)}" style="color:var(--bad)">Delete ${esc(p.name)}</button><span class="spacer"></span>` : ''}<button class="btn" type="button" data-close-modal>Cancel</button><button class="btn btn-accent" type="submit">${p ? 'Save changes' : 'Add person'}</button></div>
      </form>`);
  }
  function customModal(pid) {
    const p = person(pid); if (!p) return;
    modal(`<h3 id="modal-title">Add something for ${esc(p.name)}</h3>
      <p class="sub">Anything from any store: paste the product link so you can find it again.</p>
      <form id="custom-form" data-person="${esc(pid)}" style="display:grid;gap:12px">
        <div class="field"><label for="cf-name">What is it?</label><input type="text" id="cf-name" maxlength="120" required autofocus placeholder="e.g. Hello Kitty squishy dumpling"></div>
        <div class="field"><label for="cf-url">Link (optional)</label><input type="url" id="cf-url" placeholder="https://"></div>
        <div class="grid2"><div class="field"><label for="cf-price">Price ($)</label><input type="number" id="cf-price" min="0" step="0.01" placeholder="Optional"></div>
          <div class="field"><label for="cf-note">Note</label><input type="text" id="cf-note" maxlength="300" placeholder="Size, color…"></div></div>
        <div class="modal-actions"><button class="btn" type="button" data-close-modal>Cancel</button><button class="btn btn-accent" type="submit">Add to ${esc(p.name)}'s list</button></div>
      </form>`);
  }
  async function shareModal(pid, hide = true) {
    const p = person(pid); if (!p) return;
    const code = await encodeShare(sharePayload(p, hide));
    const link = `${location.href.split('#')[0]}#share=${code}`;
    modal(`<h3 id="modal-title">Share ${esc(p.name)}'s list</h3>
      <p class="sub">Anyone with this link can see the list and save a copy in their own browser. The list travels inside the link itself, so nothing is uploaded anywhere.</p>
      <label class="check"><input type="checkbox" id="share-hide" data-share-hide="${esc(pid)}" ${hide ? 'checked' : ''}> Hide what's been bought or wrapped (no spoilers)</label>
      <div class="share-link"><input type="text" id="share-url" readonly value="${esc(link)}" aria-label="Share link"><button class="btn btn-accent" type="button" data-copy="#share-url">Copy link</button></div>
      <div class="modal-actions" style="justify-content:flex-start"><button class="btn" type="button" data-copy-text="${esc(pid)}">Copy as text</button><button class="btn" type="button" data-print>Print</button><span class="spacer"></span><button class="btn" type="button" data-close-modal>Done</button></div>`);
  }
  function sharedModal(obj) {
    const d = normalizeLists({ people: [fromShare(obj)] }).people[0];
    if (!d) throw new Error('not a Christmas list');
    const existing = state.lists.people.find((p) => p.name.toLowerCase() === String(d.name).toLowerCase());
    const rows = d.items.map((x) => { const g = x.gift && BYID[x.gift]; const name = g ? g.name : x.name;
      return `<li>${esc(g ? g.emoji + ' ' : '')}${esc(name)}${g ? `, about ${money(priceOf(g))}` : x.price ? `, ${money(x.price)}` : ''}${x.status !== 'idea' ? ` <span class="chip good">${STATUS[x.status]}</span>` : ''}${x.url ? ` <a href="${esc(x.url)}" target="_blank" rel="noopener">link</a>` : ''}${x.note ? ` <span class="cell-sub">(${esc(x.note)})</span>` : ''}</li>`; }).join('');
    pendingShare = d;
    modal(`<h3 id="modal-title">${esc(d.name)}'s Christmas list</h3>
      <p class="sub">Someone shared this list with you${d.age ? `. ${esc(d.name)} is ${d.age}` : ''}. Save it to see matched ideas, mark things bought and coordinate.</p>
      <ul style="margin:0;padding-left:20px;display:grid;gap:4px">${rows || '<li>No gifts on it yet.</li>'}</ul>
      <div class="modal-actions">${existing ? `<button class="btn" type="button" data-save-share="merge">Add to my ${esc(existing.name)}'s list</button>` : ''}<button class="btn" type="button" data-close-modal>Just looking</button><button class="btn btn-accent" type="button" data-save-share="new">Save as ${existing ? 'a new person' : 'a list'}</button></div>`);
  }
  let pendingShare = null;
  function saveShared(mode) {
    const d = pendingShare; if (!d) return;
    let p = mode === 'merge' ? state.lists.people.find((x) => x.name.toLowerCase() === String(d.name).toLowerCase()) : null;
    if (!p) p = addPerson({ name: state.lists.people.some((x) => x.name === d.name) ? `${d.name} (shared)` : d.name, age: d.age, interests: d.interests, color: d.color });
    for (const x of d.items) {
      if (x.gift ? BYID[x.gift] && !p.items.some((y) => y.gift === x.gift) : !p.items.some((y) => y.name === x.name)) {
        p.items.push(Object.assign({}, x, { uid: uid(), paid: null, added: new Date().toISOString() }));
      }
    }
    saveLists(); pendingShare = null; closeModal();
    state.listView = p.id; store.set('listView', p.id);
    location.hash = '#lists'; route();
    toast(`Saved ${p.name}'s list`);
  }
  function backupModal() {
    modal(`<h3 id="modal-title">Back up or restore your lists</h3>
      <p class="sub">Lists live in this browser only. Download a backup to keep them safe or move them to another device, then restore it there.</p>
      <div class="modal-actions" style="justify-content:flex-start"><button class="btn btn-accent" type="button" data-download-backup>Download backup</button>
        <label class="btn" for="restore-file" style="cursor:pointer">Restore from a backup…</label><input type="file" id="restore-file" accept="application/json,.json" hidden></div>
      <p class="hint">Restoring replaces the lists in this browser with the ones in the file.</p>
      <div class="modal-actions"><button class="btn" type="button" data-close-modal>Close</button></div>`);
  }
  function downloadBackup() {
    const blob = new Blob([JSON.stringify({ app: 'christmas-gift-finder', saved_at: new Date().toISOString(), lists: state.lists }, null, 1)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `christmas-lists-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand('copy'); } catch (e2) { ok = false; } ta.remove(); return ok;
    }
  }

  // ------------------------------------------------------------------ price refresh (GitHub Actions)
  const GH = 'https://api.github.com';
  const ghHeaders = (tok) => Object.assign({ Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' }, tok ? { Authorization: `Bearer ${tok}` } : {});
  const actionsUrl = () => `https://github.com/${CFG.repo}/actions/workflows/${CFG.workflow}`;
  let pollTimer = null;
  function statusHtml() {
    const sc = DATA.scrape || {};
    const per = Object.entries(sc.by_retailer || {}).map(([r, v]) => `${esc(retName(r))}: ${v.ok} read${v.failed ? `, ${v.failed} not read` : ''}${v.blocked ? ` (${v.blocked} bot check${v.blocked > 1 ? 's' : ''})` : ''}`).join('<br>');
    const runner = { 'github-actions': "GitHub's servers", 'self-hosted': 'the home computer', local: 'a computer (run by hand)' }[sc.runner] || sc.runner || '—';
    return `<dl class="kv"><dt>Store prices</dt><dd>${DATA.live_prices ? `${DATA.live_prices} gifts have a current store price (oldest ${esc(ago(DATA.prices_as_of))})` : 'None read yet; every price shown is a typical price'}</dd>
      <dt>Last check</dt><dd>${sc.mode === 'offline' && !sc.ok && !sc.failed ? 'Not run yet' : `${esc(fmtDate(DATA.generated_at))} on ${esc(runner)}`}</dd>
      <dt>Links tracked</dt><dd>${sc.tracked_links ?? ITEMS.reduce((n, it) => n + (isPick(it) ? 0 : it.offers.length), 0)} exact product pages</dd>
      ${per ? `<dt>By store</dt><dd>${per}</dd>` : ''}
      <dt>Automatic</dt><dd>${esc(CFG.schedule || 'daily')}</dd>
      ${(sc.notes || []).length ? `<dt>Notes</dt><dd>${sc.notes.map(esc).join('<br>')}</dd>` : ''}</dl>`;
  }
  function openRescrape() {
    const tok = store.get('ghToken', '');
    modal(`<h3 id="modal-title">Refresh store prices</h3>${statusHtml()}
      <p class="sub">This runs the price checker on GitHub (a few minutes), saves the new prices and republishes the site. Stores that block automated checks keep their last known price, and every gift still links to each store's own page.</p>
      ${tok ? `<div class="modal-actions" style="justify-content:flex-start"><button class="btn btn-accent" type="button" id="go-scrape" autofocus>Check prices now</button><button class="btn btn-ghost btn-sm" type="button" id="forget-token">Forget saved key</button></div>`
      : `<p class="sub">Starting it needs a refresh key${CFG.maintainer ? ` from ${esc(CFG.maintainer)}` : ''}. Paste it once; it's saved in this browser only.</p>
        <label for="tok-in">Refresh key</label><input type="password" id="tok-in" autocomplete="off" placeholder="github_pat_…">
        <div class="modal-actions" style="justify-content:flex-start"><button class="btn btn-accent" type="button" id="save-go">Save key and check prices</button></div>
        <details><summary>Making a key (repo owner)</summary><ol><li>On GitHub, open <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">Settings, Developer settings, Fine-grained tokens</a>.</li><li>Repository access: only <b>${esc(CFG.repo)}</b>. Permissions: <b>Actions: Read and write</b>, nothing else.</li><li>Paste it above. Use a short expiry and forget the key on shared computers.</li></ol><p>Or skip the key: <a href="${esc(actionsUrl())}" target="_blank" rel="noopener">open the workflow on GitHub</a> and press "Run workflow".</p></details>`}
      <div class="status-list" id="run-status"></div>
      <div class="modal-actions"><button class="btn" type="button" id="reload-data">Reload latest data</button><button class="btn" type="button" data-close-modal>Close</button></div>`);
    showLastRun(tok);
  }
  async function showLastRun(tok) {
    try {
      const r = await fetch(`${GH}/repos/${CFG.repo}/actions/workflows/${CFG.workflow}/runs?per_page=1`, { headers: ghHeaders(tok) });
      if (!r.ok) return;
      const run = ((await r.json()).workflow_runs || [])[0]; if (!run) return;
      const el = $('#run-status'); if (!el || el.dataset.busy) return;
      el.innerHTML = `<div class="status-step ${run.status !== 'completed' ? 'run' : run.conclusion === 'success' ? 'done' : 'fail'}"><span class="s"></span>Latest run: ${esc(run.status === 'completed' ? run.conclusion : run.status)}, ${esc(ago(run.created_at))}. <a href="${esc(run.html_url)}" target="_blank" rel="noopener">View log</a></div>`;
    } catch (e) { /* offline or blocked */ }
  }
  async function dispatchScrape(tok) {
    const el = $('#run-status'); el.dataset.busy = '1'; el.innerHTML = '';
    const step = (cls, text) => { el.insertAdjacentHTML('beforeend', `<div class="status-step ${cls}"><span class="s"></span>${text}</div>`); };
    const t0 = new Date(Date.now() - 60000).toISOString();
    const before = DATA.generated_at;
    try {
      const r = await fetch(`${GH}/repos/${CFG.repo}/actions/workflows/${CFG.workflow}/dispatches`, { method: 'POST', headers: Object.assign({ 'Content-Type': 'application/json' }, ghHeaders(tok)), body: JSON.stringify({ ref: CFG.branch || 'main' }) });
      if (r.status === 401 || r.status === 403) { step('fail', 'GitHub refused the key. It needs Actions: Read and write on this repository, and it may have expired.'); return; }
      if (r.status === 404) { step('fail', 'Workflow not found. Check that the repository has been pushed and the key can see it.'); return; }
      if (!r.ok) { step('fail', `GitHub returned ${r.status}.`); return; }
      step('done', 'Price check requested.');
    } catch (e) {
      step('fail', `Couldn't reach GitHub from this page (${esc(e.message)}). Use the hosted site: <a href="${esc(CFG.siteUrl)}" target="_blank" rel="noopener">${esc(CFG.siteUrl)}</a>`);
      return;
    }
    el.insertAdjacentHTML('beforeend', '<div class="status-step run" id="live-step"><span class="s"></span><span>Waiting for the run to start…</span></div>');
    const live = $('#live-step');
    const poll = async () => {
      try {
        const r = await fetch(`${GH}/repos/${CFG.repo}/actions/workflows/${CFG.workflow}/runs?per_page=5&event=workflow_dispatch`, { headers: ghHeaders(tok) });
        const run = ((await r.json()).workflow_runs || []).filter((x) => x.created_at >= t0)[0];
        if (run) {
          live.lastChild.innerHTML = `Run ${esc(run.status === 'completed' ? run.conclusion : run.status.replace('_', ' '))}. <a href="${esc(run.html_url)}" target="_blank" rel="noopener">Watch on GitHub</a>`;
          if (run.status === 'completed') {
            live.className = `status-step ${run.conclusion === 'success' ? 'done' : 'fail'}`;
            if (run.conclusion === 'success') { step('run', 'Publishing new prices…'); waitForData(before, step); } else step('fail', 'The run failed. Open the log to see which step broke; the old prices stay up meanwhile.');
            return;
          }
        }
      } catch (e) { /* keep polling */ }
      pollTimer = setTimeout(poll, 8000);
    };
    pollTimer = setTimeout(poll, 5000);
  }
  async function waitForData(before, step, tries = 0) {
    try {
      const d = await (await fetch(`data/gifts.json?ts=${Date.now()}`, { cache: 'no-store' })).json();
      if (d.generated_at !== before) {
        DATA = d; boot(true);
        const s = $$('.status-step.run').pop(); if (s) s.className = 'status-step done';
        const sc = d.scrape || {};
        step(sc.ok ? 'done' : 'fail', sc.ok ? `New prices loaded: ${sc.ok} store links read${sc.failed ? `, ${sc.failed} couldn't be read (last known price kept)` : ''}.` : 'The checker ran but no store gave it a price this time. Stores often block cloud servers; see the README for running it from home.');
        return;
      }
    } catch (e) { /* retry */ }
    if (tries < 30) pollTimer = setTimeout(() => waitForData(before, step, tries + 1), 10000);
    else step('fail', 'The run finished but the site hasn\'t updated yet. GitHub Pages can lag a few minutes; reload later.');
  }
  function renderFreshness() {
    const el = $('#freshness'); el.classList.remove('is-live', 'is-aging', 'is-stale');
    const n = DATA.live_prices || 0;
    if (n) {
      const hours = (Date.now() - new Date(DATA.prices_as_of).getTime()) / 36e5;
      el.classList.add(hours < 36 ? 'is-live' : hours < 96 ? 'is-aging' : 'is-stale');
      $('#freshness-text').textContent = `${n} store price${n > 1 ? 's' : ''}, oldest ${ago(DATA.prices_as_of)}`;
    } else {
      $('#freshness-text').textContent = `${ITEMS.length} gifts, typical prices`;
    }
    sizeHeader();
  }

  // ------------------------------------------------------------------ header: countdown, snow, theme
  function renderCountdown(now = new Date()) {
    const n = daysUntil(christmasDate(now), now);
    $('#countdown').innerHTML = n === 0 ? '<b>Merry Christmas!</b>' : `<b>${n} sleep${n > 1 ? 's' : ''}</b> until Christmas`;
  }
  let snowRaf = null;
  function startSnow() {
    const c = $('#snow'); if (!c || !c.getContext) return;
    const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    const on = store.get('snow', true) && !reduce;
    $('#snow-btn').setAttribute('aria-pressed', String(on));
    if (snowRaf) { cancelAnimationFrame(snowRaf); snowRaf = null; }
    const ctx = c.getContext('2d');
    const fit = () => { c.width = c.offsetWidth * (window.devicePixelRatio || 1); c.height = c.offsetHeight * (window.devicePixelRatio || 1); };
    fit();
    if (!on) { ctx.clearRect(0, 0, c.width, c.height); return; }
    const dpr = window.devicePixelRatio || 1;
    const flakes = Array.from({ length: 46 }, () => ({ x: Math.random(), y: Math.random(), r: 0.8 + Math.random() * 2, s: 0.12 + Math.random() * 0.25, d: Math.random() * Math.PI * 2 }));
    let last = performance.now();
    const tick = (t) => {
      const dt = Math.min(64, t - last) / 16; last = t;
      if (c.width !== c.offsetWidth * dpr) fit();
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.fillStyle = 'rgba(255,255,255,0.55)';
      for (const f of flakes) {
        f.y += (f.s * dt) / c.offsetHeight * 2.2; f.d += 0.01 * dt; f.x += Math.sin(f.d) * 0.0006 * dt;
        if (f.y > 1.05) { f.y = -0.05; f.x = Math.random(); }
        ctx.beginPath(); ctx.arc(f.x * c.width, f.y * c.height, f.r * dpr, 0, Math.PI * 2); ctx.fill();
      }
      snowRaf = document.hidden ? null : requestAnimationFrame(tick);
    };
    snowRaf = requestAnimationFrame(tick);
  }
  function sizeHeader() {
    const inner = $('.topbar-inner');
    document.documentElement.style.setProperty('--topbar-hide', `${window.matchMedia && matchMedia('(max-width: 760px)').matches && inner ? inner.offsetHeight : 0}px`);
  }
  function setPrefsCollapsed(c) {
    $('.prefs').classList.toggle('collapsed', c);
    const b = $('#prefs-toggle'); b.textContent = c ? 'Change filters' : 'Hide filters'; b.setAttribute('aria-expanded', String(!c));
  }
  function updateListCount() {
    const el = $('#lists-count'); if (!el) return;
    const n = listCount(); el.hidden = !n; el.textContent = n;
  }

  // ------------------------------------------------------------------ routing + events
  const VIEWS = ['find', 'lists', 'browse', 'deals', 'stores'];
  const currentView = () => { const h = (location.hash || '').replace('#', ''); return VIEWS.includes(h) ? h : 'find'; };
  const RENDER = { find: () => { renderFindPrefs(); renderFind(); }, lists: renderLists, browse: () => { renderFilters(); renderBrowse(); }, deals: renderDeals, stores: renderStores };
  function route() {
    const v = currentView();
    VIEWS.forEach((x) => { $(`#view-${x}`).hidden = x !== v; });
    $$('.tabs a').forEach((a) => { a.classList.toggle('is-active', a.dataset.view === v); if (a.dataset.view === v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    RENDER[v]();
  }
  function refresh() { RENDER[currentView()](); if (!$('#drawer').hidden && drawerGift) openDrawer(drawerGift); }
  let drawerGift = null;
  function setFind(patch, keepWho = true) {
    Object.assign(state.find, patch);
    if (!keepWho) state.find.who = '';
    state.shown = 9; saveFind(); renderFindPrefs(); renderFind();
  }
  function toggleGift(giftId, pid) {
    const p = person(pid); if (!p) return;
    if (p.items.some((x) => x.gift === giftId)) {
      const removed = p.items.find((x) => x.gift === giftId);
      removeGift(pid, giftId);
      toast(`Removed from ${p.name}'s list`, () => { p.items.push(removed); saveLists(); refresh(); });
    } else {
      addGift(pid, giftId);
      toast(`Added to ${p.name}'s list`, () => { removeGift(pid, giftId); refresh(); });
    }
    refresh();
  }
  function bind() {
    sizeHeader(); window.addEventListener('resize', () => { sizeHeader(); closeMenu(false); });
    if (document.fonts) document.fonts.ready.then(sizeHeader);
    window.addEventListener('hashchange', () => {
      if (location.hash.startsWith('#share=')) { openShareFromHash(); return; }
      closeDrawer(); closeMenu(false); route(); window.scrollTo(0, 0);
    });
    document.addEventListener('visibilitychange', () => { if (!document.hidden && !snowRaf) startSnow(); });
    document.addEventListener('click', (e) => {
      const m = $('#menu');
      if (!m.hidden && !e.target.closest('#menu') && !e.target.closest('[data-add]')) closeMenu(false);
      const t = e.target.closest('[data-open],[data-add],[data-star],[data-toggle-gift],[data-new-person],[data-new-person-for],[data-example],[data-view-list],[data-edit-person],[data-delete-person],[data-share],[data-print],[data-find-for],[data-custom],[data-status],[data-remove],[data-band],[data-interest],[data-pick-interest],[data-swatch],[data-more],[data-more-interests],[data-reset-find],[data-sort],[data-quick],[data-type],[data-types-toggle],[data-show-list],[data-add-pick],[data-pick-to],[data-new-person-pick],[data-pick-band],[data-picks-more],[data-picks-reset],[data-picks-goto],[data-picks-type],[data-close-drawer],[data-close-modal],[data-copy],[data-copy-text],[data-save-share],[data-backup],[data-restore],[data-download-backup],[data-undo],[data-rescrape],#rescrape-btn,#freshness,#theme-btn,#snow-btn,#reset-find,#prefs-toggle,#go-scrape,#save-go,#forget-token,#reload-data');
      if (!t) return;
      const d = t.dataset;
      if (d.add !== undefined) { e.preventDefault(); e.stopPropagation(); const m2 = $('#menu'); if (!m2.hidden && menuTrigger === t) closeMenu(); else openAddMenu(d.add, t); return; }
      if (d.addPick !== undefined) { e.preventDefault(); e.stopPropagation(); const m2 = $('#menu'); if (!m2.hidden && menuTrigger === t) closeMenu(); else openPickMenu(d.addPick, t); return; }
      if (d.pickTo !== undefined) { const [pk, pid] = d.pickTo.split('|'); closeMenu(false); togglePick(pk, pid); return; }
      if (d.newPersonPick !== undefined) { closeMenu(false); personModal(null, { forPick: d.newPersonPick }); return; }
      if (d.pickBand !== undefined) { state.picks.band = d.pickBand; state.picks.shown = 24; $$('[data-pick-band]').forEach((b) => { const on = b.dataset.pickBand === d.pickBand; b.classList.toggle('is-on', on); b.setAttribute('aria-pressed', String(on)); }); renderPicks(); return; }
      if (d.picksMore !== undefined) { state.picks.shown += 24; renderPicks(); return; }
      if (d.picksReset !== undefined) { state.picks = Object.assign(state.picks, { band: '', type: '', show: '', max: '', q: '', shown: 24 }); renderPicksPanel(); return; }
      if (d.picksGoto !== undefined || d.picksType !== undefined) {
        closeDrawer();
        Object.assign(state.picks, { band: d.picksGoto || '', type: d.picksType || '', show: '', max: '', q: '', shown: 24 });
        if (currentView() !== 'deals') location.hash = '#deals'; else renderPicksPanel();
        setTimeout(() => { const pnl = $('#picks-panel'); if (pnl && pnl.scrollIntoView) pnl.scrollIntoView({ block: 'start' }); }, 60);
        return;
      }
      if (d.toggleGift !== undefined) { const fromMenu = !!t.closest('#menu'); toggleGift(d.toggleGift, d.person); if (fromMenu) closeMenu(false); return; }
      if (d.star !== undefined) { const on = toggleShortlist(d.star); toast(on ? 'Saved to your shortlist' : 'Removed from your shortlist'); closeMenu(false); refresh(); return; }
      if (d.newPersonFor !== undefined) { closeMenu(false); personModal(null, { forGift: d.newPersonFor }); return; }
      if (d.newPerson !== undefined) { personModal(null); return; }
      if (d.example !== undefined) { personModal(null, { prefill: EXAMPLE }); return; }
      if (d.open !== undefined) { if (t.closest('#modal')) closeModal(); drawerGift = d.open; openDrawer(d.open); return; }
      if (d.viewList !== undefined) { state.listView = d.viewList; store.set('listView', d.viewList); renderLists(); return; }
      if (d.type !== undefined) { closeDrawer(); state.browse.type = d.type; if (currentView() !== 'browse') { location.hash = '#browse'; return; } renderFilters(); renderBrowse(); if (d.type && innerWidth <= 760) { const f = $('#filters'); if (f && f.scrollIntoView) f.scrollIntoView({ block: 'start' }); } return; }
      if (d.typesToggle !== undefined) { state.typesOpen = !state.typesOpen; renderBrowse(); return; }
      if (d.showList !== undefined) { state.browse = Object.assign({}, state.browse, { list: d.showList, type: '', q: '' }); location.hash = '#browse'; if (currentView() === 'browse') { renderFilters(); renderBrowse(); } return; }
      if (d.editPerson !== undefined) { personModal(person(d.editPerson)); return; }
      if (d.deletePerson !== undefined) {
        const p = person(d.deletePerson); if (!p) return;
        if (t.dataset.confirm !== '1') { t.dataset.confirm = '1'; t.textContent = `Yes, delete ${p.name} and their list`; return; }
        state.lists.people = state.lists.people.filter((x) => x.id !== p.id); if (state.find.who === p.id) { state.find.who = ''; saveFind(); }
        saveLists(); closeModal(); state.listView = null; toast(`Deleted ${p.name}`); refresh(); return;
      }
      if (d.share !== undefined) { shareModal(d.share, true); return; }
      if (d.print !== undefined) { closeModal(); if (currentView() !== 'lists') { location.hash = '#lists'; } setTimeout(() => window.print(), 50); return; }
      if (d.findFor !== undefined) { const p = person(d.findFor); if (!p) return; state.find = profileOf(p); state.shown = 9; saveFind(); location.hash = '#find'; return; }
      if (d.custom !== undefined) { customModal(d.custom); return; }
      if (d.status !== undefined) {
        const [pid, u] = d.status.split('|'); const p = person(pid); const x = p && p.items.find((y) => y.uid === u); if (!x) return;
        x.status = t.closest('.store-group') ? 'bought' : NEXT_STATUS[x.status]; saveLists();
        if (t.closest('.store-group')) toast(`Marked bought for ${p.name}`, () => { x.status = 'idea'; saveLists(); refresh(); });
        refresh(); return;
      }
      if (d.remove !== undefined) {
        const [pid, u] = d.remove.split('|'); const p = person(pid); if (!p) return;
        const idx = p.items.findIndex((y) => y.uid === u); if (idx < 0) return;
        const [gone] = p.items.splice(idx, 1); saveLists();
        toast(`Removed from ${p.name}'s list`, () => { p.items.splice(idx, 0, gone); saveLists(); refresh(); }); refresh(); return;
      }
      if (d.band !== undefined) { const b = AGE_BANDS.find((x) => x.id === d.band); setFind({ age: b.age }); return; }
      if (d.interest !== undefined) { const s = new Set(state.find.interests); s.has(d.interest) ? s.delete(d.interest) : s.add(d.interest); setFind({ interests: [...s] }); return; }
      if (d.pickInterest !== undefined) { t.setAttribute('aria-pressed', String(t.getAttribute('aria-pressed') !== 'true')); return; }
      if (d.swatch !== undefined) { $$('[data-swatch]').forEach((s) => s.setAttribute('aria-pressed', String(s === t))); return; }
      if (d.more !== undefined) { state.shown += 12; renderFind(); return; }
      if (d.moreInterests !== undefined) { $('.prefs').classList.toggle('show-all'); renderFindPrefs(); return; }
      if (t.id === 'prefs-toggle') { const c = !$('.prefs').classList.contains('collapsed'); setPrefsCollapsed(c); return; }
      if (d.resetFind !== undefined || t.id === 'reset-find') { state.find = Object.assign({}, DEFAULT_FIND); state.shown = 9; saveFind(); renderFindPrefs(); renderFind(); return; }
      if (d.sort !== undefined) { const k = d.sort; state.browse.dir = state.browse.sort === k ? -state.browse.dir : 1; state.browse.sort = k; renderBrowse(); return; }
      if (d.quick !== undefined) { state.storeQ = d.quick; $('#store-q').value = d.quick; renderStores(); return; }
      if (d.closeDrawer !== undefined) { closeDrawer(); return; }
      if (d.closeModal !== undefined) { closeModal(); return; }
      if (d.copy !== undefined) { const inp = $(d.copy); copyText(inp.value).then((ok) => { t.textContent = ok ? 'Copied' : 'Select and copy'; if (!ok) inp.select(); }); return; }
      if (d.copyText !== undefined) { const p = person(d.copyText); const hide = ($('#share-hide') || {}).checked; copyText(listText(p, hide)).then((ok) => { t.textContent = ok ? 'Copied' : 'Copy failed'; }); return; }
      if (d.saveShare !== undefined) { saveShared(d.saveShare); return; }
      if (d.backup !== undefined || d.restore !== undefined) { backupModal(); return; }
      if (d.downloadBackup !== undefined) { downloadBackup(); return; }
      if (d.undo !== undefined) { const u = toastUndo; $('#toast').hidden = true; toastUndo = null; if (u) u(); return; }
      if (d.rescrape !== undefined || t.id === 'rescrape-btn' || t.id === 'freshness') { openRescrape(); return; }
      if (t.id === 'theme-btn') { const cur = document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); const nx = cur === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = nx; store.set('theme', nx); return; }
      if (t.id === 'snow-btn') { store.set('snow', t.getAttribute('aria-pressed') !== 'true'); startSnow(); return; }
      if (t.id === 'go-scrape') { t.disabled = true; dispatchScrape(store.get('ghToken', '')); return; }
      if (t.id === 'save-go') { const v = ($('#tok-in').value || '').trim(); if (!v) { $('#tok-in').focus(); return; } store.set('ghToken', v); t.disabled = true; dispatchScrape(v); return; }
      if (t.id === 'forget-token') { store.del('ghToken'); closeModal(); openRescrape(); return; }
      if (t.id === 'reload-data') { reloadData(); }
    });
    document.addEventListener('submit', (e) => {
      const f = e.target;
      if (f.id === 'person-form') {
        e.preventDefault();
        const name = $('#pf-name').value.trim(); if (!name) { $('#pf-name').focus(); return; }
        const data = { name, age: $('#pf-age').value === '' ? null : clamp(+$('#pf-age').value, 1, 30), budget: $('#pf-budget').value === '' ? null : Math.max(0, +$('#pf-budget').value),
          interests: $$('[data-pick-interest]').filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.pickInterest),
          color: ($$('[data-swatch]').find((b) => b.getAttribute('aria-pressed') === 'true') || {}).dataset?.swatch, note: $('#pf-note').value.trim() };
        let p;
        if (f.dataset.id) { p = person(f.dataset.id); Object.assign(p, normalizeLists({ people: [Object.assign({}, p, data)] }).people[0], { id: p.id, items: p.items }); saveLists(); toast(`Saved ${p.name}`); }
        else { p = addPerson(data); toast(`Added ${p.name}`); if (f.dataset.forGift) addGift(p.id, f.dataset.forGift); if (f.dataset.forPick) togglePick(f.dataset.forPick, p.id); }
        closeModal();
        if (!f.dataset.id && currentView() === 'lists') { state.listView = p.id; store.set('listView', p.id); }
        refresh(); return;
      }
      if (f.id === 'custom-form') {
        e.preventDefault();
        const x = addCustom(f.dataset.person, { name: $('#cf-name').value.trim(), url: $('#cf-url').value.trim(), price: $('#cf-price').value, note: $('#cf-note').value.trim() });
        if (!x) { $('#cf-name').focus(); return; }
        closeModal(); toast('Added'); refresh(); return;
      }
      if (f.id === 'store-search-form') { e.preventDefault(); state.storeQ = $('#store-q').value; renderStores(); const first = $('#store-results a'); if (first) first.focus(); }
    });
    document.addEventListener('input', (e) => {
      const t = e.target;
      if (t.id === 'age') { setFind({ age: +t.value }); $('#age').focus(); return; }
      if (t.id === 'budget') { state.find.budget = +t.value; $('#budget-out').textContent = +t.value >= BUDGET_ANY ? 'Any amount' : money(+t.value); state.shown = 9; saveFind(); renderFind(); return; }
      if (t.id === 'f-q') { state.browse.q = t.value; renderBrowse(); return; }
      if (t.id === 'f-age') { state.browse.age = t.value; renderBrowse(); return; }
      if (t.id === 'pk-q') { state.picks.q = t.value; state.picks.shown = 24; renderPicks(); return; }
    });
    document.addEventListener('change', (e) => {
      const t = e.target;
      if (t.id === 'for-who') {
        const p = person(t.value);
        state.find = p ? profileOf(p) : Object.assign({}, state.find, { who: '' }); state.shown = 9; saveFind(); renderFindPrefs(); renderFind(); return;
      }
      if (t.dataset.toggle) { setFind({ [t.dataset.toggle]: t.checked }); return; }
      const map = { 'f-interest': 'interest', 'f-max': 'max', 'f-store': 'store', 'f-type': 'type', 'f-list': 'list' };
      if (map[t.id]) { state.browse[map[t.id]] = t.value; renderBrowse(); return; }
      const pmap = { 'pk-type': 'type', 'pk-show': 'show', 'pk-max': 'max', 'pk-sort': 'sort' };
      if (pmap[t.id]) { state.picks[pmap[t.id]] = t.value; state.picks.shown = 24; renderPicks(); return; }
      if (t.id === 'f-hot' || t.id === 'f-live') { state.browse[t.id.slice(2)] = t.checked; renderBrowse(); return; }
      if (t.dataset.paid) {
        const [pid, u] = t.dataset.paid.split('|'); const p = person(pid); const x = p && p.items.find((y) => y.uid === u); if (!x) return;
        x.paid = t.value === '' ? null : Math.max(0, +t.value); if (x.paid != null && x.status === 'idea') x.status = 'bought';
        saveLists(); renderLists(); return;
      }
      if (t.dataset.shareHide) { shareModal(t.dataset.shareHide, t.checked); return; }
      if (t.id === 'restore-file' && t.files && t.files[0]) {
        t.files[0].text().then((txt) => {
          const raw = JSON.parse(txt); const lists = normalizeLists(raw.lists || raw);
          if (!lists.people.length && !lists.shortlist.length) throw new Error('no lists in that file');
          state.lists = lists; saveLists(); closeModal(); state.listView = null; toast(`Restored ${lists.people.length} list${lists.people.length === 1 ? '' : 's'}`); refresh();
        }).catch((err) => { toast(`Couldn't restore: ${err.message}`); });
      }
    });
    document.addEventListener('keydown', (e) => {
      const m = $('#menu');
      if (!m.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        const items = $$('.menu-item', m); const i = items.indexOf(document.activeElement);
        e.preventDefault(); (items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length] || items[0]).focus(); return;
      }
      const dialog = !$('#modal-backdrop').hidden ? $('#modal') : !$('#drawer').hidden ? $('#drawer') : null;
      if (e.key === 'Tab' && dialog && m.hidden) {
        const focusable = $$('button:not([disabled]), a[href], input:not([disabled]):not([type="file"]), select:not([disabled]), textarea, summary, label[for], [tabindex="0"]', dialog).filter((el) => el.getClientRects().length);
        const first = focusable[0]; const last = focusable[focusable.length - 1];
        if (first && (e.shiftKey ? document.activeElement === first || !dialog.contains(document.activeElement) : document.activeElement === last || !dialog.contains(document.activeElement))) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
      }
      if (e.key === 'Escape') { if (!m.hidden) closeMenu(); else if (!$('#modal-backdrop').hidden) closeModal(); else if (!$('#drawer').hidden) closeDrawer(); }
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-open]')) { e.preventDefault(); drawerGift = e.target.dataset.open; openDrawer(e.target.dataset.open); }
    });
    $('#drawer-backdrop').addEventListener('click', closeDrawer);
    $('#modal-backdrop').addEventListener('click', (e) => { if (e.target.id === 'modal-backdrop') closeModal(); });
  }
  async function openShareFromHash() {
    const code = location.hash.slice('#share='.length);
    history.replaceState(null, '', location.pathname + location.search + '#lists');
    route();
    try { sharedModal(await decodeShare(code)); } catch (e) { toast(`That share link couldn't be read (${e.message}).`); }
  }
  async function reloadData() {
    try {
      const picksReq = fetch(`data/store-picks.json?ts=${Date.now()}`, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      DATA = await (await fetch(`data/gifts.json?ts=${Date.now()}`, { cache: 'no-store' })).json(); prepPicks(await picksReq); boot(true); closeModal();
    }
    catch (e) { const el = $('#run-status'); if (el) el.insertAdjacentHTML('beforeend', `<div class="status-step fail"><span class="s"></span>Couldn't load data: ${esc(e.message)}</div>`); }
  }
  // Gifts on a store's or expert's 2026 list get the "Hot this year" seal; gift-guide picks are cited but not sealed.
  function prepItem(it) {
    it.lists = Array.isArray(it.lists) ? it.lists.filter((l) => HOT[l]) : [];
    it.tags = Array.isArray(it.tags) ? it.tags.slice() : [];
    if (!it.tags.includes('hot') && it.lists.some((l) => HOT[l].kind !== 'guide')) it.tags.push('hot');
  }
  const typeLabel = (it) => (TYPES[it.type] || {}).label || '';
  function boot(isReload) {
    RET = DATA.retailers || {}; INT = DATA.interests || {};
    TYPES = DATA.types || {}; HOT = DATA.hot_lists || {}; CATS = DATA.categories || {};
    ITEMS = DATA.items.concat(pickItems()); BYID = Object.fromEntries(ITEMS.map((it) => [it.id, it]));
    ITEMS.forEach(prepItem);
    if (state.browse.type && !TYPES[state.browse.type] && !CATS[state.browse.type.replace(/^cat:/, '')]) state.browse.type = '';
    state.find.interests = state.find.interests.filter((i) => INT[i]);
    if (state.find.who && !person(state.find.who)) state.find.who = '';
    renderFreshness(); renderCountdown(); updateListCount();
    $('#footer').innerHTML = `<p>Prices marked "typical" are usual list prices and "estimated" ones are our best guess until a store price is read; store prices show which store and when they were read. Prices change quickly around Black Friday, so check the store before you buy. Not affiliated with any store.</p>
      <p>Your lists are saved only in this browser. Source and data: <a href="https://github.com/${esc(CFG.repo)}" target="_blank" rel="noopener">github.com/${esc(CFG.repo)}</a>.</p>`;
    if (!isReload) route(); else refresh();
  }
  async function init() {
    const th = store.get('theme', null); if (th) document.documentElement.dataset.theme = th;
    bind(); startSnow();
    if (window.matchMedia && matchMedia('(max-width: 1000px)').matches) setPrefsCollapsed(true);
    if (window.matchMedia && matchMedia('(max-width: 760px)').matches) state.typesOpen = false;
    try {
      const picksReq = fetch(`data/store-picks.json?ts=${Date.now()}`, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      DATA = await (await fetch(`data/gifts.json?ts=${Date.now()}`, { cache: 'no-store' })).json();
      prepPicks(await picksReq);
    } catch (e) {
      const b = $('#banner'); b.hidden = false;
      b.textContent = `Couldn't load the gift list (${e.message}). If you opened index.html straight from disk, serve the folder instead, for example "python3 -m http.server" inside site/.`;
      return;
    }
    boot(false);
    if (location.hash.startsWith('#share=')) openShareFromHash();
  }
  init();
})();
