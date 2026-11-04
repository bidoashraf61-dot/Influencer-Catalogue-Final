"""The Helvi Intelligence board (item 313, owner 2026-11-03): every competitor study as a card on a kanban,
the same board the campaigns and selections use (assets/js/hv-board.js), drawn by /intelligence/.

Lanes follow a study's life: Requested (filed, no posts yet), Running (posts in, numbers still being
captured), Ready (analysed), Shared (an open client link to the study exists). A stage is worked out from the
data; an admin may move a card by hand, and that choice is kept in ``evidence_stage`` until moved again.

Who sees what is board.viewer(): admins and the team every study, a KAM her clients', a client their own
company's studies that HelloVoice made visible to them. Only admins move cards.

    GET  /api/evidence/board          payload()
    POST /api/evidence/board/stage    {id, to} -> move()
    GET  /api/evidence/board/manage?id=   manage_view(): the Manage drawer (item 331)
    POST /api/evidence/board/manage       manage_act():  {id, do: stage | meta | visibility | delete, ...}

Manage matrix: owner all; admin all but delete; KAM on her own clients stage and next step/notes; nobody else.
"""
import time

import db

STAGES = ("requested", "running", "ready", "shared")
LABEL = {"requested": "Requested", "running": "Running", "ready": "Ready", "shared": "Shared"}
HINT = {"requested": "Filed, waiting for competitor posts",
        "running": "Posts in, numbers still being captured",
        "ready": "Analysed: who works for the competitors",
        "shared": "The client has a link to the study"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_stage (
    pack_id INTEGER PRIMARY KEY,
    stage TEXT NOT NULL,
    by TEXT,
    at INTEGER
);
"""

META = """
CREATE TABLE IF NOT EXISTS study_meta (
    pack_id INTEGER PRIMARY KEY,
    next_text TEXT,
    next_due INTEGER,
    notes TEXT,
    last_move TEXT,
    updated_by TEXT,
    updated_at INTEGER
);
"""


def ensure(conn):
    """Here too, not only at start-up: a trial link's database is a copy of a template that never ran init()."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_meta'").fetchone():
        conn.executescript(META)
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'evidence_stage'").fetchone():
        conn.executescript(SCHEMA)


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        ensure(conn)


def _shared_refs(conn):
    """Selection tokens with an open (not revoked, not ended) client link to their study."""
    now = int(time.time())
    try:
        return {r[0] for r in conn.execute(
            "SELECT ref FROM report_shares WHERE kind = 'study' AND revoked_at IS NULL AND expires_at > ?", (now,))}
    except Exception:
        return set()


def derived(n_posts, n_measured, shared):
    if shared:
        return "shared"
    if not n_posts:
        return "requested"
    return "ready" if n_measured * 2 >= n_posts else "running"


def _rows(conn):
    ensure(conn)
    return conn.execute(
        "SELECT p.id, p.title, p.code_id, p.selection_id, p.objective, p.platforms, p.client_visible, p.updated_at, "
        "p.created_at, p.brands, s.token sel_token, s.name sel_name, s.deleted_at sel_deleted, c.label code_label, "
        "u.company company, u.kam kam, st.stage manual, sm.next_text next_text, sm.next_due next_due, "
        "(SELECT COUNT(*) FROM evidence_posts x WHERE x.pack_id = p.id) n_posts, "
        "(SELECT COUNT(*) FROM evidence_posts x WHERE x.pack_id = p.id AND x.views IS NOT NULL) n_measured, "
        "(SELECT COUNT(DISTINCT x.competitor) FROM evidence_posts x WHERE x.pack_id = p.id) n_comp, "
        "(SELECT COUNT(DISTINCT x.handle) FROM evidence_posts x WHERE x.pack_id = p.id) n_creators, "
        "(SELECT COUNT(DISTINCT x.code) FROM evidence_posts x WHERE x.pack_id = p.id AND x.code IS NOT NULL) n_matched, "
        # "Who to book": the creator whose posts for the competitors drew the most views, and how many brands they serve.
        "(SELECT json_object('handle', x.handle, 'name', MAX(x.name), 'code', MAX(x.code), 'views', SUM(x.views), "
        "'brands', COUNT(DISTINCT x.competitor)) FROM evidence_posts x WHERE x.pack_id = p.id AND x.views IS NOT NULL "
        "AND x.handle IS NOT NULL AND instr(lower(x.handle), lower(replace(x.competitor, ' ', ''))) = 0 GROUP BY x.handle ORDER BY SUM(x.views) DESC LIMIT 1) top "
        "FROM evidence_packs p LEFT JOIN selections s ON s.id = p.selection_id "
        "LEFT JOIN codes c ON c.id = p.code_id LEFT JOIN users u ON u.code_id = p.code_id "
        "LEFT JOIN evidence_stage st ON st.pack_id = p.id LEFT JOIN study_meta sm ON sm.pack_id = p.id "
        "WHERE p.deleted_at IS NULL ORDER BY p.updated_at DESC").fetchall()


def _visible(h, role, who, rows):
    if role in ("admin", "team"):
        return rows
    if role == "kam":
        sc = h.kam_clients() or frozenset()
        sel_ids = getattr(sc, "sel_ids", ()) or ()
        return [r for r in rows if (r["code_id"] is not None and int(r["code_id"]) in sc) or r["selection_id"] in sel_ids]
    import portal
    team = set(portal.team_codes(int(who)))
    granted = set(db.granted_selection_ids(int(who)))
    # A study filed under no selection is still the company's own (collected from the workspace); it opens there.
    return [r for r in rows if r["client_visible"]
            and ((r["code_id"] is not None and int(r["code_id"]) in team) or r["selection_id"] in granted)]


def card(r, role, shared_refs, logo_dir):
    import board
    shared = bool(r["sel_token"]) and r["sel_token"] in shared_refs
    auto = derived(r["n_posts"], r["n_measured"], shared)
    stage = r["manual"] if r["manual"] in STAGES else auto
    client = board.clean_client(r["company"] or r["code_label"] or "")
    logos = []
    f = (board.client_logo(client, logo_dir) or board.client_logo(r["title"] or "", logo_dir)) if logo_dir is not None else None
    if f:
        logos.append("/assets/clients/" + f)
    camps = []
    if r["selection_id"]:
        for cid in board.campaigns_holding(r["selection_id"]):
            k = db.campaign(cid)
            if k is not None and (role != "client" or k["status"] != "draft"):
                camps.append({"name": k["name"], "token": k["token"], "live": k["status"] == "live"})
    sel_ok = bool(r["sel_token"]) and not r["sel_deleted"]
    # Where the card opens: the study map for its selection, else the client's workspace results, or for staff
    # the admin's own view of the pack.
    opens = ("/market/#s=" + r["sel_token"]) if sel_ok else (
        "/workspace/#helvi-intelligence" if role == "client" else "/admin/evidence/view?id=%d" % r["id"])
    top = None
    if role in ("admin", "team", "kam") and r["top"]:
        try:
            import json
            t = json.loads(r["top"])
            top = {"handle": t.get("handle") or "", "name": t.get("name") or "", "views": int(t.get("views") or 0),
                   "brands": int(t.get("brands") or 0), "on_roster": bool(t.get("code"))}
        except (ValueError, TypeError):
            top = None
    nxt = None
    if r["next_text"]:
        nxt = {"text": r["next_text"], "due": r["next_due"],
               "overdue": bool(r["next_due"] and r["next_due"] < time.time() and stage != "shared")}
    return {"id": r["id"], "top": top, "next": nxt, "manage": role in ("admin", "kam"), "title": r["title"], "stage": stage, "opens": opens, "auto_stage": auto, "manual": stage != auto,
            "moves": [s for s in STAGES if s != stage] if role == "admin" else [],
            "client": client, "logos": logos[:1], "kam": r["kam"] or "",
            "selection": {"token": r["sel_token"], "name": r["sel_name"]} if r["sel_token"] and not r["sel_deleted"] else None,
            "campaigns": camps[:3], "posts": r["n_posts"], "competitors": r["n_comp"], "creators": r["n_creators"],
            "matched": r["n_matched"], "objective": r["objective"] or "", "platforms": r["platforms"] or "",
            "visible": bool(r["client_visible"]), "updated_at": r["updated_at"] or r["created_at"]}


def payload(h, logo_dir):
    import board
    role, who = board.viewer(h)
    if role is None:
        return None
    with db.connect() as conn:
        rows = _rows(conn)
        refs = _shared_refs(conn)
    cards = [card(r, role, refs, logo_dir) for r in _visible(h, role, who, rows)]
    return {"role": role, "can_move": role == "admin", "me": board._me(h),
            "stages": [{"key": s, "label": LABEL[s], "hint": HINT[s]} for s in STAGES], "studies": cards}


def move(h, pack_id, to, actor=""):
    """(ok, message). Admins only; moving a card back to the stage the data gives clears the hand-set one."""
    import board
    role, _ = board.viewer(h)
    if role != "admin":
        return False, "Only a HelloVoice admin moves studies."
    if to not in STAGES:
        return False, "That is not a column on this board."
    with db.connect() as conn:
        rows = [r for r in _rows(conn) if r["id"] == pack_id]
        if not rows:
            return False, "That study is not here any more."
        r = rows[0]
        auto = derived(r["n_posts"], r["n_measured"], bool(r["sel_token"]) and r["sel_token"] in _shared_refs(conn))
        if to == auto:
            conn.execute("DELETE FROM evidence_stage WHERE pack_id = ?", (pack_id,))
        else:
            conn.execute("INSERT INTO evidence_stage (pack_id, stage, by, at) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT(pack_id) DO UPDATE SET stage = excluded.stage, by = excluded.by, at = excluded.at",
                         (pack_id, to, actor, int(time.time())))
    return True, "Moved to %s." % LABEL[to]


# ------------------------------------------------------------ the Manage drawer (item 331)
def _actor(h):
    import board
    import team
    role, who = board.viewer(h)
    if role == "admin":
        role = "owner" if team.role_of(who) == "owner" else "admin"
    return role, board._me(h) or ""


def _one(h, pack_id, level):
    """(row, can) for this study, or (None, None) when this person may not see it."""
    try:
        pid = int(pack_id)
    except (TypeError, ValueError):
        return None, None
    with db.connect() as conn:
        rows = [r for r in _rows(conn) if r["id"] == pid]
    if not rows:
        return None, None
    r = rows[0]
    off = {"stage": False, "meta": False, "visibility": False, "delete": False}
    if level in ("owner", "admin"):
        return r, dict(off, stage=True, meta=True, visibility=True, delete=(level == "owner"))
    if level == "kam" and _visible(h, "kam", None, [r]):
        return r, dict(off, stage=True, meta=True)
    return r, off


def manage_view(h, pack_id):
    level, _ = _actor(h)
    if level is None:
        return 401, {"ok": False, "reason": "signin"}
    r, can = _one(h, pack_id, level)
    if r is None or not any(can.values()):
        return 403, {"ok": False, "message": "You cannot manage this study."}
    with db.connect() as conn:
        m = conn.execute("SELECT * FROM study_meta WHERE pack_id = ?", (r["id"],)).fetchone()
        refs = _shared_refs(conn)
    shared = bool(r["sel_token"]) and r["sel_token"] in refs
    auto = derived(r["n_posts"], r["n_measured"], shared)
    stage = r["manual"] if r["manual"] in STAGES else auto
    return 200, {"ok": True, "level": level, "can": can, "id": r["id"], "name": r["title"], "stage": stage, "by_hand": stage != auto,
                 "stages": [{"key": k, "label": LABEL[k]} for k in STAGES], "hidden": not r["client_visible"],
                 "next_text": (m["next_text"] if m else "") or "", "next_due": m["next_due"] if m else None,
                 "notes": (m["notes"] if m else "") or "", "last_move": (m["last_move"] if m else "") or ""}


def _meta_set(pid, email, **cols):
    keys = list(cols)
    with db.connect() as conn:
        ensure(conn)
        conn.execute("INSERT INTO study_meta (pack_id, %s, updated_by, updated_at) VALUES (?, %s, ?, ?) "
                     "ON CONFLICT(pack_id) DO UPDATE SET %s, updated_by = excluded.updated_by, updated_at = excluded.updated_at"
                     % (", ".join(keys), ", ".join("?" * len(keys)), ", ".join("%s = excluded.%s" % (k, k) for k in keys)),
                     [pid] + [cols[k] for k in keys] + [email, int(time.time())])


def manage_act(h, b):
    import evidence
    level, email = _actor(h)
    if level is None:
        return 401, {"ok": False, "reason": "signin"}
    r, can = _one(h, b.get("id"), level)
    if r is None:
        return 404, {"ok": False, "message": "That study is not here any more."}
    do = str(b.get("do") or "")
    if not (can or {}).get(do):
        return 403, {"ok": False, "message": "That is not yours to change."}
    pid = r["id"]
    if do == "stage":
        to = str(b.get("to") or "")
        if to not in STAGES:
            return 400, {"ok": False, "message": "That is not a column on this board."}
        with db.connect() as conn:
            auto = derived(r["n_posts"], r["n_measured"], bool(r["sel_token"]) and r["sel_token"] in _shared_refs(conn))
        now = r["manual"] if r["manual"] in STAGES else auto
        if to == now:
            return 200, {"ok": True, "stage": now, "message": "Already in %s." % LABEL[to]}
        reason = " ".join(str(b.get("reason") or "").split())[:300]
        if STAGES.index(to) - STAGES.index(now) != 1 and len(reason) < 3:
            return 400, {"ok": False, "need_reason": True, "message": "Say why: moving back, or skipping a stage, needs a short reason."}
        with db.connect() as conn:
            if to == auto:
                conn.execute("DELETE FROM evidence_stage WHERE pack_id = ?", (pid,))
            else:
                conn.execute("INSERT INTO evidence_stage (pack_id, stage, by, at) VALUES (?, ?, ?, ?) "
                             "ON CONFLICT(pack_id) DO UPDATE SET stage = excluded.stage, by = excluded.by, at = excluded.at",
                             (pid, to, email, int(time.time())))
        _meta_set(pid, email, last_move="%s to %s by %s%s" % (LABEL[now], LABEL[to], email or level, (": " + reason) if reason else ""))
        return 200, {"ok": True, "stage": to, "message": "Moved to %s." % LABEL[to]}
    if do == "meta":
        due = None
        raw = str(b.get("next_due") or "").strip()
        if raw:
            try:
                due = int(time.mktime(time.strptime(raw[:10], "%Y-%m-%d"))) + 12 * 3600
            except ValueError:
                return 400, {"ok": False, "message": "The due date must be a day, like 2026-11-20."}
        _meta_set(pid, email, next_text=" ".join(str(b.get("next_text") or "").split())[:200], next_due=due,
                  notes=str(b.get("notes") or "").strip()[:2000])
        return 200, {"ok": True, "message": "Saved."}
    if do == "visibility":
        hide = bool(b.get("hidden"))
        evidence.save(pid, r["title"], r["selection_id"], not hide)
        return 200, {"ok": True, "hidden": hide, "message": "Hidden from the client." if hide else "Visible to the client again."}
    if do == "delete":
        if " ".join(str(b.get("confirm") or "").split()).lower() != " ".join((r["title"] or "").split()).lower():
            return 400, {"ok": False, "message": "Type the study's name exactly to delete it."}
        evidence.delete(pid)
        return 200, {"ok": True, "deleted": True, "message": "Study deleted."}
    return 400, {"ok": False, "message": "Unknown action."}
