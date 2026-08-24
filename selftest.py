"""Offline checks for the parts that don't need the internet."""
import json
from datetime import datetime, timezone

import hunter as H
import config as C

now = datetime(2026, 8, 24, tzinfo=timezone.utc)
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {name}")
    else:
        fail += 1
        print(f"  FAIL  {name} {extra}")


print("\n1. Sold-date parsing")
for txt, want in [
    ("12 Aug 2026", (2026, 8, 12)),
    ("Aug 12, 2026", (2026, 8, 12)),
    ("3 Jul 2026", (2026, 7, 3)),
    ("Sept 9, 2026", (2026, 9, 9)),
    ("1 Jan 26", (2026, 1, 1)),
]:
    d = H.parse_sold_date(txt, now)
    check(f"{txt!r}", d is not None and (d.year, d.month, d.day) == want, f"got {d}")
check("garbage rejected", H.parse_sold_date("no date here", now) is None)


print("\n2. eBay page parsing (old s-item markup)")
old_html = "<ul>" + "".join(f"""
<li class="s-item s-item__pl-on-bottom">
  <a class="s-item__link" href="https://www.ebay.com.au/itm/2860012345{i}?hash=x">
  <img src="https://i.ebayimg.com/img{i}.jpg">
  <div class="s-item__title">Magnetic Phone Holder Car Mount Dashboard Stand</div>
  <span class="s-item__price">AU $14.9{i}</span>
  <span class="s-item__title--tag">Sold  {10+i} Aug 2026</span>
  <span class="s-item__shipping">Free postage</span></a>
</li>""" for i in range(5)) + "</ul>"
rows = H.parse_ebay_page(old_html, now)
check("found 5 rows", len(rows) == 5, f"got {len(rows)}")
check("title clean", rows[0]["title"].startswith("Magnetic Phone Holder"))
check("price parsed", rows[0]["price"] == 14.90, rows[0]["price"])
check("date parsed", rows[0]["sold_date"].day == 10, rows[0]["sold_date"])
check("id extracted", rows[0]["item_id"] == "28600123450", rows[0]["item_id"])
check("image kept", rows[0]["image"].endswith(".jpg"))


print("\n3. eBay page parsing (new s-card markup)")
new_html = """<ul>
<li class="s-card s-card--horizontal">
  <a href="https://www.ebay.co.uk/itm/167788990011">
  <img data-src="https://i.ebayimg.com/n.jpg">
  <span class="s-card__title"><span class="su-styled-text">Stainless Steel Kitchen Grater Set 4pcs</span></span>
  <span class="s-card__price">£8.49</span>
  <span class="s-card__caption">Sold 21 Aug 2026</span></a>
</li>
<li class="s-card"><a href="https://www.ebay.co.uk/itm/167788990012">
  <span class="s-card__title">New Listing Silicone Baking Mat Non Stick Tray Liner</span>
  <span class="s-card__price">£5.99</span>
  <span class="s-card__caption">Sold 22 Aug 2026</span></a></li>
</ul>"""
rows2 = H.parse_ebay_page(new_html, now)
check("found 2 rows", len(rows2) == 2, f"got {len(rows2)}")
check("price GBP", rows2[0]["price"] == 8.49, rows2[0]["price"])
check("'New Listing' stripped",
      rows2[1]["title"].startswith("Silicone Baking"), rows2[1]["title"])
check("data-src image", rows2[0]["image"].endswith("n.jpg"))


print("\n4. Junk cards ignored")
junk = """<ul>
<li class="s-item"><div class="s-item__title">Shop on eBay</div></li>
<li class="s-item"><a href="/b/category/12345"><span class="s-item__price">$5</span></a></li>
<li class="s-card"><a href="https://www.ebay.com.au/itm/999"><span class="s-card__title">ab</span><span class="s-card__price">$1</span></a></li>
</ul>"""
check("all 3 junk rows dropped", len(H.parse_ebay_page(junk, now)) == 0,
      H.parse_ebay_page(junk, now))


print("\n5. Brand / VeRO blocklist")
bl = H.load_blocklist("brands.txt")
for title, want in [
    ("Wireless Earbuds Bluetooth Headphones Sport", False),
    ("Apple iPhone 14 Case Clear Cover", True),
    ("Case for Samsung Galaxy S23 Shockproof", True),
    ("Silicone Baking Mat Non Stick Tray Liner", False),
    ("Disney Frozen Elsa Girls Backpack", True),
    ("Stainless Steel Kitchen Grater Set 4pcs", False),
    ("Genuine Nike Running Socks 3 Pack", True),
    ("Pineapple Shaped LED Night Light", False),
    ("Premium Watch Strap 22mm Leather\u2122", True),
]:
    check(f"{title[:42]!r} -> {want}", H.is_branded(title, bl) is want)


print("\n6. Product grouping (same item, different sellers)")
t1 = "Magnetic Phone Holder Car Mount Dashboard Stand"
t2 = "Car Dashboard Mount Magnetic Phone Stand Holder"   # same words reordered
t3 = "Stainless Steel Kitchen Grater Set 4pcs"
check("reordered titles merge", H.product_key(t1) == H.product_key(t2),
      f"{H.product_key(t1)} vs {H.product_key(t2)}")
check("different products don't merge", H.product_key(t1) != H.product_key(t3))


print("\n7. AliExpress JSON extraction (deeply nested, unknown path)")
ali_blob = {"data": {"root": {"fields": {"mods": {"itemList": {"content": [
    {"productId": "1005006123456",
     "title": {"displayTitle": "Magnetic Car Phone Holder Dashboard Mount Stand"},
     "prices": {"salePrice": {"formattedPrice": "US $3.42"}},
     "trade": {"realTradeCount": "2,000+ sold"},
     "evaluation": {"starRating": "4.7"},
     "sellingPoints": [{"tagContent": {"tagText": "Free Shipping"}}]},
    {"productId": "1005006999999",
     "title": {"displayTitle": "Magnetic Phone Car Mount Holder Dashboard"},
     "prices": {"salePrice": {"formattedPrice": "US $9.80"}},
     "trade": {"realTradeCount": "58 sold"},
     "evaluation": {"starRating": "4.9"},
     "sellingPoints": [{"tagContent": {"tagText": "Free Shipping"}}]},
    {"productId": "1005006777777",
     "title": {"displayTitle": "Totally Unrelated Garden Hose Reel 30m"},
     "prices": {"salePrice": {"formattedPrice": "US $2.10"}},
     "trade": {"realTradeCount": "5000 sold"},
     "evaluation": {"starRating": "4.8"},
     "sellingPoints": [{"tagContent": {"tagText": "Free Shipping"}}]},
]}}}}}}
found = []
H._walk_for_products(ali_blob, found)
check("located the product list", len(found) == 1 and len(found[0]) == 3,
      f"{len(found)} lists")

parsed = []
for p in found[0]:
    txt = json.dumps(p).lower()
    parsed.append({
        "ali_id": str(H._deep_get(p, "productId")),
        "ali_title": H.norm_text(str(H._deep_get(p, "displayTitle", "title"))),
        "ali_price_usd": H.money(str(H._deep_get(p, "formattedPrice", "salePrice"))),
        "ali_orders": H.parse_ali_orders(H._deep_get(p, "realTradeCount")),
        "ali_rating": H.money(str(H._deep_get(p, "starRating"))) or 0.0,
        "ali_free_ship": "free shipping" in txt,
        "ali_url": "",
    })
check("price parsed", parsed[0]["ali_price_usd"] == 3.42, parsed[0]["ali_price_usd"])
check("'2,000+ sold' -> 2000", parsed[0]["ali_orders"] == 2000, parsed[0]["ali_orders"])
check("'58 sold' -> 58", parsed[1]["ali_orders"] == 58, parsed[1]["ali_orders"])
check("rating parsed", parsed[0]["ali_rating"] == 4.7, parsed[0]["ali_rating"])
check("free shipping detected", parsed[0]["ali_free_ship"] is True)


print("\n8. ROI maths")
au = C.MARKETS[0]
fx = {"AUD": 1.52, "GBP": 0.79, "USD": 1.0}
roi, cost, net = H.calc_roi(45.0, au, 10.0, fx)
check("A$45 vs US$10 -> cost A$15.20", round(cost, 2) == 15.20, cost)
check("net after fees ~A$38.66", round(net, 2) == 38.66, round(net, 2))
check("ROI ~154%", 1.5 < roi < 1.6, roi)
roi2, _, _ = H.calc_roi(45.0, au, 17.0, fx)
check("US$17 gives ROI ~50%", 0.48 < roi2 < 0.52, roi2)
roi3, _, _ = H.calc_roi(45.0, au, 25.0, fx)
check("US$25 fails the 50% rule", roi3 < C.MIN_ROI, roi3)


print("\n9. Supplier picking (all rules together)")
best = H.pick_supplier(parsed, t1, 45.0, au, fx)
check("picked a supplier", best is not None)
if best:
    check("picked the 2000-order one", best["ali_id"] == "1005006123456", best["ali_id"])
    check("rejected the 58-order one", best["ali_orders"] >= C.ALI_MIN_ORDERS)
    check("ROI clears 50%", best["roi"] >= C.MIN_ROI, best["roi"])
check("unrelated product rejected by title check",
      H.overlap_score(t1, "Totally Unrelated Garden Hose Reel 30m") < 0.30)
check("no supplier when eBay price too low",
      H.pick_supplier(parsed, t1, 4.0, au, fx) is None)


print("\n10. Search query building")
q = H.build_query("Magnetic Phone Holder Car Mount Dashboard Stand 360 Rotating NEW UK")
check("query is short and clean", 2 <= len(q.split()) <= 6, q)
check("stopwords removed", "new" not in q and "uk" not in q, q)

print(f"\n{'='*46}\n  {ok} passed, {fail} failed\n{'='*46}")
raise SystemExit(1 if fail else 0)
