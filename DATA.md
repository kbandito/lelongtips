# Where the data lives

A short orientation for a future session. Everything is JSON files in this
repository — there is no database server, nothing to connect to, no
credentials needed to read any of it.

## The files that matter

| File | Size | What it is |
|---|---|---|
| `data/snapshots/YYYY-MM-DD.json` | ~2–8 MB each, 53 files | **The source of truth.** One scrape, exactly as observed that day. Never edit these. |
| `data/properties.json` | 30 MB | The rebuilt database: 14,335 unique properties, each with its price and auction-date history. Derived — regenerated from snapshots. |
| `data/changes.json` | 9 MB | Every change ever detected (price moves, date moves). Derived. |
| `docs/data/active.json` | 15 MB | Trimmed, short-key version the dashboard reads in the browser. Derived. |
| `docs/data/stats.json` | 9 KB | Headline counts and the scan history. Derived. |

Only `data/snapshots/` is original. Everything else is rebuilt from it by
`src/reprocess.py`, so a bad run is undone by deleting that day's snapshot
and rerunning — nothing is lost permanently.

## Reading it

```python
import json
db = json.load(open('data/properties.json', encoding='utf-8'))   # keep the encoding
prop = db['retail_lot_klselangor_size_not_specified_plaza_haji_taib_...']
```

Always pass `encoding='utf-8'`. Malaysian property names carry accents
(`Résidensi 280`), and on Windows the default is cp1252, which silently
writes files nothing else can read.

`properties.json` is a dict keyed by a slug built from title, location, size
and address. That key is **not** stable across time — the site re-issues its
own ids and has stopped showing street addresses. To follow one property
across scrapes, use `site_listing_id` (the site's numeric id) and fall back
to the number in `image_url` (`/listings/901493.jpg`) for older records.

## The fields worth knowing

```
price, price_value        the reserve. price_value is None or price_masked
                          is true when the scan could not see a price
price_history[]           {price, date, url} per observed change — the asset
auction_date              "08 Oct 2026 (Thu)" logged in, "Sep 2026" as a guest
auction_date_precision    "day" or "month" — tells you which of the two
auction_round             3 means the lot has already failed twice
discount                  the site's own badge, e.g. "-77%"
size, size_basis          built-up or land area
tenure, laca              Leasehold/Freehold; LACA flag
site_listing_id           the durable identifier
address_locked            true when the street address was members-only
past_auction_price        the site's own prior reserve, when it shows one
```

## The one rule

**Never write a masked price into `price_history`.** Logged out, the site
shows `RM98,xxx`, which parses to a plausible but fictional number. Treating
that as real would append a fabricated point to all 14,335 properties and
destroy the reserve-price record, which is the only thing here that cannot be
re-acquired. `price_observed()` in `src/reprocess.py` is the guard; keep using
it.

## What the data is good for

53 scrapes since 14 March, roughly every 3 days. Because each one records what
the reserve was that day, the set holds several thousand observed
reserve-price cuts — how far banks drop a reserve after a failed auction, and
how long they wait. The site itself only ever shows today's price, so this
history cannot be bought or rebuilt by anyone who did not record it.

`data/snapshots/2026-09-20.json` is the first scrape taken while logged in:
1,823 upcoming auctions with real prices, exact dates and full addresses.
Earlier snapshots have prices too; the ones taken between 13 August and
19 September are empty, because the scraper was broken then.

## Scripts

```
src/monitor.py          scrape (MAX_PAGES, DRY_RUN, SNAPSHOT_ONLY env vars)
src/reprocess.py        rebuild properties.json from all snapshots
src/generate_page.py    build docs/ dashboard from the database
src/check_session.py    is a given cookie logged in? exits 2 if not
local/run_scrape.bat    scrape from a Malaysian connection (prices need this)
```

## The catch to know about

The site masks prices, exact dates and addresses from anyone not logged in,
and it ties a login to the network that created it. A session cookie that
works in a browser in Malaysia is refused from a server abroad — confirmed
with a plain HTTP client and again with a full Chromium browser on a US
machine. So scheduled scrapes on GitHub collect everything **except** prices,
and a priced scrape has to be run from a Malaysian connection via
`local/run_scrape.bat`. See `local/README.md`.
