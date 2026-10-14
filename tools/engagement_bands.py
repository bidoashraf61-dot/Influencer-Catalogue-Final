"""TikTok engagement bands from OUR roster (owner-approved 2026-10-14): for each size, the middle half of creators
(25th to 75th percentile) of engagement per view. TikTok's rate is engagements / views, so the published per-follower
ranges (3.4-3.8%) made ordinary creators read as "twice the top". Only aggregates are written.

    python3 tools/engagement_bands.py [db] > admin/reference/engagement_bands.json
Creators under 1,000 followers, a rate of 0 (missing) and rates above 50% (bad data) are left out.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "admin"))
import db
if len(sys.argv) > 1:
    db.DB_PATH = Path(sys.argv[1])

BANDS = ("nano", "micro", "mid", "macro", "mega")


def band(f):
    return "nano" if f < 20000 else "micro" if f < 100000 else "mid" if f < 500000 else "macro" if f < 1000000 else "mega"


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))]


out = {"version": "2026-10-14", "note": "TikTok engagement = (likes + comments) / views, %; middle half of our creators per size", "platforms": {}}
with db.connect() as c:
    fol = {r["code"]: r["followers"] for r in c.execute("select code, followers from creators")}
    rows = c.execute("select code, platform, data from creator_analysis").fetchall()
groups = {}
for r in rows:
    if not str(r["platform"]).lower().startswith("tik"):
        continue
    d = json.loads(r["data"])
    f = fol.get(r["code"]) or d.get("followers")
    er = d.get("er")
    if not isinstance(f, (int, float)) or f < 1000 or not isinstance(er, (int, float)) or er <= 0:
        continue
    rate = er * 100.0 if er < 1 else float(er)
    if rate > 50:
        continue
    groups.setdefault(band(f), []).append(rate)
out["platforms"]["TikTok"] = {}
for b in BANDS:
    vals = groups.get(b, [])
    if len(vals) < 30:
        continue
    out["platforms"]["TikTok"][b] = {"n": len(vals), "low": round(pct(vals, 0.25), 2), "median": round(pct(vals, 0.5), 2),
                                     "high": round(pct(vals, 0.75), 2)}
print(json.dumps(out, indent=1))
