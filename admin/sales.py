"""Clicks to sales, admin side (owner, 2026-10-20): the campaign's Sales tab. Download the template (sales_xlsx.py), fill
it from the stores' reports, upload it, check the totals, map promo codes to the campaign's creators, type the campaign
spend and publish. Publishing writes one client-safe summary to settings.campaign_sales {campaign id: {...}}, the shape
tools/demo_sales.py writes for the Demo Campaign and the dashboard's "Clicks to sales" card draws (metrics.client_report
sends it as report.sales). Unpublish removes it; the card goes back to affiliate clicks.

What reaches the client: sales, orders, average basket, return on spend (sales / spend), cost per order (spend / orders),
the spend itself, new-customer share, store, creator, day, city and product splits. Never costs, margins or prices paid
to creators. The upload itself (every row) stays in the sales_uploads table, admin only."""
import calendar
import json
import time
import urllib.parse

import db

DAY = 86400
CURRENCIES = ("SAR", "AED", "USD", "EGP", "KWD", "QAR", "BHD", "OMR")
KEY = "campaign_sales"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sales_uploads (
  campaign_id  INTEGER PRIMARY KEY,
  data         TEXT NOT NULL,          -- {"rows": {promo, reports, daily}, "map": {code: creator}, "spend", "currency", "note"}
  filename     TEXT,
  uploaded_at  INTEGER,
  updated_at   INTEGER
);
"""


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def draft(cid):
    init()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sales_uploads WHERE campaign_id = ?", (cid,)).fetchone()
    if row is None:
        return None
    try:
        d = json.loads(row["data"])
    except ValueError:
        return None
    d["filename"], d["uploaded_at"] = row["filename"], row["uploaded_at"]
    return d


def save_draft(cid, d, filename=None, new_upload=False):
    init()
    keep = {k: d.get(k) for k in ("rows", "map", "spend", "currency", "note")}
    now = int(time.time())
    with db.connect() as conn:
        if new_upload:
            conn.execute("INSERT INTO sales_uploads (campaign_id, data, filename, uploaded_at, updated_at) VALUES (?, ?, ?, ?, ?) "
                         "ON CONFLICT(campaign_id) DO UPDATE SET data = excluded.data, filename = excluded.filename, "
                         "uploaded_at = excluded.uploaded_at, updated_at = excluded.updated_at",
                         (cid, json.dumps(keep), filename, now, now))
        else:
            conn.execute("UPDATE sales_uploads SET data = ?, updated_at = ? WHERE campaign_id = ?", (json.dumps(keep), now, cid))


def published(cid):
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (KEY,)).fetchone()
    try:
        cur = json.loads(row["value"]) if row and row["value"] else {}
    except ValueError:
        cur = {}
    v = cur.get(str(cid)) if isinstance(cur, dict) else None
    return v if isinstance(v, dict) and v.get("totals") else None


def _write(cid, blob):
    """Set (blob) or remove (None) one campaign's summary, read-modify-write in one connection (never from the cache)."""
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (KEY,)).fetchone()
        try:
            cur = json.loads(row["value"]) if row and row["value"] else {}
        except ValueError:
            cur = {}
        if not isinstance(cur, dict):
            cur = {}
        if blob is None:
            cur.pop(str(cid), None)
        else:
            cur[str(cid)] = blob
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (KEY, json.dumps(cur)))
    getattr(db, "_setting_cache", {}).pop(KEY, None)


# ------------------------------------------------------------------------------------------------ summary --

def _day(t):
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def _t(d):
    return calendar.timegm(time.strptime(d, "%Y-%m-%d"))


def _join(words):
    words = [w for w in words if w]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] if words else ""


def codes(d):
    """Every promo code / link name in the upload: [{code, orders, revenue, creator (from the sheet), rows}], biggest first."""
    out = {}
    for r in d["rows"]["promo"] + [x for x in d["rows"]["reports"] if x.get("code")]:
        c = out.setdefault(r["code"], {"code": r["code"], "orders": 0, "revenue": 0.0, "creator": "", "rows": 0})
        c["orders"] += r["orders"] or 0
        c["revenue"] += r["revenue"] or 0
        c["rows"] += 1
        c["creator"] = c["creator"] or r.get("creator") or ""
    return sorted(out.values(), key=lambda c: -c["revenue"])


def build(k, d, members=None, views=None, clicks=None):
    """(summary, notes) from a draft. notes are admin-only remarks about the data (rows outside the dates, unmapped codes)."""
    import sales_xlsx
    rows = d["rows"]
    promo, reports, daily = rows["promo"], rows["reports"], rows["daily"]
    members = members if members is not None else db.campaign_creators(k["id"])
    names = {m["cc_code"]: (m["name"] or m["cc_code"]) for m in members}
    cmap = {c: v for c, v in (d.get("map") or {}).items() if v in names}
    cur = d.get("currency") or "SAR"
    spend = d.get("spend") or None
    notes = []

    def who(r):
        if r.get("creator") in names:
            return r["creator"]
        return cmap.get(r.get("code") or "")

    sales = promo + reports
    revenue = sum(r["revenue"] for r in sales)
    orders = sum(r["orders"] for r in sales)

    # Stores, and how each was measured.
    src = {}
    for r in sales:
        s = src.setdefault(r["retailer"], {"key": r["retailer"], "label": r["retailer_label"], "via": [], "orders": 0, "revenue": 0.0})
        s["orders"] += r["orders"]
        s["revenue"] += r["revenue"]
        via = "Promo codes" if "report" not in r else sales_xlsx.REPORT_LABEL.get(r["report"], "Report")
        if via not in s["via"]:
            s["via"].append(via)
    sources = sorted(({"key": s["key"], "label": s["label"], "via": " + ".join(s["via"]), "orders": s["orders"],
                       "revenue": int(round(s["revenue"]))} for s in src.values()), key=lambda s: -s["revenue"])

    # Creators: their own code (mapped on the tab) or the creator column.
    by = {}
    unmapped = 0.0
    for r in sales:
        c = who(r)
        if not c:
            unmapped += r["revenue"]
            continue
        x = by.setdefault(c, {"code": c, "orders": 0, "revenue": 0.0, "promos": {}})
        x["orders"] += r["orders"]
        x["revenue"] += r["revenue"]
        if r.get("code"):
            x["promos"][r["code"]] = x["promos"].get(r["code"], 0) + r["revenue"]
    creators = sorted(({"code": c, "name": names.get(c, c), "promo": max(x["promos"], key=x["promos"].get) if x["promos"] else "",
                        "orders": x["orders"], "revenue": int(round(x["revenue"]))} for c, x in by.items()), key=lambda x: -x["revenue"])
    if unmapped and revenue:
        notes.append("%s %s (%d%% of sales) is not linked to a creator. Map the codes below, or it is left out of "
                     "\"Creators who sold the most\" (it still counts in the totals)." % (cur, "{:,.0f}".format(unmapped), round(unmapped / revenue * 100)))

    # New and returning customers, where the reports say.
    new = ret = 0
    for r in promo:
        if r["customer"] == "new":
            new += r["orders"]
        elif r["customer"] == "returning":
            ret += r["orders"]
    for r in reports:
        if r.get("new_orders") is not None:
            new += r["new_orders"]
            ret += r["orders"] - r["new_orders"]
    customers = {"new": new, "returning": ret} if new + ret else None

    # Funnel: views and clicks from the campaign, the rest from link-measured reports.
    link_orders = sum(r["orders"] for r in reports if r["link"])
    dpv = sum(r["dpv"] or 0 for r in reports)
    atc = sum(r["atc"] or 0 for r in reports)
    if views is None or clicks is None:
        import metrics
        views = (metrics.report(k)["total"].get("views") or 0) if views is None else views
        clicks = (db.click_stats(k["id"])["clicks"] or 0) if clicks is None else clicks
    funnel = [{"k": a, "n": b} for a, b in (("Video views", views), ("Link clicks", clicks), ("Product page views", dpv),
                                             ("Added to cart", atc), ("Orders from links", link_orders)) if b]
    if not link_orders or len(funnel) < 3:
        funnel = []

    # Days: the usual day from the Daily sales sheet before the start; the campaign days from the sheet when it has
    # them, else the usual day plus the sales on the other two sheets.
    start = _day(k["starts_at"]) if k["starts_at"] else min([r["date"] for r in sales] or [_day(time.time())])
    by_day = {}
    for r in sales:
        by_day[r["date"]] = by_day.get(r["date"], 0) + r["revenue"]
    early = sorted(dd for dd in by_day if dd < start)
    if early:
        notes.append("%d day%s of sales %s dated before the campaign start (%s); they are still counted." % (
            len(early), "" if len(early) == 1 else "s", "is" if len(early) == 1 else "are", start))
    before = [r for r in daily if r["date"] < start]
    during = [r for r in daily if r["date"] >= start]
    base = sum(r["revenue"] for r in before) / len(before) if before else None
    if before and len(before) < 7:
        notes.append("The usual day is the average of only %d day%s before the start. 7 to 14 days is fairer." % (len(before), "" if len(before) == 1 else "s"))
    days, lift, method = [], None, ""
    last = max([r["date"] for r in sales] + [r["date"] for r in during] or [start])
    camp = []
    t = _t(start)
    while _day(t) <= last:
        camp.append(_day(t))
        t += DAY
    if during:
        method = "sheet"
        days = [{"d": r["date"], "revenue": int(round(r["revenue"])), "before": r["date"] < start} for r in daily]
        if base:
            lift = (sum(r["revenue"] for r in during) / len(during) - base) / base * 100
    elif base:
        method = "added"
        days = ([{"d": r["date"], "revenue": int(round(r["revenue"])), "before": True} for r in before]
                + [{"d": dd, "revenue": int(round(base + by_day.get(dd, 0))), "before": False} for dd in camp])
        lift = sum(by_day.get(dd, 0) for dd in camp) / len(camp) / base * 100 if camp else None
    else:
        method = "sales"
        first = min(by_day) if by_day else start
        t = _t(first)
        while _day(t) <= last:
            days.append({"d": _day(t), "revenue": int(round(by_day.get(_day(t), 0))), "before": _day(t) < start})
            t += DAY

    def top(field):
        acc = {}
        for r in sales:
            if r.get(field):
                acc[r[field]] = acc.get(r[field], 0) + r["revenue"]
        return [{"k": a, "n": int(round(b))} for a, b in sorted(acc.items(), key=lambda x: -x[1])[:8]]

    measured = []
    promo_shops = sorted({r["retailer_label"] for r in promo})
    if promo_shops:
        measured.append("promo-code redemptions at " + _join(promo_shops))
    for code in ("amazon_attribution", "noon_affiliate", "sell_out", "website_links", "other"):
        shops = sorted({r["retailer_label"] for r in reports if r["report"] == code})
        if shops:
            measured.append({"amazon_attribution": "the Amazon Attribution report", "noon_affiliate": "the Noon affiliate report",
                             "sell_out": _join(shops) + " sell-out", "website_links": "brand-store orders from the creators' tracked links",
                             "other": "reports from " + _join(shops)}[code])
    basis = "From " + _join(measured) + "." if measured else ""
    basis += " Return on spend = sales ÷ campaign spend."
    if method == "added":
        basis += " Daily sales during the campaign are the usual day before it plus the sales above."
    if (d.get("note") or "").strip():
        basis += " " + d["note"].strip()

    blob = {
        "currency": cur, "updated": max([r["date"] for r in sales] or [start]), "basis": basis.strip(),
        "totals": {"revenue": int(round(revenue)), "orders": orders, "aov": round(revenue / orders, 1) if orders else None,
                   "roas": round(revenue / spend, 2) if spend else None, "cpo": round(spend / orders, 1) if spend and orders else None,
                   "new_share": round(new / float(new + ret), 2) if new + ret else None,
                   "conv": round(link_orders / float(clicks) * 100, 2) if clicks and link_orders else None, "spend": spend},
        "baseline": {"daily": round(base), "lift": round(lift) if lift is not None else None} if base else None,
        "funnel": funnel, "sources": sources, "creators": creators[:10], "days": days,
        "customers": customers, "cities": top("city"), "products": top("product"),
    }
    return blob, notes


# ------------------------------------------------------------------------------------------------ admin tab --

def _fmt(v, cur=""):
    if v is None:
        return "—"
    return (cur + " " if cur else "") + ("{:,.0f}".format(v) if abs(v) >= 100 or float(v).is_integer() else "{:,.2f}".format(v))


def admin_page(k, error=None, message=None):
    import views
    import metrics
    e, u = views.e, views.u
    cid = k["id"]
    d = draft(cid)
    pub = published(cid)
    members = db.campaign_creators(cid)
    hidden = not metrics.visibility(k).get("clicks", True)

    status = ("<div class='card'><div class='row' style='gap:28px;flex-wrap:wrap;align-items:center'>"
              + ("<div><label>On the client's dashboard</label><b style='font-size:20px'>%s</b></div>"
                 "<div><label>Sales</label><b style='font-size:20px'>%s</b></div><div><label>Return on spend</label><b style='font-size:20px'>%s</b></div>"
                 "<div><label>Data up to</label><b style='font-size:20px'>%s</b></div>" % (
                     "Published" + (" (sample data)" if pub.get("sample") else ""), e(_fmt(pub["totals"].get("revenue"), pub.get("currency", ""))),
                     "%.2f×" % pub["totals"]["roas"] if pub["totals"].get("roas") else "—", e(pub.get("updated") or "—"))
                 if pub else "<div><label>On the client's dashboard</label><b style='font-size:20px'>Not published</b>"
                             "<div class='price-hint'>The card shows affiliate clicks until sales are published.</div></div>")
              + ("<form method='post' action='%s' style='margin-left:auto' data-confirm-title='Take sales off the dashboard?' "
                 "data-confirm='The card goes back to affiliate clicks. The upload stays here, so you can publish again.' data-confirm-ok='Unpublish'>"
                 "<input type='hidden' name='id' value='%d'><input type='hidden' name='do' value='unpublish'>"
                 "<button class='btn small danger'>Unpublish</button></form>" % (u("/campaigns/sales"), cid) if pub else "")
              + "</div>"
              + ("<p class='err'>Affiliate clicks are hidden for this campaign (Setup → what the client sees), so the sales card "
                 "is hidden too. Turn clicks on to show it.</p>" if hidden else "")
              + "</div>")

    upload = ("<h2>1. Upload the sales sheet</h2><form method='post' action='%s' enctype='multipart/form-data' class='card'>"
              "<input type='hidden' name='id' value='%d'><input type='hidden' name='do' value='upload'>"
              "<p class='sec-desc' style='margin-top:0'>Fill the template from the stores' reports: promo-code redemptions, Amazon "
              "Attribution, the Noon affiliate report, Nahdi / Al-Dawaa sell-out and brand-store orders from tracked links, plus the "
              "usual days before the campaign. Uploading again replaces the previous upload; what is published does not change until "
              "you publish again.</p><div class='row' style='align-items:flex-end'>"
              "<div style='flex:2'><label>Sales workbook (.xlsx)</label><input type='file' name='file' accept='.xlsx' required></div>"
              "<div><button class='btn small'>Upload and preview</button></div>"
              "<div><a class='btn small ghost' href='%s'>Download the template</a></div></div>%s</form>" % (
                  u("/campaigns/sales"), cid, u("/campaigns/sales/template.xlsx"),
                  "<p class='price-hint'>Current upload: %s · %s</p>" % (e(d.get("filename") or "workbook"), e(views._when(d["uploaded_at"])))
                  if d else ""))
    if not d:
        body = (views._head(k, "sales", error, message)
                + "<p class='sub'>Sales the campaign drove, from the stores' own reports. Published, they replace the affiliate-clicks "
                  "card on the client's dashboard with \"Clicks to sales\": sales, return on spend, stores, creators and days.</p>"
                + status + upload)
        return views.page(k["name"] + " — Sales", body, "/campaigns")

    blob, notes = build(k, d, members)
    T, cur = blob["totals"], blob["currency"]
    box = lambda a, b: "<div><label>%s</label><b style='font-size:22px'>%s</b></div>" % (a, b)
    pv = ("<h2>2. Check the totals</h2><div class='card'><div class='row' style='gap:28px;flex-wrap:wrap'>"
          + box("Sales", e(_fmt(T["revenue"], cur))) + box("Orders", "{:,}".format(T["orders"]))
          + box("Average basket", e(_fmt(T["aov"], cur))) + box("Return on spend", "%.2f×" % T["roas"] if T["roas"] else "set the spend")
          + box("Cost per order", e(_fmt(T["cpo"], cur))) + box("New customers", "%d%%" % round(T["new_share"] * 100) if T["new_share"] is not None else "—")
          + box("Link clicks that bought", "%.2f%%" % T["conv"] if T["conv"] is not None else "—")
          + box("Above a usual day", ("%+d%%" % blob["baseline"]["lift"]) if blob["baseline"] and blob["baseline"]["lift"] is not None else "—")
          + "</div>"
          + "".join("<p class='price-hint' style='color:#b45309'>%s</p>" % e(n) for n in notes)
          + "<table style='margin-top:14px'><thead><tr><th>Store</th><th>Measured through</th><th class='n'>Orders</th><th class='n'>Sales</th></tr></thead><tbody>"
          + "".join("<tr><td><b>%s</b></td><td class='muted'>%s</td><td class='n'>%s</td><td class='n'>%s</td></tr>" % (
              e(s["label"]), e(s["via"]), "{:,}".format(s["orders"]), e(_fmt(s["revenue"], cur))) for s in blob["sources"])
          + "</tbody></table><p class='price-hint'>%d promo-code rows · %d report rows · %d daily-sales rows · %d days on the chart%s</p></div>" % (
              len(d["rows"]["promo"]), len(d["rows"]["reports"]), len(d["rows"]["daily"]), len(blob["days"]),
              "" if blob["funnel"] else " · no view-to-order funnel (it needs link-measured orders: Amazon Attribution, Noon affiliate or tracked links)"))

    opts = lambda sel: "<option value=''>Not a creator / unknown</option>" + "".join(
        "<option value='%s'%s>%s</option>" % (e(m["cc_code"]), " selected" if m["cc_code"] == sel else "",
                                             e((m["name"] or m["cc_code"]) + " · " + m["cc_code"])) for m in members)
    names = {m["cc_code"] for m in members}
    cmap = d.get("map") or {}
    crow = []
    for i, c in enumerate(codes(d)):
        sel = cmap.get(c["code"]) or (c["creator"] if c["creator"] in names else "")
        warn = " <span class='pill bad'>%s is not in this campaign</span>" % e(c["creator"]) if c["creator"] and c["creator"] not in names else ""
        crow.append("<tr><td><b>%s</b>%s<input type='hidden' name='code_%d' value='%s'></td><td class='n'>%s</td><td class='n'>%s</td>"
                    "<td><select name='who_%d'>%s</select></td></tr>" % (
                        e(c["code"]), warn, i, e(c["code"]), "{:,}".format(c["orders"]), e(_fmt(c["revenue"], cur)), i, opts(sel)))
    curopts = "".join("<option%s>%s</option>" % (" selected" if x == cur else "", x) for x in CURRENCIES)
    form = ("<h2>3. Codes, spend and publish</h2><form method='post' action='%s' class='card'>"
            "<input type='hidden' name='id' value='%d'><input type='hidden' name='n' value='%d'>" % (u("/campaigns/sales"), cid, len(crow))
            + ("<p class='sec-desc' style='margin-top:0'>Which creator each promo code or link belongs to. Codes with a creator on "
               "the sheet are filled in already.</p><table><thead><tr><th>Code</th><th class='n'>Orders</th><th class='n'>Sales</th>"
               "<th>Creator</th></tr></thead><tbody>" + "".join(crow) + "</tbody></table>" if crow else
               "<p class='price-hint'>No promo codes or link names in the upload, so no creator ranking. Add a Creator code column value to show one.</p>")
            + "<div class='row' style='margin-top:14px;align-items:flex-end'>"
              "<div><label>Campaign spend (what the client paid)</label><input type='number' name='spend' min='0' step='any' value='%s' required></div>"
              "<div><label>Currency</label><select name='currency'>%s</select></div>"
              "<div style='flex:2'><label>Note for the client (optional)</label><input type='text' name='note' maxlength='300' value='%s' "
              "placeholder='e.g. Nahdi figures to 18 Oct; Amazon to 17 Oct'></div></div>"
              "<p class='price-hint'>Return on spend = sales ÷ spend; cost per order = spend ÷ orders. The client sees these and the spend, "
              "never costs or margins.</p>"
              "<div class='row' style='gap:8px'><button class='btn small' name='do' value='save'>Save</button>"
              "<button class='btn small lime' name='do' value='publish'>%s</button></div></form>" % (
                  ("%g" % d["spend"]) if d.get("spend") else "", curopts, e(d.get("note") or ""),
                  "Publish again" if pub else "Publish to the client's dashboard"))
    discard = ("<form method='post' action='%s' style='margin-top:18px' data-confirm-title='Delete this upload?' "
               "data-confirm='Only the upload on this tab is deleted. What is published stays until you unpublish it.' data-confirm-ok='Delete upload'>"
               "<input type='hidden' name='id' value='%d'><input type='hidden' name='do' value='discard'>"
               "<button class='btn small ghost'>Delete the upload</button></form>" % (u("/campaigns/sales"), cid))
    body = (views._head(k, "sales", error, message)
            + "<p class='sub'>Sales the campaign drove, from the stores' own reports. Published, they replace the affiliate-clicks card "
              "on the client's dashboard with \"Clicks to sales\".</p>"
            + status + upload + pv + form + discard)
    return views.page(k["name"] + " — Sales", body, "/campaigns")


def admin_get(handler, query):
    cid = query.get("id", "")
    k = db.campaign(int(cid)) if cid.isdigit() else None
    if k is None:
        return handler.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
    return handler.send(200, admin_page(k, query.get("e"), query.get("ok")))


def template_get(handler):
    import sales_xlsx
    return handler.send(200, sales_xlsx.template(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        [("Content-Disposition", 'attachment; filename="sales-template.xlsx"'), ("Cache-Control", "no-store")])


def admin_post(handler):
    import sales_xlsx
    import xlsx
    f = handler.form_body()
    cid = (f.get("id") or "").strip()
    k = db.campaign(int(cid)) if cid.isdigit() else None
    if k is None:
        return handler.redirect("/campaigns")
    back = "/campaigns/sales?id=%d" % k["id"]
    say = lambda kind, msg: handler.redirect(back + "&" + kind + "=" + urllib.parse.quote(msg))
    do = f.get("do")
    if do == "upload":
        up = f.get("file")
        raw = up.get("data") if isinstance(up, dict) else None
        if not raw:
            return say("e", "Choose the filled-in sales workbook first.")
        if not sales_xlsx.is_xlsx(raw):
            return say("e", "That is not an .xlsx file. Save it from Excel as .xlsx and upload again.")
        try:
            rows = sales_xlsx.parse(raw)
        except (ValueError, xlsx.BadWorkbook) as ex:
            return say("e", str(ex))
        old = draft(k["id"]) or {}
        pub = published(k["id"]) or {}
        d = {"rows": rows, "map": old.get("map") or {}, "spend": old.get("spend") or (pub.get("totals") or {}).get("spend"),
             "currency": old.get("currency") or pub.get("currency") or "SAR", "note": old.get("note") or ""}
        save_draft(k["id"], d, (up.get("filename") or "")[:120], new_upload=True)
        n = len(rows["promo"]) + len(rows["reports"])
        return say("ok", "Read %d sales row%s and %d daily-sales row%s. Check the totals, then publish." % (
            n, "" if n == 1 else "s", len(rows["daily"]), "" if len(rows["daily"]) == 1 else "s"))
    if do == "unpublish":
        _write(k["id"], None)
        return say("ok", "Sales taken off the client's dashboard. The card shows affiliate clicks again.")
    d = draft(k["id"])
    if d is None:
        return say("e", "Upload the sales workbook first.")
    if do == "discard":
        init()
        with db.connect() as conn:
            conn.execute("DELETE FROM sales_uploads WHERE campaign_id = ?", (k["id"],))
        return say("ok", "Upload deleted.")
    if do not in ("save", "publish"):
        return handler.redirect(back)
    names = {m["cc_code"] for m in db.campaign_creators(k["id"])}
    cmap = {}
    n = int(f.get("n") or 0) if str(f.get("n") or "0").isdigit() else 0
    for i in range(min(n, 2000)):
        c, w = (f.get("code_%d" % i) or "").strip().upper(), (f.get("who_%d" % i) or "").strip().upper()
        if c and w in names:
            cmap[c] = w
    try:
        spend = float((f.get("spend") or "").replace(",", "")) if (f.get("spend") or "").strip() else None
    except ValueError:
        return say("e", "The spend should be a number.")
    if spend is not None and spend < 0:
        return say("e", "The spend cannot be negative.")
    cur = f.get("currency") if f.get("currency") in CURRENCIES else (d.get("currency") or "SAR")
    d.update({"map": cmap, "spend": spend or None, "currency": cur, "note": (f.get("note") or "").strip()[:300]})
    save_draft(k["id"], d)
    if do == "save":
        return say("ok", "Saved. Nothing changed on the client's dashboard.")
    if not spend:
        return say("e", "Type the campaign spend before publishing: return on spend is the card's headline.")
    blob, _notes = build(k, d)
    if not blob["totals"]["revenue"]:
        return say("e", "The upload has no sales to publish.")
    blob["published_at"] = int(time.time())
    _write(k["id"], blob)
    return say("ok", "Published: %s in sales, %.2f× return on spend. The client's dashboard shows it now." % (
        _fmt(blob["totals"]["revenue"], cur), blob["totals"]["roas"]))
