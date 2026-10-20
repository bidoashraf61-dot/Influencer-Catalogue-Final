"""Roster › Out of scope and same-handle pairs (items 224-225). Staff only: counts are fine here,
never on a client page."""
import time

import links
import rosterq
import ui
from views import e, page, pager, u, urlencode

PER = 100

QCSS = """<style>
.rq-sum{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 14px}
.rq-sum a{display:flex;gap:6px;align-items:baseline;padding:7px 12px;border:1px solid var(--line,#e3e3e3);border-radius:999px;text-decoration:none;color:inherit;font-size:13px}
.rq-sum a[aria-current]{border-color:var(--ink,#111);font-weight:600}
.rq-sum b{font-variant-numeric:tabular-nums}
.rq-job{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px;font-size:13px}
table.rq{width:100%;border-collapse:collapse;font-size:13px}
table.rq th,table.rq td{padding:8px 6px;border-bottom:1px solid var(--line,#eee);text-align:left;vertical-align:top}
table.rq td.num,table.rq th.num{text-align:right;font-variant-numeric:tabular-nums}
.rq-who{display:flex;gap:8px;align-items:center;min-width:180px}
.rq-why{display:flex;flex-direction:column;gap:3px}
.rq-why span{font-size:12px;color:var(--muted,#666)}
.rq-why b{font-weight:600}
.rq-lock{font-size:12px;color:var(--muted,#666);white-space:nowrap}
.rq-mix{white-space:nowrap}
.rq-bar{position:sticky;bottom:0;display:flex;gap:10px;align-items:center;padding:10px 0;background:var(--bg,#fff);border-top:1px solid var(--line,#eee)}
.rq-ai{font-size:12px}
@media (max-width:720px){table.rq .rq-hide{display:none}}
</style>"""


def _pct(v):
    return "—" if v is None else ("%g%%" % v)


def _row(d, tab):
    c = d
    face = ("<img class='tface' src='" + e(links.thumb(c["photo"])) + "' alt=''>") if c.get("photo") else "<span class='tface none'>—</span>"
    profs = ui_profiles(c.get("profiles"))
    why = "".join("<div><b>%s</b> <span>%s</span></div>" % (e(x["label"]), e(x["detail"])) for x in d["reasons"])
    if not d["reasons"] and d.get("unclear"):
        why = "<div><b>Unclear</b> <span>%s</span></div>" % (
            "no audience data" if not (d["mix"] or {}).get("has") else "borderline audience, no second signal")
    if d.get("ai_verdict"):
        why += "<div class='rq-ai'>AI: <b>%s</b> <span>%s</span></div>" % (e(d["ai_verdict"]), e(d.get("ai_reason") or ""))
    m = d["mix"] or {}
    mix = ("<span class='rq-mix'>%s · GCC %s</span>" % (_pct(m.get("core")), _pct(m.get("gcc")))) if m.get("has") else "<span class='muted'>no data</span>"
    if d["protected"]:
        pick = "<span class='rq-lock' title='On a selection or campaign: never archived from here'>" + ui.icon("key", 14) + " in use</span>"
    elif tab == "open":
        pick = "<input type='checkbox' form='rq-form' name='codes' value='%s'%s aria-label='Tick %s'>" % (
            e(c["code"]), " checked" if d.get("preselect") else "", e(c["code"]))
    else:
        pick = ""
    return ("<tr><td>" + pick + "</td><td><div class='rq-who'>" + face + "<div><b>" + e(c["name"] or "") + "</b><br><code>"
            + e(c["code"]) + "</code> <span class='muted'>@" + e((c.get("handle") or "").lstrip("@")) + "</span>" + profs
            + "</div></div></td><td class='rq-hide'>" + e(c.get("platform") or "") + "</td><td class='num'>"
            + ui.compact(c.get("followers")) + "</td><td class='rq-hide'>" + e(c.get("city") or "") + "</td><td>" + mix
            + "</td><td><div class='rq-why'>" + why + "</div></td></tr>")


def ui_profiles(raw):
    import db
    out = []
    for p in db.split_profiles(raw or "")[:3]:
        if p.get("url"):
            out.append("<a href='%s' target='_blank' rel='noopener noreferrer'>%s</a>" % (e(p["url"]), e(p["platform"] or "link")))
    return (" · " + " ".join(out)) if out else ""


def quality_page(tab, reason, rows, counts, page_no, last, job, ok=None, err=None):
    tabs = [(u("/roster/quality") + "?tab=open", "To review", "{:,}".format(counts.get("total", 0)) if counts.get("total") else None, tab == "open"),
            (u("/roster/quality") + "?tab=kept", "Kept", None, tab == "kept"),
            (u("/roster/quality") + "?tab=archived", "Archived", None, tab == "archived"),
            (u("/roster/quality") + "?tab=pairs", "Same-handle pairs", None, tab == "pairs")]
    head = ui.header("Out of scope", "Creators whose own data says they do not fit our markets (KSA, UAE, Egypt and the Gulf). "
                     "Decided by evidence only: audience countries, content language, fake followers, empty profiles. Never by a name. "
                     "Archive hides a creator from the catalogue and every client view; each one can be undone from History.",
                     crumbs=[("Creators", u("/roster")), ("Out of scope", None)], tabs=tabs)
    banner = (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")
    when = time.strftime("%d %b %Y %H:%M", time.gmtime(last["at"])) + " UTC" if last and last.get("at") else "never"
    state = ("Running: " + e(job["kind"] or "") + "…") if rosterq.running() else (
        ("Last job: " + e(job["message"])) if job.get("message") else "")
    jobbar = ("<div class='rq-job'><span class='muted'>Last scan: " + e(when) + "</span><span>" + state + "</span>"
              "<form method='post' action='" + u("/roster/quality/run") + "' class='inline'><input type='hidden' name='kind' value='scan'>"
              "<button class='btn small'" + (" disabled" if rosterq.running() else "") + ">" + ui.icon("refresh", 14) + " Scan now</button></form>"
              "<form method='post' action='" + u("/roster/quality/run") + "' class='inline'><input type='hidden' name='kind' value='ai'>"
              "<button class='btn small ghost'" + (" disabled" if rosterq.running() else "") + " title='Gemini flash-lite reads the unclear ones and gives in / out / unsure with a reason'>"
              + ui.icon("star", 14) + " Read unclear with AI (%s)</button></form></div>" % "{:,}".format(counts.get("unclear_unread", 0)))
    if tab == "pairs":
        return page("Out of scope", QCSS + head + banner + pairs_panel(rows), "/roster")
    chips = [("", "All", sum(v for k, v in counts.items() if k in rosterq.REASONS))]
    chips += [(k, rosterq.REASONS[k], counts.get(k, 0)) for k in rosterq.REASONS if counts.get(k)]
    chips += [("unclear", "Unclear", counts.get("unclear", 0))]
    sumbar = "<div class='rq-sum'>" + "".join(
        "<a href='%s'%s>%s <b>%s</b></a>" % (u("/roster/quality") + "?" + urlencode(tab=tab, reason=k), " aria-current='true'" if (reason or "") == k else "",
                                            e(lab), "{:,}".format(n)) for k, lab, n in chips) + "</div>" if tab == "open" else ""
    start = (page_no - 1) * PER
    shown = rows[start:start + PER]
    if not rows:
        body = ui.empty("check", "Nothing here", "Run a scan to check the roster again." if tab == "open" else "No creators in this list.")
    else:
        table = ("<table class='rq'><thead><tr><th>" + ("<input type='checkbox' id='rq-all' aria-label='Tick every row on this page'>" if tab == "open" else "")
                 + "</th><th>Creator</th><th class='rq-hide'>Platform</th><th class='num'>Followers</th><th class='rq-hide'>City on record</th>"
                 "<th>Audience KSA/UAE/EG · GCC</th><th>Why</th></tr></thead><tbody>"
                 + "".join(_row(d, tab) for d in shown) + "</tbody></table>"
                 + pager(len(rows), page_no, "/roster/quality", per=PER, tab=tab, reason=reason or ""))
        if tab == "open":
            bar = ("<form id='rq-form' method='post' action='" + u("/roster/quality/decide") + "' class='rq-bar'>"
                   "<input type='hidden' name='back' value='" + e("/roster/quality?" + urlencode(tab=tab, reason=reason or "", page=page_no)) + "'>"
                   "<b id='rq-n'></b>"
                   "<button class='btn small danger' name='do' value='archive' data-confirm-title='Archive the ticked creators?' "
                   "data-confirm='They disappear from the catalogue and every client view. Creators on a selection or campaign are skipped. Each one can be undone from History.'>"
                   + ui.icon("flag", 14) + " Archive ticked</button>"
                   "<button class='btn small ghost' name='do' value='keep'>Keep ticked (in scope)</button>"
                   "<span class='muted'>Pre-ticked: strong evidence only. Fake followers alone and big creators with some local audience are left for you.</span></form>"
                   "<script>(function(){var b=function(){return [].slice.call(document.querySelectorAll('input[form=rq-form][name=codes]'));};"
                   "function n(){document.getElementById('rq-n').textContent=b().filter(function(x){return x.checked;}).length+' ticked';}"
                   "document.addEventListener('change',function(ev){if(ev.target.matches('input[form=rq-form]'))n();});"
                   "var a=document.getElementById('rq-all');if(a)a.addEventListener('change',function(){b().forEach(function(x){x.checked=a.checked;});n();});n();})();</script>")
            body = table + bar
        elif tab == "kept":
            body = table
        else:
            body = table + "<p class='price-hint'>To bring one back, undo its \"Archived\" entry in History, or open it in Creators and show it to clients.</p>"
    return page("Out of scope", QCSS + head + banner + jobbar + sumbar + body, "/roster")


def pairs_panel(groups):
    from views import duplicate_group_card
    if not groups:
        return ui.empty("check", "No pairs found", "No two creator cards share a handle.")
    same = [g for g in groups if g["kind"] == "same"]
    cross = [g for g in groups if g["kind"] == "cross"]
    out = ("<p class='sec-desc'>Cards that share a handle but not a profile link, so the Duplicates tab does not catch them. "
           "<b>Same platform</b>: one account written two ways (<code>a.b</code> / <code>ab</code>). <b>Different platforms</b>: one person with an "
           "Instagram card and a TikTok card. Combine makes one card with every platform, link, analysis, post, selection and campaign. "
           "Pairs whose names match come first; a shared handle is not always the same person, so check the links. Every merge can be undone from History.</p>")
    for title, gs in (("Same platform, handle written differently", same), ("Same handle on different platforms", cross)):
        if gs:
            out += "<h3>%s <span class='muted'>%s</span></h3>" % (e(title), "{:,}".format(len(gs)))
            for g in gs:
                out += ("<p class='muted' style='margin:12px 0 4px'>%s%s</p>" % (e(g["why"]), " · names match" if g["strong"] else "")
                        + duplicate_group_card(g["creators"], back="/roster/quality?tab=pairs"))
    return out
