"""Mock data for the client dashboard's Goals & benchmarks tab: a campaign shaped like Jamjoom Wave 1
(5 doctors, Instagram + TikTok, pharma, 11 videos, targets 1,082,000 views / 14,200 engagements / 1.31% rate).

It writes to a throwaway copy of the admin (the e2e harness's temp dir), never a real database, and dumps the
client report the dashboard would receive:

    python3 admin/tests/mock_goals.py early out.json     # one doctor live, four coming soon (the real situation)
    python3 admin/tests/mock_goals.py mid out.json       # most live, mixed results, a YouTube add-on post, a hidden-likes post
    python3 admin/tests/mock_goals.py single out.json   # Instagram only, tracked link, TikTok add-on, hidden likes
    python3 admin/tests/mock_goals.py noplan out.json   # no plan, no targets, nobody published
"""
import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402
import apify, db, metrics, plans  # noqa: E402

DOCTORS = [  # code, name, instagram followers, tiktok followers, planned
    ("HV-DR-001", "Dr. Reem Alharbi", 1400000, 900000, 3),
    ("HV-DR-002", "Dr. Faisal Qahtani", 620000, 410000, 2),
    ("HV-DR-003", "Dr. Nouf Alsubaie", 210000, 330000, 2),
    ("HV-DR-004", "Dr. Omar Basahel", 900000, 570000, 2),
    ("HV-DR-005", "Dr. Lama Fadel", 115000, 190000, 2),
]


def day(offset):
    return (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")


def build_other(mode):
    """Other shapes, so nothing in the tab is Jamjoom-specific. single: Instagram only, two creators, tracked link,
    a TikTok add-on post, a creator with no follower count. noplan: no saved plan, no targets, nobody published."""
    base.seed()
    apify.init()
    now = int(time.time())
    cid = db.create_campaign("Single platform", client="Acme", code_id=None, platform="Instagram", codes=["HV-MI-001", "HV-MI-002"])
    db.set_planned(cid, {"HV-MI-001": 2, "HV-MI-002": 1})
    if mode == "single":
        plan = {"platform": "Instagram", "category": "beauty", "template": "engagement", "benchmark": {"view_rate": [9.0, 20.0], "eng_rate": [2.5, 4.5]},
                "estimate": {"safe": {"views": 60000, "engagement": 1500}, "expected": {"views": 140000, "engagement": 5000}}}
        db.save_campaign(cid, status="live", starts_at=now - 5 * 86400, ends_at=now + 25 * 86400, plan=plan, objective="engagement",
                         steps=[{"key": "publishing", "on": True, "start": day(-3), "end": day(14), "state": "active"}],
                         targets={"posts": 3, "views": 60000, "engagement": 1500, "er": 2.5}, destination="https://acme.test")
        for i, (code, pl, v, hide) in enumerate([("HV-MI-001", "Instagram", 31000, False), ("HV-MI-002", "TikTok", 8000, True)]):
            db.add_content(cid, {"code": code, "platform": pl, "kind": "reel" if pl == "Instagram" else "tiktok", "url": "https://x/%d" % i,
                                 "posted_at": now - 2 * 86400, "caption": "ad", "thumb": None, "followers": None, "views": v,
                                 "likes": None if hide else 900, "comments": 40, "shares": 0, "saves": 0})
    else:
        db.save_campaign(cid, status="live", starts_at=now, ends_at=now + 30 * 86400)
    return db.campaign(cid)


def build_gap(mode):
    """gap: goals on Instagram + TikTok (plan keeps by_platform) but nobody has posted on TikTok yet, plus a YouTube bonus post.
    addons: goals on Instagram, only a TikTok post exists."""
    base.seed()
    apify.init()
    now = int(time.time())
    cid = db.create_campaign("Gap", client="Acme", code_id=None, platform="Instagram", codes=["HV-MI-001", "HV-MI-002"])
    db.set_planned(cid, {"HV-MI-001": 2, "HV-MI-002": 2})
    both = mode == "gap"
    plan = {"platform": "Instagram + TikTok" if both else "Instagram", "platforms": ["Instagram", "TikTok"] if both else ["Instagram"],
            "category": "beauty", "benchmark": {"view_rate": [9.0, 20.0], "eng_rate": [2.5, 4.5]},
            "estimate": {"safe": {"views": 90000, "engagement": 2400}, "expected": {"views": 210000, "engagement": 8000}},
            "by_platform": {"Instagram": {"safe": {"views": 50000, "engagement": 1300}, "expected": {"views": 120000, "engagement": 4200}},
                            "TikTok": {"safe": {"views": 40000, "engagement": 1100}, "expected": {"views": 90000, "engagement": 3800}}} if both else
                           {"Instagram": {"safe": {"views": 90000, "engagement": 2400}, "expected": {"views": 210000, "engagement": 8000}}}}
    db.save_campaign(cid, status="live", starts_at=now - 5 * 86400, ends_at=now + 25 * 86400, plan=plan, objective="awareness",
                     steps=[{"key": "publishing", "on": True, "start": day(-3), "end": day(14), "state": "active"}],
                     targets={"posts": 4, "views": 90000, "engagement": 2400})
    posts = [("HV-MI-001", "Instagram", 30000), ("HV-MI-002", "YouTube", 9000)] if both else [("HV-MI-001", "TikTok", 25000), ("HV-MI-002", "YouTube", 9000)]
    for i, (code, pl, v) in enumerate(posts):
        db.add_content(cid, {"code": code, "platform": pl, "kind": {"Instagram": "reel", "TikTok": "tiktok"}.get(pl, "video"), "url": "https://x/%d" % i,
                             "posted_at": now - 2 * 86400, "caption": "ad", "thumb": None, "followers": None, "views": v,
                             "likes": 700, "comments": 30, "shares": 0, "saves": 0})
    return db.campaign(cid)


def build(mode):
    if mode in ("gap", "addons"):
        return build_gap(mode)
    if mode in ("single", "noplan"):
        return build_other(mode)
    base.seed()
    apify.init()
    for code, name, ig, tt, n in DOCTORS:
        db.upsert_creator({"code": code, "name": name, "handle": code.lower(), "platform": "Instagram", "followers": ig,
                           "city": "Riyadh", "nationality": "Saudi Arabia", "tier": "Mid-Tier", "interest": "Health", "photo": None,
                           "profiles": json.dumps([{"platform": "Instagram", "url": "https://i/" + code, "followers": ig},
                                                   {"platform": "TikTok", "url": "https://t/" + code, "followers": tt}]),
                           "active": 1, "note": "", "sort": 0})
    now = int(time.time())
    with db.connect() as conn:              # the live server has the pieces column (feature/video-pieces); this base does not
        if "piece" not in {r["name"] for r in conn.execute("PRAGMA table_info(content)")}:
            conn.execute("ALTER TABLE content ADD COLUMN piece INTEGER")
    cid = db.create_campaign("Jamjoom Wave 1", client="Jamjoom Pharma", code_id=None, platform="Instagram",
                             codes=[d[0] for d in DOCTORS])
    db.set_planned(cid, {d[0]: d[4] for d in DOCTORS})
    lib, cf = plans.library(), plans.CATEGORIES["pharma"][1]
    est = {"safe": {"views": 0.0, "engagement": 0.0}, "expected": {"views": 0.0, "engagement": 0.0}}
    byp = {pl: {"safe": {"views": 0.0, "engagement": 0.0, "er": 0}, "expected": {"views": 0.0, "engagement": 0.0, "er": 0}} for pl in ("Instagram", "TikTok")}
    for code, name, ig, tt, n in DOCTORS:
        for pl, f in (("Instagram", ig), ("TikTok", tt)):
            t = plans.tier_of(f)
            for i, k in enumerate(("safe", "expected")):
                v = f * lib[pl]["view_rate"][t][i] / 100.0 * n
                est[k]["views"] += v
                est[k]["engagement"] += v * lib[pl]["eng_rate"][t][i] * cf / 100.0
                byp[pl][k]["views"] += v
                byp[pl][k]["engagement"] += v * lib[pl]["eng_rate"][t][i] * cf / 100.0
    plan = {"platform": "Instagram + TikTok", "platforms": ["Instagram", "TikTok"], "category": "pharma", "template": "awareness",
            "benchmark": {"view_rate": [6.0, 14.0], "eng_rate": [1.6, 3.0]},
            "estimate": {k: {kk: int(round(vv, -3)) for kk, vv in v.items()} for k, v in est.items()}}
    if "--no-byplatform" not in sys.argv:    # older plans did not keep a per-platform estimate
        plan["by_platform"] = {pl: {k: {"views": int(round(d[k]["views"], -3)), "engagement": int(round(d[k]["engagement"], -2)),
                                        "er": round(d[k]["engagement"] / d[k]["views"] * 100, 2)} for k in d} for pl, d in byp.items()}
    steps = [{"key": "publishing", "on": True, "start": day(0), "end": day(21), "state": "active"}]
    db.save_campaign(cid, status="live", starts_at=now - 17 * 86400, ends_at=now + 43 * 86400, plan=plan, steps=steps,
                     targets=({"posts": 11, "views": sum(v["safe"]["views"] for v in plan["by_platform"].values()),
                              "engagement": sum(v["safe"]["engagement"] for v in plan["by_platform"].values()), "er": 1.31}
                             if plan.get("by_platform") else {"posts": 11, "views": 1082000, "engagement": 14200, "er": 1.31}), objective="awareness",
                     visibility={"clicks": False})
    vid = [0]

    def post(code, pl, views, likes, comments, ago_h, piece, kind="reel", hide=False):
        vid[0] += 1
        item = {"code": code, "platform": pl, "kind": kind if pl != "TikTok" else "tiktok", "url": "https://x/%d" % vid[0],
                "posted_at": now - ago_h * 3600, "caption": "Jamjoom #ad", "thumb": None, "followers": None,
                "views": views, "likes": None if hide else likes, "comments": comments, "shares": 0, "saves": 0}
        content_id, _ = db.add_content(cid, item)
        with db.connect() as conn:
            conn.execute("UPDATE content SET piece = ? WHERE id = ?", (piece, content_id))
    # the first doctor is live on both platforms with one video, today
    post("HV-DR-001", "Instagram", 118000, 6200, 410, 5, "p1")
    post("HV-DR-001", "TikTok", 84000, 4300, 260, 5, "p1")
    pend = {d[0]: day(13) for d in DOCTORS[1:]}          # the placeholder next-video date (31 Oct in the real campaign)
    if mode == "mid":
        post("HV-DR-001", "Instagram", 61000, 2100, 150, 80, "p2")
        post("HV-DR-001", "TikTok", 90000, 5200, 300, 80, "p2")
        post("HV-DR-002", "Instagram", 14000, 380, 22, 60, "p3")
        post("HV-DR-002", "TikTok", 22000, 700, 40, 60, "p3")
        post("HV-DR-003", "Instagram", 41000, 1500, 90, 40, "p4", hide=True)
        post("HV-DR-003", "TikTok", 30000, 1900, 70, 40, "p4")
        post("HV-DR-004", "Instagram", 9000, 210, 11, 20, "p5")
        post("HV-DR-001", "YouTube", 12000, 300, 20, 30, "p6", kind="video")
        pend = {"HV-DR-005": day(13), "HV-DR-002": day(9), "HV-DR-004": day(11)}
    with db.connect() as conn:
        for code, d in pend.items():
            conn.execute("UPDATE campaign_creators SET pending_date = ? WHERE campaign_id = ? AND code = ?", (d, cid, code))
    return db.campaign(cid)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "early"
    try:
        k = build(mode)
        rep = metrics.client_report(k, photo=lambda n: "")
        Path(sys.argv[2] if len(sys.argv) > 2 else "mock-%s.json" % mode).write_text(json.dumps(rep, indent=1))
        print("ok", mode, "goals" in rep and rep["goals"] is not None)
    finally:
        shutil.rmtree(base.TMP, ignore_errors=True)
