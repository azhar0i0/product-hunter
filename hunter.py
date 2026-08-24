#!/usr/bin/env python3
"""
Product Hunter
--------------
Finds products that already sell on eBay (AU/UK), locates a cheap AliExpress
supplier for each, keeps only the ones that clear your ROI rule, and appends
them to a Google Sheet. Runs unattended once a day.

Run it with:   python hunter.py
"""

import json
import os
import random
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import config as C

# --------------------------------------------------------------------------
# Basics
# --------------------------------------------------------------------------

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

STOPWORDS = {
    "the", "and", "for", "with", "new", "free", "pcs", "pack", "set", "x",
    "uk", "au", "aus", "usa", "hot", "sale", "high", "quality", "premium",
    "best", "top", "size", "color", "colour", "style", "type", "mini", "pro",
    "plus", "max", "kit", "pieces", "piece", "of", "in", "on", "to", "a",
}


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def fetch(session, url, timeout=25):
    """GET a URL with retries and a polite delay. Returns text or None."""
    for attempt in range(C.MAX_RETRIES):
        try:
            session.headers["User-Agent"] = random.choice(UA_POOL)
            r = session.get(url, timeout=timeout)
            if r.status_code == 200 and len(r.text) > 2000:
                return r.text
            log(f"  status {r.status_code} (len {len(r.text)}) attempt {attempt+1}")
        except requests.RequestException as e:
            log(f"  network error: {type(e).__name__} attempt {attempt+1}")
        time.sleep(C.REQUEST_DELAY_SECONDS * (attempt + 2))
    return None


def norm_text(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def money(s):
    """Pull the first number out of a price string like 'AU $12.99 to $19.99'."""
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    return float(m.group(1)) if m else None


def tokens(title):
    t = re.sub(r"[^a-z0-9 ]", " ", norm_text(title).lower())
    return [w for w in t.split() if len(w) > 2 and w not in STOPWORDS]


def product_key(title):
    """A stable-ish fingerprint so the same product from different sellers merges."""
    return " ".join(sorted(tokens(title))[:6])


# --------------------------------------------------------------------------
# Currency
# --------------------------------------------------------------------------

def get_fx():
    """Units of each currency per 1 USD. Falls back to config if offline."""
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=AUD,GBP", timeout=12)
        if r.ok:
            rates = r.json().get("rates", {})
            if "AUD" in rates and "GBP" in rates:
                rates["USD"] = 1.0
                log(f"FX live: {rates}")
                return rates
    except Exception:
        pass
    log(f"FX fallback: {C.FX_FALLBACK}")
    return dict(C.FX_FALLBACK)


# --------------------------------------------------------------------------
# Brand / VeRO blocklist
# --------------------------------------------------------------------------

def load_blocklist(path="brands.txt"):
    words = set()
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip().lower()
            if line and not line.startswith("#"):
                words.add(line)
    log(f"Blocklist loaded: {len(words)} entries")
    return words


def is_branded(title, blocklist):
    low = " " + re.sub(r"[^a-z0-9 ]", " ", norm_text(title).lower()) + " "
    if "\u2122" in title or "\u00ae" in title:
        return True
    for brand in blocklist:
        if f" {brand} " in low:
            return True
    if C.BLOCK_COMPATIBLE_WITH and re.search(r"\b(for|compatible with|fits)\b", low):
        return True
    return False


# --------------------------------------------------------------------------
# eBay: sold listings (free scrape)
# --------------------------------------------------------------------------

def parse_sold_date(text, now):
    """eBay writes 'Sold 12 Aug 2026' or 'Sold Aug 12, 2026'. Handle both."""
    t = norm_text(text)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{2,4})", t)
    if m:
        d, mon, y = int(m.group(1)), m.group(2).lower()[:3], int(m.group(3))
    else:
        m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{2,4})", t)
        if not m:
            return None
        mon, d, y = m.group(1).lower()[:3], int(m.group(2)), int(m.group(3))
    if mon not in MONTHS:
        return None
    if y < 100:
        y += 2000
    try:
        return datetime(y, MONTHS[mon], d, tzinfo=timezone.utc)
    except ValueError:
        return None


def _card_text(card, *class_hints):
    for hint in class_hints:
        el = card.select_one(f'[class*="{hint}"]')
        if el and el.get_text(strip=True):
            return el.get_text(" ", strip=True)
    return ""


def parse_ebay_page(html, now):
    """Extract sold rows from an eBay search-results page.
    Written defensively: eBay swaps between s-item and s-card markup."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.s-item, li.s-card, li[class*='s-item'], li[class*='s-card']")
    rows = []
    for card in cards:
        link_el = card.select_one('a[href*="/itm/"]')
        if not link_el:
            continue
        href = link_el.get("href", "").split("?")[0]
        m = re.search(r"/itm/(\d+)", href)
        if not m:
            continue
        item_id = m.group(1)

        title = _card_text(card, "s-item__title", "s-card__title", "su-styled-text")
        title = re.sub(r"^(New Listing|Shop on eBay|SPONSORED)\s*", "", title).strip()
        if not title or len(title) < 8:
            continue

        price = money(_card_text(card, "s-item__price", "s-card__price"))
        if price is None:
            continue

        blob = card.get_text(" ", strip=True)
        sold_dt = None
        sm = re.search(r"Sold\s+([^|]{6,20})", blob)
        if sm:
            sold_dt = parse_sold_date(sm.group(1), now)

        img_el = card.select_one("img")
        img = ""
        if img_el:
            img = img_el.get("src") or img_el.get("data-src") or ""

        rows.append({
            "item_id": item_id,
            "title": norm_text(title),
            "price": price,
            "sold_date": sold_dt,
            "url": href,
            "image": img,
        })
    return rows


def ebay_sold_free(session, market, term, now, max_pages=2):
    """Scrape eBay sold listings. 240 items per page = very few requests."""
    out = []
    for page in range(1, max_pages + 1):
        url = (
            f"https://{market['site']}/sch/i.html"
            f"?_nkw={quote_plus(term)}"
            f"&LH_Sold=1&LH_Complete=1"
            f"&LH_ItemCondition=1000"          # new only
            f"&_udhi={market['max_price']}"    # max price
            f"&_sop=13"                        # ended most recently
            f"&_ipg=240"                       # 240 results per page
            f"&_pgn={page}"
        )
        html = fetch(session, url)
        if not html:
            break
        rows = parse_ebay_page(html, now)
        if not rows:
            break
        for r in rows:
            r["market"] = market["name"]
            r["term"] = term
        out.extend(rows)
        time.sleep(C.REQUEST_DELAY_SECONDS)
        if len(rows) < 100:
            break
    return out


def ebay_sold_apify(market, term, now):
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        return []
    url = f"https://api.apify.com/v2/acts/{C.APIFY_EBAY_ACTOR}/run-sync-get-dataset-items?token={token}"
    payload = {
        "keywords": [term],
        "ebaySite": market["site"].replace("www.", ""),
        "daysToScrape": C.SOLD_WINDOW_DAYS,
        "count": 200,
        "maxPrice": market["max_price"],
        "itemCondition": "new",
        "sortOrder": "endedRecently",
    }
    try:
        r = requests.post(url, json=payload, timeout=300)
        if not r.ok:
            return []
        out = []
        for it in r.json():
            dt = None
            if it.get("endedAt"):
                try:
                    dt = datetime.fromisoformat(
                        it["endedAt"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            out.append({
                "item_id": str(it.get("itemId", "")),
                "title": norm_text(it.get("title", "")),
                "price": money(str(it.get("soldPrice", ""))),
                "sold_date": dt,
                "url": it.get("url", ""),
                "image": it.get("thumbnailUrl", "") or "",
                "market": market["name"],
                "term": term,
            })
        return [r for r in out if r["title"] and r["price"]]
    except requests.RequestException:
        return []


# --------------------------------------------------------------------------
# AliExpress
# --------------------------------------------------------------------------

def _walk_for_products(node, found):
    """AliExpress moves its JSON around. Rather than hardcode a path,
    hunt anywhere in the blob for a list of dicts that look like products."""
    if isinstance(node, list):
        if len(node) >= 3 and all(isinstance(x, dict) for x in node[:3]):
            keys = set(node[0].keys())
            if keys & {"productId", "product_id", "productIds", "itemId"}:
                found.append(node)
        for x in node:
            _walk_for_products(x, found)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_for_products(v, found)


def _deep_get(d, *names):
    """Find the first value whose key matches any of `names`, at any depth."""
    stack = [d]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, (str, int, float)) and v != "":
                    return v
                stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def parse_ali_orders(val):
    """'1,234 sold' / '1000+ sold' / 500  ->  int"""
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).replace(",", "").lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k)?", s)
    if not m:
        return 0
    n = float(m.group(1))
    if m.group(2) == "k":
        n *= 1000
    return int(n)


def ali_search_free(session, query, max_price_usd):
    url = (
        "https://www.aliexpress.com/w/wholesale-"
        f"{quote_plus(query).replace('+', '-')}.html"
        f"?SortType=total_tranpro_desc&maxPrice={int(max_price_usd * 100)}"
    )
    html = fetch(session, url)
    if not html:
        return []

    blobs = re.findall(
        r"_init_data_\s*=\s*(\{.*?\})\s*</script>", html, re.S) or \
        re.findall(r"window\.__INIT_DATA__\s*=\s*(\{.*?\})\s*;?\s*</script>", html, re.S)

    products = []
    for blob in blobs:
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        found = []
        _walk_for_products(data, found)
        for lst in found:
            products.extend(lst)
        if products:
            break

    out = []
    for p in products:
        pid = _deep_get(p, "productId", "product_id", "itemId")
        if not pid:
            continue
        title = _deep_get(p, "displayTitle", "title", "subject", "productTitle")
        price = _deep_get(p, "formattedPrice", "salePrice",
                          "minPrice", "targetSalePrice")
        orders = _deep_get(p, "realTradeCount", "tradeCount",
                           "orders", "lastestVolume", "tradeDesc")
        rating = _deep_get(p, "averageStar", "evaluationRate", "starRating")
        blob_txt = json.dumps(p).lower()
        out.append({
            "ali_id": str(pid),
            "ali_title": norm_text(str(title or "")),
            "ali_price_usd": money(str(price or "")),
            "ali_orders": parse_ali_orders(orders),
            "ali_rating": money(str(rating or "")) or 0.0,
            "ali_free_ship": ("free shipping" in blob_txt
                              or "freeshipping" in blob_txt
                              or '"free"' in blob_txt),
            "ali_url": f"https://www.aliexpress.com/item/{pid}.html",
        })
    return [o for o in out if o["ali_title"] and o["ali_price_usd"]]


def ali_search_apify(query, max_price_usd):
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        return []
    url = f"https://api.apify.com/v2/acts/{C.APIFY_ALI_ACTOR}/run-sync-get-dataset-items?token={token}"
    payload = {
        "query": query,
        "maxItems": 20,
        "maxPrice": max_price_usd,
        "freeShipping": C.ALI_REQUIRE_FREE_SHIPPING,
        "minRating": C.ALI_MIN_RATING,
        "sortBy": "orders",
    }
    try:
        r = requests.post(url, json=payload, timeout=300)
        if not r.ok:
            return []
        out = []
        for it in r.json():
            pid = it.get("productId") or it.get("id") or ""
            if not pid:
                continue
            out.append({
                "ali_id": str(pid),
                "ali_title": norm_text(it.get("title", "")),
                "ali_price_usd": money(str(it.get("price", it.get("salePrice", "")))),
                "ali_orders": parse_ali_orders(it.get("sold", it.get("orders"))),
                "ali_rating": float(it.get("rating") or 0),
                "ali_free_ship": bool(it.get("freeShipping", True)),
                "ali_url": it.get("url") or f"https://www.aliexpress.com/item/{pid}.html",
            })
        return [o for o in out if o["ali_title"] and o["ali_price_usd"]]
    except requests.RequestException:
        return []


# --------------------------------------------------------------------------
# Matching and profit
# --------------------------------------------------------------------------

def build_query(title):
    """Turn a long eBay title into a short AliExpress search."""
    return " ".join(tokens(title)[:6])


def overlap_score(a, b):
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta)


def calc_roi(ebay_price, market, ali_price_usd, fx):
    """Returns (roi, ali_cost_in_market_currency, net_after_fees)."""
    rate = fx.get(market["currency"], 1.0)
    ali_cost = ali_price_usd * rate
    if ali_cost <= 0:
        return None, None, None
    net = ebay_price * (1 - market["fee_percent"]) - market["fee_fixed"]
    roi = (net - ali_cost) / ali_cost
    return roi, ali_cost, net


def pick_supplier(candidates, ebay_title, ebay_price, market, fx):
    """Choose the cheapest AliExpress listing that passes every rule."""
    best = None
    for c in candidates:
        if c["ali_orders"] < C.ALI_MIN_ORDERS:
            continue
        if C.ALI_REQUIRE_FREE_SHIPPING and not c["ali_free_ship"]:
            continue
        if C.ALI_MIN_RATING and c["ali_rating"] and c["ali_rating"] < C.ALI_MIN_RATING:
            continue
        if overlap_score(ebay_title, c["ali_title"]) < 0.30:
            continue  # not actually the same product
        roi, cost, net = calc_roi(ebay_price, market, c["ali_price_usd"], fx)
        if roi is None or roi < C.MIN_ROI:
            continue
        cand = dict(c, roi=roi, ali_cost=cost, net_after_fees=net)
        if best is None or cand["roi"] > best["roi"]:
            best = cand
    return best


# --------------------------------------------------------------------------
# Google Sheets
# --------------------------------------------------------------------------

HEADERS = [
    "Date added", "Market", "Product title", "eBay price", "Currency",
    "Sales (30d)", "Sale days (30d)", "eBay link",
    "AliExpress title", "Ali cost", "Ali orders", "Ali rating",
    "Profit", "ROI %", "AliExpress link", "Image",
]


def open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_CREDENTIALS", "")
    if not raw:
        raise SystemExit("GOOGLE_CREDENTIALS is not set. See README step 3.")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    gc = gspread.authorize(creds)
    try:
        sh = gc.open(C.SHEET_NAME)
    except Exception:
        raise SystemExit(
            f"Cannot open sheet '{C.SHEET_NAME}'. Did you share it with "
            f"{info.get('client_email', 'your service account')}?")
    return sh


def get_tab(sh, title, headers=None):
    try:
        ws = sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows=2000, cols=max(len(headers or []), 4))
        if headers:
            ws.append_row(headers)
    return ws


def load_seen(sh):
    ws = get_tab(sh, C.TAB_SEEN, ["key"])
    try:
        return set(x.strip() for x in ws.col_values(1) if x.strip())
    except Exception:
        return set()


def save_results(sh, rows, new_keys):
    ws = get_tab(sh, C.TAB_RESULTS, HEADERS)
    if not ws.get_all_values():
        ws.append_row(HEADERS)
    ws.append_rows(rows, value_input_option="USER_ENTERED")
    seen_ws = get_tab(sh, C.TAB_SEEN, ["key"])
    seen_ws.append_rows([[k] for k in new_keys])


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=C.SOLD_WINDOW_DAYS)
    session = make_session()
    fx = get_fx()
    blocklist = load_blocklist()

    log("Opening Google Sheet...")
    sh = open_sheet()
    seen = load_seen(sh)
    log(f"Already delivered before: {len(seen)} products")

    # ---- Stage 1: collect eBay sold rows -----------------------------------
    raw = []
    terms = list(C.SEARCH_TERMS)
    random.shuffle(terms)

    for market in C.MARKETS:
        for term in terms:
            rows = []
            if C.SOURCE_MODE in ("free", "auto"):
                rows = ebay_sold_free(session, market, term, now)
            if not rows and C.SOURCE_MODE in ("apify", "auto"):
                rows = ebay_sold_apify(market, term, now)
            log(f"eBay {market['name']:>2} | {term:<20} -> {len(rows)} sold rows")
            raw.extend(rows)

    log(f"Stage 1 done: {len(raw)} raw sold rows")
    if not raw:
        log("Nothing came back. eBay may be blocking you -- set SOURCE_MODE='apify'.")
        return

    # ---- Stage 2: group into products, measure consistency -----------------
    groups = defaultdict(list)
    for r in raw:
        if r["sold_date"] and r["sold_date"] < cutoff:
            continue
        groups[(r["market"], product_key(r["title"]))].append(r)

    candidates = []
    for (market_name, key), rows in groups.items():
        if len(rows) < C.MIN_SALES_IN_WINDOW:
            continue
        days = {r["sold_date"].date() for r in rows if r["sold_date"]}
        if days and len(days) < C.MIN_DISTINCT_SALE_DAYS:
            continue
        rows.sort(key=lambda r: r["price"])
        rep = rows[len(rows) // 2]          # median-priced listing
        if is_branded(rep["title"], blocklist):
            continue
        candidates.append({
            "key": f"{market_name}|{key}",
            "market_name": market_name,
            "rep": rep,
            "sales": len(rows),
            "sale_days": len(days),
        })

    candidates = [c for c in candidates if c["key"] not in seen]
    candidates.sort(key=lambda c: (c["sale_days"], c["sales"]), reverse=True)
    log(f"Stage 2 done: {len(candidates)} unique products worth sourcing")

    # ---- Stage 3: find an AliExpress supplier for each ---------------------
    out_rows, new_keys = [], []
    market_by_name = {m["name"]: m for m in C.MARKETS}

    for cand in candidates:
        if len(out_rows) >= C.TARGET_PRODUCTS_PER_DAY:
            break
        market = market_by_name[cand["market_name"]]
        rep = cand["rep"]
        rate = fx.get(market["currency"], 1.0)
        # We can never pay more than this on Ali and still hit the ROI target
        net = rep["price"] * (1 - market["fee_percent"]) - market["fee_fixed"]
        max_usd = (net / (1 + C.MIN_ROI)) / rate
        if max_usd <= 0.5:
            continue

        query = build_query(rep["title"])
        found = []
        if C.SOURCE_MODE in ("free", "auto"):
            found = ali_search_free(session, query, max_usd)
            time.sleep(C.REQUEST_DELAY_SECONDS)
        if not found and C.SOURCE_MODE in ("apify", "auto"):
            found = ali_search_apify(query, max_usd)

        supplier = pick_supplier(found, rep["title"], rep["price"], market, fx)
        if not supplier:
            continue

        profit = supplier["net_after_fees"] - supplier["ali_cost"]
        out_rows.append([
            now.strftime("%Y-%m-%d"),
            market["name"],
            rep["title"],
            round(rep["price"], 2),
            market["currency"],
            cand["sales"],
            cand["sale_days"],
            rep["url"],
            supplier["ali_title"],
            round(supplier["ali_cost"], 2),
            supplier["ali_orders"],
            supplier["ali_rating"],
            round(profit, 2),
            round(supplier["roi"] * 100, 1),
            supplier["ali_url"],
            rep["image"],
        ])
        new_keys.append(cand["key"])
        log(f"  MATCH {len(out_rows):>3}/{C.TARGET_PRODUCTS_PER_DAY} "
            f"| ROI {supplier['roi']*100:5.1f}% | {rep['title'][:52]}")

    # ---- Stage 4: write --------------------------------------------------
    if out_rows:
        save_results(sh, out_rows, new_keys)
        log(f"DONE. Wrote {len(out_rows)} products to '{C.SHEET_NAME}'.")
    else:
        log("DONE, but 0 products passed. Loosen MIN_ROI or add more SEARCH_TERMS.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
