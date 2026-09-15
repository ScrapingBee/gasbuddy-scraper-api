// GasBuddy: station identity for 1 credit, pump prices for 25.
// Verified against gasbuddy.com/gasprices/new-york/new-york on 2026-09-15.
// Public city and station pages only. Nothing here signs in.

const axios = require('axios');

const BASE = 'https://app.scrapingbee.com/api/v1/';
const headers = { Authorization: `Bearer ${process.env.SCRAPINGBEE_API_KEY}` };

// CSS module class names carry a build hash suffix such as ___3rARL, which
// rotates on deploy. Match the stable prefix, never the whole string.
const PRICE_RULES = {
  prices: { selector: 'span[class*="StationDisplayPrice-module__price"]', type: 'list' },
};

const cityUrl = (state, city) => `https://www.gasbuddy.com/gasprices/${state}/${city}`;

async function fetchPage(url, params = {}) {
  const res = await axios.get(BASE, {
    headers,
    params: { url, ...params },
    timeout: 180000,
    responseType: 'text',
    transformResponse: [(d) => d],
  });
  return String(res.data);
}

// The Apollo cache is assigned to a window global and terminated by a
// semicolon and a newline.
function apolloState(html) {
  const m = html.match(/window\.__APOLLO_STATE__\s*=\s*(\{[\s\S]*?\});\s*\n/);
  if (!m) throw new Error('Apollo cache not found, the page shape changed');
  return JSON.parse(m[1]);
}

// Tier one. 1 credit. Full station identity, no prices.
// `fuels` lists grades (regular_gas, midgrade_gas, premium_gas), NOT prices,
// despite the name. `priceUnit` names the unit the prices would be in.
async function stations(state, city) {
  const cache = apolloState(await fetchPage(cityUrl(state, city), { mode: 'auto' }));
  return Object.values(cache)
    .filter((v) => v && v.__typename === 'Station')
    .map((v) => {
      const address = v.address || {};
      const brands = v.brands || [];
      const byType = (t) => (brands.find((b) => b.brandingType === t) || {}).name || null;
      return {
        id: v.id,
        name: v.name,
        line1: address.line1,
        locality: address.locality,
        region: address.region,
        postal_code: address.postalCode,
        country: address.country,
        latitude: v.latitude,
        longitude: v.longitude,
        // A station can carry a fuel supplier and a forecourt shop brand.
        fuel_brand: byType('fuel'),
        store_brand: byType('cstore'),
        amenities: (v.amenities || []).map((a) => a.name),
        grades: v.fuels || [],
        price_unit: v.priceUnit,
        star_rating: v.starRating,
        ratings_count: v.ratingsCount,
        has_active_outage: v.hasActiveOutage,
      };
    });
}

// Tier one, same 1 credit fetch. Member reviews with GasBuddy's own
// sentiment score. These carry a memberId, so treat them as personal data.
async function reviews(state, city) {
  const cache = apolloState(await fetchPage(cityUrl(state, city), { mode: 'auto' }));
  return Object.values(cache)
    .filter((v) => v && v.__typename === 'Review')
    .map((v) => ({
      review_id: v.reviewId,
      member_id: v.memberId,
      overall_rating: v.overallRating,
      text: v.review,
      date: v.reviewDate,
      sentiment_score: v.sentimentScore,
      agree_total: v.agreeTotal,
      visible: v.isVisible,
    }));
}

// Tier two. 25 credits. Prices land after hydration, so this is a genuine
// case for a browser. A 9 second wait produced 10 price nodes against 20
// cached stations, because the visible list is paginated.
async function prices(state, city, wait = 9000) {
  const body = await fetchPage(cityUrl(state, city), {
    extract_rules: JSON.stringify(PRICE_RULES),
    render_js: 'true',
    premium_proxy: 'true',
    country_code: 'us',
    wait,
  });
  return (JSON.parse(body).prices || []).filter(Boolean);
}

(async () => {
  const rows = await stations('new-york', 'new-york');
  console.log(`${rows.length} stations for 1 credit`);
  rows.slice(0, 5).forEach((s) => {
    console.log(`  ${s.name}  ${s.fuel_brand}  ${s.locality}  ${s.star_rating} stars`);
  });

  const rv = await reviews('new-york', 'new-york');
  console.log(`\n${rv.length} reviews, sentiment:`, rv.slice(0, 6).map((r) => r.sentiment_score));

  console.log('\nnow the expensive part');
  console.log('  prices:', await prices('new-york', 'new-york'));
})();

module.exports = { stations, reviews, prices };
