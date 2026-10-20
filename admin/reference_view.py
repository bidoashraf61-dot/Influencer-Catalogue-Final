"""The Reference page (admins only, read only).

The research the team collected on 2026-10-10, in one place, so an admin can look a number up and
see where it came from: market prices per sponsored post, international benchmarks, the campaign
structure evidence, the sources, and a live view of our own roster.

The datasets are static, public-safe JSON under admin/reference/ (no client or creator data).
Nothing here is written anywhere, and nothing here feeds the ROI calculator: the calculator
reads only measured data (our roster, tracked posts) and the recommended structure. The one place
the two meet is the Campaign structure tab, which marks the values the calculator reads right now
and shows the LIVE value (from Settings, when it was edited).

The "Our roster" tab is worked out from the creator_analysis table through benchmarks.py when the
page is opened (cached ten minutes there). It holds only counts and percentiles, never a name.
"""
import json
import re
from pathlib import Path

import benchmarks
import roi
import ui
import views as V

e, u = V.e, V.u
DIR = Path(__file__).resolve().parent / "reference"
FILES = {"market": "market_prices.json", "bench": "benchmarks.json", "structure": "campaign_structure.json",
         "sources": "sources.json"}
UPDATED = "2026-10-10"
NOTE = ("Reference only. Vendor and published figures are estimates, not verified. The calculator uses only "
        "measured data (our roster, tracked posts) and the recommended structure.")

TABS = [("market", "Market prices"), ("bench", "International benchmarks"), ("structure", "Campaign structure"),
        ("roster", "Our roster"), ("sources", "Sources")]
MARKETS = [("KSA", "Saudi Arabia"), ("UAE", "United Arab Emirates"), ("Egypt", "Egypt")]
PLATFORMS = [("instagram", "Instagram"), ("tiktok", "TikTok"), ("snapchat", "Snapchat"), ("youtube", "YouTube")]
BENCH_PLATFORM = {"instagram": "instagram_reels", "tiktok": "tiktok", "snapchat": "snapchat", "youtube": "youtube_shorts"}
SIZES = ("nano", "micro", "mid", "macro", "mega")
SIZE_LABEL = {"nano": "Nano", "micro": "Micro", "mid": "Mid", "macro": "Macro", "mega": "Mega"}
SIZE_RANGE = {"nano": "under 20K", "micro": "20K to 100K", "mid": "100K to 500K", "macro": "500K to 1M", "mega": "1M+"}
KIND = {"published_vendor": ("Published", ""), "published_global_proxy": ("Proxy", "own"),
        "extrapolation": ("Extrapolation", "warn"), "no_public_data": ("No public data", ""),
        "published": ("Published", ""), "measured": ("Measured", "live")}
CONF = {"high": "live", "medium": "own", "low": "warn"}

_cache = {}


class MissingData(Exception):
    pass


def load(name):
    """A dataset by short name; read once per process (the files only change on a deploy)."""
    if name not in _cache:
        try:
            with open(DIR / FILES[name], encoding="utf-8") as fh:
                _cache[name] = json.load(fh)
        except (OSError, ValueError) as exc:
            raise MissingData("%s: %s" % (FILES[name], exc))
    return _cache[name]


# ------------------------------------------------------------------ pieces --

def pill(text, tone=""):
    return "<span class='pill%s'>%s</span>" % (" " + tone if tone else "", e(text))


def conf_pill(c):
    word = (c or "").split(" ")[0].split("(")[0].strip().lower()
    return pill((c or "").split("(")[0].strip() or "n/a", CONF.get(word, ""))


def kind_pill(k):
    label, tone = KIND.get(k, (k or "", ""))
    return pill(label, tone)


def stamp(updated=UPDATED):
    return "<span class='muted'>Last updated " + e(updated) + "</span>"


def src_chips(ids, inline_limit=4):
    ids = [i for i in (ids or []) if i and i != "X"]
    if not ids:
        return "<span class='muted'>none</span>"
    chips = "".join("<a class='pill rf-src' href='%s'>%s</a>" % (e(u("/reference?tab=sources&q=" + i)), e(i)) for i in ids)
    if len(ids) <= inline_limit:
        return "<span class='rf-chips'>" + chips + "</span>"
    return ("<details class='rf-more'><summary>" + str(len(ids)) + " sources</summary><span class='rf-chips'>"
            + chips + "</span></details>")


def intro(ref, extra=""):
    """The header strip of a tab: what it is, when it was updated, how to read it, the caveats."""
    how = "".join("<li>" + e(x) + "</li>" for x in ref.get("how_to_read", []))
    cav = "".join("<li>" + e(x) + "</li>" for x in ref.get("caveats", []))
    return ("<section class='card'><div class='hd'><h2>" + e(ref.get("title", "")) + "</h2>" + stamp(ref.get("updated", UPDATED))
            + "</div><p class='sec-desc'>" + e(ref.get("note", "")) + "</p>" + extra
            + ("<details class='rf-box' open><summary>How to read</summary><ul>" + how + "</ul></details>" if how else "")
            + ("<details class='rf-box' open><summary>Caveats</summary><ul>" + cav + "</ul></details>" if cav else "")
            + "</section>")


def _money(cell, cur):
    """'SAR 3,000' with the other currencies small underneath."""
    if not isinstance(cell, dict) or cur not in cell:
        return "<span class='muted'>—</span>"
    others = [c for c in ("SAR", "AED", "USD", "EGP") if c != cur and c in cell]
    sub = " · ".join("%s %s" % (c, format(cell[c], ",")) for c in others if c in ("SAR", "USD"))
    return ("<b>%s %s</b>" % (e(cur), format(cell[cur], ",")) + ("<br><small class='muted'>" + e(sub) + "</small>" if sub else ""))


def _num(v, nd=None):
    if v is None:
        return None
    if isinstance(v, float) and nd is not None:
        out = format(round(v, nd), ",.%df" % nd)
        return out.rstrip("0").rstrip(".") if "." in out else out
    return format(v, ",") if isinstance(v, int) else str(v)


def _pct(v):
    return str(int(v)) if float(v).is_integer() else str(round(float(v), 1))


def _range(lo, hi, pre="", suf="", nd=2):
    if lo is None and hi is None:
        return None
    if lo == hi or hi is None:
        return pre + _num(lo, nd) + suf
    if lo is None:
        return pre + _num(hi, nd) + suf
    return pre + _num(lo, nd) + " to " + _num(hi, nd) + suf


def _select(name, options, current, label):
    return ("<label class='rf-f'><span>" + e(label) + "</span><select name='" + name + "'>"
            + "".join("<option value='%s'%s>%s</option>" % (e(v), " selected" if v == current else "", e(l)) for v, l in options)
            + "</select></label>")


# ---------------------------------------------------------------- market tab --

def market_tab(q):
    d = load("market")
    mk = q.get("market") if q.get("market") in d["markets"] else "KSA"
    pf = q.get("platform") if q.get("platform") in dict(PLATFORMS) else "instagram"
    cur = d["markets"][mk]["currency"]
    plat = d["markets"][mk]["platforms"][pf]
    form = ("<form method='get' action='" + u("/reference") + "' class='rf-filters'><input type='hidden' name='tab' value='market'>"
            + _select("market", [(k, "%s (%s)" % (l, d["markets"][k]["currency"])) for k, l in MARKETS], mk, "Market")
            + _select("platform", PLATFORMS, pf, "Platform") + "<button class='btn small'>Show</button></form>")
    fx = d["meta"]["fx"]
    rows = ""
    for t in SIZES:
        c = plat["tiers"].get(t)
        if not c:
            continue
        extra = ("Extrapolation" if c.get("is_extrapolation") else "Published")
        kind = pill(extra, "warn" if c.get("is_extrapolation") else "")
        if "T4" in (c.get("sources") or []) and not c.get("is_extrapolation"):
            kind += " " + pill("with contracts", "live")
        why = ("<details class='rf-more'><summary>Why this number</summary><p>" + e(c.get("rationale") or c.get("basis") or "")
               + "</p><p class='muted'>Basis: " + e(c.get("basis") or "") + "</p></details>")
        rows += ("<tr><th scope='row'>" + e(SIZE_LABEL[t]) + "<br><small class='muted'>" + e(SIZE_RANGE[t]) + "</small></th>"
                 "<td>" + _money(c.get("average"), cur) + "</td><td>" + _money(c.get("cap"), cur) + "</td><td>"
                 + _money(c.get("low"), cur) + "</td><td>" + kind + "</td><td>" + conf_pill(c.get("confidence")) + "</td>"
                 "<td>" + e(c.get("n_independent_sources", "")) + "</td><td>" + src_chips(c.get("sources")) + why + "</td></tr>")
    grid = ("<section class='card'><div class='hd'><h2>" + e(dict(MARKETS)[mk]) + ", " + e(dict(PLATFORMS)[pf]) + "</h2>"
            "<span class='muted'>" + e(plat.get("unit", "")) + "</span></div>" + form
            + "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Size</th><th>Average</th><th>Cap</th><th>Low</th>"
              "<th>Kind</th><th>Confidence</th><th>Independent sources</th><th>Sources</th></tr></thead><tbody>" + rows
            + "</tbody></table></div><p class='price-hint'>Creator-side fee, per one organic deliverable, ex-VAT. Client price is about "
              "creator fee x 1.27. FX used: 1 USD = %s SAR, %s AED, %s EGP. Average and cap are what the calculator's price "
              "references would show; the calculator itself does not read this page.</p></section>"
            % (e(fx["USD_SAR"]), e(fx["USD_AED"]), e(fx["USD_EGP"])))

    # doctor / pharmacist creators (extrapolated)
    hcp = d.get("hcp_rows_extrapolated", {}).get(mk, {})
    hrows = ""
    for key, c in hcp.items():
        plat_k, size = key.split("_", 1)
        if plat_k != pf:
            continue
        hrows += ("<tr><th scope='row'>" + e(SIZE_LABEL.get(size, size)) + "</th><td>" + _money(c.get("average"), cur) + "</td><td>"
                  + _money(c.get("cap"), cur) + "</td><td>" + _money(c.get("low"), cur) + "</td><td>" + kind_pill("extrapolation")
                  + "</td><td>" + conf_pill(c.get("confidence")) + "</td><td>" + src_chips(c.get("sources")) + "</td></tr>")
    hcp_card = ("<section class='card'><div class='hd'><h2>Doctor and pharmacist creators</h2></div>"
                "<p class='sec-desc'>Extrapolated from a single US vendor (+30 to 80% over lifestyle creators). Instagram and TikTok, micro and mid only.</p>"
                "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Size</th><th>Average</th><th>Cap</th><th>Low</th><th>Kind</th>"
                "<th>Confidence</th><th>Sources</th></tr></thead><tbody>" + hrows + "</tbody></table></div></section>") if hrows else ""

    # UGC per finished video
    ug = d["ugc_per_deliverable"].get(mk, {})
    ugc = ""
    if ug:
        ugc = ("<section class='card'><div class='hd'><h2>UGC per finished video</h2></div><p class='sec-desc'>" + e(ug.get("unit", ""))
               + "</p><div class='rf-kpis'>"
               + "".join("<div class='rf-kpi'><span>%s</span><b>%s %s</b><small class='muted'>SAR %s · USD %s</small></div>" % (
                   l, e(ug.get("currency", cur)), format(ug[k], ","), format(ug.get(k + "_SAR", ug[k]), ","), format(ug.get(k + "_USD", ""), ","))
                   for l, k in (("Low", "low"), ("Average", "average"), ("Cap", "cap")) if k in ug)
               + "</div><p>" + conf_pill(ug.get("confidence")) + " <span class='muted'>n = " + e(ug.get("n", "")) + "</span></p>"
               + "<details class='rf-more'><summary>Evidence</summary><ul>" + "".join("<li>" + e(x) + "</li>" for x in ug.get("evidence", []))
               + "</ul></details></section>")

    # general rules of thumb
    am = d["agency_markup"]
    ap = d["asking_vs_paid"]
    sea = d["seasonality"]
    prem = d["premiums"]
    mult = am["creator_to_client_multiplier"]
    allin = am["all_in_multiplier_incl_production_usage"]
    rules = ("<section class='card'><div class='hd'><h2>Rules of thumb</h2><span class='muted'>apply to all three markets</span></div>"
             "<div class='rf-two'>"
             "<div><h3>Creator fee to client price</h3><p><b>x" + e(mult["typical"]) + "</b> (range x" + e(mult["low"]) + " to x" + e(mult["high"])
             + "). " + e(mult.get("logic", "")) + " " + conf_pill("medium") + "</p>"
             "<p>All-in budget (production, usage, management) is about <b>x" + e(allin["typical"]) + "</b> the creator fees (x" + e(allin["low"])
             + " to x" + e(allin["high"]) + "). " + src_chips([allin.get("source")]) + "</p>"
             "<h3>Asking vs paid (UAE contracts)</h3><ul>"
             + "".join("<li>" + e(ap["uae_contract_vs_rate_card"][k]) + "</li>" for k in ("micro_10_50K", "mid_50_250K", "macro_250K_1M", "slope"))
             + "</ul><p class='muted'>" + e(ap["uae_contract_vs_rate_card"].get("caveat", "")) + "</p><p class='muted'>" + e(ap.get("ksa_note", "")) + "</p></div>"
             "<div><h3>Discounts</h3><ul>" + "".join("<li><b>" + e(k.replace("_", " ")) + ":</b> " + e(v) + "</li>" for k, v in ap["discount_stack"].items())
             + "</ul><h3>Surcharges</h3><ul>" + "".join("<li><b>" + e(k.replace("_", " ")) + ":</b> " + e(v) + "</li>" for k, v in ap["surcharges"].items())
             + "</ul></div></div>"
             "<h3>Seasonality</h3><p><b>Ramadan and peak seasons: +" + e(sea["ramadan_peak"]["uplift_pct"]["low"]) + " to +"
             + e(sea["ramadan_peak"]["uplift_pct"]["high"]) + "%, typical +" + e(sea["ramadan_peak"]["uplift_pct"]["typical"]) + "%.</b> "
             + conf_pill(sea["ramadan_peak"]["confidence"]) + " " + e(sea.get("national_day_eid", "")) + " " + e(sea.get("off_peak", "")) + "</p>"
             "<details class='rf-more'><summary>Evidence</summary><ul>" + "".join("<li>" + e(x) + "</li>" for x in sea["ramadan_peak"]["evidence"])
             + "</ul></details>"
             "<h3>Premiums</h3><ul>" + "".join("<li><b>" + e(k.replace("_", " ")) + ":</b> "
                                                + e(v.get("pct") or v.get("detail") or "")
                                                + (" " + conf_pill(v["confidence"]) if v.get("confidence") else "") + "</li>"
                                                for k, v in prem.items()) + "</ul></section>")

    cm = d.get("cpm_crosscheck", {}).get("transacted_creator_cpm_uae", {})
    cpm = ("<section class='card'><div class='hd'><h2>CPM cross-check (UAE, transacted)</h2></div><p><b>AED " + e(cm.get("range_AED_per_1000_views", ""))
           + " per 1,000 views</b> (SAR " + e(cm.get("range_SAR", "")) + "). " + e(cm.get("reading", "")) + " " + src_chips([cm.get("source")])
           + "</p></section>") if cm else ""

    conf = ("<section class='card'><div class='hd'><h2>Conflicts between sources</h2></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols>"
            "<thead><tr><th>Topic</th><th>The conflict</th><th>Which to trust</th></tr></thead><tbody>"
            + "".join("<tr><th scope='row'>" + e(c["topic"]) + "</th><td>" + e(c["detail"]) + "</td><td>" + e(c["trust"]) + "</td></tr>"
                      for c in d["conflicts"]) + "</tbody></table></div></section>")

    led = [r for r in d["evidence_rows"] if r.get("market") == mk]
    ledger = ("<section class='card'><div class='hd'><h2>Evidence ledger: " + e(dict(MARKETS)[mk]) + "</h2><span class='muted'>"
              + str(len(led)) + " published or observed figures</span></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols>"
              "<thead><tr><th>Platform</th><th>What</th><th>Figure</th><th>Type</th><th>Source</th><th>Date</th><th>Confidence</th></tr></thead><tbody>"
              + "".join("<tr><td>" + e(r.get("platform", "")) + "</td><td>" + e(r.get("scope", "")) + "</td><td>" + e(r.get("figure", ""))
                        + "<br><small class='muted'>" + e(r.get("unit", "")) + "</small></td><td>" + e(r.get("type", ""))
                        + "</td><td>" + "".join(src_chips([s.strip()]) for s in re.split(r"[,/]", str(r.get("source", ""))) if s.strip())
                        + "</td><td>" + e(r.get("date", "")) + "</td><td>" + conf_pill(r.get("confidence")) + "</td></tr>" for r in led)
              + "</tbody></table></div></section>") if led else ""

    meth = ("<details class='card rf-box'><summary>Method</summary><ol>" + "".join("<li>" + e(x) + "</li>" for x in d.get("method", []))
            + "</ol></details>")
    return intro(d["reference"]) + grid + hcp_card + ugc + rules + cpm + conf + ledger + meth


# --------------------------------------------------------------- bench tab --

def bench_tab(q):
    d = load("bench")
    mk = q.get("market") if q.get("market") in d["markets"] else "KSA"
    pf = q.get("platform") if q.get("platform") in dict(PLATFORMS) else "instagram"
    data = d["markets"][mk][BENCH_PLATFORM[pf]]
    lcur = d["markets"][mk].get("currency") or {"KSA": "SAR", "UAE": "AED", "Egypt": "EGP"}[mk]
    form = ("<form method='get' action='" + u("/reference") + "' class='rf-filters'><input type='hidden' name='tab' value='bench'>"
            + _select("market", [(k, l) for k, l in MARKETS], mk, "Market") + _select("platform", PLATFORMS, pf, "Platform")
            + "<button class='btn small'>Show</button></form>")
    unit = {"view_rate": "%", "eng_rate": "%"}
    rows, detail = "", ""
    for t in SIZES:
        c = data.get(t)
        if not c:
            continue
        cells = ""
        for key in ("view_rate", "eng_rate", "cpm_usd", "cpe_usd", "cpc_usd"):
            m = c.get(key) or {}
            if m.get("kind") == "no_public_data" or (m.get("low") is None and m.get("high") is None):
                cells += "<td><span class='muted'>No public data</span></td>"
                continue
            if key in unit:
                val = _range(m.get("low"), m.get("high"), suf="%")
            else:
                val = _range(m.get("low"), m.get("high"), pre="$")
            cells += "<td><b>" + e(val) + "</b><br>" + kind_pill(m.get("kind")) + " " + src_chips(m.get("sources"), 2) + "</td>"
        pp = c.get("price_per_post_usd") or {}
        if pp.get("local_low") is not None or pp.get("usd_low") is not None:
            lc = pp.get("local_currency", lcur)
            price = ("<b>" + e(lc) + " " + e(_range(pp.get("local_low"), pp.get("local_high"), nd=0)) + "</b><br><small class='muted'>USD "
                     + e(_range(pp.get("usd_low"), pp.get("usd_high"), nd=0)) + "</small><br>" + kind_pill(pp.get("kind")) + " "
                     + src_chips(pp.get("sources"), 2))
        else:
            price = "<span class='muted'>No public data</span><br>" + kind_pill(pp.get("kind") or "no_public_data")
        rows += ("<tr><th scope='row'>" + e(SIZE_LABEL[t]) + "<br><small class='muted'>" + e(SIZE_RANGE[t]) + "</small></th>"
                 + cells + "<td>" + price + "</td><td>" + conf_pill(c.get("confidence")) + "</td></tr>")
        bl = ""
        for key, label in (("view_rate", "View rate"), ("eng_rate", "Engagement rate"), ("price_per_post_usd", "Price per post"),
                           ("cpm_usd", "CPM"), ("cpe_usd", "CPE"), ("cpc_usd", "CPC")):
            m = c.get(key) or {}
            if m.get("basis"):
                bl += "<li><b>" + e(label) + ":</b> " + e(m["basis"]) + "</li>"
        if bl:
            detail += "<details class='rf-more'><summary>" + e(SIZE_LABEL[t]) + ": where each figure comes from</summary><ul>" + bl + "</ul></details>"
    meta = d["meta"]
    grid = ("<section class='card'><div class='hd'><h2>" + e(dict(MARKETS)[mk]) + ", " + e(dict(PLATFORMS)[pf]) + "</h2></div>" + form
            + "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Size</th><th>View rate<br><small>views / followers</small></th>"
              "<th>Engagement rate<br><small>" + ("of followers" if pf == "instagram" else "of views") + "</small></th>"
              "<th>CPM<br><small>USD per 1,000 views</small></th><th>CPE<br><small>USD per engagement</small></th>"
              "<th>CPC<br><small>USD per click</small></th><th>Price per post</th><th>Confidence</th></tr></thead><tbody>" + rows
            + "</tbody></table></div><p class='price-hint'>" + e(meta.get("note", "")) + "</p>" + detail + "</section>")

    leg = ("<section class='card'><div class='hd'><h2>Kinds and confidence</h2></div><div class='rf-two'><div><ul>"
           + "".join("<li>" + kind_pill(k) + " " + e(v) + "</li>" for k, v in meta["kind_legend"].items())
           + "</ul></div><div><ul>" + "".join("<li>" + conf_pill(k) + " " + e(v) + "</li>" for k, v in meta["confidence_legend"].items())
           + "</ul><p class='muted'>FX: 1 USD = " + e(meta["fx"]["SAR_per_USD"]) + " SAR, " + e(meta["fx"]["AED_per_USD"]) + " AED, "
           + e(meta["fx"]["EGP_per_USD"]) + " EGP. " + e(meta["fx"].get("EGP_note", "")) + "</p></div></div></section>")

    fv = d["fair_value_cpm_ceiling_per_1000_views"]
    names = dict(instagram_reels="Instagram Reels", tiktok="TikTok", snapchat="Snapchat", youtube_shorts="YouTube Shorts")
    fvt = ("<section class='card'><div class='hd'><h2>Fair-value CPM ceilings</h2>" + kind_pill("extrapolation") + " " + conf_pill("low")
           + "</div><p class='sec-desc'>" + e(fv.get("note", "")) + "</p><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Platform</th>"
           "<th>Acceptable ceiling</th><th>Good target</th></tr></thead><tbody>"
           + "".join("<tr><th scope='row'>" + e(names[k]) + "</th><td><b>SAR " + e(fv["acceptable_ceiling_sar"][k]) + "</b> <span class='muted'>USD "
                     + e(fv["acceptable_ceiling_usd"][k]) + "</span></td><td><b>SAR " + e(fv["good_target_sar"][k]) + "</b> <span class='muted'>USD "
                     + e(fv["good_target_usd"][k]) + "</span></td></tr>" for k in names) + "</tbody></table></div></section>")

    adj = d.get("category_adjustments", {})
    spec = d.get("market_specifics", {})

    def _items(obj):
        return "".join("<tr><th scope='row'>" + e(k.replace("_", " ")) + "</th><td>" + e(v.get("published", "")) + "</td><td>" + conf_pill(v.get("confidence"))
                       + "</td><td>" + src_chips(v.get("sources")) + "</td></tr>" for k, v in obj.items())
    adjt = ("<section class='card'><div class='hd'><h2>Category adjustments and market specifics</h2></div><div class='rf-scroll'>"
            "<table class='rf-table' data-nosort data-nocols><thead><tr><th>Topic</th><th>What was published</th><th>Confidence</th><th>Sources</th></tr></thead><tbody>"
            + _items(adj) + _items(spec) + "</tbody></table></div><p class='price-hint'>The pharma and healthcare premium has no public source; the "
            "figures above are modelled or anecdotal. Mawthooq, UAE advertiser permit and SFDA points need checking against the original text.</p></section>")
    return intro(d["reference"]) + grid + fvt + adjt + leg


# ----------------------------------------------------------- structure tab --

def _live(goal):
    live = roi.shapes()[goal]
    default = {t: float(v) for t, v in roi.SHAPES_DEFAULT[goal].items()}
    cl = {t: float(v) for t, v in live.items() if v}
    return live, cl != default


def structure_tab(q):
    d = load("structure")
    counts_live = roi.count_ranges()
    out = [intro(d["reference"], "<p>" + pill("In use by the ROI calculator", "live") + " marks a value the calculator reads right now. "
                                  "It shows the LIVE value (from Settings when edited), next to the research value.</p>")]
    for ob in d["objectives"]:
        g = ob["id"]
        live, edited = _live(g)
        rows = ""
        for t in ("mega", "macro", "mid", "micro", "nano"):
            lv = live.get(t, 0.0)
            rec = ob["shape"].get(t, "0")
            rows += ("<tr><th scope='row'>" + e(SIZE_LABEL[t]) + "<br><small class='muted'>" + e(SIZE_RANGE[t]) + "</small></th><td>" + e(rec) + "%</td>"
                     "<td><b>" + e(_pct(lv)) + "%</b> " + pill("In use by the ROI calculator", "live") + "</td></tr>")
        lo, hi = counts_live[g]
        c_edited = (lo, hi) != tuple(roi.COUNT_RANGES_DEFAULT[g])
        cf = ob["confidence"]
        card = ("<section class='card'><div class='hd'><h2>" + e(ob["label"]) + " <small class='muted'>" + e(ob["means"]) + "</small></h2>"
                + pill("Inference", "warn") + " " + stamp(d["reference"]["updated"]) + "</div>"
                + ("<p class='sec-desc'>" + e(ob["note"]) + "</p>" if ob.get("note") else "")
                + "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Size</th><th>Research: share of creators</th>"
                  "<th>Calculator: share of creators</th></tr></thead><tbody>" + rows + "</tbody></table></div>"
                + ("<p class='price-hint'><b>The calculator's shape was edited in Settings</b> and differs from the built-in default.</p>" if edited else "")
                + "<div class='rf-kpis'>"
                  "<div class='rf-kpi'><span>Creators, research range</span><b>" + e(ob["creators"][0]) + " to " + e(ob["creators"][1]) + "</b>"
                  "<small class='muted'>mid-size budget, SAR 50K to 150K</small></div>"
                  "<div class='rf-kpi'><span>Creators, calculator hint</span><b>" + e(lo) + " to " + e(hi) + "</b>"
                  "<small>" + pill("In use by the ROI calculator", "live") + (" edited in Settings" if c_edited else "") + "</small></div>"
                  "<div class='rf-kpi'><span>Posts per creator</span><b>" + e(ob["posts_each"]) + "</b>"
                  "<small class='muted'>Calculator: plans one post per creator; a second post counts at "
                  + e(int(roi.SECOND_POST * 100)) + "% (an assumption)</small></div>"
                  "<div class='rf-kpi'><span>Implied spend split</span><b>" + e(ob["implied_spend"]) + "</b>"
                  "<small class='muted'>at the default planning prices</small></div></div>"
                + "<p>Confidence: direction " + conf_pill(cf["direction"]) + " percentages " + conf_pill(cf["percentages"]) + " count "
                + conf_pill(cf["count"]) + " posts " + conf_pill(cf["posts"]) + " " + src_chips(ob.get("sources")) + "</p></section>")
        out.append(card)

    # other values the calculator reads that are assumptions, not research
    asm = roi.assumptions()
    out.append("<section class='card'><div class='hd'><h2>Other values the calculator reads</h2></div>"
               "<p class='sec-desc'>These are HelloVoice assumptions or measured calibrations, not published research. Shown so the numbers behind a result can be read.</p>"
               "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Value</th><th>Now</th><th>What it is</th></tr></thead><tbody>"
               "<tr><th scope='row'>On-structure tolerance</th><td><b>" + e(roi.ON_STRUCTURE_POINTS) + " points</b> " + pill("In use by the ROI calculator", "live")
               + "</td><td>A size within this many points of its recommended share counts as on structure.</td></tr>"
               "<tr><th scope='row'>Second post by the same creator</th><td><b>" + e(int(roi.SECOND_POST * 100)) + "%</b> " + pill("In use by the ROI calculator", "live")
               + "</td><td>Assumption. No source supports a post-level decay constant.</td></tr>"
               "<tr><th scope='row'>Peers needed for a roster benchmark</th><td><b>" + e(benchmarks.MIN_PEERS) + " creators</b> " + pill("In use by the ROI calculator", "live")
               + "</td><td>Below this a cell is not used; the calculator falls back to the guide.</td></tr>"
               "<tr><th scope='row'>Mean over median views</th><td><b>x" + e(roi.MEAN_OVER_MEDIAN) + "</b> " + pill("In use by the ROI calculator", "live")
               + "</td><td>Derived from the roster's spread of views, applied to median-based figures.</td></tr>"
               "<tr><th scope='row'>Instagram reel view rate by size, no measured views</th><td>"
               + e(", ".join("%s %s%%" % (SIZE_LABEL[t].lower(), _num(roi.IG_VIEW_RATE[t])) for t in SIZES)) + " " + pill("In use by the ROI calculator", "live")
               + "</td><td>Calibrated on 39 real reels (2026-10-10).</td></tr>"
               "<tr><th scope='row'>Impressions per view</th><td>" + e(", ".join("%s %s" % (p, v) for p, v in asm["impressions_per_view"].items())) + " "
               + pill("In use by the ROI calculator", "live") + "</td><td>Planning assumption; editable in Settings.</td></tr>"
               "<tr><th scope='row'>Landing rate</th><td>" + e(asm["landing_rate"]) + " " + pill("In use by the ROI calculator", "live")
               + "</td><td>Planning assumption; editable in Settings.</td></tr></tbody></table></div></section>")

    out.append("<section class='card'><div class='hd'><h2>What is well supported</h2></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>#</th>"
               "<th>Finding</th><th>Direction</th><th>Magnitude</th><th>Evidence</th><th>Sources</th></tr></thead><tbody>"
               + "".join("<tr><td>" + e(f["n"]) + "</td><td><b>" + e(f["title"]) + "</b><br>" + e(f["text"]) + "</td><td>" + conf_pill(f["direction"])
                         + "</td><td>" + conf_pill(f["magnitude"]) + "</td><td>" + pill(f["evidence"]) + "</td><td>" + src_chips(f["sources"], 3) + "</td></tr>"
                         for f in d["findings"]) + "</tbody></table></div>"
               "<h3>Not supported by the evidence</h3><ul>" + "".join("<li>" + e(x) + "</li>" for x in d["not_supported"]) + "</ul></section>")

    bs = d["budget_scaling"]
    out.append("<section class='card'><div class='hd'><h2>Budget and sector overlays</h2>" + pill("Inference") + " " + conf_pill(bs["confidence"]) + "</div>"
               "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Creator budget</th><th>Creators</th><th>Note</th></tr></thead><tbody>"
               + "".join("<tr><th scope='row'>" + e(r["budget"]) + "</th><td>" + e(r["creators"]) + "</td><td>" + e(r["note"]) + "</td></tr>" for r in bs["rows"])
               + "</tbody></table></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Sector</th><th>Creators</th><th>Shape</th><th>Posts</th>"
                 "<th>Why</th><th>Calculator</th><th>Sources</th></tr></thead><tbody>"
               + "".join("<tr><th scope='row'>" + e(o["label"]) + "<br>" + conf_pill(o["confidence"]) + "</th><td>" + e(o["creators"]) + "</td><td>" + e(o["shape"])
                         + "</td><td>" + e(o["posts_each"]) + "</td><td>" + e(o["text"]) + "</td><td>" + e(o["calculator"]) + "</td><td>"
                         + src_chips(o["sources"], 3) + "</td></tr>" for o in d["overlays"]) + "</tbody></table></div>"
               "<p class='price-hint'>" + e(d["tolerance_points"]["text"]) + "</p></section>")

    out.append("<section class='card'><div class='hd'><h2>Owner's proposal against the evidence</h2></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols>"
               "<thead><tr><th>Objective</th><th>Proposal</th><th>Implied spend</th><th>Verdict</th><th>Sources</th></tr></thead><tbody>"
               + "".join("<tr><th scope='row'>" + e(r["objective"]) + "</th><td>" + e(r["proposal"]) + "</td><td>" + e(r["implied_spend"]) + "</td><td>"
                         + e(r["verdict"]) + "</td><td>" + src_chips(r["sources"], 3) + "</td></tr>" for r in d["owner_proposal_check"])
               + "</tbody></table></div></section>")

    out.append("<section class='card'><div class='hd'><h2>How many creators and posts</h2></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr>"
               "<th>Question</th><th>What the evidence says</th><th>Type</th><th>Confidence</th><th>Sources</th></tr></thead><tbody>"
               + "".join("<tr><th scope='row'>" + e(r["question"]) + "</th><td>" + e(r["says"]) + "</td><td>" + pill(r["tag"]) + "</td><td>" + e(r["confidence"])
                         + "</td><td>" + src_chips(r["sources"], 3) + "</td></tr>" for r in d["posts_and_counts"]) + "</tbody></table></div></section>")

    out.append("<section class='card'><div class='hd'><h2>By platform</h2></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>Platform</th>"
               "<th>What the evidence supports</th><th>Implication (inference)</th><th>Confidence</th><th>Sources</th></tr></thead><tbody>"
               + "".join("<tr><th scope='row'>" + e(r["platform"]) + "</th><td>" + e(r["supports"]) + "</td><td>" + e(r["structure"]) + "</td><td>"
                         + e(r["confidence"]) + "</td><td>" + src_chips(r["sources"], 3) + "</td></tr>" for r in d["platforms"]) + "</tbody></table></div></section>")

    out.append("<section class='card'><div class='hd'><h2>Conflicts, gaps and how our own data settles them</h2></div><div class='rf-two'><div><h3>Conflicts</h3><ul>"
               + "".join("<li><b>" + e(r["conflict"]) + ".</b> " + e(r["reading"]) + " " + src_chips(r["sources"], 3) + "</li>" for r in d["conflicts"])
               + "</ul></div><div><h3>Gaps (no evidence found)</h3><ul>" + "".join("<li>" + e(x) + "</li>" for x in d["gaps"]) + "</ul><h3>Validating the defaults</h3><ul>"
               + "".join("<li>" + e(x) + "</li>" for x in d["validation"]) + "</ul></div></div></section>")
    return "".join(out)


# -------------------------------------------------------------- roster tab --

def _markets_card():
    """Creators per top-audience market (item 226): the catalogue's "Audience in" filter, counted. Staff only."""
    try:
        import discover
        n = discover.market_counts()
    except Exception:
        return ""
    rows = [("SA", "Saudi Arabia"), ("AE", "UAE"), ("EG", "Egypt"), ("GCC", "GCC (any of the four below)"),
            ("KW", "Kuwait"), ("QA", "Qatar"), ("BH", "Bahrain"), ("OM", "Oman")]
    trs = "".join("<tr><th scope='row'>" + ("&nbsp;&nbsp;" if k in discover.GCC else "") + e(label) + "</th><td><b>"
                  + e("{:,}".format(n.get(k, 0))) + "</b></td></tr>" for k, label in rows)
    return ("<section class='card'><div class='hd'><h2>Audience markets</h2>" + pill("Measured", "live")
            + " <span class='muted'>the catalogue's \"Audience in\" filter: the country is the biggest audience country on any analysed platform."
              " A creator can count in two markets. Staff only, never shown to clients.</span></div><div class='rf-scroll'>"
              "<table class='rf-table' data-nosort data-nocols><thead><tr><th>Market</th><th>Creators</th></tr></thead><tbody>"
            + trs + "</tbody></table></div></section>")


def roster_tab(q):
    rows = benchmarks.table()
    ref = {"title": "Our roster, measured now",
           "note": "Peers are the creator analyses already on file, grouped by platform and size. Worked out when this page opens (cached about ten minutes) and never stored. Counts and percentiles only; no creator is named.",
           "updated": "live",
           "how_to_read": ["A cell is a platform and a size. n is how many creators it holds; p25, median and p75 are the quarter points of their rates.",
                           "Engagement is per follower on Instagram, Facebook and X, and per view on TikTok and YouTube. View rate is average views / followers.",
                           "A cell with %d or more creators is used by the ROI calculator as a peer benchmark. Smaller cells are shown but not used." % benchmarks.MIN_PEERS],
           "caveats": ["Measured on the analyses we hold, not a sample of the market: it is skewed to the creators we have analysed.",
                       "Rates come from scraped or uploaded analyses and have outliers removed only for implausible values.",
                       "Median-post variants are the same creators' median post rather than their average."]}
    by = {}
    for r in rows:
        by.setdefault(r["platform"], {}).setdefault(r["size"], {})[r["metric"]] = r
    if not by:
        return intro(ref) + ("<section class='card'>" + ui.empty("bars", "No analyses yet", "Upload creator analyses and the cells appear here.") + "</section>")
    out = [intro(ref), _markets_card()]
    used = pill("Used by the calculator", "live")
    for plat in sorted(by):
        trs = ""
        for s in SIZES:
            cell = by[plat].get(s)
            if not cell:
                continue
            tds = ""
            flags = ""
            for m, nm in (("er", "Engagement"), ("view_rate", "View rate")):
                r = cell.get(m)
                if r:
                    tds += ("<td>" + e(r["n"]) + "</td><td>" + e(r["p25"]) + "%</td><td><b>" + e(r["median"]) + "%</b></td><td>" + e(r["p75"]) + "%</td>")
                    if r["usable"]:
                        flags += "<div>" + used + " <small class='muted'>" + e(nm.lower()) + "</small></div>"
                else:
                    tds += "<td colspan='4'><span class='muted'>no data</span></td>"
            if not flags:
                flags = "<span class='muted'>fewer than %d creators</span>" % benchmarks.MIN_PEERS
            trs += ("<tr><th scope='row'>" + e(SIZE_LABEL[s]) + "<br><small class='muted'>" + e(SIZE_RANGE[s]) + "</small></th>" + tds + "<td>" + flags + "</td></tr>")
        eng_basis = "per follower" if plat in benchmarks.FEED else "per view"
        extra = ""
        mrows = [r for s in SIZES for m in ("er_med", "view_rate_med", "spread") for r in [by[plat].get(s, {}).get(m)] if r]
        if mrows:
            extra = ("<details class='rf-more'><summary>Median-post variants and spread</summary><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr>"
                     "<th>Size</th><th>Measure</th><th>n</th><th>p25</th><th>Median</th><th>p75</th><th></th></tr></thead><tbody>"
                     + "".join("<tr><td>" + e(SIZE_LABEL[r["size"]]) + "</td><td>" + e({"er_med": "Engagement, median post", "view_rate_med": "View rate, median video",
                                                                                         "spread": "Spread of views (std / mean)"}[r["metric"]]) + "</td><td>"
                               + e(r["n"]) + "</td><td>" + e(r["p25"]) + ("" if r["metric"] == "spread" else "%") + "</td><td>" + e(r["median"])
                               + ("" if r["metric"] == "spread" else "%") + "</td><td>" + e(r["p75"]) + ("" if r["metric"] == "spread" else "%") + "</td><td>"
                               + (used if r["usable"] else "") + "</td></tr>" for r in mrows) + "</tbody></table></div></details>")
        out.append("<section class='card'><div class='hd'><h2>" + e(plat) + "</h2>" + pill("Measured", "live") + " <span class='muted'>engagement " + eng_basis
                   + "</span></div><div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th rowspan='2'>Size</th><th colspan='4'>Engagement</th><th colspan='4'>View rate</th>"
                     "<th rowspan='2'>Calculator</th></tr><tr><th>n</th><th>p25</th><th>Median</th><th>p75</th><th>n</th><th>p25</th><th>Median</th><th>p75</th></tr></thead><tbody>"
                   + trs + "</tbody></table></div>" + extra + "</section>")
    return "".join(out)


# ------------------------------------------------------------- sources tab --

def _citations():
    """{source id: number of figures that cite it} across the three datasets."""
    if "cites" not in _cache:
        text = ""
        for k in ("market", "bench", "structure"):
            d = dict(load(k))
            d.pop("reference", None)
            text += json.dumps(d)
        counts = {}
        for m in re.finditer(r"\b(CS\d+|[ST]\d+)\b", text):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
        _cache["cites"] = counts
    return _cache["cites"]


SET_LABEL = {"benchmarks": "Benchmarks (S)", "market_prices": "Market prices (T)", "campaign_structure": "Campaign structure (CS)"}


def sources_tab(q):
    d = load("sources")
    term = (q.get("q") or "").strip()
    which = q.get("set") if q.get("set") in SET_LABEL else ""
    items = d["sources"]
    if which:
        items = [s for s in items if s["set"] == which]
    if term:
        if re.match(r"^(CS|S|T)\d+$", term, re.I):
            items = [s for s in items if s["id"].upper() == term.upper()]
        else:
            low = term.lower()
            items = [s for s in items if low in " ".join(str(s.get(k, "")) for k in ("id", "title", "publisher", "year", "evidence_type", "url")).lower()]
    cites = _citations()
    form = ("<form method='get' action='" + u("/reference") + "' class='rf-filters'><input type='hidden' name='tab' value='sources'>"
            "<label class='rf-f rf-grow'><span>Search</span><input name='q' value='" + e(term) + "' placeholder='Publisher, title, year, type or an id such as S9' autocomplete='off'></label>"
            + _select("set", [("", "All lists")] + list(SET_LABEL.items()), which, "List") + "<button class='btn small'>Search</button></form>")
    rows = "".join(
        "<tr id='src-" + e(s["id"]) + "'><th scope='row'><span class='pill'>" + e(s["id"]) + "</span></th><td><b>" + e(s["publisher"]) + "</b><br>"
        "<span class='muted'>" + e(s["title"]) + "</span></td><td>" + e(s.get("year", "")) + "</td><td>" + e(s.get("evidence_type", ""))
        + ("<br>" + conf_pill(s["credibility"]) if s.get("credibility") else "") + "</td><td>" + e(cites.get(s["id"], 0)) + "</td><td>"
        + ("<a href='%s' target='_blank' rel='noopener noreferrer'>Open</a>" % e(s["url"]) if s.get("url", "").startswith("http") else "<span class='muted'>no link</span>")
        + "</td></tr>" for s in items)
    body = ("<section class='card'><div class='hd'><h2>Sources</h2><span class='muted'>" + str(len(items)) + " of " + str(len(d["sources"]))
            + " shown</span></div><p class='sec-desc'>" + e(d["reference"]["note"]) + " Publisher and year are read from the source title; "
            "evidence type is the researcher's description.</p>" + form
            + "<div class='rf-scroll'><table class='rf-table' data-nosort data-nocols><thead><tr><th>ID</th><th>Publisher and title</th><th>Year</th><th>Evidence type</th>"
              "<th>Cited</th><th>Link</th></tr></thead><tbody>"
            + (rows or "<tr><td colspan='6' class='muted'>No source matches.</td></tr>") + "</tbody></table></div></section>")
    return body


# -------------------------------------------------------------------- page --

STYLE = """<style>
.rf-note{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--line-strong);background:var(--white);border-radius:12px;padding:12px 16px;margin:0 0 18px}
.rf-note .ic{flex:none;margin-top:2px}
.rf-filters{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end;margin:0 0 16px}
.rf-f{display:flex;flex-direction:column;gap:4px;font-size:var(--t-xs,12px);font-weight:600;color:var(--gray)}
.rf-f select,.rf-f input{font:inherit;font-weight:400;color:var(--ink);min-width:170px;padding:9px 12px;border:1px solid var(--line-strong);border-radius:10px;background:#fff}
.rf-grow{flex:1 1 260px}.rf-grow input{width:100%}
.rf-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.rf-table th,.rf-table td{vertical-align:top}
main .rf-table thead th{position:static}
.rf-table tbody th{text-transform:none;letter-spacing:0;font-size:var(--t-md,14.5px);color:var(--ink);padding:12px;border-bottom:1px solid var(--line);white-space:nowrap}
.rf-table small{font-size:var(--t-xs,12px);text-transform:none;letter-spacing:0;font-weight:400}
.rf-table td b{font-variant-numeric:tabular-nums}
.rf-chips{display:inline-flex;flex-wrap:wrap;gap:4px}
.rf-src{text-decoration:none}.rf-src:hover{background:var(--ink);color:#fff}
.rf-more summary{cursor:pointer;color:var(--gray);font-size:var(--t-xs,12px);font-weight:600}
.rf-more[open]>summary{margin-bottom:6px}
.rf-more p,.rf-more ul{font-size:var(--t-sm,13px);margin:4px 0;max-width:62ch}
.rf-box{border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
.rf-box summary{cursor:pointer;font-weight:600}
.rf-box ul,.rf-box ol{margin:8px 0 0;padding-left:20px;max-width:80ch}
.rf-two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.rf-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:14px 0}
.rf-kpi{display:flex;flex-direction:column;gap:3px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--white)}
.rf-kpi span{font-size:var(--t-sm,13px);color:var(--gray)}
.rf-kpi b{font-size:var(--t-lg,17px);line-height:1.25}
.rf-kpi small{font-size:var(--t-xs,12px)}
.card h3{font-size:var(--t-md,14.5px);margin:18px 0 6px}
@media(max-width:700px){
.rf-table{display:table;min-width:640px}.rf-table thead{display:table-header-group}.rf-table tbody{display:table-row-group}
.rf-table tr{display:table-row}.rf-table td,.rf-table th{display:table-cell}
.rf-table th,.rf-table td{padding:10px 10px}.rf-table td{min-width:96px}
.rf-scroll{border:1px solid var(--line);border-radius:12px}
}
@media(max-width:800px){.rf-two{grid-template-columns:1fr}.rf-f select,.rf-f input{min-width:0;width:100%}.rf-f{flex:1 1 100%}.rf-note{flex-direction:column;gap:4px}}
</style>"""


def reference_page(query=None):
    q = query or {}
    tab = q.get("tab") if q.get("tab") in dict(TABS) else "market"
    tabs = [(u("/reference?tab=" + k), l, None, k == tab) for k, l in TABS]
    try:
        inner = {"market": market_tab, "bench": bench_tab, "structure": structure_tab, "roster": roster_tab, "sources": sources_tab}[tab](q)
    except MissingData as exc:
        inner = ("<div class='err'><strong>The reference data could not be read.</strong> " + e(str(exc))
                 + " The files live in admin/reference/ and are copied with the admin code.</div>")
    body = (STYLE + ui.header("Reference", "The research behind the numbers: where each figure comes from.", crumbs=[("Scoring rules", None), ("Reference", None)], tabs=tabs)
            + "<div class='rf-note' role='note'>" + ui.icon("info", 18) + "<span>" + e(NOTE) + "</span></div>" + inner)
    return V.page("Reference", body, "/reference")
