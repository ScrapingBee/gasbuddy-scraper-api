# GasBuddy Scraper API

<p align="center">
  <a href="https://www.scrapingbee.com/">
    <img src="REPLACE_WITH_SCREENSHOT_URL" alt="gasbuddy-scraper-api" />
  </a>
</p>

[![checks](https://github.com/ScrapingBee/gasbuddy-scraper-api/workflows/checks/badge.svg)](https://github.com/ScrapingBee/gasbuddy-scraper-api/actions)
[![license](https://img.shields.io/github/license/ScrapingBee/gasbuddy-scraper-api.svg)](LICENSE)

A GasBuddy station page holds two kinds of data at two very different prices. Everything about the station, its identity, address, coordinates, brands, amenities, ratings and reviews, comes back for **1 credit**. The one number everybody actually wants, today's pump price, costs **25**. Knowing which is which is most of the job.

This is a [gasbuddy api](https://www.scrapingbee.com/scrapers/gasbuddy-scraper-api/) client built on [ScrapingBee's web scraping API](https://www.scrapingbee.com/features/ai-web-scraping-api/), organised around that split.

Verified live on 2026-09-15 against `gasbuddy.com/gasprices/new-york/new-york`. Every field, cost and selector below came back from a real call.

## Tier one: everything except the price, for 1 credit

GasBuddy is an Apollo GraphQL application, and it ships its own cache into the page. No browser, no selectors, no rendering:

```python
import json, os, re, requests

html = requests.get(
    "https://app.scrapingbee.com/api/v1/",
    headers={"Authorization": f"Bearer {os.environ['SCRAPINGBEE_API_KEY']}"},
    params={"url": "https://www.gasbuddy.com/gasprices/new-york/new-york", "mode": "auto"},
    timeout=120,
).text

blob = re.search(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\s*\n", html, re.S).group(1)
state = json.loads(blob)

stations = [v for v in state.values() if v.get("__typename") == "Station"]
print(len(stations), "stations")
```

That returned **20 Station objects and 20 Review objects** from a 48,261 character cache, at `spb-cost: 1`.

A live Station object:

```json
{
  "__typename": "Station",
  "id": "85975",
  "name": "Atlantis",
  "address": {
    "line1": "3276 Jerome Ave", "line2": "",
    "locality": "Bronx", "region": "NY",
    "postalCode": "10468", "country": "US"
  },
  "latitude": 40.878489,
  "longitude": -73.886108,
  "brands": [
    {"brandId": "2071", "name": "Atlantis", "brandingType": "cstore", "imageUrl": "https://images.gasbuddy.io/b/2071.png"},
    {"brandId": "23",   "name": "BP",       "brandingType": "fuel",   "imageUrl": "https://images.gasbuddy.io/b/23.png"}
  ],
  "amenities": [
    {"amenityId": "cash_credit", "name": "Offers Cash Discount", "imageUrl": "https://images.gasbuddy.com/di/features/v2/6.png"}
  ],
  "fuels": ["regular_gas", "midgrade_gas", "premium_gas"],
  "priceUnit": "dollars_per_gallon",
  "starRating": 4.1,
  "ratingsCount": 21,
  "hasActiveOutage": false,
  "emergencyStatus": null
}
```

Note what `fuels` is and is not. **It lists the fuel grades the station sells. It does not contain prices.** That trips people up, because the field name reads like it should. `priceUnit` is there too, telling you the unit the missing numbers would be in.

`brandingType` is worth a mention: a station can carry two brands, one `fuel` and one `cstore`, which is how you separate the fuel supplier from the shop over the forecourt.

The Review objects are in the same cache, free:

```
reviewId, memberId, overallRating, review, reviewDate,
sentimentScore, agreeTotal, isVisible, isReportable, replyRequested
```

`sentimentScore` is GasBuddy's own number, so you get station sentiment without running a model over the text.

## Tier two: the price, for 25 credits

The price node exists in the delivered HTML but it is a spinner:

```html
<span class="text__xl___2MXGo StationDisplayPrice-module__price___3rARL"><div class="loader__loa...
```

Prices are fetched after hydration, so this is one of the genuine cases for a browser:

```bash
curl -G "https://app.scrapingbee.com/api/v1/" \
  -H "Authorization: Bearer $SCRAPINGBEE_API_KEY" \
  --data-urlencode "url=https://www.gasbuddy.com/gasprices/new-york/new-york" \
  --data-urlencode 'extract_rules={"prices":{"selector":"span[class*=\"StationDisplayPrice-module__price\"]","type":"list"}}' \
  -d render_js=true -d premium_proxy=true -d country_code=us -d wait=9000
```

Live result, 25 credits:

```json
{"prices": ["$4.07", "$4.13", "$4.15", "$4.15", "$4.15", "$4.17", "$4.19", "$4.19", "$4.19", "$4.25"]}
```

### Use a prefix match, never the full class

`StationDisplayPrice-module__price___3rARL` is a CSS module name and the `___3rARL` tail is a build hash. It rotates when the component changes, and a scraper keyed on the full string then returns an empty list with a 200 status and no error.

`span[class*="StationDisplayPrice-module__price"]` matches the stable half and survives the rotation. Every selector in this repo is written that way. The same applies to the other module classes on the page: `StationDisplay-module__address`, `StationDisplay-module__ratingContainer`, `StationBrandings-module__logoImages`.

Two things measured that are worth knowing before you tune this. The wait matters: `wait=9000` produced 10 price nodes against 20 stations in the cache, so the visible list is paginated and the top of the page fills first. And the selector guess for the station name (`StationDisplay-module__stationName`) matched nothing, which is why names come from tier one rather than from the rendered DOM.

## Putting the tiers together

The pipeline that actually makes sense: build your station table once from tier one, then poll only the prices.

```python
stations = tier_one("new-york", "new-york")     # 1 credit, full identity
prices   = tier_two("new-york", "new-york")     # 25 credits, today's numbers
```

Because the cache gives you `latitude` and `longitude` per station, you can match the rendered price list back to stations positionally on the same page, or key your own table by `id` and poll prices on whatever cadence your use case needs. Identity data barely changes. Prices change daily. Paying 25 credits to learn a station's postcode again is the waste worth avoiding.

At the entry paid tier of 250,000 credits, a daily price poll across 100 city pages costs 2,500 credits a day, which fits comfortably. Doing the same thing without the split, by rendering every page to get every field, costs the same 2,500 but throws away the free identity data you already had.

## Credit cost

Measured from `spb-cost` response headers:

| Call | Credits |
|---|---|
| City page, `mode=auto`, Apollo cache only | 1 |
| Same page with `render_js` plus `premium_proxy` | 25 |
| Rejected request | 0 |

`mode=auto` walks the proxy ladder cheapest first and bills only the rung that worked, and nothing at all if every rung fails. It cannot be combined with `render_js`, `premium_proxy` or `stealth_proxy`, and sending both returns HTTP 400 while billing nothing. That is why tier two names its parameters explicitly instead of using auto.

Plan tiers are on the [pricing page](https://www.scrapingbee.com/pricing).

## Scope

Public GasBuddy station and city pages. Member accounts, saved stations, GasBuddy Pay and anything requiring a signed in session are out of reach, and scraping under login credentials is prohibited by ScrapingBee's terms of service.

Reviews in the cache are written by named GasBuddy members and carry a `memberId`, so treat them as personal data where that applies rather than as anonymous strings. [GasBuddy's Privacy Policy](https://www.gasbuddy.com/privacy) covers the member data on these pages, and prices are crowdsourced reports rather than a verified feed, so they can be stale or wrong for any individual station.

Reference: [extraction rules](https://www.scrapingbee.com/documentation/data-extraction/), [data extraction feature](https://www.scrapingbee.com/features/data-extraction/), [screenshots](https://www.scrapingbee.com/features/screenshot/) when you need to prove what a page looked like at fetch time.

Adjacent local data endpoints: [local results API](https://www.scrapingbee.com/scrapers/local-results-api/), [Google reviews results API](https://www.scrapingbee.com/scrapers/google-reviews-results-api/), [Bing maps API](https://www.scrapingbee.com/scrapers/bing-maps-api/), [Bing local search API](https://www.scrapingbee.com/scrapers/bing-local-search-api/), [review API](https://www.scrapingbee.com/scrapers/review-api/).

## FAQ

**Is there an official GasBuddy API?**
GasBuddy has a commercial data business and does not publish a free public API for station prices. This project reads the public web pages instead.

**Why is my price field empty at 1 credit?**
Because prices are not in the page you were served. They arrive after hydration. The `fuels` array in the Apollo cache lists grades, not numbers. Move to tier two for the prices.

**Why did my selector stop working?**
Almost certainly because it included a CSS module build hash such as `___3rARL`. Match the stable prefix with `class*=` instead.

**How do I cover a whole state?**
Iterate the city pages under `gasbuddy.com/gasprices/<state>/<city>`. Each one carries its own 20 station cache, so a state is a loop over cities rather than one giant request.

**Can I get historical prices?**
Not from these pages. Each fetch is the current crowdsourced snapshot, and ScrapingBee does not cache, so building a history means storing your own daily pulls.

## License

MIT. See [LICENSE](LICENSE).
