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
"""

FIT_LABEL = {"direct": "Direct competitor", "partial": "Partly the same product", "off-product": "Different product"}
REL_LABEL = {"match": "Same category", "unspecified": "Product not named", "other": "Other product"}
POST_COLS = ("brand", "competitor", "platform", "url", "handle", "code", "name", "creator_type", "city", "followers",
             "posted_at", "collab_type", "posted_on", "content_type", "product_tags", "relevance", "views", "likes",
             "comments", "shares", "saves", "er_views", "views_per_follower", "x_brand_avg", "rating",
             "likely_paid_boost", "likes_hidden", "note")
COLLAB_LABEL = {"co_author": "Co-author", "co_author_paid": "Co-author + paid", "creator_post_tag": "Own post, tagged",
                "creator_post_tag_paid": "Own post + paid", "brand_page": "On brand page"}


_ready = False


def init():
    global _ready
    with db.connect() as conn:
        conn.executescript(SCHEMA)
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
    """The evidence-pack JSON -> (brands meta, posts). Raises ValueError with a readable reason."""
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
                    "name": p.get("name"), "creator_type": p.get("creator_type"), "city": p.get("city"),
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
                })
        brands.append({"brand": name, "product": b.get("product") or "", "fit": fit})
    if not posts:
        raise ValueError("No posts with links found in that file.")
    meta = {"objective": data.get("objective") or "", "platforms": data.get("platforms") or [],
            "source": data.get("source") or ""}
    return brands, posts, meta


def import_pack(raw, title, code_id, selection_id=None, by="", pack_id=None):
    """Create a pack (or add a platform's posts to an existing one, e.g. TikTok after Instagram).
    Returns (pack id, posts saved, posts matched to the roster)."""
    brands, posts, meta = parse_pack(raw)
    t = db.now()
    with _conn() as conn:
        idx = handle_index(conn)
        if pack_id is None:
            pack_id = conn.execute(
                "INSERT INTO evidence_packs (title, code_id, selection_id, objective, platforms, source, brands, "
                "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (title or "Competitor evidence", code_id, selection_id, meta["objective"],
                 json.dumps(meta["platforms"]), meta["source"], json.dumps(brands, ensure_ascii=False), by, t, t)).lastrowid
        else:
            row = conn.execute("SELECT brands, platforms, source FROM evidence_packs WHERE id = ?", (pack_id,)).fetchone()
            old = {b["brand"]: b for b in json.loads(row["brands"] or "[]")}
            for b in brands:
                if b["brand"] in old:
                    old[b["brand"]]["fit"].update(b["fit"])
                    old[b["brand"]]["product"] = old[b["brand"]]["product"] or b["product"]
                else:
                    old[b["brand"]] = b
            plats = sorted(set(json.loads(row["platforms"] or "[]")) | set(meta["platforms"]))
            src = "; ".join(x for x in (row["source"], meta["source"]) if x)
            conn.execute("UPDATE evidence_packs SET brands = ?, platforms = ?, source = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(list(old.values()), ensure_ascii=False), json.dumps(plats), src, t, pack_id))
        matched = 0
        for p in posts:
            p["code"] = idx.get(p["handle"])
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
        for r in conn.execute("SELECT id, handle FROM evidence_posts WHERE pack_id = ?", (pack_id,)).fetchall():
            code = idx.get(r["handle"] or "")
            n += bool(code)
            conn.execute("UPDATE evidence_posts SET code = ? WHERE id = ?", (code, r["id"]))
    return n


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
    return {"title": pk["title"], "objective": pk["objective"], "platforms": json.loads(pk["platforms"] or "[]"),
            "updated": pk["updated_at"], "brands": brands}


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
    body.append("<div class='ev-card'><h2>Import a study</h2><p class='ev-sub'>The evidence-pack JSON from "
                "<code>build_evidence_pack.py</code>. Handles are matched to the roster as it imports.</p>"
                "<form method='post' action='%s' enctype='multipart/form-data'><div class='ev-form'>"
                "<label>File (.json)<input type='file' name='file' accept='.json,application/json' required></label>"
                "<label>Title<input name='title' placeholder='Avalon Pharma — Instagram competitors' required></label>"
                "<label>Client<select name='code_id' required><option value=''>Choose…</option>%s</select></label>"
                "<label>Selection (optional)<select name='selection_id'><option value=''>None yet</option>%s</select></label>"
                "</div><div class='ev-bar'><button class='btn' type='submit'>Import</button></div></form></div>"
                % (e(u("/evidence/import")),
                   "".join("<option value='%d'>%s</option>" % (c["id"], e(c["label"])) for c in clients),
                   "".join("<option value='%d'>%s</option>" % (s["id"], e(s["name"])) for s in selections)))
    return page("Competitor evidence", "".join(body), "/evidence")


def view_page(pk, brand, selections, ok=None, err=None):
    data = summary(pk)
    cur = next((b for b in data if b["brand"] == brand), data[0] if data else None)
    sel = db.selection(pk["selection_id"]) if pk["selection_id"] else None
    in_sel = set(json.loads(sel["codes"] or "[]")) if sel is not None else set()
    body = [CSS, "<div class='ev-top'><div><h1>%s</h1><p>%s · %s · updated %s</p></div>"
            "<div class='ev-bar'><a class='btn' href='%s'>All packs</a></div></div>" % (
                e(pk["title"]), e(", ".join(json.loads(pk["platforms"] or "[]")) or "—"), e(pk["source"] or ""),
                e(db_date(pk["updated_at"])), e(u("/evidence")))]
    body.append(_msgs(ok, err))
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
                "<div class='ev-bar'><input type='file' name='file' accept='.json,application/json' required>"
                "<button class='btn' type='submit'>Add to pack</button></div></form></div>" % (
                    e(u("/evidence/save")), pk["id"], e(pk["title"]),
                    "".join("<option value='%d'%s>%s</option>" % (s["id"], " selected" if s["id"] == pk["selection_id"] else "", e(s["name"]))
                            for s in selections),
                    " checked" if pk["client_visible"] else "",
                    e(u("/evidence/rematch")), pk["id"], e(u("/evidence/delete")), pk["id"],
                    e(u("/evidence/import")), pk["id"]))
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
