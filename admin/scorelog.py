"""Prediction log for the creator score (2026-10-13).

Every creator of a campaign gets ONE row in ``score_log`` the first time the log sees them: the score,
tag and confidence the portal gave them (scoring v5), the predicted view rate and engagement rate, and the
inputs behind it. The first row is frozen (UNIQUE campaign + creator, INSERT OR IGNORE), so a later
re-analysis cannot rewrite what was predicted. When the campaign's posts come in, ``report()`` sets the
prediction against what the creator delivered and says whether a higher score meant better results.

A row logged AFTER the campaign already had captured numbers is marked ``late``: it is not a real prediction
(the score was worked out with the results in sight of the data) and the report keeps it out of the verdict.
Sample/demo campaigns are never logged.

How it runs: ``start()`` (called from server.main, like weekly.py) runs ``ensure_all()`` 60 seconds after the
service starts and then every 30 minutes. It is idempotent: it only adds rows that are missing. Nothing here
changes a score or a campaign; a failure is printed and the next pass tries again.

    python3 admin/scorelog.py            log anything missing, then print the report
    python3 admin/scorelog.py report     print the report only
"""
import json
import math
import sys
import threading
import time

import db

INTERVAL = 1800
KIND = {"Awareness": "view rate", "Engagement": "engagement", "Traffic": "clicks per post"}


def _is_sample(camp):
    text = ("%s %s" % (camp["name"] or "", camp["client"] or "")).lower()
    return text.startswith("sample") or "(demo)" in text or "dummy data" in text


def _objective(camp, sel):
    import fit
    if sel is not None and sel["objective"] and fit.known_objective(sel["objective"]):
        return fit.canonical(sel["objective"])
    return fit.FROM_CAMPAIGN.get(str(camp["objective"] or "").lower(), "Balanced")


def _target(sel):
    import fit
    try:
        t = json.loads((sel["target"] if sel is not None else None) or "{}")
    except ValueError:
        t = {}
    return dict(fit.DEFAULT_TARGET, **{k: v for k, v in (t or {}).items() if v})


def snapshot(cid):
    """Log every creator of campaign ``cid`` that has no row yet. Returns how many rows were added."""
    import analysis
    import fit
    import metrics
    with db.connect() as conn:
        camp = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cid,)).fetchone()
        if camp is None or _is_sample(camp):
            return 0
        sel = (conn.execute("SELECT * FROM selections WHERE id = ?", (camp["selection_id"],)).fetchone()
               if camp["selection_id"] else None)
        have = {r["code"] for r in conn.execute("SELECT code FROM score_log WHERE campaign_id = ?", (cid,))}
        codes = [r["code"] for r in conn.execute("SELECT code FROM campaign_creators WHERE campaign_id = ?", (cid,))
                 if r["code"] not in have]
        late = 1 if conn.execute("SELECT 1 FROM content c JOIN snapshots s ON s.content_id = c.id "
                                 "WHERE c.campaign_id = ? LIMIT 1", (cid,)).fetchone() else 0
        try:
            plan = json.loads(camp["plan"] or "{}")
        except ValueError:
            plan = {}
    if not codes:
        return 0
    objective, target = _objective(camp, sel), _target(sel)
    wanted = analysis.canon_platform(camp["platform"] or plan.get("platform") or "") if (camp["platform"] or plan.get("platform")) else None
    rows = {c["code"]: c for c in db.creators_by_codes(codes)}
    every = db.analyses_for(codes)
    bench = metrics.benchmarks()
    out = []
    for code in codes:
        c = rows.get(code)
        if c is None:
            continue
        mine = every.get(code) or {}
        pl = wanted if wanted in mine else ("Instagram" if "Instagram" in mine else (sorted(mine)[0] if mine else None))
        entry = dict(campaign_id=cid, code=code, platform=pl or wanted or "", objective=objective, target=json.dumps(target),
                     engine=fit.score_engine(), score=None, tag=None, confidence=None, confidence_pct=None,
                     pred_view_rate=None, pred_engagement=None, followers=c["followers"], inputs=None, late=late, at=db.now())
        if pl:
            try:
                doc = mine[pl]["data"]
                fol = doc.get("followers") or c["followers"]
                entry["followers"] = fol
                r = fit.score(doc, pl, c["followers"], objective=objective, target=target, band=metrics.band_of(fol),
                              bench=bench, creator_interest=c["interest"], creator=c)
                if r.get("score") is not None:
                    entry.update(score=r["score"], tag=r["tag"], confidence=(r.get("confidence") or {}).get("level"),
                                 confidence_pct=(r.get("confidence") or {}).get("pct"),
                                 inputs=json.dumps({"parts": r.get("parts"), "metrics": r.get("metrics"),
                                                    "checks": r.get("checks"), "conclusion": r.get("conclusion")}))
                if entry["engine"] == "v5":
                    v5 = fit._v5_run(doc, pl, fol, objective)
                    if not v5.get("unscored"):
                        entry["pred_view_rate"] = (v5["metrics"].get("reach") or {}).get("value")
                        entry["pred_engagement"] = (v5["metrics"].get("engagement") or {}).get("value")
            except Exception as exc:                    # one bad analysis must not stop the rest
                print(("scorelog: %s %s skipped: %r" % (cid, code, exc))[:160], flush=True)
        out.append(entry)
    if not out:
        return 0
    cols = list(out[0])
    with db.connect() as conn:
        n = 0
        for e in out:
            n += conn.execute("INSERT OR IGNORE INTO score_log (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))),
                              [e[k] for k in cols]).rowcount
    return n


def ensure_all():
    """Log every campaign's missing creators. Returns {campaign_id: rows added}."""
    with db.connect() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM campaigns ORDER BY id")]
    return {cid: n for cid, n in ((cid, snapshot(cid)) for cid in ids) if n}


# -- what the creators delivered ----------------------------------------------------------------------
def outcomes(cid):
    """{code: {posts, view_rate, engagement, clicks_per_post}} from the campaign's captured posts (percent)."""
    by = {}
    for r in db.campaign_content(cid, include_hidden=False):
        views, likes, comments = r.get("views"), r.get("likes"), r.get("comments")
        if not views and likes is None:
            continue
        d = by.setdefault(r["code"], {"posts": 0, "v": [], "f": [], "eng": [], "tt_eng": 0.0, "tt_views": 0.0, "platform": r["platform"]})
        d["posts"] += 1
        fol = r.get("followers")
        if views and fol:
            d["v"].append(views / float(fol) * 100.0)
        if likes is not None and fol:
            d["eng"].append((likes + (comments or 0)) / float(fol) * 100.0)
        if likes is not None and views:
            d["tt_eng"] += likes + (comments or 0)
            d["tt_views"] += views
    with db.connect() as conn:
        clicks = {r["code"]: r["n"] for r in conn.execute(
            "SELECT code, COUNT(*) n FROM clicks WHERE campaign_id = ? AND COALESCE(bot, 0) = 0 GROUP BY code", (cid,))}
    out = {}
    for code, d in by.items():
        mean = lambda xs: sum(xs) / len(xs) if xs else None
        eng = (d["tt_eng"] / d["tt_views"] * 100.0) if d["platform"] == "TikTok" and d["tt_views"] else mean(d["eng"])
        out[code] = {"posts": d["posts"], "view_rate": mean(d["v"]), "engagement": eng,
                     "clicks_per_post": (clicks.get(code, 0) / float(d["posts"])) if d["posts"] else None}
    return out


def _rank(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r, i = [0.0] * len(v), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0 + 1
        i = j + 1
    return r


def spearman(a, b):
    """Rank correlation of two lists (-1..1), or None when there are fewer than 4 pairs or no spread."""
    if len(a) != len(b) or len(a) < 4:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return None if den == 0 else num / den


def report(cid=None):
    """One dict per campaign with logged predictions: how many were logged, how many delivered results, and
    how well the score, the predicted lead metric and the follower count each ranked the creators by what
    they delivered. Late rows are counted but kept out of the verdict."""
    with db.connect() as conn:
        where = "WHERE campaign_id = ?" if cid else ""
        logs = [dict(r) for r in conn.execute("SELECT * FROM score_log %s ORDER BY campaign_id, id" % where, (cid,) if cid else ())]
        names = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM campaigns")}
    out = []
    for k in sorted({r["campaign_id"] for r in logs}):
        rows = [r for r in logs if r["campaign_id"] == k]
        obj = rows[0]["objective"] or "Balanced"
        first = obj.split("+")[0] if obj != "Balanced" else "Awareness"
        got = outcomes(k)
        key = {"Awareness": "view_rate", "Engagement": "engagement", "Traffic": "clicks_per_post"}.get(first, "view_rate")
        pred_key = "pred_engagement" if key == "engagement" else "pred_view_rate"
        pairs = [(r, got[r["code"]][key]) for r in rows if r["code"] in got and got[r["code"]][key] is not None and r["score"] is not None]
        real = [(r, y) for r, y in pairs if not r["late"]]
        def corr(sel, x):
            xs = [(x(r), y) for r, y in sel if x(r) is not None]
            return spearman([a for a, _ in xs], [b for _, b in xs]) if xs else None
        out.append({"campaign_id": k, "name": names.get(k), "objective": obj, "outcome": key.replace("_", " "),
                    "logged": len(rows), "scored": sum(1 for r in rows if r["score"] is not None),
                    "late": sum(1 for r in rows if r["late"]), "with_results": len(pairs), "real_predictions": len(real),
                    "score_corr": corr(real, lambda r: r["score"]), "lead_corr": corr(real, lambda r: r[pred_key]),
                    "followers_corr": corr(real, lambda r: r["followers"]),
                    "score_corr_incl_late": corr(pairs, lambda r: r["score"]),
                    "rows": [{"code": r["code"], "score": r["score"], "tag": r["tag"], "confidence": r["confidence"],
                              "late": bool(r["late"]), "predicted": r[pred_key], "actual": got.get(r["code"], {}).get(key),
                              "posts": got.get(r["code"], {}).get("posts")} for r in rows]})
    return out


def report_text(cid=None):
    f = lambda v: "n/a" if v is None else "%.2f" % v
    lines = []
    for c in report(cid):
        lines.append("Campaign %s (%s) | %s | outcome: %s" % (c["campaign_id"], (c["name"] or "")[:40], c["objective"], c["outcome"]))
        lines.append("  logged %d | scored %d | late %d | with results %d | real predictions with results %d" % (
            c["logged"], c["scored"], c["late"], c["with_results"], c["real_predictions"]))
        lines.append("  rank correlation with what they delivered (real predictions only): score %s | predicted lead metric %s | followers %s" % (
            f(c["score_corr"]), f(c["lead_corr"]), f(c["followers_corr"])))
        if c["late"]:
            lines.append("  including late rows (not a real prediction): score %s" % f(c["score_corr_incl_late"]))
    return "\n".join(lines) or "Nothing logged yet."


def start():
    def loop():
        time.sleep(60)
        while True:
            try:
                added = ensure_all()
                if added:
                    print("scorelog: logged", added, flush=True)
            except Exception as exc:
                print("scorelog: pass skipped:", repr(exc)[:160], flush=True)
            time.sleep(INTERVAL)
    threading.Thread(target=loop, daemon=True, name="scorelog").start()


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
    db.init()
    if "report" not in sys.argv[1:]:
        print("logged:", ensure_all() or "nothing new")
    print(report_text())
