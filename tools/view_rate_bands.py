"""View-rate bands from OUR roster (owner-approved 2026-10-14): for each platform and size, the middle
half of creators (25th to 75th percentile) of views as a share of followers. Only aggregates are written.

    python3 tools/view_rate_bands.py > admin/reference/view_rate_bands.json      (run inside the admin container)
Instagram uses reel plays (else views); TikTok uses average views. Creators under 1,000 followers and
figures above 500% are left out as bad data.
"""
import json, statistics, sys
sys.path.insert(0, "/app/admin")
import db

BANDS = ("nano", "micro", "mid", "macro", "mega")

def band(f):
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"

def pct(vals, q):
    vals = sorted(vals); return vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))]

out = {"version": "2026-10-14", "note": "view rate = views as % of followers; middle half of our creators per size",
       "platforms": {}}
with db.connect() as c:
    fol = {r["code"]: r["followers"] for r in c.execute("select code, followers from creators")}
    rows = c.execute("select code, platform, data from creator_analysis").fetchall()
groups = {}
for r in rows:
    pl = "TikTok" if str(r["platform"]).lower().startswith("tik") else "Instagram" if str(r["platform"]).lower().startswith("insta") else None
    if not pl: continue
    d = json.loads(r["data"]); f = fol.get(r["code"]) or d.get("followers")
    if not isinstance(f, (int, float)) or f < 1000: continue
    v = (d.get("avg_reel_plays") or d.get("avg_views")) if pl == "Instagram" else d.get("avg_views")
    if not isinstance(v, (int, float)) or v <= 0: continue
    rate = v / f * 100.0
    if rate > 500: continue
    groups.setdefault((pl, band(f)), []).append(rate)
for pl in ("Instagram", "TikTok"):
    out["platforms"][pl] = {}
    for b in BANDS:
        vals = groups.get((pl, b), [])
        if len(vals) < 30: continue
        out["platforms"][pl][b] = {"n": len(vals), "low": round(pct(vals, 0.25), 2), "median": round(pct(vals, 0.5), 2),
                                   "high": round(pct(vals, 0.75), 2)}
print(json.dumps(out, indent=1))
