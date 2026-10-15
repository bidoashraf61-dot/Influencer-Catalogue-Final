"""The full-analysis template: every section of a creator analysis filled with dummy data (owner, 2026-10-15).

General rule: every profile-analysis page carries a button that previews the FULL analysis, even when the
creator's own data is not there yet. The preview is invented from start to finish: no figure, name, picture
or link is read from any creator, so it can be shown to anyone signed in. It fills every field the creator
page draws (overview, reels, stories, audience quality, audience by followers and by likers, growth, popular,
sponsored and recent posts, brands, hashtags, interests, languages), for Instagram and TikTok, with the dummy
pictures in assets/sample/ (a profile photo and a cover on every post, none of them anyone's) and our client logos
from assets/clients/ as the brand marks.
"""
import time

import gating
import metrics

LABEL = "Sample data · not a real creator"
# Brand marks for the sample (owner, 2026-10-15): our own client logos from assets/clients/, so brand affinity,
# brands worked with and the sponsored-post badges show real marks. The pairings are invented.
BRANDS = [("cerave", "CeraVe"), ("la-roche-posay", "La Roche-Posay"), ("vichy", "Vichy"), ("svr", "SVR"),
          ("uriage", "Uriage"), ("filorga", "Filorga"), ("skinceuticals", "SkinCeuticals"), ("ivatherm", "Ivatherm"),
          ("bayer", "Bayer"), ("nahdi", "Nahdi"), ("qv-face", "QV Face"), ("abbott", "Abbott")]
PLATFORMS = ("Instagram", "TikTok")


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def analysis(platform):
    """One platform's complete dummy analysis, the same every time."""
    a = gating.sample("TEMPLATE-FULL", platform)["analysis"]
    f, likes, views, comments = a["followers"], a["avg_likes"], a["avg_views"], a["avg_comments"]
    a.update({
        "template": True, "updated": _today(), "likes_hidden": False,
        "following": 812, "posts_count": 486, "posts_per_week": 3.4, "last_post": _today(), "sample_posts": 30,
        "credibility_pct": 84.6, "real_people_pct": 71.3, "mass_followers_pct": 6.8, "suspicious_mass_pct": 4.1,
        "suspicious_pct": 17.8, "notable_followers_pct": 2.4,
        "er_note": "Above the typical rate for creators of this size.",
        "reels_er_note": "Reels earn more engagement than this creator's photos.",
        "bio": "Skincare and wellness creator sharing honest routines, product tests and clinic visits. Sample text.",
        "bio_ai": True, "location": "Riyadh, Saudi Arabia",
        "content_languages": ["Arabic", "English"],
    })
    for kind, n in (("top_posts", 8), ("sponsored_posts", 6)):
        base = a.get(kind) or []
        while len(base) < n:                                     # more posts than the locked sample draws
            q = dict(base[len(base) % len(base)]) if base else {"url": "#", "likes": likes, "comments": comments, "views": views}
            if kind == "sponsored_posts":
                q["brand"] = "Brand %s" % "ABCDEF"[len(base) % 6]
            base.append(q)
        a[kind] = base[:n]
    a["recent_posts"] = [{"url": "#", "date": _today(), "likes": int(likes * (0.8 + i * 0.1)), "comments": int(comments * (0.9 + i * 0.05)),
                          "views": int(views * (0.7 + i * 0.15))} for i in range(6)]
    for kind in ("top_posts", "sponsored_posts", "recent_posts"):
        for i, p in enumerate(a[kind]):
            p["url"] = "#"
            p["thumb"] = "/assets/sample/post-%d.jpg" % ((i + (3 if kind == "recent_posts" else 0)) % 8 + 1)
            if f and p.get("likes") is not None:
                p["er"] = round((p["likes"] + (p.get("comments") or 0)) * 100.0 / f, 2)
    a["brands"] = [{"name": name, "count": 9 - i * 2 // 3, "logo": "/assets/clients/%s@2x.webp" % slug, "logo_w": 128}
                   for i, (slug, name) in enumerate(BRANDS)]
    for i, p in enumerate(a["sponsored_posts"]):
        p["brand"] = BRANDS[i % len(BRANDS)][1]
    for aud in (a["audience"], a["audience_likers"]):
        aud["brand_affinity"] = [{"name": BRANDS[(i + 4) % len(BRANDS)][1], "pct": r["pct"]}
                                 for i, r in enumerate(aud.get("brand_affinity") or [])]
    a["photo_url"] = "/assets/sample/profile.jpg"
    return a


def payload():
    """The creator page's data, the same shape as /api/creator, for the template creator."""
    analyses = {p: analysis(p) for p in PLATFORMS}
    followers = sum(x["followers"] for x in analyses.values())
    card = {"code": "SAMPLE", "name": "Sample creator", "tier": "Macro", "city": "Riyadh", "nationality": None,
            "interest": "Beauty & Wellness", "followers": followers, "photo_url": "/assets/sample/profile.jpg",
            "profiles": [{"platform": p, "url": None, "followers": analyses[p]["followers"]} for p in PLATFORMS],
            "band": metrics.band_of(followers)}
    return {"ok": True, "sample": True, "template": True, "label": LABEL, "creator": card, "platforms": list(PLATFORMS),
            "analyses": analyses, "requested": [], "gate": {"state": "unlocked", "sample": True},
            "benchmarks": metrics.benchmarks()}
