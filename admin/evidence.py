"""Competitor evidence packs: which creators already worked with a client's competitors, and how
every one of those posts performed. Built from a competitor-collab study (the evidence-pack JSON
that FY27 Proposal/Evidence Pack/build_evidence_pack.py writes — Instagram now, TikTok merged in
the same shape), imported here, matched to roster creators by handle, and filed under a client
and, optionally, one of her selections.

Admins and KAMs read the full pack (/evidence/view) and add its creators to the selection. When a
pack is switched on for the client, the selection page shows it too (owner decision 2026-10-14:
an exception to the logos-only collab rule, for packs an admin chooses to share).

The study data is confidential: it lives in the database only, never in the (public) repo."""
import json
import statistics
import urllib.parse

import db
from views import e, page, u

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    code_id INTEGER,
    selection_id INTEGER,
    objective TEXT,
    platforms TEXT,
    source TEXT,
    brands TEXT,                  -- JSON [{brand, product, fit: {competitor: direct|partial|off-product}}]
    client_visible INTEGER NOT NULL DEFAULT 0,
    created_by TEXT,
    created_at INTEGER,
    updated_at INTEGER,
    deleted_at INTEGER
);
CREATE TABLE IF NOT EXISTS evidence_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    brand TEXT NOT NULL,          -- the client's brand this post is evidence for
    competitor TEXT NOT NULL,
    platform TEXT NOT NULL,
    url TEXT NOT NULL,
    handle TEXT,
    code TEXT,                    -- roster creator, when the handle matched one
    name TEXT, creator_type TEXT, city TEXT, followers INTEGER,
    posted_at TEXT, collab_type TEXT, posted_on TEXT, content_type TEXT, product_tags TEXT,
    relevance TEXT,               -- match | unspecified | other (vs. the client's product)
    views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER,
    er_views REAL, views_per_follower REAL, x_brand_avg REAL,
    rating TEXT, likely_paid_boost INTEGER NOT NULL DEFAULT 0, likes_hidden INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    UNIQUE (pack_id, brand, url)
);
CREATE INDEX IF NOT EXISTS evidence_posts_pack ON evidence_posts (pack_id, brand, competitor);
CREATE INDEX IF NOT EXISTS evidence_posts_code ON evidence_posts (code);
-- Brand logos (competitors and the client's own brands), shown only once approved by HelloVoice.
CREATE TABLE IF NOT EXISTS brand_logos (
    name TEXT PRIMARY KEY,        -- the brand as studies name it, e.g. "Garnier", "Alpha Plus"
    file TEXT NOT NULL,           -- in LOGO_DIR
    source TEXT,
    credit TEXT,                  -- licence credit when one is required
    approved_at INTEGER,
    updated_at INTEGER
);
-- Creators a pack put on the roster: the mark Apify jobs target ("evidence:<pack id>"), even while hidden.
CREATE TABLE IF NOT EXISTS evidence_roster (
    code TEXT PRIMARY KEY,
    pack_id INTEGER NOT NULL,
    handle TEXT,
    added_at INTEGER,
    added_by TEXT
);
"""

ACCEPT = ".xlsx,.json,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FIT_LABEL = {"direct": "Direct competitor", "partial": "Partly the same product", "off-product": "Different product"}
REL_LABEL = {"match": "Same category", "unspecified": "Product not named", "other": "Other product"}
POST_COLS = ("brand", "competitor", "platform", "url", "handle", "alt_handle", "save_rate", "code", "name", "creator_type", "city", "followers",
             "posted_at", "collab_type", "posted_on", "content_type", "product_tags", "relevance", "views", "likes",
             "comments", "shares", "saves", "er_views", "views_per_follower", "x_brand_avg", "rating",
             "likely_paid_boost", "likes_hidden", "note")
COLLAB_LABEL = {"tiktok_summary": "Best video \u00B7 median figures", "co_author": "Co-author", "co_author_paid": "Co-author + paid", "creator_post_tag": "Own post, tagged",
                "creator_post_tag_paid": "Own post + paid", "brand_page": "On brand page"}


_ready = False


def _ctype(t):
    """Creator types are influencer and hcp only: UGC is a kind of video, not a kind of creator (owner, 2026-10-14)."""
    t = (t or "").strip().lower()
    return "hcp" if t == "hcp" else "influencer"


def init():
    global _ready
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(evidence_packs)")}
        if "creators" not in cols:     # handle -> {name, followers, city, type, links}
            conn.execute("ALTER TABLE evidence_packs ADD COLUMN creators TEXT")
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(evidence_posts)")}
        if "alt_handle" not in pcols:  # the same creator's handle on the other platform (roster matching)
            conn.execute("ALTER TABLE evidence_posts ADD COLUMN alt_handle TEXT")
        if "save_rate" not in pcols:
            conn.execute("ALTER TABLE evidence_posts ADD COLUMN save_rate REAL")
        # Studies imported before 2026-10-14 tagged some creators "ugc"; they are influencers.
        conn.execute("UPDATE evidence_posts SET creator_type = 'influencer' WHERE creator_type = 'ugc'")
    _ready = True


def _conn():
    """db.connect(), making sure the tables exist (tests and tools import this module without main())."""
    if not _ready:
        init()
    return db.connect()


# ------------------------------------------------------------------ import --

def _num(v, kind=float):
    try:
        return None if v is None or v == "" else kind(v)
    except (TypeError, ValueError):
        return None


def handle_index(conn):
    """lower-case handle -> roster code, from the main handle and every profile link."""
    out = {}
    for r in conn.execute("SELECT code, handle, profiles FROM creators").fetchall():
        for pr in db.split_profiles(r["profiles"]):
            h = db.profile_handle(pr.get("url"))
            if h:
                out.setdefault(h, r["code"])
        if r["handle"]:
            out.setdefault(r["handle"].lower().lstrip("@").strip(), r["code"])
    return out


def parse_pack(raw):
    """The evidence-pack JSON, or the filled Excel template (evidence_xlsx) -> (brands meta, posts, meta).
    Raises ValueError with a readable reason."""
    import evidence_xlsx
    if evidence_xlsx.is_xlsx(raw):
        return evidence_xlsx.parse(raw)
    try:
        data = json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw)
    except Exception:
        raise ValueError("That file is not evidence-pack JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("brands"), list):
        raise ValueError("That JSON has no \"brands\" list — export it with build_evidence_pack.py.")
    brands, posts = [], []
    for b in data["brands"]:
        name = str(b.get("brand") or "").strip()
        if not name:
            continue
        fit = {}
        for c in b.get("competitors") or []:
            comp = str(c.get("competitor") or "").strip()
            if not comp:
                continue
            fit[comp] = c.get("fit") or "unknown"
            for p in c.get("posts_detail") or []:
                url = str(p.get("url") or "").strip()
                if not url.startswith("http"):
                    continue
                posts.append({
                    "brand": name, "competitor": comp, "platform": str(p.get("platform") or "instagram").lower(),
                    "url": url, "handle": str(p.get("handle") or "").lower().lstrip("@").strip(),
                    "name": p.get("name"), "creator_type": _ctype(p.get("creator_type")), "city": p.get("city"),
                    "followers": _num(p.get("followers"), int), "posted_at": str(p.get("date") or "")[:10],
                    "collab_type": p.get("collab_type"), "posted_on": p.get("posted_on"),
                    "content_type": p.get("content_type"), "product_tags": p.get("product_tags"),
                    "relevance": p.get("relevance") or "unspecified",
                    "views": _num(p.get("views"), int), "likes": _num(p.get("likes"), int),
                    "comments": _num(p.get("comments"), int), "shares": _num(p.get("shares"), int),
                    "saves": _num(p.get("saves"), int), "er_views": _num(p.get("er_views")),
                    "views_per_follower": _num(p.get("views_per_follower")), "x_brand_avg": _num(p.get("x_brand_avg")),
                    "rating": p.get("rating"), "likely_paid_boost": 1 if p.get("likely_paid_boost") else 0,
                    "likes_hidden": 1 if p.get("likes_hidden") or p.get("likes") is None else 0,
                    "note": p.get("performance_read"),
                    "alt_handle": (str((p.get("also_handles") or [""])[0] or "").lower().lstrip("@").strip() or None),
                    "save_rate": _num(p.get("save_rate")),
                })
        brands.append({"brand": name, "product": b.get("product") or "", "fit": fit})
    if not posts:
        raise ValueError("No posts with links found in that file.")
    creators = {}
    for h, c in (data.get("creators") or {}).items():
        h = str(h).lower().lstrip("@").strip()
        if h and isinstance(c, dict):
            links = {str(k): str(v) for k, v in (c.get("links") or {}).items() if str(v).startswith("http")}
            creators[h] = {"name": c.get("name"), "followers": _num(c.get("followers"), int), "city": c.get("city"),
                           "type": c.get("type"), "links": links}
    meta = {"objective": data.get("objective") or "", "platforms": data.get("platforms") or [],
            "source": data.get("source") or "", "creators": creators}
    return brands, posts, meta


def import_pack(raw, title, code_id, selection_id=None, by="", pack_id=None):
    """Create a pack (or add a platform's posts to an existing one, e.g. TikTok after Instagram).
    Returns (pack id, posts saved, posts matched to the roster)."""
    brands, posts, meta = parse_pack(raw)
    # A filled template is the whole truth for the brands and platforms it covers (owner, 2026-10-15):
    # uploading it again updates the pack in place, and a post taken off the sheet leaves the pack.
    sheet = meta.get("source") == "Excel template"
    t = db.now()
    with _conn() as conn:
        idx = handle_index(conn)
        if pack_id is None:
            pack_id = conn.execute(
                "INSERT INTO evidence_packs (title, code_id, selection_id, objective, platforms, source, brands, "
                "creators, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (title or "Competitor evidence", code_id, selection_id, meta["objective"],
                 json.dumps(meta["platforms"]), meta["source"], json.dumps(brands, ensure_ascii=False),
                 json.dumps(meta["creators"], ensure_ascii=False), by, t, t)).lastrowid
        else:
            row = conn.execute("SELECT brands, platforms, source, creators FROM evidence_packs WHERE id = ?", (pack_id,)).fetchone()
            known = json.loads(row["creators"] or "{}")
            for h, c in meta["creators"].items():
                old_c = known.setdefault(h, c)
                old_c["links"] = dict(c["links"], **(old_c.get("links") or {}))
            conn.execute("UPDATE evidence_packs SET creators = ? WHERE id = ?", (json.dumps(known, ensure_ascii=False), pack_id))
            old = {b["brand"]: b for b in json.loads(row["brands"] or "[]")}
            for b in brands:
                if b["brand"] in old:
                    old[b["brand"]]["fit"].update(b["fit"])
                    old[b["brand"]]["product"] = (b["product"] or old[b["brand"]]["product"]) if sheet else (old[b["brand"]]["product"] or b["product"])
                    if b.get("match_tags"):
                        old[b["brand"]]["match_tags"] = b["match_tags"]
                else:
                    old[b["brand"]] = b
            plats = sorted(set(json.loads(row["platforms"] or "[]")) | set(meta["platforms"]))
            src = "; ".join(dict.fromkeys(x for x in (row["source"], meta["source"]) if x))
            conn.execute("UPDATE evidence_packs SET brands = ?, platforms = ?, source = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(list(old.values()), ensure_ascii=False), json.dumps(plats), src, t, pack_id))
        if sheet:
            keep = {(p["brand"], p["url"]) for p in posts}
            for brand, plat in {(p["brand"], p["platform"]) for p in posts}:
                for r in conn.execute("SELECT id, url FROM evidence_posts WHERE pack_id = ? AND brand = ? AND platform = ?",
                                      (pack_id, brand, plat)).fetchall():
                    if (brand, r["url"]) not in keep:
                        conn.execute("DELETE FROM evidence_posts WHERE id = ?", (r["id"],))
        matched = 0
        for p in posts:
            p["code"] = idx.get(p["handle"]) or (idx.get(p["alt_handle"]) if p.get("alt_handle") else None)
            matched += bool(p["code"])
            conn.execute("INSERT OR REPLACE INTO evidence_posts (pack_id, %s) VALUES (?, %s)"
                         % (", ".join(POST_COLS), ", ".join("?" * len(POST_COLS))),
                         [pack_id] + [p.get(k) for k in POST_COLS])
    return pack_id, len(posts), matched


def rematch(pack_id):
    """Match the pack's handles to the roster again (after creators were added). Returns matches."""
    with _conn() as conn:
        idx = handle_index(conn)
        n = 0
        for r in conn.execute("SELECT id, handle, alt_handle FROM evidence_posts WHERE pack_id = ?", (pack_id,)).fetchall():
            code = idx.get(r["handle"] or "") or idx.get(r["alt_handle"] or "")
            n += bool(code)
            conn.execute("UPDATE evidence_posts SET code = ? WHERE id = ?", (code, r["id"]))
    return n


# ------------------------------------------------------------------ roster --

INTEREST = {"hcp": "Skincare, Health", "influencer": "Skincare, Beauty"}


def roster_status(pk):
    """Creators in the pack: on the roster already, added from this pack, and not on it yet."""
    with _conn() as conn:
        rows = conn.execute("SELECT handle, MAX(code) code, MAX(followers) followers, MAX(creator_type) creator_type "
                            "FROM evidence_posts WHERE pack_id = ? GROUP BY handle", (pk["id"],)).fetchall()
        added = {r["code"] for r in conn.execute("SELECT code FROM evidence_roster WHERE pack_id = ?", (pk["id"],))}
    on = [r for r in rows if r["code"] and r["code"] not in added]
    new = [r for r in rows if r["code"] and r["code"] in added]
    missing = [r for r in rows if not r["code"]]
    return {"total": len(rows), "on_roster": len(on), "added": len(new), "missing": len(missing),
            "missing_hcp": sum(r["creator_type"] == "hcp" for r in missing),
            "missing_handles": [r["handle"] for r in missing]}


def add_to_roster(pk, by="", handles=None):
    """Put the pack's creators who are not on the roster onto it, from what the study knows: name, every
    platform link, followers, city and tier. They go in HIDDEN (the roster's rule for a creator nobody
    has reviewed: no photo, no price) and marked with this pack, so an Apify job can target exactly
    them ("evidence:<pack id>") and fill in the rest. Returns (codes added, notes)."""
    meta = json.loads(pk["creators"] or "{}") if "creators" in pk.keys() else {}
    want = set(handles) if handles else None
    added, notes = [], []
    with _conn() as conn:
        idx = handle_index(conn)
        rows = conn.execute("SELECT handle, MAX(name) name, MAX(followers) followers, MAX(city) city, "
                            "MAX(creator_type) creator_type, MAX(platform) platform FROM evidence_posts "
                            "WHERE pack_id = ? GROUP BY handle", (pk["id"],)).fetchall()
        for r in rows:
            h = r["handle"]
            if not h or (want is not None and h not in want):
                continue
            if idx.get(h):
                continue                                      # on the roster under another pack or by hand
            m = meta.get(h) or {}
            links = dict(m.get("links") or {})
            plat = "TikTok" if (r["platform"] or "").lower() == "tiktok" else "Instagram"
            links.setdefault(plat, db.PROFILE_PATTERNS[plat] % h)
            followers = r["followers"] or m.get("followers")
            profiles = [{"platform": p, "url": links[p].split("?")[0], "followers": followers if p == plat else None}
                        for p in db.PLATFORMS if p in links]
            tier = db.tier_for_reach(followers) or "Nano"
            city = (m.get("city") or r["city"] or "").strip()
            ctype = m.get("type") or r["creator_type"] or "influencer"
            code = db.next_code(tier, conn=conn)
            db.upsert_creator({
                "code": code, "name": (m.get("name") or r["name"] or h).strip(), "handle": h,
                "platform": db.join_cities([p["platform"] for p in profiles]),
                "profiles": db.join_profiles(profiles), "followers": followers,
                "city": None if city.lower() in ("", "saudi arabia", "ksa") else city,
                "nationality": None, "tier": tier, "interest": INTEREST.get(ctype, "Skincare, Beauty"),
                "photo": None, "active": 0, "sort": 0,
                "note": "Added from competitor evidence \"%s\" on %s%s. Lives in Saudi Arabia (study). Hidden from "
                        "clients until reviewed: run the Apify analysis (target: this evidence pack), add a photo, "
                        "then show." % (pk["title"], __import__("time").strftime("%Y-%m-%d"),
                                         " · doctor / pharmacist" if ctype == "hcp" else ""),
            }, conn)
            conn.execute("INSERT OR REPLACE INTO evidence_roster (code, pack_id, handle, added_at, added_by) VALUES (?,?,?,?,?)",
                         (code, pk["id"], h, db.now(), by))
            idx[h] = code
            added.append(code)
    rematch(pk["id"])
    return added, notes


def gap_codes(pack_id, photo_dir=None):
    """Roster creators a pack names who have no analysis at all, or no photo / a photo under 320px:
    the cheap Apify profile run fills both ("evidence-gaps:<pack id>")."""
    from pathlib import Path
    photo_dir = Path(photo_dir or PHOTO_DIR) if (photo_dir or PHOTO_DIR) else None
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM creators WHERE code IN (SELECT DISTINCT code FROM evidence_posts "
                            "WHERE pack_id = ? AND code IS NOT NULL)", (pack_id,)).fetchall()
        have = {r[0] for r in conn.execute("SELECT DISTINCT code FROM creator_analysis")}
    return {r["code"] for r in rows if r["code"] not in have or (photo_dir is not None and _needs_photo(r, photo_dir))}


def noviews_codes(pack_id):
    """Roster creators a pack names with no view numbers anywhere (analysis or post sample): the
    reel-views run's target ("evidence-noviews:<pack id>")."""
    with _conn() as conn:
        codes = [r[0] for r in conn.execute("SELECT DISTINCT code FROM evidence_posts WHERE pack_id = ? AND code IS NOT NULL", (pack_id,))]
        seen = set()
        for i in range(0, len(codes), 400):
            part = codes[i:i + 400]
            q = ",".join("?" * len(part))
            for code, data in conn.execute("SELECT code, data FROM creator_analysis WHERE code IN (%s)" % q, part):
                d = json.loads(data or "{}")
                if d.get("median_views") is not None or d.get("avg_reel_plays") or d.get("avg_views"):
                    seen.add(code)
            try:
                for code, data in conn.execute("SELECT code, data FROM post_samples WHERE code IN (%s)" % q, part):
                    if json.loads(data or "{}").get("median_views") is not None:
                        seen.add(code)
            except Exception:
                pass
    return set(codes) - seen


def roster_codes(pack_id=None):
    """Roster codes a pack added (every pack when None), for Apify targets."""
    with _conn() as conn:
        if pack_id is None:
            return {r["code"] for r in conn.execute("SELECT code FROM evidence_roster")}
        return {r["code"] for r in conn.execute("SELECT code FROM evidence_roster WHERE pack_id = ?", (pack_id,))}


# ------------------------------------------------------------------ photos --

# The live photo folder, <root>/site/assets/catalogue (server.py sets the same path). Known here too, so a
# job started outside the server process (a script, the shell) still sees photo gaps.
from pathlib import Path as _Path
_DEFAULT_PHOTOS = _Path(__file__).resolve().parent.parent / "site" / "assets" / "catalogue"
PHOTO_DIR = _DEFAULT_PHOTOS if _DEFAULT_PHOTOS.is_dir() else None
GOOD_PHOTO = 320          # tools/photo_audit.py: under this the card draws the small soft circle
_PIC_HOSTS = ("cdninstagram.com", "fbcdn.net", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokcdn-eu.com", "ibyteimg.com")


def _short_side(path):
    try:
        import uploads
        data = path.read_bytes()
        i = 2
        while i < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            if data[i + 1] in (0xC0, 0xC1, 0xC2):
                h, w = int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 7:i + 9], "big")
                return min(w, h)
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
        return 0 if not uploads.image_kind(data) else GOOD_PHOTO      # PNG/WebP: not measured, left alone
    except Exception:
        return 0


def _needs_photo(row, photo_dir):
    if not row["photo"]:
        return True
    f = photo_dir / row["photo"]
    return not f.exists() or _short_side(f) < GOOD_PHOTO


def _put_photo(conn, code, data, photo_dir):
    import uploads
    ok, _ = uploads.photo_bytes(data)
    if not ok:
        return False
    name = uploads.write_photo(data, code, photo_dir)
    conn.execute("UPDATE creators SET photo = ?, updated_at = ? WHERE code = ?", (name, db.now(), code))
    return True


def attach_photos(pack_id, folder, photo_dir=None):
    """Placeholder photos for the creators a pack added: <handle>.jpg from the study's own
    sheet (thumbnails). Only fills a creator with no photo. Returns how many were attached."""
    from pathlib import Path
    photo_dir, folder, n = Path(photo_dir or PHOTO_DIR), Path(folder), 0
    with _conn() as conn:
        for r in conn.execute("SELECT c.code, c.photo, e.handle FROM evidence_roster e JOIN creators c ON c.code = e.code "
                              "WHERE e.pack_id = ?", (pack_id,)).fetchall():
            f = folder / ((r["handle"] or "") + ".jpg")
            if not r["photo"] and f.is_file():
                n += _put_photo(conn, r["code"], f.read_bytes(), photo_dir)
    return n


def _fetch_pic(url):
    """An Instagram profile picture, only from Instagram's own image hosts, at most 6MB."""
    import urllib.parse
    import urllib.request
    u_ = urllib.parse.urlparse(url or "")
    host = (u_.hostname or "").lower()
    if u_.scheme != "https" or not any(host == h or host.endswith("." + h) for h in _PIC_HOSTS):
        return None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            return r.read(6 * 1024 * 1024 + 1)
    except Exception:
        return None


def on_profile(conn, code, platform, followers, item):
    """Apify profile result for a creator a pack added (apify.ingest calls this for every profile).
    Brings the roster up to date: that platform's follower count, the creator's followers and tier
    (from the biggest platform), and a proper photo when theirs is missing or a thumbnail.
    Creators the roster had before are never touched here. Returns True when it updated one."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'evidence_roster'").fetchone():
        return False
    row = conn.execute("SELECT * FROM creators WHERE code = ?", (code,)).fetchone()
    if row is None:
        return False
    if not conn.execute("SELECT 1 FROM evidence_roster WHERE code = ?", (code,)).fetchone():
        # A creator the roster had before a study named them: only a missing or low-res photo is
        # replaced (owner decision 2026-10-14); their numbers and tier stay as the roster keeps them.
        if (PHOTO_DIR is not None and isinstance(item, dict)
                and conn.execute("SELECT 1 FROM evidence_posts WHERE code = ? LIMIT 1", (code,)).fetchone()):
            from pathlib import Path
            if _needs_photo(row, Path(PHOTO_DIR)):
                data = _fetch_pic(_pic_url(platform, item))
                if data:
                    return _put_photo(conn, code, data, Path(PHOTO_DIR))
        return False
    profiles = db.split_profiles(row["profiles"])
    if followers is not None:
        for p in profiles:
            if p.get("platform") == platform:
                p["followers"] = int(followers)
    best = max([p.get("followers") or 0 for p in profiles] + [int(followers or 0)]) or row["followers"]
    tier = db.tier_for_reach(best) or row["tier"]
    conn.execute("UPDATE creators SET profiles = ?, followers = ?, tier = ?, updated_at = ? WHERE code = ?",
                 (db.join_profiles(profiles), best, tier, db.now(), code))
    if PHOTO_DIR is not None and isinstance(item, dict):
        from pathlib import Path
        if _needs_photo(row, Path(PHOTO_DIR)):
            data = _fetch_pic(_pic_url(platform, item))
            if data:
                _put_photo(conn, code, data, Path(PHOTO_DIR))
    return True


def _pic_url(platform, item):
    """The profile picture in an Apify result: Instagram's HD picture, or TikTok's avatar (a TikTok-only
    creator has no other photo)."""
    if platform == "Instagram":
        return item.get("profilePicUrlHD") or item.get("profilePicUrl")
    if platform == "TikTok":
        cr = item.get("creator") if isinstance(item.get("creator"), dict) else {}
        am = item.get("authorMeta") if isinstance(item.get("authorMeta"), dict) else {}
        return item.get("avatar_url") or item.get("avatarLarger") or cr.get("avatarUrl") or am.get("avatar")
    return None


# ------------------------------------------------------------------- reads --

def pack(pid, deleted=False):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM evidence_packs WHERE id = ?", (pid,)).fetchone()
    return None if r is None or (r["deleted_at"] and not deleted) else r


def pack_code(pid):
    """(found, code_id), for kam_scope."""
    r = pack(pid) if pid is not None else None
    return (r is not None, r["code_id"] if r is not None else None)


def list_packs(scope=None):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM evidence_posts x WHERE x.pack_id = p.id) AS n_posts, "
            "(SELECT COUNT(DISTINCT x.code) FROM evidence_posts x WHERE x.pack_id = p.id AND x.code IS NOT NULL) AS n_matched, "
            "(SELECT label FROM codes c WHERE c.id = p.code_id) AS client, "
            "(SELECT name FROM selections s WHERE s.id = p.selection_id) AS selection "
            "FROM evidence_packs p WHERE p.deleted_at IS NULL ORDER BY p.updated_at DESC").fetchall()
    return [r for r in rows if scope is None or r["code_id"] in scope]


def for_selection(selection_id, client_only=False):
    with _conn() as conn:
        r = conn.execute("SELECT * FROM evidence_packs WHERE selection_id = ? AND deleted_at IS NULL %s "
                         "ORDER BY updated_at DESC LIMIT 1" % ("AND client_visible = 1" if client_only else ""),
                         (selection_id,)).fetchone()
    return r


def posts(pid, brand=None):
    with _conn() as conn:
        if brand:
            return conn.execute("SELECT * FROM evidence_posts WHERE pack_id = ? AND brand = ?", (pid, brand)).fetchall()
        return conn.execute("SELECT * FROM evidence_posts WHERE pack_id = ?", (pid,)).fetchall()


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def creators_of(rows):
    """Creators ranked by median organic views over posts that are (or may be) the client's product.
    Paid-boosted posts are bought reach, so they never count; creators with only those drop out."""
    by = {}
    for p in rows:
        if p["relevance"] != "other":
            by.setdefault(p["handle"], []).append(p)
    out = []
    for h, ps in by.items():
        organic = [p for p in ps if not p["likely_paid_boost"]]
        if not organic:
            continue
        best = max(organic, key=lambda p: p["views"] or 0)
        out.append({"handle": h, "name": ps[0]["name"], "code": ps[0]["code"], "creator_type": ps[0]["creator_type"],
                    "city": ps[0]["city"], "followers": ps[0]["followers"], "platform": ps[0]["platform"],
                    "posts": len(ps), "matched": sum(p["relevance"] == "match" for p in ps),
                    "median_views": _med([p["views"] for p in organic]),
                    "median_er": _med([p["er_views"] for p in organic]),
                    "views_per_follower": _med([p["views_per_follower"] for p in organic]),
                    "likes_hidden": any(p["likes_hidden"] for p in ps),
                    "last": max(p["posted_at"] or "" for p in ps),
                    "best_url": best["url"], "best_views": best["views"]})
    out.sort(key=lambda c: c["median_views"] or 0, reverse=True)
    return out


def summary(pk):
    """The whole pack as data: brand -> competitors (stats, top creators, posts). Shared by both views."""
    rows = posts(pk["id"])
    out = []
    for b in json.loads(pk["brands"] or "[]"):
        brows = [r for r in rows if r["brand"] == b["brand"]]
        comps = []
        for comp in sorted({r["competitor"] for r in brows}):
            cr = [r for r in brows if r["competitor"] == comp]
            organic = [r for r in cr if not r["likely_paid_boost"]]
            matched = [r for r in organic if r["relevance"] == "match"]
            comps.append({
                "competitor": comp, "fit": b["fit"].get(comp, "unknown"),
                "posts": len(cr), "matched_posts": sum(r["relevance"] == "match" for r in cr),
                "creators": len({r["handle"] for r in cr}),
                "platforms": sorted({r["platform"] for r in cr}),
                "total_views": sum(r["views"] or 0 for r in cr),
                "median_views": _med([r["views"] for r in organic]),
                "median_views_matched": _med([r["views"] for r in matched]),
                "median_er": _med([r["er_views"] for r in organic]),
                "paid_boost": sum(r["likely_paid_boost"] for r in cr),
                "top": creators_of(cr),
                "rows": sorted(cr, key=lambda r: (r["relevance"] != "match", -(r["views"] or 0))),
            })
        rank = {"direct": 0, "partial": 1}
        comps.sort(key=lambda c: (rank.get(c["fit"], 2), -(c["median_views_matched"] or c["median_views"] or 0)))
        out.append({"brand": b["brand"], "product": b.get("product") or "", "posts": len(brows), "competitors": comps})
    return out


def client_payload(pk, selection_codes=()):
    """What the client's selection page shows: numbers and links, no internal notes or roster codes.
    Posts are capped per competitor (best first) so the page stays light."""
    inset = set(selection_codes or ())
    brands = []
    for b in summary(pk):
        comps = []
        for c in b["competitors"]:
            comps.append({
                "competitor": c["competitor"], "fit": FIT_LABEL.get(c["fit"], ""), "posts": c["posts"],
                "matched_posts": c["matched_posts"], "creators": c["creators"], "platforms": c["platforms"],
                "total_views": c["total_views"], "median_views": c["median_views"], "median_er": c["median_er"],
                "top": [{"handle": t["handle"], "name": t["name"], "followers": t["followers"], "platform": t["platform"],
                         "type": t["creator_type"], "city": t["city"], "posts": t["posts"],
                         "median_views": t["median_views"], "median_er": t["median_er"],
                         "likes_hidden": t["likes_hidden"], "best_url": t["best_url"], "best_views": t["best_views"],
                         "in_selection": bool(t["code"] and t["code"] in inset)} for t in c["top"][:10]],
                "rows": [{"url": r["url"], "date": r["posted_at"], "handle": r["handle"], "platform": r["platform"],
                          "views": r["views"], "likes": r["likes"], "comments": r["comments"], "shares": r["shares"],
                          "saves": r["saves"], "er": r["er_views"], "rating": r["rating"],
                          "collab": COLLAB_LABEL.get(r["collab_type"], r["collab_type"] or ""),
                          "same_category": r["relevance"] == "match", "paid_boost": bool(r["likely_paid_boost"])}
                         for r in c["rows"] if r["relevance"] != "other"][:40],
            })
        brands.append({"brand": b["brand"], "product": b["product"], "competitors": comps})
    # Per-card "Track record" counts, only for creators already in this selection (their codes are on
    # the cards anyway); no other roster code leaves the server.
    by_code = {}
    for r in posts(pk["id"]):
        if r["code"] and r["code"] in inset and r["relevance"] != "other":
            d = by_code.setdefault(r["code"], {"brands": set(), "posts": 0})
            d["brands"].add(r["competitor"])
            d["posts"] += 1
    by_code = {c: {"brands": len(d["brands"]), "posts": d["posts"]} for c, d in by_code.items()}
    approved = logos()
    names = {c["competitor"] for b in brands for c in b["competitors"]} | {b["brand"] for b in brands}
    return {"title": pk["title"], "objective": pk["objective"], "platforms": json.loads(pk["platforms"] or "[]"),
            "updated": pk["updated_at"], "brands": brands, "by_code": by_code,
            "logos": {n: logo_url(n, approved) for n in names if logo_url(n, approved)}}


def _reach(code):
    """A creator's normal reach: median and average views on their own posts, per platform, from the
    analysis and the latest post scan / reel run."""
    out = {}
    docs = db.analyses_for([code]).get(code) or {}
    for plat, row in docs.items():
        d = row.get("data") if isinstance(row, dict) else None
        if isinstance(d, dict):
            m = {k: d.get(k) for k in ("median_views", "avg_reel_plays", "avg_views", "er", "followers") if d.get(k) is not None}
            if m:
                out[plat] = m
    with _conn() as conn:
        try:
            for plat, data in conn.execute("SELECT platform, data FROM post_samples WHERE code = ?", (code,)):
                d = json.loads(data or "{}")
                cur = out.setdefault(plat, {})
                for k in ("median_views", "avg_reel_plays"):
                    if d.get(k) is not None:
                        cur[k] = d[k]
        except Exception:
            pass
    return out


import hashlib as _hashlib
import threading as _threading
_thumb_locks = {}
_thumb_guard = _threading.Lock()
_thumb_miss = {}                      # file name -> when a fetch last failed (retried after an hour)


LOGO_DIR = None      # set in init(): admin/brand_logos (not in git)


def logo_dir():
    from pathlib import Path
    return LOGO_DIR or (Path(__file__).resolve().parent / "brand_logos")


def logos():
    """{brand name (lower case): row} for approved logos."""
    with _conn() as conn:
        return {r["name"].lower(): r for r in conn.execute("SELECT * FROM brand_logos WHERE approved_at IS NOT NULL")}


def logo_url(name, approved=None):
    """The public link of a brand's approved logo, or None (then the page falls back to text)."""
    approved = logos() if approved is None else approved
    r = approved.get((name or "").lower())
    return ("/api/brand-logo?n=%s&v=%d" % (urllib.parse.quote(r["name"]), r["updated_at"] or 0)) if r else None


def logo_file(name):
    """(bytes, content type) of an approved logo, for /api/brand-logo."""
    r = logos().get((name or "").lower())
    if r is None:
        return None
    from pathlib import Path
    f = logo_dir() / Path(r["file"]).name
    if not f.is_file():
        return None
    ext = f.suffix.lower()
    return f.read_bytes(), {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg"}.get(ext, "application/octet-stream")


def set_logo(name, data, ext, source="", credit="", approved=True):
    """Store a brand logo (SVGs are checked for scripts and external references)."""
    import re as _re
    ext = ext.lower().lstrip(".")
    if ext not in ("svg", "png", "webp", "jpg"):
        raise ValueError("Logos must be SVG, PNG, WebP or JPG.")
    if ext == "svg":
        text = data.decode("utf-8", "replace")
        if _re.search(r"<script|[\s\"']on[a-z]+\s*=|javascript:|<foreignObject|xlink:href\s*=\s*[\"']https?:|href\s*=\s*[\"']https?:", text, _re.I):
            raise ValueError("That SVG has scripts or outside links in it.")
        # Without a viewBox an SVG drawn inside another one stretches instead of keeping its shape.
        m = _re.search(r"<svg\b[^>]*>", text)
        if m and "viewbox" not in m.group(0).lower():
            w = _re.search(r'\bwidth="([\d.]+)', m.group(0)); h = _re.search(r'\bheight="([\d.]+)', m.group(0))
            if w and h:
                text = text.replace(m.group(0), m.group(0)[:-1].rstrip("/") + ' viewBox="0 0 %s %s">' % (w.group(1), h.group(1)), 1)
                data = text.encode()
    d = logo_dir()
    d.mkdir(exist_ok=True)
    fname = "%s.%s" % (_re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "logo", ext)
    (d / fname).write_bytes(data)
    with _conn() as conn:
        conn.execute("INSERT INTO brand_logos (name, file, source, credit, approved_at, updated_at) VALUES (?,?,?,?,?,?) "
                     "ON CONFLICT(name) DO UPDATE SET file=excluded.file, source=excluded.source, credit=excluded.credit, "
                     "approved_at=excluded.approved_at, updated_at=excluded.updated_at",
                     (name, fname, source, credit, db.now() if approved else None, db.now()))
    return fname


def thumb_file(url):
    """Where a post's picture is kept: thumbs.DIR/ev-<hash of the post link>, shared by every pack."""
    import thumbs
    return thumbs.DIR / ("ev-%s.img" % _hashlib.sha1((url or "").encode()).hexdigest()[:20])


def thumb(url):
    """The stored picture of a competitor post, fetched once on the server and kept (Instagram and TikTok
    refuse their CDN pictures to other sites). Returns (bytes, kind) or None."""
    import thumbs
    import uploads
    f = thumb_file(url)
    if f.is_file():
        data = f.read_bytes()
        return (data, uploads.image_kind(data[:16]) or "jpg") if data else None
    with _thumb_guard:
        lock = _thumb_locks.setdefault(f.name, _threading.Lock())
    import time as _time
    if _time.time() - _thumb_miss.get(f.name, 0) < 3600:
        return None
    with lock:
        if f.is_file():
            data = f.read_bytes()
            return (data, uploads.image_kind(data[:16]) or "jpg") if data else None
        for cand in thumbs.candidates(url, "tiktok" if "tiktok.com" in (url or "") else "instagram"):
            got = thumbs._image(cand)
            if got:
                thumbs.DIR.mkdir(exist_ok=True)
                f.write_bytes(got[0])
                return got
        _thumb_miss[f.name] = _time.time()
    return None


def post_for_thumb(pack_id, post_id):
    """The post's link when ``post_id`` is a post of this pack that may be shown (not an "other product" one)."""
    with _conn() as conn:
        r = conn.execute("SELECT url FROM evidence_posts WHERE id = ? AND pack_id = ? AND relevance != 'other'",
                         (post_id, pack_id)).fetchone()
    return r["url"] if r else None


def fill_thumbs(pack_ids, pause=0.6, log=print):
    """Fetch every missing picture for these packs, one at a time (a background job, gentle on Instagram)."""
    import time
    with _conn() as conn:
        urls = sorted({r[0] for r in conn.execute("SELECT DISTINCT url FROM evidence_posts WHERE pack_id IN (%s) AND relevance != 'other'"
                                                    % ",".join("?" * len(pack_ids)), list(pack_ids))})
    got = miss = 0
    for u in urls:
        if thumb_file(u).is_file():
            continue
        if thumb(u):
            got += 1
        else:
            miss += 1
        time.sleep(pause)
    log("evidence thumbs: %d fetched, %d without a picture, %d already kept" % (got, miss, len(urls) - got - miss))
    return got, miss


def map_payload(pk, selection_codes=(), objective="Awareness", removed=(), locked=()):
    """The Market Intelligence map of ONE selection (owner, 2026-10-15): the client's brand, the competitors
    and only the creators of this selection who worked with them. A creator taken out of the selection, or
    rejected / marked unavailable on it (``removed``), is not on the map, and the competitor totals count
    the selection's creators only.

    ``locked`` (owner, 2026-10-15): creators HelloVoice marked Unavailable on the selection stay on the
    map, greyed with a lock, so the client can ask for them again. ``outside`` lists the competitors'
    creators who are not on the HelloVoice roster yet, for the "Not on our roster yet" strip."""
    locked = set(locked or ())
    inset = (set(selection_codes or ()) - set(removed or ())) | (locked & set(selection_codes or ()))
    every = [r for r in posts(pk["id"]) if r["relevance"] != "other"]
    rows = [r for r in every if r["code"] in inset]
    brand = (json.loads(pk["brands"] or "[]") or [{}])[0].get("brand") or ""
    comps, people = {}, {}
    for r in rows:
        c = comps.setdefault(r["competitor"], {"name": r["competitor"], "posts": 0, "views": 0, "creators": set()})
        c["posts"] += 1
        c["views"] += r["views"] or 0
        c["creators"].add(r["handle"])
        # One person per roster creator (their Instagram and TikTok handles can differ), else per handle.
        p = people.setdefault(r["code"] or r["handle"], {"handle": r["handle"], "name": r["name"], "type": r["creator_type"],
                                             "followers": r["followers"], "code": r["code"] if r["code"] in inset else None,
                                             "platforms": set(), "competitors": {}, "posts": []})
        p["platforms"].add(r["platform"])
        p["competitors"][r["competitor"]] = p["competitors"].get(r["competitor"], 0) + 1
        p["posts"].append(r)
    # Ranking follows the campaign objective (owner, 2026-10-14): awareness by views, engagement by
    # likes + comments. Nothing else is weighed in.
    import fit
    by_eng = fit.metric_for(objective) == "engagement"
    with _conn() as conn:
        roster = {r["code"]: r for r in conn.execute(
            "SELECT code, photo, active FROM creators WHERE code IN (SELECT DISTINCT code FROM evidence_posts WHERE pack_id = ?)", (pk["id"],))}
    by_handle_code = {}
    for r in rows:
        if r["code"]:
            by_handle_code.setdefault(r["handle"], r["code"])
            if r["alt_handle"]:
                by_handle_code.setdefault(r["alt_handle"], r["code"])
    import links
    out = []
    for p in people.values():
        organic = [r for r in p["posts"] if not r["likely_paid_boost"]]
        ps = sorted(p["posts"], key=lambda r: -(r["views"] or 0))
        rc = roster.get(by_handle_code.get(p["handle"]))
        photo = rc["photo"] if rc is not None and rc["active"] and rc["photo"] else None
        inter = _med([(r["likes"] or 0) + (r["comments"] or 0) for r in organic if r["likes"] is not None])
        # Estimated range per post from their competitor work (owner, 2026-10-15): lowest to highest, around
        # the typical (median) post. Views for awareness, likes + comments for engagement / conversion.
        vals = sorted(v for v in ([(r["likes"] or 0) + (r["comments"] or 0) for r in organic if r["likes"] is not None] if by_eng
                                  else [r["views"] for r in organic if r["views"]]) if v)
        est = {"lo": vals[0], "mid": _med(vals), "hi": vals[-1], "n": len(vals)} if vals else None
        out.append({"handle": p["handle"], "name": p["name"], "type": _ctype(p["type"]), "followers": p["followers"], "code": p["code"],
                    "in_selection": bool(p["code"]), "on_roster": rc is not None,
                    "locked": "unavailable" if p["code"] in locked else None,
                    "photo": links.thumb(photo) if photo else None, "photo_large": links.photo(photo) if photo else None,
                    "interactions": inter, "estimate": est,
                    "rank_value": inter if by_eng else _med([r["views"] for r in organic]),
                    "platforms": sorted(p["platforms"]), "competitors": p["competitors"],
                    "median_views": _med([r["views"] for r in organic]), "median_er": _med([r["er_views"] for r in organic]),
                    "paid_only": not organic,
                    "posts": [{"id": r["id"], "url": r["url"], "date": r["posted_at"], "competitor": r["competitor"], "platform": r["platform"],
                               "collab": COLLAB_LABEL.get(r["collab_type"], r["collab_type"] or ""), "views": r["views"], "likes": r["likes"],
                               "comments": r["comments"], "er": r["er_views"], "paid_boost": bool(r["likely_paid_boost"]),
                               "same_category": r["relevance"] == "match", "save_rate": r["save_rate"] if "save_rate" in r.keys() else None,
                               "summary": r["collab_type"] == "tiktok_summary"} for r in ps]})
    out.sort(key=lambda p: -(p["rank_value"] or 0))
    # The competitors' creators HelloVoice does not have yet: a request, never an add.
    comp_names = {r["competitor"] for r in rows} or {r["competitor"] for r in every}
    far = {}
    for r in every:
        if r["code"] or r["competitor"] not in comp_names:
            continue
        f = far.setdefault(r["handle"], {"handle": r["handle"], "name": r["name"], "type": _ctype(r["creator_type"]),
                                         "followers": r["followers"], "competitors": {}, "views": [], "posts": 0})
        f["competitors"][r["competitor"]] = f["competitors"].get(r["competitor"], 0) + 1
        f["posts"] += 1
        if not r["likely_paid_boost"] and r["views"] is not None:
            f["views"].append(r["views"])
    outside = sorted([{"handle": f["handle"], "name": f["name"], "type": f["type"], "followers": f["followers"],
                       "competitors": f["competitors"], "posts": f["posts"], "median_views": _med(f["views"])}
                      for f in far.values() if f["views"]], key=lambda f: -(f["median_views"] or 0))[:24]
    sel_n = len(set(selection_codes or ()) - set(removed or ()))
    approved = logos()
    return {"brand": brand, "outside": outside, "selection_size": sel_n,
            "on_map": sum(1 for p in out if p["code"]), "brand_logo": logo_url(brand, approved), "title": pk["title"],
            "rank_by": "interactions" if by_eng else "views", "objective": objective,
            "competitors": sorted([{"name": c["name"], "posts": c["posts"], "views": c["views"], "creators": len(c["creators"]),
                                    "logo": logo_url(c["name"], approved)} for c in comps.values()], key=lambda c: -c["views"]),
            "creators": out}


def add_by_handle(pk, sel, handle):
    """Put a creator from the pack into the selection (by handle; they must be on the roster).
    Returns their code, or None."""
    with _conn() as conn:
        r = conn.execute("SELECT code FROM evidence_posts WHERE pack_id = ? AND handle = ? AND code IS NOT NULL LIMIT 1",
                         (pk["id"], (handle or "").lower().lstrip("@"))).fetchone()
    if r is None:
        return None
    have = json.loads(sel["codes"] or "[]")
    if r["code"] not in have:
        db.save_selection(sel["id"], sel["name"], have + [r["code"]], json.loads(sel["prices"] or "{}"),
                          sel["total_from"], sel["total_to"], platform=sel["platform"] if "platform" in sel.keys() else None)
    return r["code"]


def creator_payload(pk, code):
    """One creator's Track record in a pack: competitor posts with numbers, KPIs over the organic ones,
    and their normal reach for comparison. No analyst notes. None when the pack has no post of theirs."""
    rows = [r for r in posts(pk["id"]) if r["code"] == code and r["relevance"] != "other"]
    if not rows:
        return None
    organic = [r for r in rows if not r["likely_paid_boost"]]
    comp = {}
    for r in rows:
        comp[r["competitor"]] = comp.get(r["competitor"], 0) + 1
    rows.sort(key=lambda r: -(r["views"] or 0))
    return {
        "handle": rows[0]["handle"], "name": rows[0]["name"], "type": rows[0]["creator_type"],
        "competitors": [{"name": k, "posts": v} for k, v in sorted(comp.items(), key=lambda kv: -kv[1])],
        "kpis": {"posts": len(rows), "median_views": _med([r["views"] for r in organic]),
                 "best_views": max([r["views"] or 0 for r in organic] or [0]) or None,
                 "median_er": _med([r["er_views"] for r in organic]), "last": max(r["posted_at"] or "" for r in rows),
                 "likes_hidden": any(r["likes_hidden"] for r in rows)},
        "posts": [{"id": r["id"], "url": r["url"], "date": r["posted_at"], "competitor": r["competitor"], "platform": r["platform"],
                   "summary": r["collab_type"] == "tiktok_summary", "save_rate": r["save_rate"] if "save_rate" in r.keys() else None,
                   "collab": COLLAB_LABEL.get(r["collab_type"], r["collab_type"] or ""), "views": r["views"], "likes": r["likes"],
                   "comments": r["comments"], "er": r["er_views"], "same_category": r["relevance"] == "match",
                   "paid_boost": bool(r["likely_paid_boost"])} for r in rows[:60]],
        "reach": _reach(code),
        "logos": {k: logo_url(k) for k in comp if logo_url(k)},
        "photo": _photo_of(code),
    }


def _photo_of(code):
    """A signed thumbnail of the creator's roster photo, for the Track record header."""
    try:
        import links
        with _conn() as conn:
            r = conn.execute("SELECT photo FROM creators WHERE code = ? AND active = 1", (code,)).fetchone()
        return links.thumb(r["photo"]) if r is not None and r["photo"] else None
    except Exception:
        return None


# ------------------------------------------------------------------- views --

def _n(v):
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e6:
        return "%.1fM" % (v / 1e6)
    if v >= 1e4:
        return "%.0fK" % (v / 1e3)
    if v >= 1e3:
        return "%.1fK" % (v / 1e3)
    return "%d" % v


def _pct(v, hidden=False):
    if v is None:
        return "likes hidden" if hidden else "—"
    return "%.1f%%" % (v * 100)


CSS = ("<style>"
       ".ev-top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}"
       ".ev-top h1{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:clamp(36px,4.4vw,52px);line-height:.92;margin:0}"
       ".ev-top p{margin:8px 0 0;color:var(--gray);max-width:70ch}"
       ".ev-card{background:var(--white);border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin-bottom:16px}"
       ".ev-card h2{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:28px;line-height:1;margin:0 0 6px}"
       ".ev-card h3{margin:16px 0 8px;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}"
       ".ev-sub{color:var(--muted);font-size:13.5px;margin:0 0 12px}"
       ".ev-tabs{display:inline-flex;background:var(--white);border:1px solid var(--line-strong);border-radius:999px;padding:3px;gap:2px;flex-wrap:wrap;margin-bottom:16px}"
       ".ev-tabs a{border-radius:999px;padding:7px 14px;font-weight:600;font-size:13px;text-decoration:none;color:var(--ink)}"
       ".ev-tabs a[aria-current=true]{background:var(--ink);color:var(--lime)}"
       ".ev-wrap{overflow-x:auto}.ev-t{width:100%;border-collapse:collapse;font-size:13.5px;font-variant-numeric:tabular-nums}"
       ".ev-t th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600;padding:8px 10px;border-bottom:1px solid var(--line-strong);white-space:nowrap}"
       ".ev-t td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}.ev-t td.n{text-align:right;white-space:nowrap}"
       ".ev-t tr:last-child td{border-bottom:0}"
       ".ev-chip{display:inline-flex;font-size:12px;font-weight:700;border-radius:999px;padding:2px 9px;white-space:nowrap}"
       ".ev-chip.direct{background:var(--green-soft);color:var(--green)}.ev-chip.partial{background:var(--amber-soft);color:var(--amber)}"
       ".ev-chip.off-product,.ev-chip.unknown{background:#ece9e3;color:var(--ink)}.ev-chip.paid{background:var(--red-soft);color:var(--red)}"
       ".ev-chip.cat{background:var(--blue-soft);color:var(--blue)}"
       ".ev-kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:10px 0}"
       ".ev-kv div{background:var(--paper);border-radius:12px;padding:10px 12px}"
       ".ev-kv b{display:block;font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:26px;line-height:1}.ev-kv span{font-size:12px;color:var(--muted)}"
       ".ev-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;align-items:end}"
       ".ev-form label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:600}"
       ".ev-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px}.ev-bar form{margin:0}"
       ".ev-mut{color:var(--muted);font-size:12.5px}details.ev-d summary{cursor:pointer;font-weight:600;margin-top:12px}"
       "</style>")


def _msgs(ok, err):
    return ((("<p class='ok'>%s</p>" % e(ok)) if ok else "") + (("<p class='err'>%s</p>" % e(err)) if err else ""))


def list_page(scope, clients, selections, ok=None, err=None):
    rows = list_packs(scope)
    body = [CSS, "<div class='ev-top'><div><h1>Competitor evidence</h1><p>Which creators already worked with a "
            "client's competitors, and how each post did. Import a study, file it under the client and a selection, "
            "then add the strongest creators to the proposal.</p></div></div>", _msgs(ok, err)]
    body.append("<div class='ev-card'><h2>Packs</h2>")
    if rows:
        body.append("<div class='ev-wrap'><table class='ev-t'><tr><th>Pack</th><th>Client</th><th>Selection</th>"
                    "<th>Platforms</th><th class='n'>Posts</th><th class='n'>On roster</th><th>Client sees it</th></tr>")
        for r in rows:
            body.append("<tr><td><a href='%s'><b>%s</b></a></td><td>%s</td><td>%s</td><td>%s</td><td class='n'>%d</td>"
                        "<td class='n'>%d</td><td>%s</td></tr>" % (
                            e(u("/evidence/view?id=%d" % r["id"])), e(r["title"]), e(r["client"] or "—"),
                            e(r["selection"] or "—"), e(", ".join(json.loads(r["platforms"] or "[]"))),
                            r["n_posts"], r["n_matched"], "Yes" if r["client_visible"] else "No"))
        body.append("</table></div>")
    else:
        body.append("<p class='ev-sub'>No packs yet.</p>")
    body.append("</div>")
    body.append("<div class='ev-card'><h2>Import a study</h2><p class='ev-sub'>Download the Excel template, fill the "
                "Brands and Posts sheets, and upload it here. The portal works out relevance, engagement and the best "
                "creators, and matches handles to the roster. Uploading the same file again updates its pack. "
                "The evidence-pack JSON from the old scripts still works.</p>"
                "<p><a class='btn ghost' href='%s' download>Download template (.xlsx)</a></p>"
                "<form method='post' action='%s' enctype='multipart/form-data'><div class='ev-form'>"
                "<label>File (.xlsx or .json)<input type='file' name='file' accept='%s' required></label>"
                "<label>Title<input name='title' placeholder='Avalon Pharma — Instagram competitors' required></label>"
                "<label>Client<select name='code_id' required><option value=''>Choose…</option>%s</select></label>"
                "<label>Selection (optional)<select name='selection_id'><option value=''>None yet</option>%s</select></label>"
                "</div><div class='ev-bar'><button class='btn' type='submit'>Import</button></div></form></div>"
                % (e(u("/evidence/template")), e(u("/evidence/import")), ACCEPT,
                   "".join("<option value='%d'>%s</option>" % (c["id"], e(c["label"])) for c in clients),
                   "".join("<option value='%d'>%s</option>" % (s["id"], e(s["name"])) for s in selections)))
    return page("Competitor evidence", "".join(body), "/evidence")


def _track_record_card(pk, code):
    """Admin: one creator's Track record at the top of the pack page (from the selection's row link)."""
    c = creator_payload(pk, code)
    if c is None:
        return "<div class='ev-card' id='tr'><p class='ev-sub'>No competitor posts for %s in this pack.</p></div>" % e(code)
    k = c["kpis"]
    reach = "; ".join("%s %s views (median, own posts)" % (p, _n(r.get("median_views") if r.get("median_views") is not None else r.get("avg_reel_plays")))
                      for p, r in (c["reach"] or {}).items() if (r.get("median_views") or r.get("avg_reel_plays")))
    return ("<div class='ev-card' id='tr'><h2>Track record: %s</h2><p class='ev-sub'>@%s · %s · %s</p>"
            "<div class='ev-kv'><div><b>%d</b><span>collab posts</span></div><div><b>%s</b><span>median views</span></div>"
            "<div><b>%s</b><span>best post</span></div><div><b>%s</b><span>engagement</span></div><div><b>%s</b><span>last collab</span></div></div>"
            "<p class='ev-mut'>Normal reach: %s</p><div class='ev-wrap'><table class='ev-t'><tr><th>Post</th><th>Brand</th><th>Type</th>"
            "<th class='n'>Views</th><th class='n'>Likes</th><th class='n'>Comments</th><th class='n'>ER</th></tr>%s</table></div></div>") % (
        e(c["name"] or c["handle"]), e(c["handle"]), e(code), e(", ".join("%s (%d)" % (x["name"], x["posts"]) for x in c["competitors"])),
        k["posts"], _n(k["median_views"]), _n(k["best_views"]), _pct(k["median_er"], k["likes_hidden"]), e(k["last"] or "—"),
        e(reach or "not in yet"),
        "".join("<tr><td><a href='%s' target='_blank' rel='noopener'>%s</a>%s</td><td>%s</td><td>%s</td><td class='n'>%s</td><td class='n'>%s</td>"
                "<td class='n'>%s</td><td class='n'>%s</td></tr>" % (
                    e(p["url"]), e(p["date"] or "link"), " <span class='ev-chip paid'>paid-boosted</span>" if p["paid_boost"] else "",
                    e(p["competitor"]), e(p["collab"]), _n(p["views"]), _n(p["likes"]) if p["likes"] is not None else "hidden",
                    _n(p["comments"]), _pct(p["er"], p["likes"] is None)) for p in c["posts"]))


def view_page(pk, brand, selections, ok=None, err=None, creator=None):
    data = summary(pk)
    cur = next((b for b in data if b["brand"] == brand), data[0] if data else None)
    sel = db.selection(pk["selection_id"]) if pk["selection_id"] else None
    in_sel = set(json.loads(sel["codes"] or "[]")) if sel is not None else set()
    body = [CSS, "<div class='ev-top'><div><h1>%s</h1><p>%s · %s · updated %s</p></div>"
            "<div class='ev-bar'>%s<a class='btn' href='%s'>All packs</a></div></div>" % (
                e(pk["title"]), e(", ".join(json.loads(pk["platforms"] or "[]")) or "—"), e(pk["source"] or ""),
                e(db_date(pk["updated_at"])),
                (("<a class='btn' href='%s'>Open selection: %s</a>" % (e(u("/selections/edit?id=%d" % sel["id"])), e(sel["name"])))
                 + ("<a class='btn' href='%s' target='_blank' rel='noopener'>Open map</a>" % e("/market/#s=%s" % sel["token"]))) if sel is not None else "",
                e(u("/evidence")))]
    body.append(_msgs(ok, err))
    if creator:
        body.append(_track_record_card(pk, creator))
    rs = roster_status(pk)
    body.append("<div class='ev-card'><h2>Creators on the roster</h2><div class='ev-kv'>"
                "<div><b>%d</b><span>creators in this study</span></div><div><b>%d</b><span>already on the roster</span></div>"
                "<div><b>%d</b><span>added from this pack</span></div><div><b>%d</b><span>not on the roster yet</span></div></div>"
                % (rs["total"], rs["on_roster"], rs["added"], rs["missing"]))
    if rs["missing"]:
        body.append("<form method='post' action='%s'><input type='hidden' name='id' value='%d'>"
                    "<p class='ev-sub'>Adds the %d missing creators (%d doctors or pharmacists) with every platform link, "
                    "followers, city and tier from the study. They go in <b>hidden</b> and marked with this pack, so they "
                    "can be analysed before any client sees them.</p><div class='ev-bar'>"
                    "<button class='btn' type='submit'>Add %d creators to the roster (hidden)</button></div></form>"
                    % (e(u("/evidence/roster")), pk["id"], rs["missing"], rs["missing_hcp"], rs["missing"]))
    if rs["added"]:
        body.append("<p class='ev-mut'>Full analysis: on <a href='%s'>APIs &amp; keys</a>, make a job with "
                    "<b>Which creators → Evidence: %s</b>. Nothing runs until someone starts it.</p>"
                    % (e(u("/apis")), e(pk["title"])))
    body.append("</div>")
    # settings: selection + client visibility
    body.append("<div class='ev-card'><h2>Proposal</h2><form method='post' action='%s'><input type='hidden' name='id' value='%d'>"
                "<div class='ev-form'><label>Title<input name='title' value='%s'></label>"
                "<label>Selection<select name='selection_id'><option value=''>None</option>%s</select></label>"
                "<label><span><input type='checkbox' name='client_visible' value='1'%s> Show this pack to the client on the selection page</span></label>"
                "</div><div class='ev-bar'><button class='btn' type='submit'>Save</button></div></form>"
                "<div class='ev-bar'><form method='post' action='%s'><input type='hidden' name='id' value='%d'>"
                "<button class='btn' type='submit'>Match handles to the roster again</button></form>"
                "<form method='post' action='%s' onsubmit=\"return confirm('Delete this pack?')\"><input type='hidden' name='id' value='%d'>"
                "<button class='btn' type='submit'>Delete pack</button></form></div>"
                "<p class='ev-mut'>Add another platform's study (e.g. TikTok) to this same pack:</p>"
                "<form method='post' action='%s' enctype='multipart/form-data'><input type='hidden' name='pack_id' value='%d'>"
                "<div class='ev-bar'><input type='file' name='file' accept='%s' required>"
                "<button class='btn' type='submit'>Upload to this pack</button>"
                "<a class='btn ghost' href='%s' download>Download template</a></div>"
                "<p class='ev-sub'>An Excel template updates the brands and platforms it covers: changed rows are updated, "
                "rows taken off the sheet leave the pack. A JSON file adds its posts.</p></form></div>" % (
                    e(u("/evidence/save")), pk["id"], e(pk["title"]),
                    "".join("<option value='%d'%s>%s</option>" % (s["id"], " selected" if s["id"] == pk["selection_id"] else "", e(s["name"]))
                            for s in selections),
                    " checked" if pk["client_visible"] else "",
                    e(u("/evidence/rematch")), pk["id"], e(u("/evidence/delete")), pk["id"],
                    e(u("/evidence/import")), pk["id"], ACCEPT, e(u("/evidence/template"))))
    if cur is None:
        return page(pk["title"], "".join(body) + "<p>No posts in this pack.</p>", "/evidence")
    body.append("<nav class='ev-tabs'>%s</nav>" % "".join(
        "<a href='%s' aria-current='%s'>%s</a>" % (e(u("/evidence/view?id=%d&brand=%s" % (pk["id"], urllib.parse.quote(b["brand"])))),
                                                   "true" if b is cur else "false", e(b["brand"])) for b in data))
    body.append("<div class='ev-card'><h2>%s</h2><p class='ev-sub'>%s · %d posts</p><div class='ev-wrap'><table class='ev-t'>"
                "<tr><th>Competitor</th><th>Fit</th><th class='n'>Posts</th><th class='n'>Same category</th><th class='n'>Creators</th>"
                "<th class='n'>Total views</th><th class='n'>Median views</th><th class='n'>Median ER</th><th class='n'>Paid-boosted</th></tr>%s"
                "</table></div><p class='ev-mut'>Medians leave out paid-boosted posts (very high views with almost no engagement). "
                "ER = (likes + comments) ÷ views.</p></div>" % (
                    e(cur["brand"]), e(cur["product"]), cur["posts"],
                    "".join("<tr><td><a href='#c-%d'><b>%s</b></a></td><td><span class='ev-chip %s'>%s</span></td><td class='n'>%d</td>"
                            "<td class='n'>%d</td><td class='n'>%d</td><td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td><td class='n'>%d</td></tr>" % (
                                i, e(c["competitor"]), e(c["fit"]), e(FIT_LABEL.get(c["fit"], c["fit"])), c["posts"], c["matched_posts"],
                                c["creators"], _n(c["total_views"]), _n(c["median_views"]), _pct(c["median_er"]), c["paid_boost"])
                            for i, c in enumerate(cur["competitors"]))))
    for i, c in enumerate(cur["competitors"]):
        body.append("<div class='ev-card' id='c-%d'><h2>%s <span class='ev-chip %s'>%s</span></h2>"
                    "<div class='ev-kv'><div><b>%d</b><span>posts</span></div><div><b>%d</b><span>creators</span></div>"
                    "<div><b>%s</b><span>total views</span></div><div><b>%s</b><span>median views (organic)</span></div>"
                    "<div><b>%s</b><span>median views, same category</span></div><div><b>%s</b><span>median ER</span></div></div>" % (
                        i, e(c["competitor"]), e(c["fit"]), e(FIT_LABEL.get(c["fit"], c["fit"])), c["posts"], c["creators"],
                        _n(c["total_views"]), _n(c["median_views"]), _n(c["median_views_matched"]), _pct(c["median_er"])))
        body.append("<h3>Best creators with %s</h3>" % e(c["competitor"]))
        if c["top"]:
            can_add = sel is not None
            body.append("<form method='post' action='%s'><input type='hidden' name='id' value='%d'>"
                        "<input type='hidden' name='back' value='%s'><div class='ev-wrap'><table class='ev-t'><tr>%s<th>Creator</th><th>Type</th>"
                        "<th class='n'>Followers</th><th class='n'>Posts</th><th class='n'>Median views</th><th class='n'>Median ER</th>"
                        "<th class='n'>Views ÷ followers</th><th>Last collab</th><th>Best post</th><th>Roster</th></tr>" % (
                            e(u("/evidence/add")), pk["id"], e(cur["brand"]), "<th></th>" if can_add else ""))
            for t in c["top"][:15]:
                box = ""
                if can_add:
                    box = ("<td>%s</td>" % ("<input type='checkbox' name='codes' value='%s' aria-label='Add %s'>" % (e(t["code"]), e(t["handle"]))
                                            if t["code"] and t["code"] not in in_sel else ("✓" if t["code"] in in_sel else "")))
                body.append("<tr>%s<td><b>%s</b><br><span class='ev-mut'>@%s · %s</span></td><td>%s</td><td class='n'>%s</td><td class='n'>%d</td>"
                            "<td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td><td>%s</td>"
                            "<td><a href='%s' target='_blank' rel='noopener'>%s views</a></td><td>%s</td></tr>" % (
                                box, e(t["name"]), e(t["handle"]), e(t["city"] or ""), e(t["creator_type"] or ""), _n(t["followers"]),
                                t["posts"], _n(t["median_views"]), _pct(t["median_er"], t["likes_hidden"]),
                                "%.2f×" % t["views_per_follower"] if t["views_per_follower"] is not None else "—", e(t["last"]),
                                e(t["best_url"]), _n(t["best_views"]),
                                ("<a href='%s'>%s</a>" % (e(u("/roster?q=" + t["code"])), e(t["code"]))) if t["code"] else
                                "<span class='ev-mut'>not on roster</span>"))
            body.append("</table></div>")
            if can_add:
                body.append("<div class='ev-bar'><button class='btn' type='submit'>Add ticked creators to “%s”</button></div>" % e(sel["name"]))
            body.append("</form>")
        else:
            body.append("<p class='ev-sub'>Only paid-boosted or other-product posts — no organic evidence.</p>")
        body.append("<details class='ev-d'><summary>All %d posts</summary><div class='ev-wrap'><table class='ev-t'><tr><th>Date</th><th>Creator</th>"
                    "<th>Collab</th><th>Product</th><th class='n'>Views</th><th class='n'>Likes</th><th class='n'>Comments</th><th class='n'>ER</th>"
                    "<th class='n'>× brand avg</th><th>Rating</th><th>Read</th></tr>%s</table></div></details></div>" % (
                        c["posts"], "".join(
                            "<tr><td><a href='%s' target='_blank' rel='noopener'>%s</a></td><td>@%s</td><td>%s</td><td>%s%s</td>"
                            "<td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td><td class='n'>%s</td>"
                            "<td>%s%s</td><td class='ev-mut' dir='auto'>%s</td></tr>" % (
                                e(r["url"]), e(r["posted_at"] or "link"), e(r["handle"]), e(COLLAB_LABEL.get(r["collab_type"], r["collab_type"] or "")),
                                "<span class='ev-chip cat'>%s</span> " % e(REL_LABEL["match"]) if r["relevance"] == "match" else "",
                                e(r["product_tags"] or ""), _n(r["views"]), _n(r["likes"]) if r["likes"] is not None else "hidden",
                                _n(r["comments"]), _pct(r["er_views"], r["likes_hidden"]),
                                "%.1f×" % r["x_brand_avg"] if r["x_brand_avg"] is not None else "—", e(r["rating"] or ""),
                                " <span class='ev-chip paid'>paid-boosted</span>" if r["likely_paid_boost"] else "", e(r["note"] or ""))
                            for r in c["rows"])))
    return page(pk["title"], "".join(body), "/evidence")


def db_date(t):
    import time
    return time.strftime("%d %b %Y", time.gmtime(t)) if t else "—"


def add_to_selection(pk, codes):
    """Append roster codes to the pack's selection (prices stay as the selection prices them)."""
    sel = db.selection(pk["selection_id"]) if pk["selection_id"] else None
    if sel is None:
        return 0
    have = json.loads(sel["codes"] or "[]")
    known = {c["code"] for c in db.creators_by_codes(codes)}
    new = [c for c in codes if c in known and c not in have]
    if new:
        db.save_selection(sel["id"], sel["name"], have + new, json.loads(sel["prices"] or "{}"),
                          sel["total_from"], sel["total_to"], platform=sel["platform"] if "platform" in sel.keys() else None)
    return len(new)


def save(pid, title, selection_id, client_visible):
    with _conn() as conn:
        conn.execute("UPDATE evidence_packs SET title = ?, selection_id = ?, client_visible = ?, updated_at = ? WHERE id = ?",
                     (title, selection_id, 1 if client_visible else 0, db.now(), pid))


def delete(pid):
    with _conn() as conn:
        conn.execute("UPDATE evidence_packs SET deleted_at = ? WHERE id = ?", (db.now(), pid))
