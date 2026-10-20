"""The account CRM behind the Companies tab (items 209 + 220, 2026-10-21).

One row per client company (key = email domain, as in hub.py) or prospect. Staff only: admins every
company, a KAM hers. Clients never see any of this (money, notes, health, phone numbers).

    stage    Lead / Engaged / Quote / Active / Repeat / Dormant, set from the data; a person can override it,
             and the override holds until the data moves the company to a different stage.
    health   green / amber / red from the worst signal: days since last activity, an overdue next step,
             sign-ups waiting, a quote unanswered, every account at 0 credits. A plain-words reason comes with it.
    money    portal quotes only, typed by the KAM per quote request (SAR before VAT).
    notes    dated staff notes and call logs, kept per company.
    prospect a company added by staff before anyone has signed up; when a person from that domain signs up
             it becomes a full account (same key).
"""
import json
import re

import db
import hub
import kam_scope

STAGES = ["lead", "engaged", "quote", "active", "repeat", "dormant"]
STAGE_LABEL = {"lead": "Lead", "engaged": "Engaged", "quote": "Quote", "active": "Active", "repeat": "Repeat", "dormant": "Dormant"}
DORMANT_DAYS = 90
DAY = 86400

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    key TEXT PRIMARY KEY, name TEXT, domain TEXT, kam TEXT,
    stage_override TEXT, override_from TEXT,
    next_step TEXT, next_due INTEGER,
    is_prospect INTEGER NOT NULL DEFAULT 0, created_by TEXT, created_at INTEGER, updated_at INTEGER
);
CREATE TABLE IF NOT EXISTS company_notes (
    id INTEGER PRIMARY KEY, key TEXT NOT NULL, author TEXT, text TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'note', at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS company_notes_key ON company_notes(key, at);
"""
_ready = False


def ensure():
    global _ready
    if _ready:
        return
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "decision_maker" not in ucols:
            conn.execute("ALTER TABLE users ADD COLUMN decision_maker INTEGER NOT NULL DEFAULT 0")
        rcols = {r["name"] for r in conn.execute("PRAGMA table_info(requests)")}
        for col, typ in (("value_sar", "INTEGER"), ("approved_sar", "INTEGER"), ("quote_set_by", "TEXT"), ("quote_set_at", "INTEGER")):
            if col not in rcols:
                conn.execute("ALTER TABLE requests ADD COLUMN %s %s" % (col, typ))
    _ready = True


def _norm_domain(v):
    v = (v or "").strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v).split("/")[0].split("@")[-1]
    return v if re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", v) else ""


# ------------------------------------------------------------------ the data --

def _facts(role, a):
    """{key: facts} for every company this viewer may see, from a handful of bulk queries."""
    groups, _, _ = hub._groups(role, a)
    dmap = kam_scope.domain_map()
    codes = {}
    for key, g in groups.items():
        for u in g["users"]:
            if u["code_id"] is not None:
                codes[int(u["code_id"])] = key
    marks = ",".join("?" * len(codes)) or "NULL"
    ids = list(codes)
    out = {}
    for key, g in groups.items():
        out[key] = {"key": key, "name": hub._name_of(key, g), "domain": "" if key.startswith(hub.FREE) else key, "users": g["users"],
                    "kam": "" if key.startswith(hub.FREE) else dmap.get(key, ""), "selections": 0, "campaigns": 0, "live": 0,
                    "last": max([u["last_login_at"] or 0 for u in g["users"]] + [u["created_at"] or 0 for u in g["users"]] or [0]),
                    "open_n": 0, "open_sar": 0, "approved_sar": 0, "oldest_open": None, "unpriced": 0}
    with db.connect() as conn:
        if ids:
            for s in conn.execute("SELECT code_id, updated_at FROM selections WHERE code_id IN (%s) AND archived_at IS NULL AND deleted_at IS NULL" % marks, ids):
                f = out[codes[s["code_id"]]]
                f["selections"] += 1
                f["last"] = max(f["last"], s["updated_at"] or 0)
            for k in conn.execute("SELECT code_id, status, updated_at FROM campaigns WHERE code_id IN (%s)" % marks, ids):
                f = out[codes[k["code_id"]]]
                f["campaigns"] += 1
                f["live"] += 1 if k["status"] == "live" else 0
                f["last"] = max(f["last"], k["updated_at"] or 0)
            year = db.now() - 365 * DAY
            for r in conn.execute("SELECT code_id, at, handled_at, value_sar, approved_sar, quote_set_at FROM requests WHERE code_id IN (%s)" % marks, ids):
                f = out[codes[r["code_id"]]]
                f["last"] = max(f["last"], r["at"] or 0)
                if r["approved_sar"] is not None:
                    if (r["quote_set_at"] or r["at"] or 0) >= year:
                        f["approved_sar"] += r["approved_sar"] or 0
                elif r["handled_at"] is None or r["value_sar"]:
                    f["open_n"] += 1
                    f["open_sar"] += r["value_sar"] or 0
                    f["unpriced"] += 0 if r["value_sar"] else 1
                    f["oldest_open"] = min(f["oldest_open"] or r["at"], r["at"])
    return out, dmap


def _credit_zero(users):
    import portal
    live = [u for u in users if u["status"] == "active" and u["code_id"] is not None]
    return bool(live) and all(portal.balance(u["code_id"]) <= 0 for u in live)


def auto_stage(f, now):
    """The stage the data says."""
    if f["selections"] == 0 and f["campaigns"] == 0 and f["open_n"] == 0 and not f["users"]:
        return "lead"
    if f["live"] == 0 and f["last"] and now - f["last"] > DORMANT_DAYS * DAY and (f["campaigns"] or f["selections"]):
        return "dormant"
    if f["campaigns"] >= 2:
        return "repeat"
    if f["live"]:
        return "active"
    if f["open_n"]:
        return "quote"
    if f["selections"] or f["campaigns"]:
        return "engaged"
    return "lead"


def health(f, row, now):
    """(grade, reason). grade: good | moderate | low | none. The worst signal decides."""
    sig = []                                                    # (rank 0 good, 1 moderate, 2 low, text)
    if not f["users"] and not f["last"]:
        return "none", "No activity yet."
    days = (now - f["last"]) // DAY if f["last"] else None
    if days is not None:
        sig.append((0 if days < 14 else 1 if days <= 45 else 2,
                    "Active today." if days < 1 else "Last active %d day%s ago." % (days, "" if days == 1 else "s")))
    if row.get("next_due") and row.get("next_step") and row["next_due"] < _today(now):
        late = max(1, (_today(now) - row["next_due"]) // DAY)
        sig.append((2, "Next step is %d day%s late." % (late, "" if late == 1 else "s")))
    wait = [u for u in f["users"] if u["status"] == "pending" and not (("held_at" in u.keys()) and u["held_at"])]
    if wait:
        old = min(u["created_at"] or now for u in wait)
        sig.append((1 if now - old > DAY else 0, "%d sign-up%s waiting for approval." % (len(wait), "" if len(wait) == 1 else "s")))
    if f["oldest_open"] and now - f["oldest_open"] > 5 * DAY:
        sig.append((1, "A quote has waited %d days." % ((now - f["oldest_open"]) // DAY)))
    if _credit_zero(f["users"]):
        sig.append((1, "Every account is out of credits."))
    worst = max(s[0] for s in sig) if sig else 0
    bad = [s[1] for s in sorted(sig, key=lambda s: -s[0]) if s[0] >= 1][:2]
    return ("good" if worst == 0 else "moderate" if worst == 1 else "low"), (" ".join(bad) if bad else (sig[0][1] if sig else ""))


def _today(now):
    import time
    t = time.localtime(now)
    return int(time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1)))


def _meta():
    with db.connect() as conn:
        return {r["key"]: r for r in conn.execute("SELECT * FROM companies")}


def _mine_prospect(role, a, m):
    if role == "admin":
        return True
    em = (a["email"] or "").lower()
    return (m["kam"] or "").lower() == em or (m["created_by"] or "").lower() == em


def rows(role, a):
    """The table: every company this viewer may see, with stage, health and the numbers."""
    ensure()
    now = db.now()
    facts, dmap = _facts(role, a)
    meta = _meta()
    out = []
    for key, f in facts.items():
        m = meta.get(key)
        mrow = dict(m) if m else {}
        auto = auto_stage(f, now)
        stage, ovr = auto, False
        if mrow.get("stage_override") in STAGES and mrow.get("override_from") == auto:
            stage, ovr = mrow["stage_override"], True
        grade, why = health(f, mrow, now)
        kam = f["kam"] or (mrow.get("kam") or "")
        waiting = sum(1 for u in f["users"] if u["status"] == "pending" and not (("held_at" in u.keys()) and u["held_at"]))
        blocked = sum(1 for u in f["users"] if (u["status"] == "suspended") or (u["status"] == "pending" and ("held_at" in u.keys()) and u["held_at"]))
        out.append({"key": key, "name": mrow.get("name") or f["name"], "domain": f["domain"], "prospect": False,
                    "kam": {"email": kam, "name": hub._kam_name(kam) if kam else ""},
                    "stage": stage, "stage_auto": auto, "stage_override": ovr, "health": grade, "why": why,
                    "people": len(f["users"]), "waiting": waiting, "blocked": blocked, "selections": f["selections"], "campaigns": f["campaigns"],
                    "live": f["live"], "open_n": f["open_n"], "open_sar": f["open_sar"], "unpriced": f["unpriced"], "approved_sar": f["approved_sar"],
                    "last": f["last"] or None, "next_step": mrow.get("next_step") or "", "next_due": mrow.get("next_due"),
                    "overdue": bool(mrow.get("next_step") and mrow.get("next_due") and mrow["next_due"] < _today(now))})
    for key, m in meta.items():
        if key in facts or not m["is_prospect"] or not _mine_prospect(role, a, m):
            continue
        mrow = dict(m)
        kam = mrow.get("kam") or ""
        out.append({"key": key, "name": mrow["name"] or key, "domain": mrow["domain"] or key, "prospect": True,
                    "kam": {"email": kam, "name": hub._kam_name(kam) if kam else ""}, "stage": "lead", "stage_auto": "lead", "stage_override": False,
                    "health": "none", "why": "No activity yet.", "people": 0, "waiting": 0, "blocked": 0, "selections": 0, "campaigns": 0, "live": 0,
                    "open_n": 0, "open_sar": 0, "unpriced": 0, "approved_sar": 0, "last": mrow.get("created_at"),
                    "next_step": mrow.get("next_step") or "", "next_due": mrow.get("next_due"),
                    "overdue": bool(mrow.get("next_step") and mrow.get("next_due") and mrow["next_due"] < _today(now))})
    out.sort(key=lambda r: ((r["name"] or "").lower()))
    return {"rows": out, "stages": [{"key": s, "label": STAGE_LABEL[s]} for s in STAGES], "role": role}


def row(role, a, key):
    for r in rows(role, a)["rows"]:
        if r["key"] == key:
            return r
    return None


# ----------------------------------------------------------------- the actions --

def _can(role, a, key):
    return row(role, a, key) is not None


def set_fields(role, a, key, fields):
    """Next step, due date, stage override ('' = back to the data's stage). (code, {ok, message, row})."""
    import history
    ensure()
    r = row(role, a, key)
    if r is None:
        return 404, {"ok": False, "message": "That company is not in your list."}
    history.set_actor(a["email"])
    now = db.now()
    with history.tracked("company", key, "Updated " + (r["name"] or key)):
        with db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO companies (key, name, domain, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                         (key, r["name"], r["domain"], a["email"], now, now))
            if "next_step" in fields:
                conn.execute("UPDATE companies SET next_step = ? WHERE key = ?", ((fields["next_step"] or "").strip()[:200], key))
            if "next_due" in fields:
                v = fields["next_due"]
                try:
                    v = int(v) if v not in (None, "") else None
                except (TypeError, ValueError):
                    v = None
                conn.execute("UPDATE companies SET next_due = ? WHERE key = ?", (v, key))
            if "stage" in fields:
                st = (fields["stage"] or "").strip().lower()
                if st in STAGES:
                    conn.execute("UPDATE companies SET stage_override = ?, override_from = ? WHERE key = ?", (st, r["stage_auto"], key))
                else:
                    conn.execute("UPDATE companies SET stage_override = NULL, override_from = NULL WHERE key = ?", (key,))
            conn.execute("UPDATE companies SET updated_at = ? WHERE key = ?", (now, key))
    return 200, {"ok": True, "message": "Saved.", "row": row(role, a, key)}


def add_note(role, a, key, text, kind="note"):
    ensure()
    text = (text or "").strip()
    if not text or len(text) > 2000:
        return 400, {"ok": False, "message": "Write a note of up to 2000 characters."}
    if not _can(role, a, key):
        return 404, {"ok": False, "message": "That company is not in your list."}
    with db.connect() as conn:
        cur = conn.execute("INSERT INTO company_notes (key, author, text, kind, at) VALUES (?,?,?,?,?)",
                           (key, a["email"], text, "call" if kind == "call" else "note", db.now()))
    return 200, {"ok": True, "id": cur.lastrowid, "notes": notes(key)}


def notes(key, limit=60):
    ensure()
    with db.connect() as conn:
        rows_ = conn.execute("SELECT id, author, text, kind, at FROM company_notes WHERE key = ? ORDER BY at DESC, id DESC LIMIT ?", (key, limit)).fetchall()
    return [{"id": r["id"], "author": hub._kam_name(r["author"]) if r["author"] else "", "text": r["text"], "kind": r["kind"], "at": r["at"]} for r in rows_]


def quotes(role, a, key):
    """The quote requests of this company with the money typed so far."""
    ensure()
    groups, _, _ = hub._groups(role, a)
    g = groups.get(key)
    if g is None:
        return []
    ids = [u["code_id"] for u in g["users"] if u["code_id"] is not None]
    if not ids:
        return []
    with db.connect() as conn:
        rs = conn.execute("SELECT id, at, name, selection_name, selection, handled_at, value_sar, approved_sar, quote_set_by, quote_set_at FROM requests "
                          "WHERE code_id IN (%s) ORDER BY at DESC" % ",".join("?" * len(ids)), ids).fetchall()
    out = []
    for r in rs:
        try:
            n = len(json.loads(r["selection"] or "[]"))
        except ValueError:
            n = 0
        out.append({"id": r["id"], "at": r["at"], "who": r["name"] or "", "selection": r["selection_name"] or "", "creators": n,
                    "handled": bool(r["handled_at"]), "value_sar": r["value_sar"], "approved_sar": r["approved_sar"],
                    "set_by": hub._kam_name(r["quote_set_by"]) if r["quote_set_by"] else "", "set_at": r["quote_set_at"]})
    return out


def set_quote(role, a, rid, value, approved):
    """Type the quote's value and, when the client approved it, the approved value. Blank clears. (code, body)."""
    ensure()

    def num(v):
        if v in (None, ""):
            return None
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            raise ValueError("Enter a whole number of SAR.")
        if n < 0 or n > 50_000_000:
            raise ValueError("That amount looks wrong.")
        return n
    try:
        value, approved = num(value), num(approved)
    except ValueError as e:
        return 400, {"ok": False, "message": str(e)}
    with db.connect() as conn:
        r = conn.execute("SELECT id, code_id FROM requests WHERE id = ?", (int(rid or 0),)).fetchone()
    if r is None:
        return 404, {"ok": False, "message": "That quote is gone."}
    groups, _, _ = hub._groups(role, a)
    mine = any(u["code_id"] == r["code_id"] for g in groups.values() for u in g["users"])
    if not mine:
        return 403, {"ok": False, "message": "Not one of your clients."}
    with db.connect() as conn:
        conn.execute("UPDATE requests SET value_sar = ?, approved_sar = ?, quote_set_by = ?, quote_set_at = ? WHERE id = ?",
                     (value, approved, a["email"], db.now(), r["id"]))
    return 200, {"ok": True, "message": "Saved."}


def set_person(role, a, uid, decision_maker):
    ensure()
    g, _, _ = hub._groups(role, a)
    for grp in g.values():
        for u in grp["users"]:
            if u["id"] == int(uid or 0):
                with db.connect() as conn:
                    conn.execute("UPDATE users SET decision_maker = ? WHERE id = ?", (1 if decision_maker else 0, u["id"]))
                return 200, {"ok": True}
    return 404, {"ok": False, "message": "Not one of your clients."}


def add_prospect(role, a, name, domain, kam="", next_step="", next_due=None):
    import history
    ensure()
    name = (name or "").strip()[:120]
    d = _norm_domain(domain)
    if not name or not d:
        return 400, {"ok": False, "message": "Add the company name and its website domain (like avalonpharma.com)."}
    if d in hub.staff_domains():
        return 400, {"ok": False, "message": "That is a HelloVoice or BlueHolding domain."}
    if any(r["key"] == d for r in rows(role, a)["rows"]):
        return 409, {"ok": False, "message": "That company is already in the list."}
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE domain = ? AND deleted_at IS NULL LIMIT 1", (d,)).fetchone():
            return 409, {"ok": False, "message": "People from that domain already have accounts. Ask an admin to assign it."}
    if role != "admin":
        kam = a["email"]
    elif kam and not hub._valid_kam(kam):
        kam = ""
    history.set_actor(a["email"])
    now = db.now()
    try:
        due = int(next_due) if next_due not in (None, "") else None
    except (TypeError, ValueError):
        due = None
    with history.tracked("company", d, "Added prospect " + name):
        with db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO companies (key, name, domain, kam, next_step, next_due, is_prospect, created_by, created_at, updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)", (d, name, d, (kam or "").lower(), (next_step or "").strip()[:200], due, 1, a["email"], now, now))
    return 200, {"ok": True, "message": name + " is in the list as a lead.", "key": d}
