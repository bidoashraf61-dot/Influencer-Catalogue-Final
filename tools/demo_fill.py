"""Fill campaign #9 as the client-ready "Demo Campaign" (owner, 2026-10-20). DUMMY DATA ONLY.

Run inside a throwaway python:3.11-alpine container with the admin dir mounted at /data/admin.
Rewrites campaign 9's row, creators' planned/pending, post dates, snapshots, clicks, comments,
comment reads and labels. Never creates api_jobs or 'due' comment reads (no Apify spend).
"""
import sys, json, math, random, hashlib, time, calendar
sys.path.insert(0, "/data/admin")
import db, plans

CID = 9
RNG = random.Random(20261020)
DAY = 86400
NOW = int(time.time())
TODAY0 = NOW - NOW % DAY                                   # UTC midnight today
def utc(y, m, d, h=0, mi=0):
    return calendar.timegm((y, m, d, h, mi, 0))
START = utc(2026, 9, 14)
END = utc(2026, 11, 14, 23, 59) + 59
LAST_POST_DAY = TODAY0 - DAY                               # posts run up to yesterday

_ctx = db.connect()
conn = _ctx.__enter__()

k = conn.execute("SELECT * FROM campaigns WHERE id = ?", (CID,)).fetchone()
assert k is not None and k["selection_id"] == 81, "campaign 9 is not the demo"

# ------------------------------------------------------------------ creators
members = db.campaign_creators(CID)
by_code = {m["cc_code"]: m for m in members}
posts = [dict(r) for r in conn.execute("SELECT * FROM content WHERE campaign_id = ? ORDER BY id", (CID,))]
posted_by = {}
for p in posts:
    posted_by.setdefault(p["code"], []).append(p)

def kind_of(code):
    if code.startswith("HV-HCPC") or code.startswith("HV-MD"):
        return "doctor"
    if code.startswith("HV-HCPI") or code.startswith("HV-MC"):
        return "expert"
    return "influencer"

def foll_on(m, platform):
    for a in db.split_profiles(m["profiles"] or ""):
        if a.get("platform") == platform and a.get("followers"):
            return int(a["followers"])
    return int(m["followers"] or 0)

planned, pending = {}, {}
STATUSES = [("Scheduled", 0.55), ("Editing", 0.25), ("Client review", 0.20)]
def pick_status():
    x, acc = RNG.random(), 0.0
    for s, w in STATUSES:
        acc += w
        if x <= acc:
            return s
    return "Scheduled"
not_posted = [m["cc_code"] for m in members if m["cc_code"] not in posted_by]
RNG.shuffle(not_posted)
coming = set(not_posted[:80])                  # 80 more videos booked for the next three weeks
for m in members:
    c = m["cc_code"]
    have = len(posted_by.get(c, []))
    extra = 0
    if have and kind_of(c) == "doctor" and RNG.random() < 0.5:
        extra = 1                               # doctors open and close: one more video to come
    if c in coming:
        extra = 1
    n = have + extra
    planned[c] = n if n else None
    if extra:
        st = pick_status()
        due = TODAY0 + RNG.randint(1, 23) * DAY
        if st == "Scheduled":
            due = TODAY0 + RNG.randint(1, 9) * DAY
        pending[c] = (st, time.strftime("%Y-%m-%d", time.gmtime(due)))
    else:
        pending[c] = (None, None)
for c in planned:
    conn.execute("UPDATE campaign_creators SET planned = ?, pending_status = ?, pending_date = ? WHERE campaign_id = ? AND code = ?",
                 (planned[c], pending[c][0], pending[c][1], CID, c))

# ------------------------------------------------------------------ post dates (waves)
span_days = (LAST_POST_DAY - utc(2026, 9, 16)) // DAY
def wave_day(kind):
    if kind == "doctor":                         # doctors open the season, then return mid-flight
        return RNG.choice([RNG.randint(0, 6), RNG.randint(14, 22)])
    if kind == "expert":
        return RNG.randint(4, 16)
    return int(min(span_days, max(6, RNG.triangular(6, span_days, span_days * 0.7))))
for p in posts:
    d = wave_day(kind_of(p["code"]))
    p["posted_at"] = utc(2026, 9, 16) + d * DAY + RNG.randint(14, 20) * 3600 + RNG.randint(0, 59) * 60   # 17:00-23:59 Riyadh
    p["posted_at"] = min(p["posted_at"], LAST_POST_DAY + 20 * 3600)
    m = by_code.get(p["code"])
    if m is not None:
        f = foll_on(m, p["platform"])
        if f:
            p["followers"] = f
    conn.execute("UPDATE content SET posted_at = ?, followers = ?, section = 'campaign', hidden = 0 WHERE id = ?",
                 (p["posted_at"], p["followers"], p["id"]))

# ------------------------------------------------------------------ plan + targets (planner formula)
rows = []
for m in members:
    c = m["cc_code"]
    if not planned.get(c):
        continue
    plats = sorted({p["platform"] for p in posted_by.get(c, [])}) or ["TikTok" if foll_on(m, "TikTok") >= foll_on(m, "Instagram") else "Instagram"]
    for pl in plats:
        f = foll_on(m, pl)
        if not f:
            continue
        n = sum(1 for p in posted_by.get(c, []) if p["platform"] == pl) or 0
        if pl == plats[0]:
            n += planned[c] - len(posted_by.get(c, []))
        if n <= 0:
            continue
        rows.append({"platform": pl, "tier": plans.tier_of(f), "posts": n, "followers": f, "name": m["name"] or c, "slot": c + pl})
brief = {"platform": "TikTok", "objective": "awareness+traffic", "category": "beauty", "budget": 165000.0, "tracked_links": True}
plan = plans.calculate_platforms(brief, rows)
keep = {x: plan.get(x) for x in ("platform", "platforms", "objective", "category", "budget", "links", "posts",
                                  "estimate", "floor", "target", "benchmark", "roi", "by_platform")}
keep["brief"] = {"type": "awareness+traffic", "platform": "TikTok + Instagram", "platforms": ["TikTok", "Instagram"],
                 "category": "beauty", "budget": "165000", "source": "campaign", "market": "SA", "gender": "Women",
                 "age": "20-40", "links": "1", "stories": ""}
keep["template"] = None
targets = {kk: plan["target"][kk] for kk in ("posts", "views", "engagement", "er", "clicks") if plan["target"].get(kk)}
# Engagement goal = the safe estimate (consistent with the ER goal), not the budget floor.
for kk in ("views", "engagement", "clicks"):
    if plan["estimate"]["safe"].get(kk):
        targets[kk] = plan["estimate"]["safe"][kk]
keep["agreed"] = targets
keep["saved_at"] = NOW
keep["basis"] = ("Demo brief: Saudi Arabia, women 20-40; TikTok main + Instagram; tracked links on; each video counted on the "
                 "platform it is published on, at the creator's followers there. Library rates by tier, beauty factor 1.0, "
                 "lifted for shares + saves.")

# ------------------------------------------------------------------ per-post results (aggressive)
viral = set(RNG.sample([p["id"] for p in posts if kind_of(p["code"]) != "doctor"], 4)) | \
        set(RNG.sample([p["id"] for p in posts if kind_of(p["code"]) == "doctor"], 1))
TIER_VR = {"nano": (0.9, 2.6), "micro": (0.45, 1.5), "mid": (0.25, 0.85), "macro": (0.14, 0.5), "mega": (0.08, 0.3)}
for p in posts:
    f = p["followers"] or 20000
    lo, hi = TIER_VR.get(plans.tier_of(f), (0.3, 1.0))
    vr = RNG.uniform(lo, hi) * (RNG.uniform(4.0, 7.5) if p["id"] in viral else 1.0)
    if p["platform"] == "Instagram":
        vr *= 0.8
    p["w_views"] = f * vr
    kd = kind_of(p["code"])
    p["r_likes"] = RNG.uniform(0.045, 0.075) if kd == "doctor" else RNG.uniform(0.035, 0.06)
    p["r_comments"] = RNG.uniform(0.008, 0.014) if kd == "doctor" else RNG.uniform(0.003, 0.008)
    p["r_shares"] = RNG.uniform(0.004, 0.009)
    p["r_saves"] = RNG.uniform(0.007, 0.014) if kd == "doctor" else RNG.uniform(0.005, 0.011)

goal_views = targets.get("views") or 6_000_000
goal_eng = targets.get("engagement") or 400_000
want_views = goal_views * 1.18                  # already past the full-campaign view goal at ~60% of the flight
sv = sum(p["w_views"] for p in posts)
for p in posts:
    p["views"] = int(p["w_views"] * want_views / sv)
eng = sum(p["views"] * (p["r_likes"] + p["r_comments"] + p["r_shares"] + p["r_saves"]) for p in posts)
want_eng = want_views * (targets.get("er") or 4.0) / 100.0 * 1.75   # ER ~1.75x the goal
scale = want_eng / eng if eng else 1.0
for p in posts:
    for a in ("likes", "comments", "shares", "saves"):
        p[a] = int(p["views"] * p["r_" + a] * scale)

# ------------------------------------------------------------------ snapshots (daily, growth curve)
ids = [p["id"] for p in posts]
conn.execute("DELETE FROM snapshots WHERE content_id IN (%s)" % ",".join("?" * len(ids)), ids)
snap_at = TODAY0 + 6 * 3600 if NOW >= TODAY0 + 6 * 3600 else TODAY0 - DAY + 6 * 3600
latest_at = 0
for p in posts:
    d0 = p["posted_at"] - p["posted_at"] % DAY + DAY
    days = []
    t = d0 + 6 * 3600
    while t <= snap_at:
        days.append(t)
        t += DAY
    if not days:
        days = [snap_at]
    def frac(at):
        age = max(0.15, (at - p["posted_at"]) / DAY)
        return 1 - 0.92 * math.exp(-age / 1.9)
    fin = frac(days[-1])
    for at in days:
        g = frac(at) / fin
        conn.execute("INSERT INTO snapshots (content_id, at, likes, comments, views, shares, saves, source) VALUES (?,?,?,?,?,?,?,'capture')",
                     (p["id"], at, int(p["likes"] * g), int(p["comments"] * g), int(p["views"] * g),
                      int(p["shares"] * g), int(p["saves"] * g)))
        latest_at = max(latest_at, at)

# ------------------------------------------------------------------ clicks (tracked links)
conn.execute("DELETE FROM clicks WHERE campaign_id = ?", (CID,))
slugs = {r["code"]: r["slug"] for r in conn.execute("SELECT code, slug FROM links WHERE campaign_id = ? AND active = 1 AND is_default = 1", (CID,))}
total_views = sum(p["views"] for p in posts)
want_clicks = int(max((targets.get("clicks") or 0) * 2.1, total_views * 0.0036))
APPS = [("tiktok", 0.55), ("instagram", 0.33), ("browser", 0.08), ("snapchat", 0.04)]
REF = {"tiktok": "https://www.tiktok.com/", "instagram": "https://l.instagram.com/", "browser": None, "snapchat": "https://www.snapchat.com/"}
COUNTRIES = [("SA", 0.78), ("AE", 0.07), ("KW", 0.05), ("EG", 0.03), ("QA", 0.025), ("BH", 0.02), ("OM", 0.015), ("JO", 0.01)]
def pick(opts):
    x, acc = RNG.random(), 0.0
    for v, w in opts:
        acc += w
        if x <= acc:
            return v
    return opts[0][0]
visitors = []
batch = []
for p in posts:
    slug = slugs.get(p["code"])
    if not slug:
        continue
    n = int(want_clicks * p["views"] / float(total_views) * RNG.uniform(0.75, 1.25))
    for _ in range(n):
        at = p["posted_at"] + int(RNG.expovariate(1 / (1.4 * DAY)))
        if at > NOW - 1800:
            at = NOW - RNG.randint(1800, 86400)
        if at < p["posted_at"]:
            at = p["posted_at"] + RNG.randint(60, 3600)
        if visitors and RNG.random() < 0.14:
            v = RNG.choice(visitors[-400:])
        else:
            v = hashlib.sha1(("demo%d%f" % (p["id"], RNG.random())).encode()).hexdigest()[:16]
            visitors.append(v)
        app = pick(APPS) if p["platform"] == "TikTok" else pick([("instagram", 0.82), ("browser", 0.12), ("tiktok", 0.04), ("snapchat", 0.02)])
        dev = pick([("mobile", 0.94), ("desktop", 0.04), ("tablet", 0.02)])
        os_ = pick([("iOS", 0.63), ("Android", 0.37)]) if dev != "desktop" else pick([("Windows", 0.6), ("macOS", 0.4)])
        batch.append((slug, CID, p["code"], at, v, app, dev, os_, pick(COUNTRIES), REF[app], 1 if RNG.random() < 0.02 else 0))
conn.executemany("INSERT INTO clicks (slug, campaign_id, code, at, visitor, app, device, os, country, referrer, bot) VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)

# ------------------------------------------------------------------ comments ("What people say")
import comments as _cm
_cm.init()
LABELS = {
    "Results & glow": "النتائج والنضارة",
    "Dark spots & pigmentation": "البقع والتصبغات",
    "Routine & how to use": "الروتين وطريقة الاستخدام",
    "Availability & purchasing": "توفر المنتج وإمكانية الشراء",
    "Price inquiry": "الاستفسار عن الأسعار",
    "Sensitive skin & safety": "البشرة الحساسة والأمان",
    "Sun protection pairing": "الدمج مع واقي الشمس",
    "Praise and appreciation": "عبارات الشكر والتقدير",
}
# (text, gloss, sentiment, intent, ask, ask_en, theme, flag, weight)
BANK = [
    ("والله فرق معي من أسبوعين بشرتي صارت تلمع", "Honestly it made a difference in two weeks, my skin is glowing", "positive", 0, None, None, "Results & glow", None, 9),
    ("جربته وصار وجهي منور الصبح 😍", "Tried it and my face looks bright in the morning", "positive", 0, None, None, "Results & glow", None, 9),
    ("أحلى سيروم فيتامين سي جربته بصراحة", "Honestly the best vitamin C serum I've tried", "positive", 0, None, None, "Results & glow", None, 8),
    ("النتيجة واضحة في الفيديو ما شاء الله", "The result is clear in the video, mashallah", "positive", 0, None, None, "Results & glow", None, 6),
    ("ريحته خفيفة وما يخلي البشرة دهنية 👌", "Light scent and it doesn't make skin oily", "positive", 0, None, None, "Results & glow", None, 5),
    ("This serum is actually amazing, my skin looks so fresh", "This serum is actually amazing, my skin looks so fresh", "positive", 0, None, None, "Results & glow", None, 3),
    ("البقع اللي عندي من الحبوب خفت كثير", "My acne marks have faded a lot", "positive", 0, None, None, "Dark spots & pigmentation", None, 7),
    ("يشيل التصبغات اللي حول الفم؟", "Does it remove pigmentation around the mouth?", "neutral", 1, "يفيد للتصبغات؟", "Does it help pigmentation?", "Dark spots & pigmentation", None, 6),
    ("عندي كلف خفيف هل ينفع معه؟", "I have mild melasma, does it work for it?", "neutral", 1, "يفيد للتصبغات؟", "Does it help pigmentation?", "Dark spots & pigmentation", None, 5),
    ("الهالات السوداء خفت بعد ما استخدمت الكريم حق العين", "Dark circles faded after using the eye cream", "positive", 0, None, None, "Dark spots & pigmentation", None, 4),
    ("يستخدم الصبح ولا بالليل؟", "Morning or night?", "neutral", 1, "أستخدمه الصبح ولا الليل؟", "Morning or night?", "Routine & how to use", None, 8),
    ("كم نقطة أحط؟ وقبل المرطب ولا بعده؟", "How many drops, before or after moisturiser?", "neutral", 1, "طريقة الاستخدام؟", "How do I use it?", "Routine & how to use", None, 6),
    ("ينفع مع الريتينول؟", "Can I use it with retinol?", "neutral", 1, "طريقة الاستخدام؟", "How do I use it?", "Routine & how to use", None, 5),
    ("حطيته في روتيني الصباحي وصار أساسي 🙌", "I added it to my morning routine and it's now essential", "positive", 0, None, None, "Routine & how to use", None, 5),
    ("دكتورة شرحك واضح جداً شكراً", "Doctor, your explanation is very clear, thank you", "positive", 0, None, None, "Routine & how to use", None, 6),
    ("وين ألقاه؟", "Where can I find it?", "neutral", 1, "وين ألقاه؟", "Where can I find it?", "Availability & purchasing", None, 10),
    ("متوفر في النهدي؟", "Is it available at Nahdi?", "neutral", 1, "متوفر في الصيدليات؟", "Is it in pharmacies?", "Availability & purchasing", None, 8),
    ("موجود في الدواء؟", "Is it at Al-Dawaa?", "neutral", 1, "متوفر في الصيدليات؟", "Is it in pharmacies?", "Availability & purchasing", None, 5),
    ("حطي الرابط الله يعافيك", "Please share the link", "positive", 1, "فيه رابط؟", "Is there a link?", "Availability & purchasing", None, 7),
    ("طلبته من الرابط ووصلني ثاني يوم 😍", "Ordered from the link and it arrived the next day", "positive", 1, "فيه رابط؟", "Is there a link?", "Availability & purchasing", None, 5),
    ("يتوفر في الإمارات؟", "Is it available in the UAE?", "neutral", 1, "يوصل خارج السعودية؟", "Does it ship outside KSA?", "Availability & purchasing", None, 3),
    ("يوصل الكويت؟", "Does it ship to Kuwait?", "neutral", 1, "يوصل خارج السعودية؟", "Does it ship outside KSA?", "Availability & purchasing", None, 2),
    ("كم سعره؟", "How much is it?", "neutral", 1, "كم سعره؟", "How much is it?", "Price inquiry", None, 9),
    ("فيه عرض أو كود خصم؟", "Is there an offer or discount code?", "neutral", 1, "فيه كود خصم؟", "Is there a discount code?", "Price inquiry", None, 6),
    ("السعر مناسب مقارنة بالماركات الثانية", "The price is fair compared to other brands", "positive", 0, None, None, "Price inquiry", None, 4),
    ("سعره غالي شوي بس يستاهل", "A bit pricey but worth it", "neutral", 0, None, None, "Price inquiry", None, 3),
    ("غالي بالنسبة للكمية", "Expensive for the amount", "negative", 0, None, None, "Price inquiry", None, 2),
    ("هل يناسب البشرة الحساسة؟", "Is it suitable for sensitive skin?", "neutral", 1, "يناسب البشرة الحساسة؟", "Is it OK for sensitive skin?", "Sensitive skin & safety", None, 8),
    ("بشرتي حساسة جداً وما سبب لي أي احمرار", "My skin is very sensitive and it caused no redness", "positive", 0, None, None, "Sensitive skin & safety", None, 4),
    ("حسيت بحرقان خفيف أول يومين", "I felt slight stinging for the first two days", "negative", 0, None, None, "Sensitive skin & safety", "side_effect", 1),
    ("ينفع للحامل؟", "Is it OK during pregnancy?", "neutral", 1, "يناسب الحامل؟", "Is it OK in pregnancy?", "Sensitive skin & safety", "regulatory", 1),
    ("لازم واقي شمس معه؟", "Do I need sunscreen with it?", "neutral", 1, "أحتاج واقي شمس معه؟", "Do I need sunscreen with it?", "Sun protection pairing", None, 5),
    ("الواقي SPF30 حقهم خفيف وما يبيّض", "Their SPF30 is light and leaves no white cast", "positive", 0, None, None, "Sun protection pairing", None, 4),
    ("فيتامين سي مع الواقي أحسن كومبو للصيف ☀️", "Vitamin C plus sunscreen is the best summer combo", "positive", 0, None, None, "Sun protection pairing", None, 3),
    ("أحبك يا دكتورة محتواك مفيد دايماً ❤️", "Love you doctor, your content is always useful", "positive", 0, None, None, "Praise and appreciation", None, 7),
    ("أخيراً أحد يشرح فيتامين سي صح", "Finally someone explains vitamin C properly", "positive", 0, None, None, "Praise and appreciation", None, 5),
    ("بشرتك تجنن ما شاء الله 😍😍", "Your skin is gorgeous, mashallah", "positive", 0, None, None, "Praise and appreciation", None, 6),
    ("صرت أثق بالمنتجات اللي تنصحين فيها", "I trust the products you recommend", "positive", 0, None, None, "Praise and appreciation", None, 4),
    ("فيتامين سي يشيل الكلف نهائياً من أول أسبوع", "Vitamin C removes melasma completely in the first week", "neutral", 0, None, None, "Dark spots & pigmentation", "misinformation", 1),
    ("طلبته من أسبوع وما وصل", "Ordered a week ago and it hasn't arrived", "negative", 0, None, None, "Availability & purchasing", "complaint", 1),
    ("ما شفت فرق بصراحة", "Honestly I didn't see a difference", "negative", 0, None, None, "Results & glow", None, 2),
    ("كل المشاهير صاروا يعلنون عنه 😂", "All the influencers are advertising it now", "neutral", 0, None, None, "Praise and appreciation", None, 2),
]
BANK += [
    ("شكله رهيب 😍 وين ألقاه؟", "Looks amazing, where can I find it?", "positive", 1, "وين ألقاه؟", "Where can I find it?", "Availability & purchasing", None, 8),
    ("جربته من توصيتك وعجبني، فيه حجم أكبر؟", "Tried it on your recommendation and loved it, is there a bigger size?", "positive", 1, "فيه حجم أكبر؟", "Is there a bigger size?", "Availability & purchasing", None, 4),
    ("أبي أجربه بعد هالنتيجة، كم سعره؟", "I want to try it after this result, how much is it?", "positive", 1, "كم سعره؟", "How much is it?", "Price inquiry", None, 6),
    ("بشرتي صارت أنعم بكثير، أحطه قبل المرطب؟", "My skin is much smoother, do I apply it before moisturiser?", "positive", 1, "طريقة الاستخدام؟", "How do I use it?", "Routine & how to use", None, 5),
    ("متحمسة أجربه للبقع، ينفع للبشرة الحساسة؟", "Excited to try it for spots, is it OK for sensitive skin?", "positive", 1, "يناسب البشرة الحساسة؟", "Is it OK for sensitive skin?", "Sensitive skin & safety", None, 4),
]
BANK = [b[:8] + ((b[8] * 1.7 if b[2] == "positive" else b[8]),) for b in BANK]
EMO = ["", "", "", " 😍", " 🔥", " ❤️", " 👏", " ✨", " 🙏"]
W = [b[8] for b in BANK]
conn.execute("DELETE FROM comments WHERE campaign_id = ?", (CID,))
conn.execute("DELETE FROM comment_reads WHERE campaign_id = ?", (CID,))
for lab, ar in LABELS.items():
    conn.execute("INSERT INTO comment_labels (label, ar) VALUES (?, ?) ON CONFLICT(label) DO UPDATE SET ar = COALESCE(comment_labels.ar, excluded.ar)", (lab, ar))
quotes_left = 6
crow = []
for p in posts:
    n = max(14, min(140, int(p["comments"] * RNG.uniform(0.18, 0.3))))
    for i in range(n):
        b = RNG.choices(BANK, weights=W)[0]
        text = b[0] + (RNG.choice(EMO) if not b[7] else "")
        at = p["posted_at"] + int(min(7 * DAY, RNG.expovariate(1 / (0.9 * DAY))))
        at = min(at, NOW - 600)
        likes = int(RNG.paretovariate(1.6)) - 1
        if b[2] == "positive" and RNG.random() < 0.03:
            likes += RNG.randint(80, 900)
        read_at = p["posted_at"] + (2 * DAY if at < p["posted_at"] + 2 * DAY else 7 * DAY)
        crow.append([p["id"], CID, p["code"], p["platform"], "demo-%d-%d" % (p["id"], i), text, at, likes, min(read_at, NOW),
                     b[2], b[3], b[4], b[5], b[6], b[7], b[1], 0, 1 if b[7] else 0])
crow.sort(key=lambda r: -r[7])
seen_text = set()
for r in crow:
    if quotes_left and r[9] == "positive" and not r[14] and r[5] not in seen_text and len(r[5]) > 18:
        r[16] = 1; quotes_left -= 1; seen_text.add(r[5])
conn.executemany("INSERT INTO comments (content_id, campaign_id, code, platform, ext_id, text, posted_at, likes, read_at, sentiment, intent, "
                 "ask, ask_en, theme, flag, gloss, quote, flag_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", crow)
found = {}
for r in crow:
    found[r[0]] = found.get(r[0], 0) + 1
for p in posts:
    for no, d in ((1, 2), (2, 7)):
        due = p["posted_at"] + d * DAY
        if due <= NOW:
            conn.execute("INSERT INTO comment_reads (content_id, campaign_id, platform, read_no, due_at, status, found, message, started_at, finished_at) "
                         "VALUES (?,?,?,?,?,'done',?,?,?,?)", (p["id"], CID, p["platform"], no, due,
                         found.get(p["id"], 0) // (2 if no == 1 else 1), "demo data", due, due + 900))
        else:
            conn.execute("INSERT INTO comment_reads (content_id, campaign_id, platform, read_no, due_at, status, message) "
                         "VALUES (?,?,?,?,?,'skipped','demo data: no live read')", (p["id"], CID, p["platform"], no, due))

# ------------------------------------------------------------------ the campaign itself
steps = [
    {"key": "brief", "label": "Briefing & strategy", "on": True, "start": "2026-08-17", "end": "2026-08-21", "state": "done"},
    {"key": "sourcing", "label": "Sourcing & casting", "on": True, "start": "2026-08-22", "end": "2026-09-02", "state": "done"},
    {"key": "approval", "label": "Client approval", "on": True, "start": "2026-09-03", "end": "2026-09-07", "state": "done"},
    {"key": "logistics", "label": "Logistics & product delivery", "on": True, "start": "2026-09-04", "end": "2026-09-12", "state": "done"},
    {"key": "prep", "label": "Content preparation", "on": True, "start": "2026-09-06", "end": "2026-09-13", "state": "done"},
    {"key": "shooting", "label": "Shooting", "on": True, "start": "2026-09-08", "end": "2026-10-18", "state": "done"},
    {"key": "review", "label": "Content review", "on": True, "start": "2026-09-10", "end": "2026-10-19", "state": "done"},
    {"key": "publishing", "label": "Publishing", "on": True, "start": "2026-09-16", "end": "2026-11-12", "state": "active"},
    {"key": "reporting", "label": "Reporting", "on": True, "start": "2026-11-13", "end": "2026-11-20", "state": "pending"},
]
n_live = len(posts)
n_next = sum(1 for c in pending if pending[c][0])
note = ("Publishing is in full swing: %d videos are live on TikTok and Instagram and the view goal is already passed. "
        "%d more videos are edited, in client review or scheduled for the next three weeks." % (n_live, n_next))
notes_internal = ("DEMO CAMPAIGN — dummy data for client demos (owner, 2026-10-20). Pinned on every BlueHolding / HelloVoice "
                  "account (setting pinned_campaigns). Keep '(demo)' in the client name: comments.py skips sample campaigns by it. "
                  "Refill with demo_fill.py.\n\n" + (k["notes"] or "").split("\n\n", 1)[-1])
conn.execute("UPDATE campaigns SET name = ?, client = ?, platform = NULL, starts_at = ?, ends_at = ?, status = 'live', phase = 'publishing', "
             "status_note = ?, objective = 'awareness+traffic', destination = ?, visibility = ?, logos = ?, steps = ?, targets = ?, plan = ?, "
             "notes = ?, overrides = NULL, updated_at = ? WHERE id = ?",
             ("Demo Campaign", "Alpha Plus (demo)", START, END, note, "https://hellovoice.co.uk/",
              json.dumps({"reach": False, "clicks": True, "all_content": False, "emv": False, "audience": True}),
              json.dumps(["upload/demo-alpha-plus.png"]), json.dumps(steps), json.dumps(targets), json.dumps(keep),
              notes_internal, NOW, CID))
conn.execute("UPDATE selections SET name = ? WHERE id = 81", ("Demo Campaign — Alpha Plus (demo)",))
conn.execute("INSERT INTO settings (key, value) VALUES ('pinned_campaigns', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (json.dumps([CID]),))
conn.commit()
print(json.dumps({"posts": n_live, "planned": sum(v or 0 for v in planned.values()), "coming": n_next,
                  "targets": targets, "views": total_views, "engagement": sum(p["likes"] + p["comments"] + p["shares"] + p["saves"] for p in posts),
                  "clicks": len(batch), "comments": len(crow), "viral": sorted(viral), "plan_posts": plan.get("posts")}, indent=1))
