"""Advertising licences: Saudi Mawthooq (GAMR), the UAE Advertiser Permit
(UAE Media Council) and Egypt's media licence (Supreme Council for Media
Regulation).

A licence starts as a *claim* read off the creator's own bio (or typed by an
admin), and becomes *verified* only when someone on the team has checked the
number on the regulator's portal. Clients see both, labelled for what they
are: "in bio" is the creator's own statement, "verified" is ours.

    claimed   number (or the word) found in the bio, not checked yet
    verified  checked on the regulator's portal by the team, with the date
    rejected  checked and not valid (never shown to clients)
    expired   past its expiry date (shown to admins only)

Nothing here scrapes the regulators; there is no public bulk lookup. The bios
come from the profile analyses already stored (Apify or the PDF reports).
"""
import json
import re
import time

import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS creator_licences (
  code        TEXT NOT NULL,
  country     TEXT NOT NULL,              -- SA | AE | EG
  number      TEXT,
  status      TEXT NOT NULL DEFAULT 'claimed',
  source      TEXT NOT NULL DEFAULT 'bio', -- bio | admin | creator
  evidence    TEXT,                       -- the bio words it was read from
  expires_on  TEXT,                       -- YYYY-MM-DD
  checked_at  INTEGER,
  checked_by  TEXT,
  note        TEXT,
  priority    INTEGER NOT NULL DEFAULT 0, -- 1 = on the confirmed list: verify these first
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (code, country)
);
"""

COUNTRY = {"SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt"}
NAME = {"SA": "Mawthooq", "AE": "UAE Advertiser Permit", "EG": "SCMR licence"}
PORTAL = {"SA": "https://gmedia.gov.sa", "AE": "https://uaemc.gov.ae", "EG": "https://scm.gov.eg"}

# Words that name one regulator: enough on their own.
STRONG = {
    "SA": re.compile(r"موثوق|موثّق|maw?th?oo?q|mawthouq|mauthooq|\bgamr\b|\bgcam\b|الهيئة العامة (?:ل)?(?:تنظيم )?الإعلام|هيئة الإعلام", re.I),
    "AE": re.compile(r"advertiser permit|media council|\bnmc\b|uae ?permit|مجلس الإمارات للإعلام|المجلس الوطني للإعلام|تصريح (?:ال)?معلن", re.I),
    "EG": re.compile(r"المجلس الأعلى لتنظيم الإعلام|\bscmr\b|supreme council for media", re.I),
}
# Words that say "licence" without saying whose: counted only with a number,
# and placed by where the creator is.
WEAK = re.compile(r"ترخيص|رخصة|رقم الترخيص|licen[cs]e|license no|lic\.? ?no|permit", re.I)
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
NUMBER = re.compile(r"(?<![\d+])(\d{4,12})(?!\d)")
PHONE = re.compile(r"^(?:05|5\d{8}|9665|009|00|01[0125]\d{8}|971|20)")
PLACE = {"SA": re.compile(r"saudi|ksa|riyadh|jeddah|dammam|khobar|makkah|mecca|madinah|السعودية|الرياض|جدة", re.I),
         "AE": re.compile(r"uae|emirates|dubai|abu dhabi|sharjah|الإمارات|دبي|أبوظبي", re.I),
         "EG": re.compile(r"egypt|cairo|alexandria|giza|مصر|القاهرة|الإسكندرية", re.I)}


def init():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _number_near(text, at):
    """The licence number: the first plausible number after the keyword, else
    before it, skipping anything that reads as a phone number."""
    after, before = NUMBER.findall(text[at:at + 60]), NUMBER.findall(text[max(0, at - 30):at])
    for n in after + before[::-1]:
        if not PHONE.match(n) or len(n) <= 7:
            return n
    return None


def read_bio(bio, place=""):
    """[(country, number or None, evidence, strong)] claimed in one bio. Strong = the bio names
    the regulator; weak = a "licence" word with a number, placed by where the creator is."""
    text = (bio or "").translate(DIGITS)
    if not text.strip():
        return []
    out = {}
    for cc, rx in STRONG.items():
        m = rx.search(text)
        if m:
            out[cc] = (_number_near(text, m.end()), text[max(0, m.start() - 20):m.end() + 40].strip(), True)
    if not out:
        m = WEAK.search(text)
        num = _number_near(text, m.end()) if m else None
        if m and num:
            where = next((cc for cc, rx in PLACE.items() if rx.search(place or "")), None)
            if where:
                out[where] = (num, text[max(0, m.start() - 20):m.end() + 40].strip(), False)
    return [(cc, v[0], v[1][:160], v[2]) for cc, v in out.items()]


def scan(confirmed_codes=None):
    """Read every stored bio and record what it claims. A licence the team has
    already verified, rejected or typed in is never overwritten by a bio."""
    found, touched = 0, set()
    now = db.now()
    with db.connect() as conn:
        places = {r["code"]: " ".join(filter(None, [r["city"], r["nationality"]]))
                  for r in conn.execute("SELECT code, city, nationality FROM creators WHERE active = 1")}
        current = {(r["code"], r["country"]): r for r in conn.execute("SELECT * FROM creator_licences")}
        for r in conn.execute("SELECT code, data FROM creator_analysis"):
            if r["code"] not in places:
                continue
            try:
                bio = json.loads(r["data"]).get("bio") or ""
            except ValueError:
                continue
            for cc, num, ev, strong in read_bio(bio, places[r["code"]]):
                key = (r["code"], cc)
                old = current.get(key)
                if old is not None and (old["status"] != "claimed" or old["source"] not in ("bio", "bio-weak")):
                    continue
                if key in touched and not num:
                    continue
                conn.execute("INSERT INTO creator_licences (code, country, number, status, source, evidence, updated_at) "
                             "VALUES (?,?,?,?,?,?,?) ON CONFLICT(code, country) DO UPDATE SET "
                             "number = COALESCE(excluded.number, number), evidence = excluded.evidence, source = excluded.source, "
                             "updated_at = excluded.updated_at",
                             (r["code"], cc, num, "claimed", "bio" if strong else "bio-weak", ev, now))
                touched.add(key)
                found += 1
        if confirmed_codes is not None:
            conn.execute("UPDATE creator_licences SET priority = 0")
            for code in confirmed_codes:
                conn.execute("UPDATE creator_licences SET priority = 1 WHERE code = ?", (code,))
    db.set_setting("licence_scanned_at", now)        # its own connection: not inside the one above
    return {"claims": len(touched), "creators": len({k[0] for k in touched})}


def expire_due():
    """A verified licence past its expiry date stops being shown to clients."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    with db.connect() as conn:
        conn.execute("UPDATE creator_licences SET status = 'expired', updated_at = ? "
                     "WHERE status = 'verified' AND expires_on IS NOT NULL AND expires_on < ?", (db.now(), today))


def for_roster():
    """{code: [{country, name, number, status}]} for the client pages: claimed
    and verified only, verified first."""
    expire_due()
    out = {}
    with db.connect() as conn:
        for r in conn.execute("SELECT code, country, number, status, checked_at FROM creator_licences "
                              "WHERE (status = 'verified' OR (status = 'claimed' AND source != 'bio-weak')) ORDER BY status = 'verified' DESC, country"):
            out.setdefault(r["code"], []).append({
                "country": r["country"], "name": NAME[r["country"]], "number": r["number"] or "",
                "status": r["status"],
                "checked": time.strftime("%Y-%m-%d", time.gmtime(r["checked_at"])) if r["checked_at"] else None})
    return out


def listing(status="", country="", q=""):
    where, args = [], []
    if status:
        where.append("l.status = ?"); args.append(status)
    if country:
        where.append("l.country = ?"); args.append(country)
    if q:
        where.append("(c.name LIKE ? OR c.code LIKE ? OR l.number LIKE ?)"); args += ["%" + q + "%"] * 3
    sql = ("SELECT l.*, c.name, c.handle, c.platform, c.city FROM creator_licences l JOIN creators c ON c.code = l.code "
           + ("WHERE " + " AND ".join(where) + " " if where else "")
           + "ORDER BY l.status = 'claimed' DESC, l.priority DESC, c.name")
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def counts():
    with db.connect() as conn:
        rows = conn.execute("SELECT status, country, priority, COUNT(*) n FROM creator_licences GROUP BY status, country, priority").fetchall()
    out = {"total": 0, "by_status": {}, "by_country": {}, "priority_claimed": 0}
    for r in rows:
        out["total"] += r["n"]
        out["by_status"][r["status"]] = out["by_status"].get(r["status"], 0) + r["n"]
        out["by_country"][r["country"]] = out["by_country"].get(r["country"], 0) + r["n"]
        if r["priority"] and r["status"] == "claimed":
            out["priority_claimed"] += r["n"]
    return out


def update(code, country, status, number=None, expires_on=None, note=None, who=""):
    """An admin's decision on one licence (or a licence typed in by hand)."""
    if country not in COUNTRY or status not in ("claimed", "verified", "rejected", "expired"):
        return False
    number = re.sub(r"\s+", "", str(number or "").translate(DIGITS))[:20] or None
    expires_on = expires_on if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(expires_on or "")) else None
    now = db.now()
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM creators WHERE code = ?", (code,)).fetchone() is None:
            return False
        conn.execute("INSERT INTO creator_licences (code, country, number, status, source, expires_on, checked_at, checked_by, note, updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(code, country) DO UPDATE SET "
                     "number = COALESCE(excluded.number, number), status = excluded.status, "
                     "source = CASE WHEN source IN ('bio', 'bio-weak') AND excluded.status = 'claimed' THEN source ELSE 'admin' END, "
                     "expires_on = COALESCE(excluded.expires_on, expires_on), checked_at = excluded.checked_at, "
                     "checked_by = excluded.checked_by, note = COALESCE(excluded.note, note), updated_at = excluded.updated_at",
                     (code, country, number, status, "admin", expires_on,
                      now if status in ("verified", "rejected") else None, who or None, (note or None), now))
    return True


# --------------------------------------------------------------- admin page --

STATUS_LABEL = {"claimed": "In bio · to verify", "weak": "Possible · admin only", "verified": "Verified", "rejected": "Rejected", "expired": "Expired"}


def page_html(f):
    """The review list: claims first, the confirmed creators at the top."""
    import views
    e, u = views.e, views.u
    status, country, q = f.get("status", "claimed"), f.get("country", ""), (f.get("q") or "").strip()
    rows = listing(status if status != "all" else "", country, q)
    c = counts()
    by = c["by_status"]
    stats = "".join(
        "<div class='stat'><b>%d</b><span>%s</span></div>" % (n, lab) for n, lab in (
            (by.get("claimed", 0), "In bio · to verify"), (c["priority_claimed"], "of them on the confirmed list"),
            (by.get("verified", 0), "Verified"), (by.get("rejected", 0) + by.get("expired", 0), "Rejected or expired")))
    def opt(val, cur, lab):
        return "<option value='%s'%s>%s</option>" % (e(val), " selected" if val == cur else "", e(lab))
    filt = ("<form class='lic-filter' method='get' action='" + u("/licences") + "'>"
            "<select name='status'>" + "".join(opt(v, status, l) for v, l in (("claimed", "To verify"), ("verified", "Verified"),
                                                                              ("rejected", "Rejected"), ("expired", "Expired"), ("all", "All"))) + "</select>"
            "<select name='country'>" + opt("", country, "All countries") + "".join(opt(k, country, NAME[k]) for k in COUNTRY) + "</select>"
            "<input name='q' value='" + e(q) + "' placeholder='Name, code or number'/><button class='btn tiny'>Show</button></form>"
            "<form method='post' action='" + u("/licences/scan") + "'><button class='btn tiny ghost'>Re-read all bios</button></form>")
    body = []
    for r in rows:
        cc = r["country"]
        body.append(
            "<tr" + (" class='prio'" if r["priority"] else "") + "><td><b>" + e(r["name"]) + "</b><br><code>" + e(r["code"]) + "</code>"
            + (" <span class='star' title='On the confirmed list'>★</span>" if r["priority"] else "") + "</td>"
            "<td>" + e(r["handle"] or "") + "<br><small>" + e(r["platform"] or "") + " · " + e(r["city"] or "") + "</small></td>"
            "<td>" + e(NAME[cc]) + "<br><a href='" + PORTAL[cc] + "' target='_blank' rel='noopener'>Check on the portal ↗</a></td>"
            "<td class='ev'>" + e(r["evidence"] or "—") + "</td>"
            "<td><span class='lic-st lic-st--" + e(r["status"]) + "'>" + e(STATUS_LABEL["weak"] if r["status"] == "claimed" and r["source"] == "bio-weak" else STATUS_LABEL.get(r["status"], r["status"])) + "</span>"
            + ("<br><small>checked " + time.strftime("%d %b %Y", time.gmtime(r["checked_at"])) + (" · " + e(r["checked_by"]) if r["checked_by"] else "") + "</small>" if r["checked_at"] else "") + "</td>"
            "<td><form class='lic-act' method='post' action='" + u("/licences/save") + "'>"
            "<input type='hidden' name='code' value='" + e(r["code"]) + "'/><input type='hidden' name='country' value='" + cc + "'/>"
            "<input name='number' value='" + e(r["number"] or "") + "' placeholder='Licence no.' size='10'/>"
            "<input type='date' name='expires_on' value='" + e(r["expires_on"] or "") + "' title='Expiry date'/>"
            "<button class='btn tiny' name='status' value='verified'>Verified</button><button name='status' value='rejected' class='btn tiny ghost'>Not valid</button>"
            + ("<button name='status' value='claimed' class='btn tiny ghost'>Back to bio claim</button>" if r["status"] != "claimed" else "")
            + "</form></td></tr>")
    table = ("<table class='lic-table' data-nocols><thead><tr><th>Creator</th><th>Account</th><th>Licence</th><th>From the bio</th><th>Status</th><th>Decision</th></tr></thead><tbody>"
             + ("".join(body) or "<tr><td colspan='6'>Nothing here.</td></tr>") + "</tbody></table>")
    css = ("<style>.lic-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:0 0 18px}"
           ".lic-stats .stat{background:#fff;border-radius:16px;padding:14px 16px}.lic-stats b{display:block;font:400 34px/1 Bebasneue,Arial;}"
           ".lic-stats span{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#555}"
           ".lic-bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:0 0 14px}.lic-bar form{margin:0}.lic-filter{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.lic-filter select,.lic-filter input{width:auto;min-width:150px;margin:0}"
           ".lic-table{width:100%;border-collapse:collapse;background:#fff;border-radius:16px;overflow:hidden;font-size:13px}"
           ".lic-table th,.lic-table td{padding:10px 12px;border-top:1px solid rgba(18,18,18,.08);text-align:left;vertical-align:top}"
           ".lic-table thead th{background:#faf8f4;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#555;border-top:0}"
           ".lic-table tr.prio{background:#fbffe6}.lic-table .ev{max-width:320px;color:#383838}.star{color:#b9a000}"
           ".lic-st{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#efece6}"
           ".lic-st--verified{background:#e7f7ed;color:#14884a}.lic-st--rejected,.lic-st--expired{background:#fde9e9;color:#c01010}"
           ".lic-act{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0}.lic-act input{width:auto;padding:6px 8px;margin:0}.lic-table thead th{position:static}</style>")
    intro = ("<h1>Licences</h1><p class='lede'>Licences read from creators' own bios (Saudi Mawthooq, UAE Advertiser Permit, Egypt SCMR). "
             "Clients see <b>“In bio”</b> claims (the bio names the regulator) and <b>Verified</b> ones on the cards. "
             "<b>Possible</b> matches (a licence word and a number only) stay admin-only until you verify them; rejected and expired never show. "
             "Check each number on the regulator's portal, then mark it. ★ = on the confirmed list: do these first.</p>")
    return views.page("Licences", css + intro + "<div class='lic-stats'>" + stats + "</div><div class='lic-bar'>" + filt + "</div>" + table,
                      active="/roster")
