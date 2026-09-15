"""GasBuddy: station identity for 1 credit, pump prices for 25.

Verified against gasbuddy.com/gasprices/new-york/new-york on 2026-09-15.
Public city and station pages only. Nothing here signs in.
Set SCRAPINGBEE_API_KEY in your environment before running.
"""

import json
import os
import re

import requests

BASE = "https://app.scrapingbee.com/api/v1/"
HEADERS = {"Authorization": f"Bearer {os.environ['SCRAPINGBEE_API_KEY']}"}

# The Apollo cache is assigned to a window global and terminated by a
# semicolon and a newline, so a non greedy match to that boundary is enough.
APOLLO = re.compile(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\});\s*\n", re.S)

# CSS module class names carry a build hash suffix such as ___3rARL, which
# rotates on deploy. Match the stable prefix, never the whole string.
PRICE_RULES = {
    "prices": {
        "selector": 'span[class*="StationDisplayPrice-module__price"]',
        "type": "list",
    }
}


def _fetch(url, **params):
    r = requests.get(BASE, headers=HEADERS, params={"url": url, **params}, timeout=180)
    r.raise_for_status()
    return r


def city_url(state, city):
    return f"https://www.gasbuddy.com/gasprices/{state}/{city}"


def stations(state, city):
    """Tier one. 1 credit. Full station identity, no prices.

    Returns 20 stations per city page. The `fuels` array lists the grades
    the station sells (regular_gas, midgrade_gas, premium_gas) and NOT the
    prices, despite the name. `priceUnit` names the unit the prices would
    be in, which is dollars_per_gallon in the US.
    """
    html = _fetch(city_url(state, city), mode="auto").text
    match = APOLLO.search(html)
    if not match:
        raise RuntimeError("Apollo cache not found, the page shape changed")
    state_cache = json.loads(match.group(1))

    out = []
    for value in state_cache.values():
        if not isinstance(value, dict) or value.get("__typename") != "Station":
            continue
        address = value.get("address") or {}
        brands = value.get("brands") or []
        out.append(
            {
                "id": value.get("id"),
                "name": value.get("name"),
                "line1": address.get("line1"),
                "locality": address.get("locality"),
                "region": address.get("region"),
                "postal_code": address.get("postalCode"),
                "country": address.get("country"),
                "latitude": value.get("latitude"),
                "longitude": value.get("longitude"),
                # A station can carry two brands: one fuel supplier and one
                # forecourt shop. brandingType separates them.
                "fuel_brand": next(
                    (b["name"] for b in brands if b.get("brandingType") == "fuel"), None
                ),
                "store_brand": next(
                    (b["name"] for b in brands if b.get("brandingType") == "cstore"), None
                ),
                "amenities": [a.get("name") for a in value.get("amenities") or []],
                "grades": value.get("fuels") or [],
                "price_unit": value.get("priceUnit"),
                "star_rating": value.get("starRating"),
                "ratings_count": value.get("ratingsCount"),
                "has_active_outage": value.get("hasActiveOutage"),
            }
        )
    return out


def reviews(state, city):
    """Tier one, same 1 credit fetch. Member reviews with GasBuddy's own
    sentiment score, so you get sentiment without running a model.

    Reviews carry a memberId, so treat them as personal data.
    """
    html = _fetch(city_url(state, city), mode="auto").text
    state_cache = json.loads(APOLLO.search(html).group(1))
    return [
        {
            "review_id": v.get("reviewId"),
            "member_id": v.get("memberId"),
            "overall_rating": v.get("overallRating"),
            "text": v.get("review"),
            "date": v.get("reviewDate"),
            "sentiment_score": v.get("sentimentScore"),
            "agree_total": v.get("agreeTotal"),
            "visible": v.get("isVisible"),
        }
        for v in state_cache.values()
        if isinstance(v, dict) and v.get("__typename") == "Review"
    ]


def prices(state, city, wait=9000):
    """Tier two. 25 credits. The numbers the pages actually get read for.

    Prices land after hydration, so this is a genuine case for a browser.
    A 9 second wait produced 10 price nodes against 20 cached stations,
    because the visible list is paginated and fills from the top.
    """
    data = _fetch(
        city_url(state, city),
        extract_rules=json.dumps(PRICE_RULES),
        render_js="true",
        premium_proxy="true",
        country_code="us",
        wait=wait,
    ).json()
    return [p for p in (data.get("prices") or []) if p]


if __name__ == "__main__":
    rows = stations("new-york", "new-york")
    print(f"{len(rows)} stations for 1 credit")
    for s in rows[:5]:
        print(
            f"  {s['name'][:18]:<18} {str(s['fuel_brand']):<10} "
            f"{s['locality']:<10} {s['star_rating']} stars ({s['ratings_count']})"
        )

    rv = reviews("new-york", "new-york")
    print(f"\n{len(rv)} reviews, sentiment scores: {[r['sentiment_score'] for r in rv[:6]]}")

    print("\nnow the expensive part")
    print("  prices:", prices("new-york", "new-york"))
