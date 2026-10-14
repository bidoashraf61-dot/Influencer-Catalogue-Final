"""A creator's main industry, by hand (Control Centre step 3, item 101).

The 2026-10-13 classification put every creator in one MAIN industry with sub-niches, other industries
they also cover, and a tier: Confirmed, Probable or Review (Review is hidden from industry filters).
Here an admin settles it: from the review queue, the creator form, or the catalogue's quick edit.
A choice made by hand is always Confirmed. Every change goes through History, so it can be undone.
"""
import json
import time

import db

INDUSTRIES = ["Beauty & Personal Care", "Fashion", "Food & Restaurants", "Health & Medical", "Health & Fitness", "Travel & Tourism",
              "Entertainment & Comedy", "Family & Parenting", "Tech & Gadgets", "E-commerce & Shopping", "Sports", "Education",
              "Finance & Business", "Religion & Spirituality", "Music & Art", "Home & Interior", "Automotive", "Gaming", "Pets",
              "General Lifestyle", "Unclassifiable"]
SUBS = {
    "Beauty & Personal Care": ["Makeup", "Skincare", "Hair", "Fragrance", "Bridal & makeup artist", "Nails & lashes", "Men's grooming",
                               "Beauty reviews & hauls"],
    "Fashion": ["Modest fashion", "Luxury fashion", "Everyday styling & outfits", "Fashion hauls & reviews", "Accessories, bags & shoes",
                "Kids & family fashion"],
    "Food & Restaurants": ["Restaurant reviews", "Cafés & coffee", "Home cooking & recipes", "Baking & desserts", "Street food & food tours",
                           "Healthy eating"],
    "Health & Medical": ["Dermatology & aesthetics", "Pharmacy", "Dentistry", "General medicine & health advice", "Nutrition & dietetics",
                         "Mental health", "Mother & child health"],
    "Health & Fitness": ["Gym & bodybuilding", "Personal training & coaching", "Yoga & pilates", "Running & endurance sports",
                         "Nutrition & weight loss", "Wellness"],
    "Travel & Tourism": ["Luxury travel", "Travel vlogs & guides", "Hotels & resorts", "Adventure & outdoors", "Local tourism"],
    "Family & Parenting": ["Mom life", "Baby & kids products", "Family lifestyle", "Education & parenting tips"],
}
TIERS = ["Confirmed", "Probable", "Review"]
COUNTRIES = {"KSA": "Saudi Arabia", "UAE": "UAE", "Egypt": "Egypt"}


def _list(v):
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v or "[]")
        return out if isinstance(out, list) else []
    except ValueError:
        return []


def current(row):
    """The industry fields of a creator row, as plain values."""
    k = row.keys() if hasattr(row, "keys") else row
    get = (lambda n: row[n] if n in k else None)
    return {"industry": get("industry"), "subs": _list(get("sub_niches")), "also": _list(get("also_industries")),
            "tier": get("industry_tier"), "conf": get("industry_conf"), "source": get("industry_source")}


def clean(industry, subs=(), also=(), tier="Confirmed"):
    """Validated values, or ValueError naming the problem."""
    if industry not in INDUSTRIES:
        raise ValueError("Choose a main industry from the list.")
    if tier not in TIERS:
        raise ValueError("Choose Confirmed, Probable or Review.")
    allowed = SUBS.get(industry, [])
    subs = [s for s in dict.fromkeys(subs or []) if s in allowed][:3]
    also = [a for a in dict.fromkeys(also or []) if a in INDUSTRIES and a != industry][:2]
    return industry, subs, also, tier


def write(conn, code, industry, subs, also, tier, actor, was=None):
    """Store the choice on one creator. ``was`` is the earlier row, for the note of what it replaced."""
    before = ""
    if was is not None:
        w = current(was)
        if w["industry"] and (w["industry"] != industry or w["tier"] != tier):
            before = " (was: %s, %s%s)" % (w["industry"], w["tier"] or "no tier", (", %s%% sure" % w["conf"]) if w["conf"] is not None else "")
    note = "Set by %s on %s%s" % (actor or "an admin", time.strftime("%d %b %Y", time.gmtime()), before)
    conn.execute("UPDATE creators SET industry = ?, sub_niches = ?, also_industries = ?, industry_tier = ?, industry_conf = ?, "
                 "industry_source = ?, updated_at = ? WHERE code = ?",
                 (industry, json.dumps(subs, ensure_ascii=False), json.dumps(also, ensure_ascii=False), tier,
                  100 if tier == "Confirmed" else None, note, db.now(), code))


def set_for(code, industry, subs=(), also=(), tier="Confirmed", actor=""):
    """Validate and store, recorded in History so it can be undone. Returns the cleaned values."""
    import history
    industry, subs, also, tier = clean(industry, subs, also, tier)
    with history.tracked("creator", code, "Set industry of " + code):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM creators WHERE code = ?", (code,)).fetchone()
            if row is None:
                raise ValueError("No such creator.")
            write(conn, code, industry, subs, also, tier, actor, row)
    return industry, subs, also, tier


def hide(code, actor=""):
    """"Not a fit for the catalogue": hidden from clients, nothing deleted (undo in History)."""
    import history
    with history.tracked("creator", code, "Hid %s (not a fit)" % code):
        with db.connect() as conn:
            conn.execute("UPDATE creators SET active = 0, industry_source = ?, updated_at = ? WHERE code = ?",
                         ("Hidden by %s on %s: not a fit for the catalogue" % (actor or "an admin", time.strftime("%d %b %Y", time.gmtime())),
                          db.now(), code))


# ------------------------------------------------------------- review queue --

def _where(country):
    sql, args = "active = 1 AND industry_tier = 'Review'", []
    if country in COUNTRIES:
        sql += " AND (nationality = ? OR city LIKE ?)"
        args += [COUNTRIES[country], "%" + COUNTRIES[country] + "%"]
    return sql, args


def queue_counts(country=None):
    sql, args = _where(country)
    with db.connect() as conn:
        left = conn.execute("SELECT COUNT(*) FROM creators WHERE " + sql, args).fetchone()[0]
        done = conn.execute("SELECT COUNT(*) FROM creators WHERE industry_source LIKE 'Set by %' OR industry_source LIKE 'Hidden by %'").fetchone()[0]
    return {"left": left, "done": done}


def next_in_queue(country=None, after=None):
    """The next creator to review, biggest first. ``after`` = "followers:code" of the one skipped."""
    sql, args = _where(country)
    if after and ":" in after:
        f, c = after.split(":", 1)
        try:
            f = int(f)
        except ValueError:
            f = None
        if f is not None:
            sql += " AND (COALESCE(followers, 0) < ? OR (COALESCE(followers, 0) = ? AND code > ?))"
            args += [f, f, c]
    with db.connect() as conn:
        return conn.execute("SELECT * FROM creators WHERE " + sql + " ORDER BY COALESCE(followers, 0) DESC, code LIMIT 1", args).fetchone()


def why_unsure(source):
    s = (source or "").lower()
    if "disagree" in s:
        return "The two AI checks disagreed on the main industry."
    if "first run low" in s:
        return "The AI had little to go on and gave a low-confidence answer."
    if "differ" in s:
        return "The two AI checks picked different industries, each listing the other as a second one."
    return "The AI was not sure enough to show this creator in an industry filter."


def review_card(row, base=""):
    """Everything the review screen shows about one creator: bio and up to four post pictures from the analysis."""
    import analysis
    import links
    cur = current(row)
    bio, posts = "", []
    a = db.analysis(row["code"])
    if a and isinstance(a.get("data"), dict):
        d = analysis.with_media_urls(a["data"], row["code"], base)
        bio = d.get("bio") or d.get("description") or ""          # bio_ai is only a flag (the bio was AI-written)
        for key in ("recent_posts", "top_posts"):
            for p in d.get(key) or []:
                pic = p.get("thumb") or p.get("live")
                if pic and len(posts) < 4:
                    posts.append({"pic": pic, "url": p.get("url")})
    return {"code": row["code"], "name": row["name"], "handle": row["handle"], "platform": row["platform"], "followers": row["followers"],
            "city": row["city"], "nationality": row["nationality"], "photo": links.photo(row["photo"]) if row["photo"] else None,
            "bio": str(bio)[:400], "posts": posts, "ai": cur, "why": why_unsure(cur["source"])}
