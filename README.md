# Product Hunter

Finds products that already sell consistently on eBay AU and UK, matches each
one to a cheap AliExpress supplier, keeps only the ones clearing 50%+ ROI, and
writes them into a Google Sheet.

Runs itself once a day on GitHub Actions. No server, no database, free to run.

**New here? Start with the [Setup Guide](SETUP.md).** It takes about 30 minutes,
once, and assumes no coding knowledge.

---

## The idea

Most dropshipping research tools show you what *might* sell. This one only
reports products with a proven sales record — something that sold on at least
10 different days in the last 30, not 15 units in one lucky afternoon. Then it
checks whether you can actually source it profitably, after eBay's fees.

If it can't find a supplier that clears the margin, the product is discarded.
You only ever see products that pass both tests.

---

## How it works

Four stages, all in [hunter.py](hunter.py):

**1. Collect** — Walks every term in `SEARCH_TERMS` across every market in
`MARKETS`, scraping eBay's *sold listings* (real completed sales, not asking
prices). Terms are shuffled each run so a mid-run block doesn't always cost you
the same categories.

**2. Group and filter** — Listings are normalised into a `product_key` so the
same item from different sellers merges into one product. Each group must clear:

| Rule | Config | Default |
|---|---|---|
| Sales in the window | `MIN_SALES_IN_WINDOW` | 15 |
| Distinct days sold on | `MIN_DISTINCT_SALE_DAYS` | 10 |
| Under the price cap | `max_price` per market | A$45 / £24 |
| Not a branded/VeRO item | [brands.txt](brands.txt) | 138 entries |

The **distinct-days** rule is the important one — it's what separates a product
with steady demand from a one-off spike. The median-priced listing in each group
becomes the representative, so an outlier seller doesn't skew the economics.

**3. Source** — For each survivor it works backwards from the ROI target to the
most it could possibly pay on AliExpress, then searches within that ceiling:

```
net       = ebay_price × (1 − fee_percent) − fee_fixed
max_spend = net ÷ (1 + MIN_ROI) ÷ fx_rate
```

A supplier is only accepted if it has enough orders (`ALI_MIN_ORDERS`), a decent
rating (`ALI_MIN_RATING`), free shipping if required, and a title that actually
overlaps the eBay product — this last check is what stops it pairing a phone
holder with an unrelated cheap cable.

**4. Write** — Passing rows are appended to the `Products` tab. Their keys go to
the `_seen` tab so the same product is never delivered twice.

---

## What you get

One row per product in the `Products` tab:

`Date added` · `Market` · `Product title` · `eBay price` · `Currency` ·
`Sales (30d)` · `Sale days (30d)` · `eBay link` · `AliExpress title` ·
`Ali cost` · `Ali orders` · `Ali rating` · `Profit` · `ROI %` ·
`AliExpress link` · `Image`

Results are sorted so the most consistently-selling products land first.

---

## Configuration

Everything tunable lives in [config.py](config.py). You should not need to edit
`hunter.py`.

| I want to... | Change this |
|---|---|
| Get more/fewer products | `TARGET_PRODUCTS_PER_DAY` |
| Change the max eBay price | `max_price` inside `MARKETS` |
| Change the profit rule | `MIN_ROI` (0.50 = 50%) |
| Require more AliExpress orders | `ALI_MIN_ORDERS` |
| Search different products | `SEARCH_TERMS` |
| Be stricter about "sells daily" | `MIN_DISTINCT_SALE_DAYS` |
| Add a market (e.g. US) | append to `MARKETS` |
| Switch to paid data | `SOURCE_MODE` |

**`SEARCH_TERMS` is the single biggest lever on output.** 40 terms is a starting
point, not a limit. If you want more products, add terms before you loosen any
of the quality rules — going to 150 terms costs you nothing but run time.

### Data sources

`SOURCE_MODE` controls where listings come from:

- `"free"` — scrape directly. Costs nothing, can get blocked.
- `"apify"` — paid [Apify](https://apify.com) actors. Costs roughly $2–6/day at
  100 products, very reliable.
- `"auto"` *(default)* — tries free first, pays only when free returns nothing.

`auto` is the right choice for almost everyone. See the
[troubleshooting section](SETUP.md#when-it-stops-finding-things) for adding an
Apify token.

---

## Running it yourself

The daily run happens automatically via
[.github/workflows/daily.yml](.github/workflows/daily.yml) at 02:00 UTC. To run
it now, use **Actions → Daily product hunt → Run workflow**, or change the
`cron:` line to reschedule.

To run locally you need the service-account JSON in a `GOOGLE_CREDENTIALS`
environment variable:

```bash
pip install -r requirements.txt
python hunter.py
```

### Tests

```bash
python selftest.py
```

47 checks covering page parsing, the brand blocklist, product grouping, ROI
maths, and supplier selection. No internet or credentials needed. **If these
pass, the logic is fine** and any failure is eBay changing its page layout, not
your setup — which makes this the first thing to run when something breaks.

---

## Known limitations

**This will break periodically.** eBay and AliExpress change their markup every
few months. When they do, the free scraper stops finding things and you switch
to `SOURCE_MODE = "apify"` until the parser is updated. That's expected, not a
bug — `selftest.py` tells you which of the two it is.

**Output drops after week one.** The first run pulls from a 30-day backlog and
hits the target easily. After that it only catches genuinely *new* products, and
settles around 30–60/day on two markets. To hold 100, add `SEARCH_TERMS` or add
a third market. Worth saying out loud before anyone expects 100/day forever.

**Fee percentages are approximate.** `fee_percent` and `fee_fixed` in `MARKETS`
are sensible defaults, but eBay's final value fee varies by category and seller
status. Confirm them against your own account or every ROI figure is slightly
optimistic.

**Don't delete the `_seen` tab.** It's the only record of what's already been
delivered. Clear it to deliberately start fresh; delete it and you'll get
duplicates.

---

## Project layout

```
hunter.py                    the whole pipeline
config.py                    every setting worth changing
brands.txt                   brand / VeRO blocklist, one per line
selftest.py                  47 offline checks
requirements.txt             four dependencies
SETUP.md                     first-time setup guide
.github/workflows/daily.yml  the daily schedule
```
