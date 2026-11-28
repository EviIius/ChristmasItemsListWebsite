// Reads Walmart's own lists and deal pages in a real browser and prints lines for scraper/captures/walmart.txt.
//
// Walmart shows a bot check to GitHub's servers, but its pages carry their product data (__NEXT_DATA__), so a
// browser on a home computer can read them. Use it at a person's pace: one page at a time, a few seconds apart.
// Never use it to get past a bot check: if Walmart shows "press and hold" or a captcha, stop.
//
// By hand, on walmart.com in Chrome or Safari:
//   1. Open the console (Chrome: View > Developer > JavaScript Console) and paste this whole file.
//   2. Start scraper/captures/walmart.txt with:   #run walmart <copy(new Date().toISOString()) and paste>
//   3. For each page in LISTS in scraper/store_picks.py (pages 1, 2, ... add &page=2 to the URL), open it and run
//        copy(walmartCapture('wm-top-toys'))        // the list's key from LISTS
//      then paste at the end of walmart.txt.
//   4. For the gifts the catalog links to:  copy(await walmartTracked(['17153956345', '18879162573']))
//   5. Run: python3 scraper/store_picks.py
// Products already copied in this tab are written as "=id", so each product's details are saved once.
// Each line carries the id of Walmart's product photo (the 32 hex digits of its image name), which the site shows.
// Run sessionStorage.removeItem('__xm') before starting a new capture file.

// The id in a Walmart photo address (".../Name_2384fbb2-237e-4e16-89bb-f39d20777a0f.a6d2....png"), without dashes.
function walmartPhoto(url) {
  const m = String(url || '').match(/([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})/i);
  return m ? m.slice(1).join('').toLowerCase() : '';
}

function walmartCapture(L) {
  const nd = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
  const sr = (nd.props.pageProps.initialData || {}).searchResult || {};
  const items = (sr.itemStacks || []).flatMap((s) => s.items || []).filter((i) => i.usItemId && i.name && !i.isSponsoredFlag);
  const S = JSON.parse(sessionStorage.getItem('__xm') || '{}');
  const num = (s) => { const m = String(s || '').replace(/,/g, '').match(/\d+(\.\d+)?/); return m ? m[0] : ''; };
  const C = { BESTSELLER: 'B', HOLIDAY_DEAL: 'H', ROLLBACK: 'R', REDUCED_PRICE: 'P', CLEARANCE: 'C', LOW_INVENTORY: 'L' };
  const rows = items.map((i) => {
    if (S[i.usItemId]) return '=' + i.usItemId;
    S[i.usItemId] = 1;
    const b = i.badges || {};
    let f = '';
    [...(b.flags || []), ...(b.tags || [])].forEach((x) => { if (C[x.key]) f += C[x.key]; });
    (b.groups || []).forEach((g) => (g.members || []).forEach((m) => { if (C[m.key]) f += C[m.key]; }));
    if (i.annualEventV2) f += 'E';
    const p = i.priceInfo || {};
    const cat = ((i.category || {}).categoryPathId || '').split(':').slice(1, 3).join(':');
    return [i.usItemId, num(p.linePrice || p.itemPrice || p.priceRangeString), num(p.wasPrice), i.sellerName === 'Walmart.com' ? 'W' : 'M', cat,
      [...new Set(f)].join(''), i.averageRating ? (+i.averageRating).toFixed(1) : '', i.numberOfReviews || '',
      walmartPhoto((i.imageInfo || {}).thumbnailUrl || i.image),
      i.name.replace(/[|\n\t]/g, ' ').replace(/"/g, '″').replace(/\s+/g, ' ').trim().slice(0, 80)].join('|');
  });
  sessionStorage.setItem('__xm', JSON.stringify(S));
  const pg = sr.paginationV2 || {};
  const ER = { Everyone: 'E', 'Everyone 10+': 'E10', Teen: 'T', 'Mature 17+': 'M', 'Adults Only 18+': 'AO', 'Rating Pending': 'RP' };
  const esrb = items.filter((i) => i.esrb).map((i) => `${i.usItemId}:${ER[i.esrb] || (/mature/i.test(i.esrb) ? 'RP-M' : 'RP')}`);
  return `#list ${L} page=${new URL(location.href).searchParams.get('page') || '1'} count=${sr.aggregatedCount || sr.count} maxPage=${pg.maxPage}\n${rows.join('\n')}`
    + (esrb.length ? `\n#esrb ${esrb.join(' ')}` : '');
}

// Product pages for the gifts the catalog links to, read one at a time about three seconds apart.
async function walmartTracked(ids) {
  const out = [`#list wm-tracked page=1 count=${ids.length} maxPage=1`];
  for (const id of ids) {
    try {
      const r = await fetch('/ip/' + id, { credentials: 'include' });
      const t = await r.text();
      if (/px-captcha|Robot or human|press & hold/i.test(t)) { out.push(`!blocked ${id}: Walmart showed a bot check, so this stopped`); break; }
      const m = t.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
      const p = m && (((JSON.parse(m[1]).props.pageProps.initialData || {}).data || {}).product);
      if (!p) { out.push(`!noproduct ${id}`); continue; }
      const pi = p.priceInfo || {};
      const own = p.sellerType === 'INTERNAL' || p.sellerDisplayName === 'Walmart.com' || p.sellerName === 'Walmart.com';
      const v = (x) => (x == null ? '' : String(x));
      out.push([p.usItemId || id, v((pi.currentPrice || {}).price), v((pi.wasPrice || {}).price), own ? 'W' : 'M', '',
        p.availabilityStatus && p.availabilityStatus !== 'IN_STOCK' ? 'O' : '', p.averageRating ? (+p.averageRating).toFixed(1) : '',
        p.numberOfReviews || '', walmartPhoto((p.imageInfo || {}).thumbnailUrl), (p.name || '').replace(/[|\n\t]/g, ' ').replace(/"/g, '″').replace(/\s+/g, ' ').trim().slice(0, 80)].join('|'));
    } catch (e) { out.push(`!error ${id} ${String(e).slice(0, 60)}`); }
    await new Promise((res) => setTimeout(res, 2800));
  }
  return out.join('\n');
}
