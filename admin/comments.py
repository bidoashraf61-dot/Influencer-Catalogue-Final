"""What people said (owner, 2026-10-19): the comments under each campaign video, fetched through Apify
twice per video (2 and 7 days after it is posted, up to 300 per post) and read by Gemini for mood,
buying questions, themes and red flags. Replaces the "Creators' audience countries" card on the client's
campaign dashboard. Brief: Portal Programme/BRIEF-comment-insights-2026-10-19.md (item 152).

Privacy: only the comment's text, date, like count and platform id are kept, never who wrote it. Apify's
copy of each run's dataset is deleted as soon as it is read. The client sees totals and the quotes a team
member approved, and since 2026-10-19 (owner's choice) every comment in a browser, red-flagged ones included.
Red flags (complaints, side-effect claims, misinformation, regulatory wording) are listed in the admin and
emailed to the campaign's account manager so the team can act before the client asks.

Cost: every run is written to api_runs, so it counts against the Apify budget in Settings like any other
job; Gemini calls are audited in ai_audit (kind "comments"). Instagram and TikTok re-fetch the whole
thread on the second read (no date filter), deduplicated here by the comment's id; Facebook's second
read asks only for comments newer than the first.

    docker exec influencer-catalogue-admin python /app/admin/comments.py [tick]   # one pass now
"""
import json
import re
import sys
import threading
import time
import urllib.parse

import db

READ_DAYS = (2, 7)
MAX_PER_POST = 300
FRESH_DAYS = 30              # posts older than this when first seen are not read
INTERVAL = 900
BATCH = 60                   # comments per Gemini call
MIN_SAMPLE = 30              # under this the client sees counts, not percentages
MAX_QUOTES = 6
WEEKLY_KEY = "comments_weekly"   # setting {campaign id: "YYYY-MM-DD"}: re-read every video weekly until that day

# platform: (actor, USD per comment at the account's tier, input builder)
ACTORS = {
    "Instagram": ("apify~instagram-comment-scraper", 0.0026,
                  lambda urls, n, since: {"directUrls": urls, "resultsLimit": n}),
    "TikTok": ("clockworks~tiktok-comments-scraper", 0.00125,
               lambda urls, n, since: {"postURLs": urls, "commentsPerPost": n, "maxRepliesPerComment": 0}),
    "Facebook": ("apify~facebook-comments-scraper", 0.0025,
                 lambda urls, n, since: dict({"startUrls": [{"url": x} for x in urls], "resultsLimit": n},
                                             **({"onlyCommentsNewerThan": since} if since else {}))),
    "YouTube": ("streamers~youtube-comments-scraper", 0.002,
                lambda urls, n, since: {"startUrls": [{"url": x} for x in urls], "maxComments": n}),
}
FLAGS = {"complaint": "Complaint", "side_effect": "Side-effect claim", "misinformation": "Misinformation",
         "regulatory": "Regulatory risk", "abuse": "Abuse"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS comment_reads (
  id          INTEGER PRIMARY KEY,
  content_id  INTEGER NOT NULL,
  campaign_id INTEGER NOT NULL,
  platform    TEXT NOT NULL,
  read_no     INTEGER NOT NULL,                 -- 1 = day 2, 2 = day 7
  due_at      INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'due',      -- due | running | done | failed | skipped
  apify_run   TEXT,
  run_row     INTEGER,                          -- api_runs.id (the cost is counted there)
  found       INTEGER NOT NULL DEFAULT 0,
  message     TEXT,
  started_at  INTEGER,
  finished_at INTEGER,
  UNIQUE (content_id, read_no)
);
CREATE INDEX IF NOT EXISTS comment_reads_due ON comment_reads(status, due_at);
CREATE TABLE IF NOT EXISTS comments (
  id          INTEGER PRIMARY KEY,
  content_id  INTEGER NOT NULL,
  campaign_id INTEGER NOT NULL,
  code        TEXT,
  platform    TEXT NOT NULL,
  ext_id      TEXT NOT NULL,
  text        TEXT NOT NULL,
  posted_at   INTEGER,
  likes       INTEGER,
  read_at     INTEGER NOT NULL,
  sentiment   TEXT,                             -- positive | neutral | negative (NULL = not read by AI yet)
  intent      INTEGER,                          -- 1 = asks how / where to buy, the price, availability
  ask         TEXT,                             -- the buying question in a short shared wording
  ask_en      TEXT,
  theme       TEXT,
  flag        TEXT,                             -- FLAGS key, or NULL
  gloss       TEXT,                             -- short English meaning
  quote       INTEGER NOT NULL DEFAULT 0,       -- 1 = approved by the team to show the client
  flag_seen   INTEGER NOT NULL DEFAULT 0,
  UNIQUE (content_id, ext_id)
);
CREATE INDEX IF NOT EXISTS comments_campaign ON comments(campaign_id, sentiment);
CREATE TABLE IF NOT EXISTS comment_labels (
  label TEXT PRIMARY KEY,                       -- a theme label as the AI wrote it (English)
  ar    TEXT                                    -- its Arabic title, shown under the English on the client's page
);
"""

_ready = False
_lock = threading.Lock()


def init():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        conn.executescript(SCHEMA)
    _ready = True


# ------------------------------------------------------------------------------ matching --

def post_key(platform, url):
    """What identifies a post inside any URL Apify hands back for it."""
    u = (url or "").strip()
    pats = {"Instagram": r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,})", "TikTok": r"/video/(\d{8,})",
            "YouTube": r"(?:shorts/|[?&]v=|youtu\.be/|/live/)([A-Za-z0-9_-]{6,})"}
    m = re.search(pats[platform], u) if platform in pats else None
    if m:
        return m.group(1)
    return re.sub(r"^https?://(www\.|m\.)?", "", u.lower()).split("#")[0].rstrip("/")


_URL_FIELDS = ("postUrl", "inputUrl", "videoWebUrl", "submittedVideoUrl", "pageUrl", "facebookUrl", "url", "videoUrl")


def _item_keys(platform, item):
    out = set()
    for f in _URL_FIELDS:
        v = item.get(f)
        if isinstance(v, str) and v:
            out.add(post_key(platform, v))
    return out


def _when(item):
    for f in ("timestamp", "createTimeISO", "date", "publishedAt", "postedAt"):
        v = item.get(f)
        if isinstance(v, str) and len(v) >= 10:
            try:
                return int(time.mktime(time.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone)
            except ValueError:
                pass
    v = item.get("createTime")
    return int(v) if isinstance(v, (int, float)) and v > 1e9 else None


def _parse(item):
    """(ext_id, text, posted_at, likes) or None. The commenter is never read."""
    if not isinstance(item, dict) or item.get("error"):
        return None
    ext = item.get("id") or item.get("cid") or item.get("commentId")
    text = item.get("text") if isinstance(item.get("text"), str) else item.get("comment")
    if not ext or not isinstance(text, str) or not text.strip():
        return None
    likes = next((item.get(f) for f in ("likesCount", "diggCount", "voteCount", "likes") if isinstance(item.get(f), int)), None)
    return str(ext)[:120], text.strip()[:1000], _when(item), likes


# ---------------------------------------------------------------------------- scheduling --

def _is_sample(k):
    text = ("%s %s" % (k["name"] or "", k["client"] or "")).lower()
    return text.startswith("sample") or "(demo)" in text or "dummy data" in text


def weekly_until(now=None):
    """{campaign id: last day as epoch} for the campaigns whose comments are re-read every week (owner, 2026-10-19:
    Ivatherm #10 until 30 Nov). Their videos are read however old they were when first seen."""
    now = now or db.now()
    out = {}
    for k, day in (db.setting(WEEKLY_KEY) or {}).items():
        try:
            end = time.mktime(time.strptime(str(day), "%Y-%m-%d")) + 86399
        except ValueError:
            continue
        if end >= now:
            out[int(k)] = end
    return out


def weekly_rereads(now=None):
    """Every video of a weekly campaign whose last read finished 7+ days ago is read again (comments are kept by
    their id, so a re-read adds only the new ones). The video's latest read row is the one sent again."""
    init()
    now = now or db.now()
    n = 0
    with db.connect() as conn:
        for cid in weekly_until(now):
            cur = conn.execute(
                "UPDATE comment_reads SET status = 'due', due_at = ?, message = NULL WHERE id IN ("
                "SELECT MAX(id) FROM comment_reads WHERE campaign_id = ? AND status = 'done' GROUP BY content_id) "
                "AND finished_at < ? AND content_id NOT IN "
                "(SELECT content_id FROM comment_reads WHERE campaign_id = ? AND status IN ('due','running'))",
                (now, cid, now - 7 * 86400, cid))
            n += cur.rowcount
    return n


def ensure_reads(cid=None, now=None):
    """Two reads per campaign video on a live campaign: 2 and 7 days after it went up. A post first seen after
    its second read was due gets that read only; one older than FRESH_DAYS is not read."""
    init()
    now = now or db.now()
    added = 0
    weekly = weekly_until(now)
    with db.connect() as conn:
        camps = conn.execute("SELECT * FROM campaigns WHERE status = 'live'" + (" AND id = %d" % int(cid) if cid else "")).fetchall()
        for k in camps:
            if _is_sample(k):
                continue
            rows = conn.execute("SELECT id, platform, posted_at FROM content WHERE campaign_id = ? AND hidden = 0 "
                                "AND section = 'campaign' AND posted_at IS NOT NULL", (k["id"],)).fetchall()
            for c in rows:
                old = now - c["posted_at"] > FRESH_DAYS * 86400
                if c["platform"] not in ACTORS or (old and k["id"] not in weekly):
                    continue
                d1, d2 = (c["posted_at"] + d * 86400 for d in READ_DAYS)
                for no, due in ((1, d1), (2, d2)):
                    st = "skipped" if no == 1 and now >= d2 else "due"
                    if old and no == 2 and conn.execute("SELECT 1 FROM comment_reads WHERE content_id = ? AND read_no = 1 "
                                                        "AND status != 'skipped'", (c["id"],)).fetchone():
                        st = "skipped"         # an old video read on read 1 needs no second read now; weekly re-reads follow
                    cur = conn.execute("INSERT OR IGNORE INTO comment_reads (content_id, campaign_id, platform, read_no, due_at, status) "
                                       "VALUES (?,?,?,?,?,?)", (c["id"], k["id"], c["platform"], no, due, st))
                    added += cur.rowcount
    return added


def read_now(cid):
    """Admin "Read comments now": every unread read of this campaign is due at once (the day-7 read stays)."""
    init()
    ensure_reads(cid)
    with db.connect() as conn:
        conn.execute("UPDATE comment_reads SET due_at = ? WHERE campaign_id = ? AND status IN ('due','failed') AND read_no = 1",
                     (db.now(), int(cid)))
        conn.execute("UPDATE comment_reads SET status = 'due' WHERE campaign_id = ? AND status = 'failed'", (int(cid),))
        # posts whose first read was skipped (first seen late) and have never been read: read them now as well
        conn.execute("UPDATE comment_reads SET due_at = ? WHERE campaign_id = ? AND status = 'due' AND read_no = 2 AND content_id NOT IN "
                     "(SELECT content_id FROM comment_reads WHERE campaign_id = ? AND read_no = 1 AND status = 'done')",
                     (db.now(), int(cid), int(cid)))


def _expected(conn, content_id):
    r = conn.execute("SELECT comments FROM snapshots WHERE content_id = ? AND comments IS NOT NULL ORDER BY at DESC LIMIT 1",
                     (content_id,)).fetchone()
    return min(MAX_PER_POST, int(r["comments"])) if r and r["comments"] else 40


def start_due(now=None):
    """One Apify run per platform and read number for everything due."""
    import apify
    init()
    now = now or db.now()
    if not apify.get_token():
        return 0
    started = 0
    with db.connect() as conn:
        due = conn.execute("SELECT r.*, c.url FROM comment_reads r JOIN content c ON c.id = r.content_id "
                           "WHERE r.status = 'due' AND r.due_at <= ? ORDER BY r.due_at LIMIT 200", (now,)).fetchall()
    groups = {}
    for r in due:
        groups.setdefault((r["platform"], r["read_no"]), []).append(r)
    for (platform, no), reads in groups.items():
        actor, each, build = ACTORS[platform]
        with db.connect() as conn:
            est = sum(_expected(conn, r["content_id"]) for r in reads) * each
        if apify.spent_this_month() + est > apify.budget():
            with db.connect() as conn:
                conn.executemany("UPDATE comment_reads SET message = ? WHERE id = ?",
                                 [("Waiting: the monthly Apify budget would be passed.", r["id"]) for r in reads])
            continue
        urls = list(dict.fromkeys(r["url"] for r in reads))
        since = "6 days" if platform == "Facebook" and no == 2 else None
        try:
            d = apify.call("POST", "/acts/%s/runs" % actor, build(urls, MAX_PER_POST, since),
                           params={"maxTotalChargeUsd": "%.2f" % max(0.5, est * 1.5)}).get("data") or {}
        except Exception as exc:
            with db.connect() as conn:
                conn.executemany("UPDATE comment_reads SET status = 'failed', message = ? WHERE id = ?",
                                 [(str(exc)[:300], r["id"]) for r in reads])
            continue
        with db.connect() as conn:
            cur = conn.execute("INSERT INTO api_runs (job_id, job_name, trigger, apify_run, dataset, status, handles, started_at) "
                               "VALUES (NULL, ?, 'schedule', ?, ?, 'RUNNING', ?, ?)",
                               ("Comments · %s · read %d" % (platform, no), d.get("id"), d.get("defaultDatasetId"), len(urls), db.now()))
            conn.executemany("UPDATE comment_reads SET status = 'running', apify_run = ?, run_row = ?, started_at = ?, message = NULL "
                             "WHERE id = ?", [(d.get("id"), cur.lastrowid, db.now(), r["id"]) for r in reads])
        started += 1
    return started


def _items(apify, dataset):
    out, offset = [], 0
    while True:
        page = apify.call("GET", "/datasets/%s/items" % dataset, params={"format": "json", "clean": "1", "limit": "1000",
                                                                       "offset": str(offset)}, timeout=60)
        page = page if isinstance(page, list) else (page.get("data") or [])
        out += page
        if len(page) < 1000:
            return out
        offset += 1000


def poll_runs():
    """Finished runs: keep the comments, record the cost, delete Apify's copy."""
    import apify
    init()
    with db.connect() as conn:
        runs = conn.execute("SELECT apify_run, run_row, platform FROM comment_reads WHERE status = 'running' "
                            "GROUP BY apify_run").fetchall()
    saved_total = 0
    for run in runs:
        try:
            d = apify.call("GET", "/actor-runs/%s" % run["apify_run"]).get("data") or {}
        except Exception:
            continue
        status = d.get("status")
        if status in ("READY", "RUNNING"):
            continue
        with db.connect() as conn:
            reads = conn.execute("SELECT r.*, c.url, c.code FROM comment_reads r JOIN content c ON c.id = r.content_id "
                                 "WHERE r.apify_run = ?", (run["apify_run"],)).fetchall()
        items, saved, found = [], 0, {}
        if status == "SUCCEEDED" and d.get("defaultDatasetId"):
            try:
                items = _items(apify, d["defaultDatasetId"])
            except Exception as exc:
                print("comments: dataset read failed:", repr(exc)[:160], flush=True)
                continue                                   # try again next pass
        by_key = {post_key(r["platform"], r["url"]): r for r in reads}
        with db.connect() as conn:
            for it in items:
                parsed = _parse(it)
                if not parsed:
                    continue
                r = next((by_key[k] for k in _item_keys(run["platform"], it) if k in by_key), None)
                if r is None and len(reads) == 1:
                    r = reads[0]
                if r is None:
                    continue
                ext, text, posted, likes = parsed
                cur = conn.execute("INSERT OR IGNORE INTO comments (content_id, campaign_id, code, platform, ext_id, text, posted_at, likes, read_at) "
                                   "VALUES (?,?,?,?,?,?,?,?,?)", (r["content_id"], r["campaign_id"], r["code"], r["platform"], ext, text,
                                                                  posted, likes, db.now()))
                if cur.rowcount:
                    saved += 1
                else:
                    conn.execute("UPDATE comments SET likes = ? WHERE content_id = ? AND ext_id = ?", (likes, r["content_id"], ext))
                found[r["id"]] = found.get(r["id"], 0) + 1
            ok = status == "SUCCEEDED"
            for r in reads:
                conn.execute("UPDATE comment_reads SET status = ?, found = ?, finished_at = ?, message = ? WHERE id = ?",
                             ("done" if ok else "failed", found.get(r["id"], 0), db.now(),
                              None if ok else ("Apify ended the run as %s." % status), r["id"]))
            conn.execute("UPDATE api_runs SET status = ?, results = ?, saved = ?, cost = ?, finished_at = ? WHERE id = ?",
                         (status if status in ("SUCCEEDED", "FAILED") else "FAILED", len(items), saved, apify.run_cost(d),
                          db.now(), run["run_row"]))
        if d.get("defaultDatasetId"):
            try:
                apify.call("DELETE", "/datasets/%s" % d["defaultDatasetId"])
            except Exception:
                pass
        saved_total += saved
    return saved_total


# --------------------------------------------------------------------------------- reading --

SYSTEM = (
    "You read comments left under sponsored social-media videos for a healthcare / beauty brand campaign in the Gulf "
    "and Egypt (mostly Arabic, Egyptian and Gulf dialects, some English). For every comment return:\n"
    "- sentiment: positive, neutral or negative toward the video, creator or product (jokes and emoji count by their tone).\n"
    "- intent: true only when the person asks or shows they want to buy or use it: price, where to find it, "
    "availability in a country, how to order, dosage to start.\n"
    "- ask: when intent is true, the buying question in a SHORT shared wording in the comment's language (2-4 words, "
    "e.g. 'بكام؟', 'وين أحصله؟', 'متوفر في مصر؟'); reuse an existing wording from the list when it means the same; "
    "else empty. ask_en: its English (e.g. 'How much is it?').\n"
    "- theme: one short English topic label (2-6 words). Reuse a label from the list when it fits; keep the whole "
    "campaign under 8 labels.\n"
    "- flag: only when the comment needs a person: complaint (bad experience, refund, fake product), side_effect (a "
    "health effect or harm claimed), misinformation (false medical claim), regulatory (promises a cure, prescription "
    "drug use, a minor, an unlicensed claim), abuse (insults, hate). Else none.\n"
    "- gloss: a short, natural English translation of the comment (at most 18 words), not a description of it.\n"
    "Return one item per comment with its index i."
)
RESULT = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "i": {"type": "INTEGER"},
    "sentiment": {"type": "STRING", "enum": ["positive", "neutral", "negative"]},
    "intent": {"type": "BOOLEAN"},
    "ask": {"type": "STRING"}, "ask_en": {"type": "STRING"},
    "theme": {"type": "STRING"},
    "flag": {"type": "STRING", "enum": ["none", "complaint", "side_effect", "misinformation", "regulatory", "abuse"]},
    "gloss": {"type": "STRING"}},
    "required": ["i", "sentiment", "intent", "theme", "flag", "gloss"]}}}, "required": ["items"]}


def _known(conn, cid):
    themes = [r[0] for r in conn.execute("SELECT theme FROM comments WHERE campaign_id = ? AND theme IS NOT NULL "
                                          "GROUP BY theme ORDER BY COUNT(*) DESC LIMIT 8", (cid,))]
    asks = [(r[0], r[1]) for r in conn.execute("SELECT ask, MAX(ask_en) FROM comments WHERE campaign_id = ? AND ask IS NOT NULL "
                                                "AND ask != '' GROUP BY ask ORDER BY COUNT(*) DESC LIMIT 12", (cid,))]
    return themes, asks


def classify_pending(limit=600):
    """Read the comments Gemini has not seen yet, campaign by campaign. Returns (read, new red flags by campaign)."""
    import gemini
    init()
    if not gemini.configured():
        return 0, {}
    done, flags = 0, {}
    while done < limit:
        with db.connect() as conn:
            first = conn.execute("SELECT campaign_id FROM comments WHERE sentiment IS NULL LIMIT 1").fetchone()
            if first is None:
                break
            cid = first["campaign_id"]
            rows = conn.execute("SELECT id, text FROM comments WHERE campaign_id = ? AND sentiment IS NULL LIMIT ?",
                                (cid, BATCH)).fetchall()
            themes, asks = _known(conn, cid)
        prompt = ("Existing themes: %s\nExisting buying wordings: %s\n\nComments:\n%s" % (
            json.dumps(themes, ensure_ascii=False), json.dumps([a for a, _ in asks], ensure_ascii=False),
            "\n".join("%d. %s" % (n, r["text"][:400].replace("\n", " ")) for n, r in enumerate(rows))))
        try:
            out = gemini.generate_json(prompt, RESULT, system=SYSTEM, kind="comments", temperature=0.1, max_tokens=8192, timeout=60)
        except Exception as exc:
            print("comments: reading failed:", repr(exc)[:160], flush=True)
            break
        got = {it.get("i"): it for it in (out.get("items") or []) if isinstance(it, dict)}
        with db.connect() as conn:
            for n, r in enumerate(rows):
                it = got.get(n)
                if not it:
                    conn.execute("UPDATE comments SET sentiment = 'neutral', intent = 0, theme = 'Other' WHERE id = ?", (r["id"],))
                    continue
                flag = it.get("flag") if it.get("flag") in FLAGS else None
                intent = 1 if it.get("intent") else 0
                ask = ((it.get("ask") or "").strip()[:60] or None) if intent else None
                ask_en = ((it.get("ask_en") or "").strip()[:80] or None) if intent else None
                conn.execute("UPDATE comments SET sentiment = ?, intent = ?, ask = ?, ask_en = ?, theme = ?, flag = ?, gloss = ? WHERE id = ?",
                             (it.get("sentiment") if it.get("sentiment") in ("positive", "neutral", "negative") else "neutral",
                              intent, ask, ask_en, (it.get("theme") or "Other").strip()[:60], flag,
                              (it.get("gloss") or "").strip()[:240], r["id"]))
                if flag:
                    flags[cid] = flags.get(cid, 0) + 1
        done += len(rows)
    for cid, n in flags.items():
        _tell_flags(cid, n)
    return done, flags


def _tell_flags(cid, n):
    try:
        import notify
        k = db.campaign(int(cid))
        if k is None:
            return
        notify.send("comment_flags", ['%d new comment%s on "%s" need a look (complaint, side-effect claim, misinformation, '
                                      'regulatory risk or abuse).' % (n, "" if n == 1 else "s", k["name"]),
                                      "Open the campaign's Comments tab in the admin to see them."],
                    kam=db.kam_of_item("campaign", k["id"]))
    except Exception as exc:
        print("comments: flag mail skipped:", repr(exc)[:120], flush=True)


LABELS = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "label": {"type": "STRING"}, "ar": {"type": "STRING"}}, "required": ["label", "ar"]}}}, "required": ["items"]}


def translate_labels():
    """Arabic titles for theme labels that have none yet (owner, 2026-10-19). One call for up to 40 labels."""
    import gemini
    init()
    if not gemini.configured():
        return 0
    with db.connect() as conn:
        todo = [r[0] for r in conn.execute("SELECT DISTINCT theme FROM comments WHERE theme IS NOT NULL AND theme NOT IN "
                                            "(SELECT label FROM comment_labels WHERE ar IS NOT NULL AND ar != '') LIMIT 40")]
    if not todo:
        return 0
    try:
        out = gemini.generate_json("Translate each topic label to a short, natural Modern Standard Arabic title (2-5 words) for a "
                                   "Saudi / Egyptian marketing report. Keep the meaning, no quotes.\n" + json.dumps(todo, ensure_ascii=False),
                                   LABELS, kind="comments", temperature=0.1, max_tokens=2048, timeout=45)
    except Exception as exc:
        print("comments: label translation failed:", repr(exc)[:160], flush=True)
        return 0
    got = {str(it.get("label") or "").strip(): str(it.get("ar") or "").strip()[:80] for it in (out.get("items") or []) if isinstance(it, dict)}
    with db.connect() as conn:
        for lab in todo:
            if got.get(lab):
                conn.execute("INSERT OR REPLACE INTO comment_labels (label, ar) VALUES (?, ?)", (lab, got[lab]))
    return len([l for l in todo if got.get(l)])


# --------------------------------------------------------------------------------- loop --

def tick():
    with _lock:
        ensure_reads()
        weekly_rereads()
        saved = poll_runs()
        started = start_due()
        read, _ = classify_pending()
        translate_labels()
    return {"saved": saved, "started": started, "read": read}


def start():
    def loop():
        time.sleep(90)
        while True:
            try:
                out = tick()
                if any(out.values()):
                    print("comments:", out, flush=True)
            except Exception as exc:
                print("comments: pass skipped:", repr(exc)[:160], flush=True)
            time.sleep(INTERVAL)
    threading.Thread(target=loop, daemon=True, name="comments").start()


# ----------------------------------------------------------------------------- client view --

def client_view(k):
    """What the client's dashboard needs: per creator-and-platform totals (the page filters them), the approved
    quotes and where the reading schedule stands. No comment text except approved quotes, no red flags."""
    init()
    cid = k["id"]
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT m.code, m.platform, m.sentiment, m.intent, m.ask, m.ask_en, m.theme, m.content_id, m.posted_at FROM comments m "
            "JOIN content c ON c.id = m.content_id WHERE m.campaign_id = ? AND c.hidden = 0 AND m.sentiment IS NOT NULL",
            (cid,)).fetchall()   # every comment counts on the client's page, red-flagged ones included (owner, 2026-10-19)
        reads = conn.execute("SELECT r.status, r.due_at, r.finished_at FROM comment_reads r JOIN content c ON c.id = r.content_id "
                             "WHERE r.campaign_id = ? AND c.hidden = 0", (cid,)).fetchall()
        quotes = conn.execute(
            "SELECT m.code, m.platform, m.text, m.gloss FROM comments m JOIN content c ON c.id = m.content_id "
            "WHERE m.campaign_id = ? AND m.quote = 1 AND m.flag IS NULL AND m.sentiment IS NOT NULL AND c.hidden = 0 ORDER BY COALESCE(m.likes, 0) DESC LIMIT ?",
            (cid, MAX_QUOTES)).fetchall()
        first_post = conn.execute("SELECT MIN(posted_at) FROM content WHERE campaign_id = ? AND hidden = 0 AND section = 'campaign'",
                                  (cid,)).fetchone()[0]
        labels = {r[0]: r[1] for r in conn.execute("SELECT label, ar FROM comment_labels WHERE ar IS NOT NULL")}
    buckets = {}
    for r in rows:
        b = buckets.setdefault((r["code"], r["platform"]), {"code": r["code"], "platform": r["platform"], "n": 0, "pos": 0, "neu": 0,
                                                            "neg": 0, "intent": 0, "asks": {}, "themes": {}, "videos": set(), "days": {}})
        b["n"] += 1
        b[{"positive": "pos", "negative": "neg"}.get(r["sentiment"], "neu")] += 1
        b["videos"].add(r["content_id"])
        if r["posted_at"]:                                  # comments per day, Riyadh time (owner, 2026-10-19)
            d = time.strftime("%Y-%m-%d", time.gmtime(r["posted_at"] + 3 * 3600))
            b["days"][d] = b["days"].get(d, 0) + 1
        if r["intent"]:
            b["intent"] += 1
            if r["ask"]:
                a = b["asks"].setdefault(r["ask"], {"n": 0, "en": r["ask_en"] or ""})
                a["n"] += 1
        if r["theme"]:
            b["themes"][r["theme"]] = b["themes"].get(r["theme"], 0) + 1
    # What people ask about each topic (owner, 2026-10-19): the buying questions inside every theme, most asked first.
    ta = {}
    for r in rows:
        if r["intent"] and r["ask"] and r["theme"]:
            d = ta.setdefault(r["theme"], {})
            x = d.setdefault(r["ask"], [r["ask"], r["ask_en"] or "", 0])
            x[2] += 1
    theme_asks = {th: sorted(d.values(), key=lambda x: -x[2])[:4] for th, d in ta.items()}
    out = []
    for b in buckets.values():
        b["videos"] = len(b["videos"])
        out.append(b)
    pending = [r["due_at"] for r in reads if r["status"] in ("due", "running")]
    done = [r["finished_at"] for r in reads if r["status"] == "done" and r["finished_at"]]
    return {"status": "ready" if out else ("waiting" if reads or first_post else "none"),
            "buckets": out, "quotes": [dict(q) for q in quotes], "min_sample": MIN_SAMPLE,
            "theme_asks": theme_asks, "theme_ar": {k: v for k, v in labels.items() if any(k in b["themes"] for b in out)},
            "first_post": first_post, "next_read": min(pending) if pending else None,
            "last_read": max(done) if done else None,
            "final_read": max([r["due_at"] for r in reads] or [0]) or None,
            "read_days": list(READ_DAYS)}


def client_list(k):
    """Every read comment of a campaign for the client's comment browser (owner, 2026-10-19: all comments, red flags
    included). Compact rows, most liked first: [content_id, code, platform, mood, buying, theme, ask, text, gloss, likes, posted]."""
    init()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT m.content_id, m.code, m.platform, m.sentiment, m.intent, m.theme, m.ask, m.text, m.gloss, m.likes, m.posted_at "
            "FROM comments m JOIN content c ON c.id = m.content_id WHERE m.campaign_id = ? AND c.hidden = 0 AND m.sentiment IS NOT NULL "
            "ORDER BY COALESCE(m.likes, 0) DESC, m.id", (k["id"],)).fetchall()
    mood = {"positive": "p", "negative": "x"}
    return {"items": [[r["content_id"], r["code"], r["platform"], mood.get(r["sentiment"], "n"), 1 if r["intent"] else 0, r["theme"] or "",
                       r["ask"] or "", r["text"], r["gloss"] or "", r["likes"] or 0, r["posted_at"] or 0] for r in rows]}


# ----------------------------------------------------------------------------- admin tab --

def _fmt_day(t):
    return time.strftime("%d %b", time.gmtime(t + 3 * 3600)) if t else "—"


def admin_page(k, error=None, message=None):
    import views
    import gemini
    import apify
    init()
    e, u = views.e, views.u
    cid = k["id"]
    with db.connect() as conn:
        tot = conn.execute("SELECT COUNT(*) n, SUM(sentiment = 'positive') pos, SUM(sentiment = 'negative') neg, SUM(intent) buy, "
                           "SUM(sentiment IS NULL) unread, SUM(flag IS NOT NULL) flags, SUM(quote) quotes FROM comments WHERE campaign_id = ?",
                           (cid,)).fetchone()
        flags = conn.execute("SELECT m.*, r.name FROM comments m LEFT JOIN creators r ON r.code = m.code WHERE m.campaign_id = ? "
                             "AND m.flag IS NOT NULL ORDER BY m.flag_seen, m.id DESC LIMIT 100", (cid,)).fetchall()
        cands = conn.execute("SELECT m.*, r.name FROM comments m LEFT JOIN creators r ON r.code = m.code WHERE m.campaign_id = ? "
                             "AND m.flag IS NULL AND m.sentiment IS NOT NULL AND LENGTH(m.text) >= 6 "
                             "ORDER BY m.quote DESC, m.intent DESC, (m.sentiment = 'positive') DESC, COALESCE(m.likes, 0) DESC LIMIT 60",
                             (cid,)).fetchall()
        reads = conn.execute("SELECT r.*, c.url, c.code, cr.name FROM comment_reads r JOIN content c ON c.id = r.content_id "
                             "LEFT JOIN creators cr ON cr.code = c.code WHERE r.campaign_id = ? ORDER BY c.code, r.content_id, r.read_no",
                             (cid,)).fetchall()
        cost = conn.execute("SELECT COALESCE(SUM(a.cost), 0) FROM api_runs a WHERE a.id IN (SELECT run_row FROM comment_reads WHERE campaign_id = ?)",
                            (cid,)).fetchone()[0]
    n = tot["n"] or 0
    pc = lambda x: ("%d%%" % round((x or 0) * 100.0 / n)) if n else "—"

    def form(action, label, cls="btn small", **hidden):
        return ("<form method='post' action='%s' style='display:inline'>" % u("/campaigns/comments")
                + "<input type='hidden' name='id' value='%d'><input type='hidden' name='do' value='%s'>" % (cid, action)
                + "".join("<input type='hidden' name='%s' value='%s'>" % (a, e(str(b))) for a, b in hidden.items())
                + "<button class='%s'>%s</button></form>" % (cls, label))

    stats = ("<div class='card'><div class='row' style='gap:28px;flex-wrap:wrap'>"
             + "".join("<div><label>%s</label><b style='font-size:22px'>%s</b></div>" % (a, b) for a, b in [
                 ("Comments read", "{:,}".format(n)), ("Positive", pc(tot["pos"])), ("Negative", pc(tot["neg"])),
                 ("Ask how to buy", pc(tot["buy"])), ("Red flags", tot["flags"] or 0), ("Quotes shown", "%d of %d" % (tot["quotes"] or 0, MAX_QUOTES)),
                 ("Apify cost", "$%.2f" % (cost or 0))])
             + "</div>"
             + ("<p class='price-hint'>%d comments are waiting for the AI reading.%s</p>" % (
                 tot["unread"], "" if gemini.configured() else " Gemini is not set up (Client portal → Settings & keys)") if tot["unread"] else "")
             + ("" if apify.get_token() else "<p class='err'>No Apify token is saved, so comments cannot be fetched.</p>")
             + "<div style='margin-top:10px'>" + form("read_now", "Read comments now", "btn small lime")
             + " <span class='price-hint'>Comments are read 2 and 7 days after each video (up to %d per post). This brings the "
               "next read forward.</span></div></div>" % MAX_PER_POST)

    def who(r):
        return "<b>%s</b> <span class='muted'>· %s</span>" % (e(r["name"] or r["code"] or ""), e(r["platform"]))

    def ctext(r):
        return ("<div dir='auto' style='font-size:15px;line-height:1.5'>%s</div>" % e(r["text"])
                + ("<div class='muted' style='font-size:12.5px'>%s</div>" % e(r["gloss"]) if r["gloss"] else ""))

    flag_rows = "".join(
        "<tr%s><td><span class='pill %s'>%s</span></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            "" if not r["flag_seen"] else " class='muted'", "bad" if not r["flag_seen"] else "", e(FLAGS.get(r["flag"], r["flag"])),
            ctext(r), who(r), "" if r["flag_seen"] else form("seen", "Mark seen", c=r["id"]))
        for r in flags)
    flag_card = ("<h2>Red flags <span class='muted' style='font-size:13px'>the client sees these comments too, in their comment list</span></h2><div class='card'>"
                 + ("<table><tbody>" + flag_rows + "</tbody></table>" if flag_rows else "<p class='muted'>No red flags.</p>") + "</div>")

    quote_rows = "".join(
        "<tr><td>%s</td><td>%s<div class='muted' style='font-size:12px'>%s%s · %s</div></td><td>%s</td></tr>" % (
            ("<span class='pill good'>Shown</span>" if r["quote"] else ""), ctext(r), e(r["sentiment"] or ""),
            " · asks to buy" if r["intent"] else "", e(r["theme"] or ""),
            form("quote", "Remove" if r["quote"] else "Show to client", "btn small" if r["quote"] else "btn small ghost",
                 c=r["id"], on=0 if r["quote"] else 1))
        for r in cands)
    quote_card = ("<h2>Quotes for the client</h2><p class='sec-desc'>Pick up to %d comments to show on the client's dashboard "
                  "(the Arabic and its English meaning). Nothing is shown until you pick it.</p><div class='card'>" % MAX_QUOTES
                  + ("<table><tbody>" + quote_rows + "</tbody></table>" if quote_rows else "<p class='muted'>No comments read yet.</p>") + "</div>")

    st_word = {"due": "Due", "running": "Reading…", "done": "Done", "failed": "Failed", "skipped": "Skipped (posted earlier)"}
    read_rows = "".join(
        "<tr><td>%s</td><td><a href='%s' target='_blank' rel='noopener'>%s</a></td><td>Day %d</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>" % (
            who(r), e(r["url"]), e(post_key(r["platform"], r["url"])[:24]), READ_DAYS[r["read_no"] - 1], _fmt_day(r["due_at"]),
            e(st_word.get(r["status"], r["status"])) + (" · %d" % r["found"] if r["status"] == "done" else ""), e(r["message"] or ""))
        for r in reads)
    read_card = ("<h2>Reading schedule</h2><div class='card'>"
                 + ("<table><thead><tr><th>Creator</th><th>Post</th><th>Read</th><th>When</th><th>Status</th><th></th></tr></thead><tbody>"
                    + read_rows + "</tbody></table>" if read_rows else
                    "<p class='muted'>Reads are planned when the campaign is live and creators' posts are added (Instagram, TikTok, "
                    "Facebook, YouTube).</p>") + "</div>")
    body = (views._head(k, "comments", error, message)
            + "<p class='sub'>What viewers wrote under the campaign videos. The client's dashboard shows the mood, the buying "
              "questions, the themes, every comment (red-flagged ones included) and the quotes you pick here. Commenters' names are never stored.</p>"
            + stats + flag_card + quote_card + read_card)
    return views.page(k["name"] + " — Comments", body, "/campaigns")


def admin_get(handler, query):
    cid = query.get("id", "")
    k = db.campaign(int(cid)) if cid.isdigit() else None
    if k is None:
        return handler.redirect("/campaigns?e=" + urllib.parse.quote("That campaign no longer exists."))
    return handler.send(200, admin_page(k, query.get("e"), query.get("ok")))


def admin_post(handler):
    init()
    f = handler.form_body()
    cid = (f.get("id") or "").strip()
    k = db.campaign(int(cid)) if cid.isdigit() else None
    if k is None:
        return handler.redirect("/campaigns")
    do, c = f.get("do"), (f.get("c") or "").strip()
    back = "/campaigns/comments?id=%d" % k["id"]
    if do == "read_now":
        read_now(k["id"])
        threading.Thread(target=tick, daemon=True).start()
        return handler.redirect(back + "&ok=" + urllib.parse.quote("Reading now. Comments appear here in a few minutes; refresh the page."))
    if c.isdigit():
        with db.connect() as conn:
            if do == "quote":
                on = 1 if f.get("on") == "1" else 0
                if on and conn.execute("SELECT COUNT(*) FROM comments WHERE campaign_id = ? AND quote = 1", (k["id"],)).fetchone()[0] >= MAX_QUOTES:
                    return handler.redirect(back + "&e=" + urllib.parse.quote("Up to %d quotes. Remove one first." % MAX_QUOTES))
                conn.execute("UPDATE comments SET quote = ? WHERE id = ? AND campaign_id = ?", (on, int(c), k["id"]))
            elif do == "seen":
                conn.execute("UPDATE comments SET flag_seen = 1 WHERE id = ? AND campaign_id = ?", (int(c), k["id"]))
    return handler.redirect(back)


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
    db.init()
    print(tick())
