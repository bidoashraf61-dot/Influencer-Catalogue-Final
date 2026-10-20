"""Sample sales data for the Demo Campaign (owner, 2026-10-20). DUMMY DATA. Writes settings.campaign_sales["9"].
Run in a throwaway python:3.11-alpine container with the admin dir at /data/admin."""
import sys, json, math, random, time, re, calendar
sys.path.insert(0, "/data/admin")
import db, metrics

CID = 9
RNG = random.Random(2026102001)
DAY = 86400
k = db.campaign(CID)
assert k is not None and "(demo)" in (k["client"] or "").lower(), "not the demo campaign"
r = metrics.report(k)
views = r["total"]["views"] or 0
clicks = db.click_stats(CID)["clicks"] or 0
SPEND = 165000.0

SOURCES = [("nahdi", "Nahdi", "Promo codes in the app and stores + tracked link", 0.33, 138),
           ("amazon", "Amazon.sa", "Amazon Attribution report", 0.19, 151),
           ("website", "Alpha Plus online store", "Tracked links to the brand's store", 0.17, 162),
           ("noon", "Noon", "Noon affiliate report", 0.16, 129),
           ("aldawaa", "Al-Dawaa", "Promo codes in stores + sell-out report", 0.15, 134)]
ORDERS = 5812
src = []
for key, label, via, share, aov in SOURCES:
    o = int(round(ORDERS * share * RNG.uniform(0.96, 1.04)))
    src.append({"key": key, "label": label, "via": via, "orders": o, "revenue": int(round(o * aov * RNG.uniform(0.97, 1.03)))})
orders = sum(s["orders"] for s in src)
revenue = sum(s["revenue"] for s in src)

ppv = int(clicks * 0.78)
atc = int(ppv * 0.31)
link_orders = int(atc * 0.36)
funnel = [{"k": "Video views", "n": views}, {"k": "Link clicks", "n": clicks}, {"k": "Product page views", "n": ppv},
          {"k": "Added to cart", "n": atc}, {"k": "Orders from links", "n": link_orders}]

# Creators: sales follow the views each creator delivered.
by = {}
for p in r["posts"]:
    if p["section"] == "campaign":
        by[p["code"]] = by.get(p["code"], 0) + (p.get("views") or 0)
names = {c["code"]: c["name"] for c in r["creators"]}
w = {c: v ** 0.9 for c, v in by.items()}
tw = sum(w.values()) or 1
used = set()
def promo(code):
    import unicodedata
    n = "".join(ch for ch in unicodedata.normalize("NFKD", names.get(code) or "") if not unicodedata.combining(ch))
    m = re.findall(r"[A-Za-z]+", n.split("|")[0])
    base = (m[0] if m else "HV" + code[-3:].replace("-", "")).upper()[:9]
    if base in ("DR", "DOCTOR") and len(m) > 1:
        base = ("DR" + m[1]).upper()[:9]
    c = base + "15"
    while c in used:
        c = base + str(RNG.randint(16, 99))
    used.add(c)
    return c
creators = sorted(({"code": c, "promo": promo(c), "revenue": int(revenue * w[c] / tw * RNG.uniform(0.85, 1.15))} for c in w), key=lambda x: -x["revenue"])
for c in creators:
    c["orders"] = int(round(c["revenue"] / (revenue / orders)))
    c["name"] = names.get(c["code"], c["code"])

# Days: two weeks before the campaign at the usual level, then the campaign's sales on top, following the posts.
start = k["starts_at"]
d0 = start - 14 * DAY
today = int(time.time()) // DAY * DAY
base_daily = 6200
impulse = {}
for p in r["posts"]:
    if p["section"] != "campaign" or not p.get("posted_at"):
        continue
    pd = (p["posted_at"] + 3 * 3600) // DAY * DAY
    for lag in range(0, 6):
        impulse[pd + lag * DAY] = impulse.get(pd + lag * DAY, 0) + (p.get("views") or 0) * math.exp(-lag / 1.6)
camp_days = [t for t in range(start // DAY * DAY, today, DAY)]
ti = sum(impulse.get(t, 0) + 0.15 * (sum(impulse.values()) / max(1, len(camp_days))) for t in camp_days) or 1
days = []
t = d0 // DAY * DAY
while t < today:
    b = base_daily * RNG.uniform(0.85, 1.15) * (1.12 if time.gmtime(t).tm_wday in (3, 4) else 1.0)
    extra = 0
    if t >= start // DAY * DAY:
        extra = revenue * (impulse.get(t, 0) + 0.15 * (sum(impulse.values()) / max(1, len(camp_days)))) / ti
    days.append({"d": time.strftime("%Y-%m-%d", time.gmtime(t)), "revenue": int(b + extra), "before": t < start // DAY * DAY})
    t += DAY
before = [d["revenue"] for d in days if d["before"]]
during = [d["revenue"] for d in days if not d["before"]]
bd = sum(before) / len(before)
lift = (sum(during) / len(during) - bd) / bd * 100

cities = [("Riyadh", .41), ("Jeddah", .23), ("Dammam & Khobar", .13), ("Makkah", .07), ("Madinah", .05), ("Dubai", .04)]
products = [("Vitamin C 30% serum", .46), ("Brightening day cream", .18), ("SPF30 sunscreen", .16), ("Vitamin C face scrub", .11), ("Eye contour cream", .09)]
blob = {
    "currency": "SAR", "updated": time.strftime("%Y-%m-%d", time.gmtime(today - DAY)), "sample": True,
    "basis": ("Sample data for the demo. In a live campaign these figures come from the retailers' promo-code reports, Amazon Attribution, "
              "the Noon affiliate report, Nahdi and Al-Dawaa sell-out, and brand-store orders from the creators' tracked links. "
              "Return on spend = sales ÷ campaign spend."),
    "totals": {"revenue": revenue, "orders": orders, "aov": round(revenue / orders, 1), "roas": round(revenue / SPEND, 2),
               "cpo": round(SPEND / orders, 1), "new_share": 0.64, "conv": round(link_orders / clicks * 100, 2) if clicks else None,
               "spend": SPEND},
    "baseline": {"daily": round(bd), "lift": round(lift)},
    "funnel": funnel, "sources": src, "creators": creators[:10], "days": days,
    "customers": {"new": int(orders * 0.64), "returning": orders - int(orders * 0.64)},
    "cities": [{"k": c, "n": int(revenue * s)} for c, s in cities],
    "products": [{"k": c, "n": int(revenue * s)} for c, s in products],
}
with db.connect() as conn:
    cur = json.loads((conn.execute("SELECT value FROM settings WHERE key = 'campaign_sales'").fetchone() or ["{}"])[0] or "{}")
    cur[str(CID)] = blob
    conn.execute("INSERT INTO settings (key, value) VALUES ('campaign_sales', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps(cur),))
print(json.dumps({"revenue": revenue, "orders": orders, "roas": blob["totals"]["roas"], "lift": round(lift), "clicks": clicks,
                  "link_orders": link_orders, "top": [(c["promo"], c["revenue"]) for c in creators[:5]]}, ensure_ascii=False))
