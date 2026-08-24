"""
=============================================================
  EDIT THIS FILE ONLY. You do not need to touch hunter.py.
=============================================================
"""

# ---------- 1. HOW MANY PRODUCTS DO YOU WANT PER DAY ----------
TARGET_PRODUCTS_PER_DAY = 100

# ---------- 2. WHICH EBAY MARKETS ----------
# Each market: the eBay site, its currency, and eBay's selling fee.
MARKETS = [
    {
        "name": "AU",
        "site": "www.ebay.com.au",
        "currency": "AUD",
        "max_price": 45.0,        # client rule: max A$45
        "fee_percent": 0.132,     # eBay final value fee ~13.2% -- confirm per category
        "fee_fixed": 0.40,        # per-order fixed fee
    },
    {
        "name": "UK",
        "site": "www.ebay.co.uk",
        "currency": "GBP",
        "max_price": 24.0,        # roughly A$45 in GBP -- adjust if you like
        "fee_percent": 0.128,
        "fee_fixed": 0.30,
    },
]

# ---------- 3. SALES HISTORY RULES ----------
SOLD_WINDOW_DAYS = 30      # look back this many days
MIN_SALES_IN_WINDOW = 15   # must have at least this many sales
MIN_DISTINCT_SALE_DAYS = 10  # must have sold on at least this many DIFFERENT days
#                              ^ this is what "consistent daily sales" really means

# ---------- 4. ALIEXPRESS SOURCING RULES ----------
ALI_MIN_ORDERS = 100        # client rule: 100+ sold
ALI_REQUIRE_FREE_SHIPPING = True
ALI_MIN_RATING = 4.3        # ignore junk sellers (set to 0 to disable)
MIN_ROI = 0.50              # client rule: 50% ROI or above

# ---------- 5. CURRENCY ----------
# Auto-fetched daily. These are only the fallback if the fetch fails.
FX_FALLBACK = {"AUD": 1.52, "GBP": 0.79, "USD": 1.0}  # units per 1 USD

# ---------- 6. WHAT TO SEARCH ----------
# The hunter walks through these every day. Add or remove freely.
# Tip: generic, unbranded, cheap categories work best.
SEARCH_TERMS = [
    "phone holder", "cable organiser", "kitchen gadget", "pet grooming",
    "car accessories", "led strip light", "storage box", "jewellery organiser",
    "camping gear", "garden tool", "makeup brush", "hair clip",
    "laptop stand", "desk organiser", "bike accessories", "fishing tackle",
    "baby feeding", "yoga accessories", "phone case", "keyring",
    "measuring tool", "cleaning brush", "shoe rack", "wall hook",
    "sewing kit", "craft supplies", "fitness band", "water bottle",
    "sunglasses case", "travel pouch", "door stopper", "drawer divider",
    "tap filter", "usb light", "screen protector", "watch strap",
    "dog toy", "cat toy", "bird feeder", "plant pot",
]

# ---------- 7. SAFETY: BRANDS AND BANNED WORDS ----------
# Anything matching brands.txt gets thrown away. Add to that file over time.
BLOCK_COMPATIBLE_WITH = False  # True = also reject "compatible with Apple" style titles

# ---------- 8. GOOGLE SHEET ----------
SHEET_NAME = "Product Hunter"   # name of your Google Sheet
TAB_RESULTS = "Products"        # tab where products go
TAB_SEEN = "_seen"              # tab that remembers what you already sent

# ---------- 9. DATA SOURCE MODE ----------
# "free"  = scrape directly. Costs nothing. Can get blocked.
# "apify" = use paid Apify actors. Costs money but very reliable.
# "auto"  = try free first, fall back to apify if free returns nothing.
SOURCE_MODE = "auto"

APIFY_EBAY_ACTOR = "caffein.dev~ebay-sold-listings"
APIFY_ALI_ACTOR = "sovereigntaylor~aliexpress-product-scraper"

# ---------- 10. POLITENESS ----------
REQUEST_DELAY_SECONDS = 2.5   # wait between requests. Lower = faster but riskier.
MAX_RETRIES = 3
