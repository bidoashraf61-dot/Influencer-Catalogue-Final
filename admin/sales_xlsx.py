"""The Clicks-to-sales Excel template (owner, 2026-10-20): the team fills it from the retailers' reports, uploads it on
the campaign's Sales tab, previews the totals and publishes. sales.py turns the rows into the client-safe summary the
dashboard's "Clicks to sales" card draws (settings.campaign_sales).

Four sheets: Instructions, Promo codes (one row per code per day and store, or per order), Retailer reports (Amazon
Attribution, Noon affiliate, Nahdi / Al-Dawaa sell-out, brand-website orders from tracked links) and Daily sales (the
usual days before the campaign, optionally the campaign days too). A Lists sheet feeds the dropdowns.

Money is in the campaign's currency (set on the Sales tab), as the stores report it. No costs or margins are asked for:
return on spend is worked out from the campaign spend typed on the Sales tab.

Stdlib only (admin/xlsx.py)."""
import re

import xlsx
from evidence_xlsx import _Errors, _clean_head, _date, _float, _int, _letter, is_xlsx  # noqa: F401  (is_xlsx re-exported)

# Known stores: typed name (lower case) -> (key, label shown to the client). Anything else is kept as typed.
RETAILERS = (("nahdi", "Nahdi", ("nahdi", "al nahdi", "al-nahdi", "النهدي")),
             ("aldawaa", "Al-Dawaa", ("al-dawaa", "al dawaa", "aldawaa", "dawaa", "الدواء")),
             ("amazon", "Amazon.sa", ("amazon", "amazon.sa", "amazon sa", "أمازون")),
             ("noon", "Noon", ("noon", "noon.com", "نون")),
             ("whites", "Whites", ("whites", "وايتس")),
             ("website", "Brand website", ("brand website", "website", "online store", "brand store", "e-shop")))
RETAILER_LABELS = [lab for _, lab, _ in RETAILERS]
# Report types: label -> (code, measured through a tracked link?). Link orders feed the funnel's last step.
REPORTS = (("Amazon Attribution", "amazon_attribution", True),
           ("Noon affiliate report", "noon_affiliate", True),
           ("Brand website (tracked links)", "website_links", True),
           ("Sell-out report", "sell_out", False),
           ("Other report", "other", False))
REPORT_CODE = {lab.lower(): (code, link) for lab, code, link in REPORTS}
REPORT_CODE.update({code: (code, link) for _, code, link in REPORTS})
REPORT_LABEL = {code: lab for lab, code, _ in REPORTS}
CUSTOMER = ("new", "returning")

PROMO_COLS = (("code", "Promo code", "SARA15", "The code exactly as the customer typed it. One row per code per day and store, or one row per order."),
              ("creator", "Creator code", "HV-0412", "Optional: the creator's roster code. Leave empty and map the code on the Sales tab."),
              ("date", "Date", "2026-10-03", "YYYY-MM-DD, or an Excel date."),
              ("retailer", "Store", "Nahdi", "Pick from the list, or type the store's name."),
              ("orders", "Orders", "12", "Whole number. 1 when the row is one order."),
              ("units", "Units", "15", "Optional."),
              ("revenue", "Sales", "1840", "The sales value of those orders, in the campaign currency (as the store reports it)."),
              ("city", "City", "Riyadh", "Optional."),
              ("product", "Product / SKU", "Vitamin C serum 30ml", "Optional."),
              ("customer", "New or returning", "new", "Optional: new or returning, for every order on the row."))
REPORT_COLS = (("retailer", "Store", "Amazon.sa", "Pick from the list, or type the store's name."),
               ("report", "Report", "Amazon Attribution", "Which report the row comes from (pick from the list)."),
               ("date", "Date", "2026-10-03", "YYYY-MM-DD. One row per day (and per creator, product or city when the report splits it)."),
               ("creator", "Creator code", "", "Optional: when the report splits sales by creator link or tag."),
               ("code", "Promo code or link", "", "Optional: the promo code or tracking-link name the report shows. Mapped to a creator on the Sales tab."),
               ("dpv", "Product page views", "820", "Optional (Amazon Attribution: detail page views)."),
               ("atc", "Added to cart", "160", "Optional (Amazon Attribution: add to carts)."),
               ("orders", "Orders", "41", "Whole number (Amazon Attribution: purchases)."),
               ("units", "Units", "47", "Optional."),
               ("revenue", "Sales", "6150", "Sales value, in the campaign currency."),
               ("new_orders", "New-customer orders", "", "Optional: how many of the orders were from new customers (Amazon: new-to-brand)."),
               ("city", "City", "", "Optional."),
               ("product", "Product / SKU", "", "Optional."))
DAILY_COLS = (("date", "Date", "2026-09-20", "One row per day. At least 7 days before the campaign start for a fair usual day."),
              ("revenue", "Sales", "6200", "All the brand's sales that day in the same stores, in the campaign currency."),
              ("orders", "Orders", "41", "Optional."))
PROMO_REQ = ("code", "date", "retailer", "orders", "revenue")
REPORT_REQ = ("retailer", "report", "date", "orders", "revenue")
DAILY_REQ = ("date", "revenue")
SHEETS = ("Instructions", "Promo codes", "Retailer reports", "Daily sales", "Lists")


def template():
    lists = [("Store", RETAILER_LABELS), ("Report", [lab for lab, _, _ in REPORTS]), ("New or returning", CUSTOMER)]
    depth = max(len(v) for _, v in lists)
    list_rows = [[n for n, _ in lists]] + [[(v[i] if i < len(v) else "") for _, v in lists] for i in range(depth)]
    src = {n: "Lists!$%s$2:$%s$%d" % (_letter(i), _letter(i), len(v) + 1) for i, (n, v) in enumerate(lists)}

    intro = [["Clicks to sales template"],
             ["Fill it from the stores' reports, then upload it on the campaign's Sales tab (Admin > Campaigns > the campaign > Sales). "
              "You see the totals before anything is shown to the client; nothing is published until you press Publish."],
             ["Uploading again replaces the previous upload for that campaign. Keep the header rows as they are. Columns with * are required. "
              "The examples are on this sheet only; nothing here is imported."],
             ["Do not list the same orders twice: a store's sell-out report row should hold the orders that are NOT already on the "
              "Promo codes sheet. Money is in the campaign currency, as the store reports it. Costs and margins are never asked for "
              "or shown; return on spend comes from the campaign spend you type on the Sales tab."],
             [""], ["Promo codes sheet", "What it means", "Example"]]
    intro += [[h + (" *" if k in PROMO_REQ else ""), why, ex] for k, h, ex, why in PROMO_COLS]
    intro += [[""], ["Retailer reports sheet", "What it means", "Example"]]
    intro += [[h + (" *" if k in REPORT_REQ else ""), why, ex] for k, h, ex, why in REPORT_COLS]
    intro += [[""], ["Daily sales sheet (optional)", "What it means", "Example"]]
    intro += [[h + (" *" if k in DAILY_REQ else ""), why, ex] for k, h, ex, why in DAILY_COLS]
    intro += [[""], ["Daily sales: days before the campaign start give the usual day. Add the campaign days too when you have the "
                     "brand's full daily sales; without them the chart shows the usual day plus the sales on the other two sheets."]]

    head = lambda cols, req: [h + (" *" if k in req else "") for k, h, _, _ in cols]
    at = lambda cols, key: _letter([k for k, _, _, _ in cols].index(key))
    rng = lambda cols, key: "%s2:%s20000" % (at(cols, key), at(cols, key))
    rules = [(2, rng(PROMO_COLS, "retailer"), src["Store"]), (2, rng(PROMO_COLS, "customer"), src["New or returning"]),
             (3, rng(REPORT_COLS, "retailer"), src["Store"]), (3, rng(REPORT_COLS, "report"), src["Report"])]
    width = lambda cols: {i: (24 if k in ("product", "report", "code") else 16) for i, (k, _, _, _) in enumerate(cols)}
    return xlsx.write_book([
        ("Instructions", intro, {0: 30, 1: 96, 2: 26}, None),
        ("Promo codes", [head(PROMO_COLS, PROMO_REQ)], width(PROMO_COLS), None),
        ("Retailer reports", [head(REPORT_COLS, REPORT_REQ)], width(REPORT_COLS), None),
        ("Daily sales", [head(DAILY_COLS, DAILY_REQ)], {0: 16, 1: 16, 2: 14}, None),
        ("Lists", list_rows, {i: 30 for i in range(len(lists))}, None),
    ], rules)


def retailer(name):
    """(key, label) for a typed store name; unknown stores keep their own name."""
    t = re.sub(r"\s+", " ", (name or "").strip())
    low = t.lower()
    for key, lab, words in RETAILERS:
        if low == lab.lower() or low in words:
            return key, lab
    return re.sub(r"[^a-z0-9]+", "-", low).strip("-") or "other", t


def _money(v, sheet, n, col, errs):
    f = _float(v, sheet, n, col, errs)
    if f is not None and f < 0:
        errs.add(sheet, n, col, "cannot be negative.")
        return None
    return f


def _rows(book, name, cols, req, errs):
    got = book.get(name)
    if got is None:
        return []
    if not got:
        return []
    headrow = [_clean_head(h) for h in got[0]]
    at = {k: headrow.index(label.lower()) for k, label, _, _ in cols if label.lower() in headrow}
    missing = [label for k, label, _, _ in cols if k in req and k not in at]
    if missing:
        errs.add(name, 0, "", "the column%s %s %s missing. Start from a fresh template." % (
            "s" if len(missing) > 1 else "", ", ".join(missing), "are" if len(missing) > 1 else "is"))
        return []
    out = []
    for n, r in enumerate(got[1:], start=2):
        vals = {k: (str(r[i]).strip() if i < len(r) and r[i] is not None else "") for k, i in at.items()}
        if any(vals.values()):
            out.append((n, vals))
    return out


def parse(raw):
    """{"promo": [...], "reports": [...], "daily": [...]} from an uploaded workbook. Raises ValueError listing every
    problem (nothing is imported when one row is wrong), xlsx.BadWorkbook for a file that is not an .xlsx."""
    book = xlsx.read_all(raw)
    errs = _Errors()
    if not any(s in book for s in SHEETS[1:4]):
        raise ValueError("That workbook has none of the Promo codes, Retailer reports or Daily sales sheets. "
                         "Download the template from the Sales tab and fill it in.")
    label = {k: h for k, h, _, _ in PROMO_COLS + REPORT_COLS + DAILY_COLS}

    def need(vals, keys, sheet, n):
        ok = True
        for k in keys:
            if vals.get(k, "") == "":
                errs.add(sheet, n, label[k], "is required.")
                ok = False
        return ok

    promo = []
    for n, v in _rows(book, "Promo codes", PROMO_COLS, PROMO_REQ, errs):
        sh = "Promo codes"
        if not need(v, PROMO_REQ, sh, n):
            continue
        cust = v.get("customer", "").strip().lower()
        if cust and cust not in CUSTOMER:
            errs.add(sh, n, "New or returning", "\"%s\" should be new or returning." % v["customer"])
        key, lab = retailer(v["retailer"])
        promo.append({"code": v["code"].strip().upper(), "creator": v.get("creator", "").strip().upper(),
                      "date": _date(v["date"], sh, n, "Date", errs), "retailer": key, "retailer_label": lab,
                      "orders": _int(v["orders"], sh, n, "Orders", errs) or 0, "units": _int(v.get("units", ""), sh, n, "Units", errs),
                      "revenue": _money(v["revenue"], sh, n, "Sales", errs) or 0.0,
                      "city": v.get("city", "").strip(), "product": v.get("product", "").strip(),
                      "customer": cust if cust in CUSTOMER else ""})
    reports = []
    for n, v in _rows(book, "Retailer reports", REPORT_COLS, REPORT_REQ, errs):
        sh = "Retailer reports"
        if not need(v, REPORT_REQ, sh, n):
            continue
        rep = REPORT_CODE.get(v["report"].strip().lower())
        if rep is None:
            errs.add(sh, n, "Report", "\"%s\" is not one of: %s." % (v["report"], ", ".join(lab for lab, _, _ in REPORTS)))
            continue
        key, lab = retailer(v["retailer"])
        orders = _int(v["orders"], sh, n, "Orders", errs) or 0
        new = _int(v.get("new_orders", ""), sh, n, "New-customer orders", errs)
        if new is not None and new > orders:
            errs.add(sh, n, "New-customer orders", "is more than the orders on the row.")
        reports.append({"retailer": key, "retailer_label": lab, "report": rep[0], "link": rep[1],
                        "date": _date(v["date"], sh, n, "Date", errs), "creator": v.get("creator", "").strip().upper(),
                        "code": v.get("code", "").strip().upper(),
                        "dpv": _int(v.get("dpv", ""), sh, n, "Product page views", errs),
                        "atc": _int(v.get("atc", ""), sh, n, "Added to cart", errs),
                        "orders": orders, "units": _int(v.get("units", ""), sh, n, "Units", errs),
                        "revenue": _money(v["revenue"], sh, n, "Sales", errs) or 0.0, "new_orders": new,
                        "city": v.get("city", "").strip(), "product": v.get("product", "").strip()})
    daily = {}
    for n, v in _rows(book, "Daily sales", DAILY_COLS, DAILY_REQ, errs):
        sh = "Daily sales"
        if not need(v, DAILY_REQ, sh, n):
            continue
        d = _date(v["date"], sh, n, "Date", errs)
        if d in daily:
            errs.add(sh, n, "Date", "%s is on the sheet twice. One row per day." % d)
            continue
        daily[d] = {"date": d, "revenue": _money(v["revenue"], sh, n, "Sales", errs) or 0.0,
                    "orders": _int(v.get("orders", ""), sh, n, "Orders", errs)}
    errs.raise_if_any()
    if not promo and not reports:
        raise ValueError("Nothing was imported: the Promo codes and Retailer reports sheets are both empty.")
    return {"promo": promo, "reports": reports, "daily": sorted(daily.values(), key=lambda r: r["date"])}
