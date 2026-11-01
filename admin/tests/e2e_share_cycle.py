"""The whole share cycle, through the real HTTP routes: make a selection, share it every way the portal and
admin offer, and check each recipient opens it with every creator, price and card. Then take access back.

Runs in a throwaway container with no network and no keys, on a COPY of the database (main() never runs, so no
scheduler, mail or push starts). Usage: python3 share_cycle_e2e.py (paths below match the container mounts).
"""
import json, os, secrets, sys, threading, time, urllib.parse, urllib.request, urllib.error

sys.path.insert(0, "/app/admin")
os.chdir("/app")
import db
db.DB_PATH = "/work/catalogue.db"
import auth, server, portal, hub
from http.server import ThreadingHTTPServer

server.BASE = ""
srv = ThreadingHTTPServer(("127.0.0.1", 8999), server.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)
ORIGIN = "http://127.0.0.1:8999"
EXP = db.now() + 3600


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OPEN = urllib.request.build_opener(NoRedirect)


def staff(admin_id):
    return {"hv_admin": auth.sign(db.create_session(admin_id, 3600), server.SECRET)}


def client(code_id):
    dev = secrets.token_urlsafe(24)
    dh = db.device_hash(dev)
    db.admit_device(db.get_code(code_id), dh, "127.0.0.1", "e2e")
    return {"hv_view": auth.sign("%d:%d:%s:e" % (code_id, EXP, dh), server.SECRET), "hv_dev": dev}


def call(method, path, cookies=None, body=None, form=False):
    data = None
    req = urllib.request.Request(ORIGIN + path, method=method)
    if body is not None:
        data = (urllib.parse.urlencode(body) if form else json.dumps(body)).encode()
        req.add_header("Content-Type", "application/x-www-form-urlencoded" if form else "application/json")
        req.add_header("Origin", ORIGIN)
    if cookies:
        req.add_header("Cookie", "; ".join("%s=%s" % kv for kv in cookies.items()))
    try:
        with OPEN.open(req, data, timeout=60) as r:
            raw, st, loc = r.read(), r.status, r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        raw, st, loc = e.read(), e.code, e.headers.get("Location", "")
    try:
        return st, json.loads(raw or b"{}"), loc
    except ValueError:
        return st, {}, loc


def opens(token, cookies, public=False):
    """'' when the selection opens with every creator, card (and price unless public); else what is wrong."""
    s, b, _ = call("GET", "/api/selection?s=" + token, cookies)
    if s != 200:
        return "selection refused (%s)" % s
    codes = b.get("codes") or []
    if not codes:
        return "no creators listed"
    if not public and len(b.get("prices") or {}) != len(codes):
        return "prices %d of %d" % (len(b.get("prices") or {}), len(codes))
    if public and b.get("prices"):
        return "public link shows prices"
    cs, cb, _ = call("GET", "/api/roster/cards?link=s:%s&codes=%s" % (token, ",".join(codes)), cookies)
    if cs != 200 or len(cb.get("cards") or []) != len(codes):
        return "cards %s, %d of %d" % (cs, len(cb.get("cards") or []), len(codes))
    return ""


def refused(token, cookies):
    s, _, _ = call("GET", "/api/selection?s=" + token, cookies)
    return "" if s in (401, 404) else "opened (%s) but should not" % s


# ------------------------------------------------------------------ setup --
with db.connect() as c:
    users = c.execute("SELECT * FROM users WHERE status = 'active' AND deleted_at IS NULL AND code_id IS NOT NULL").fetchall()
    base = c.execute("SELECT * FROM selections WHERE id = 149").fetchone()
owner = base["code_id"]                                                   # Fakeeh: KAM Salma by company domain
odom = next(u["domain"] for u in users if u["code_id"] == owner)
codes = json.loads(base["codes"])
taken = {"blueholding.co.uk", "hellovoice.co.uk", odom}
def new_person():
    """A fresh signed-up account on its own company domain, unrelated to anyone (so no team sharing)."""
    tag = secrets.token_hex(4)
    email = "buyer-%s@e2e-%s.com" % (tag, tag)
    cid = db.create_code(auth.hash_code(secrets.token_hex(8)), "e2e", "Client: " + email)
    cid = cid if isinstance(cid, int) else cid["id"]
    with db.connect() as c:
        c.execute("INSERT INTO users (email, domain, code_id, status, created_at, name, company) VALUES (?,?,?,?,?,?,?)",
                  (email, email.split("@")[1], cid, "active", db.now(), "E2E " + tag, "E2E Co " + tag))
    with db.connect() as c:
        return c.execute("SELECT * FROM users WHERE code_id = ?", (cid,)).fetchone()


pool = []


class _R:
    def __next__(self):
        pool.append(new_person())
        return pool[-1]


R = _R()


def fresh_selection(name, code_id=owner):
    sid = db.save_selection(None, name, codes, {}, None, None, code_id=code_id)
    return db.selection(sid)


ADMIN, KAM_SALMA, KAM_MARIAM = staff(2), staff(6), staff(4)
OWNER = client(owner)
sel = fresh_selection("E2E cycle")
T = sel["token"]
results = []


def check(step, problem):
    results.append((step, problem))
    print("%-4s %-70s %s" % ("PASS" if not problem else "FAIL", step, problem), flush=True)


# 1. KAM follows the company
k = db.effective_kam("selection", sel["id"])
check("New selection under Fakeeh follows the company KAM (Salma)", "" if k == "salma.mohamed@blueholding.co.uk" else "KAM is %r" % k)
row = hub._sel_row(sel, hub._item_kams())
check("Clients hub shows Salma on it, marked as following the company",
      "" if row["kam"] == "salma.mohamed@blueholding.co.uk" and row["kam_auto"] else "hub row %r / auto %r" % (row["kam"], row["kam_auto"]))

# 2. The people who have it without any share
check("Owner admin opens it", opens(T, ADMIN))
check("Company KAM (Salma) opens it", opens(T, KAM_SALMA))
check("Another company's KAM (Mariam) is refused", refused(T, KAM_MARIAM))
check("Client owner opens it", opens(T, OWNER))

# 3. Every share route, each to a person who had no access before
for label, who_cookies in (("Admin", ADMIN), ("KAM Salma", KAM_SALMA), ("Client owner", OWNER)):
    r = next(R)
    pre = refused(T, client(r["code_id"]))
    s, b, _ = call("POST", "/api/selection/invite", who_cookies, {"token": T, "do": "add", "email": r["email"]})
    check("%s invites an existing account from the Share panel" % label,
          pre or ("invite answered %s %s" % (s, b.get("message", ""))) if s != 200 else (pre or opens(T, client(r["code_id"]))))

new_email = "e2e-new-%s@example-e2e.com" % secrets.token_hex(3)
s, b, _ = call("POST", "/api/selection/invite", ADMIN, {"token": T, "do": "add", "email": new_email})
newcode = db.create_code(auth.hash_code(secrets.token_hex(8)), "e2e", "Client: " + new_email)
newcode = newcode if isinstance(newcode, int) else (newcode["id"] if newcode is not None else None)
if s == 200 and newcode:
    with db.connect() as c:
        c.execute("INSERT INTO users (email, domain, code_id, status, created_at) VALUES (?,?,?,?,?)",
                  (new_email, new_email.split("@")[1], newcode, "active", db.now()))
    db.invite_claim(new_email, newcode)                                  # what sign-in does for a new address
    check("Invite to a NEW email, who then signs up", opens(T, client(newcode)))
else:
    check("Invite to a NEW email, who then signs up", "invite %s / account %r" % (s, newcode))

r = next(R)
s, b, _ = call("POST", "/api/selection/request-access", client(r["code_id"]), {"token": T})
rid = None
with db.connect() as c:
    q = c.execute("SELECT id FROM access_requests WHERE selection_id = ? AND code_id = ? AND status = 'pending'", (sel["id"], r["code_id"])).fetchone()
    rid = q["id"] if q else None
if rid:
    s2, _, loc = call("POST", "/access-requests", ADMIN, {"id": rid, "do": "grant"}, form=True)
    check("Request access, then the admin grants it", opens(T, client(r["code_id"])) if "ok=" in loc else "grant answered %s %s" % (s2, loc))
else:
    check("Request access, then the admin grants it", "request answered %s %s" % (s, b))

r = next(R)
rid = db.access_request_add(sel["id"], r["code_id"], r["email"], r["name"], r["company"])[0]
s2, _, loc = call("POST", "/access-requests", KAM_SALMA, {"id": rid, "do": "grant"}, form=True)
check("Request access, then the company KAM grants it", opens(T, client(r["code_id"])) if "ok=" in loc else "grant answered %s %s" % (s2, loc))

# Hub share (the Clients hub "Share" box) needs a portal account behind the staff email.
for label, email in (("admin", "abdelrahman.ashraf@blueholding.co.uk"), ("KAM Salma", "salma.mohamed@blueholding.co.uk")):
    acct = portal.user_by_email(email)
    r = next(R)
    if acct is None or acct["code_id"] is None:
        check("Clients hub Share by %s" % label, "SKIP: %s has no portal account" % email)
        continue
    s, b, _ = call("POST", "/api/hub/share", client(acct["code_id"]), {"kind": "selection", "ref": sel["id"], "email": r["email"]})
    check("Clients hub Share by %s" % label, opens(T, client(r["code_id"])) if s == 200 and b.get("ok") else "hub share %s %s" % (s, b.get("message") or b))

# Campaign routes: assign a campaign to a client; share a campaign from the hub; invite to its dashboard.
camp = db.create_campaign("E2E cycle campaign", code_id=owner, selection_id=sel["id"])
k = db.campaign(camp)
r = next(R)
s, _, loc = call("POST", "/campaigns/assign", ADMIN, {"id": camp, "client": r["code_id"], "confirmed": "1", "tell": "1"}, form=True)
check("Assign the campaign to a client (Campaign > Setup)", opens(T, client(r["code_id"])) if "ok=" in loc else "assign answered %s %s" % (s, loc))
camp2 = db.create_campaign("E2E cycle campaign 2", code_id=owner, selection_id=sel["id"])
k2 = db.campaign(camp2)
r = next(R)
acct = portal.user_by_email("abdelrahman.ashraf@blueholding.co.uk")
if acct is not None and acct["code_id"] is not None:
    s, b, _ = call("POST", "/api/hub/share", client(acct["code_id"]), {"kind": "campaign", "ref": camp2, "email": r["email"]})
    check("Clients hub Share of the CAMPAIGN opens its selection", opens(T, client(r["code_id"])) if s == 200 and b.get("ok") else "hub share %s %s" % (s, b.get("message") or b))
r = next(R)
s, b, _ = call("POST", "/api/campaign/share", ADMIN, {"t": k2["token"], "action": "invite", "email": r["email"], "role": "edit"})
check("Campaign dashboard Share, EDIT role: opens its selection", opens(T, client(r["code_id"])) if s == 200 and b.get("ok", True) else "share %s %s" % (s, b))
r = next(R)
s, b, _ = call("POST", "/api/campaign/share", ADMIN, {"t": k2["token"], "action": "invite", "email": r["email"], "role": "view"})
check("Campaign dashboard Share, VIEW role: dashboard only, selection stays closed (by design)",
      refused(T, client(r["code_id"])) if s == 200 and b.get("ok", True) else "share %s %s" % (s, b))
r = next(R)
acct = portal.user_by_email("abdelrahman.ashraf@blueholding.co.uk")
s, b, _ = call("POST", "/api/hub/share", client(acct["code_id"]), {"kind": "campaign", "ref": camp2, "email": r["email"], "role": "view"})
check("Clients hub Share of the campaign, VIEW role: selection stays closed (by design)", refused(T, client(r["code_id"])))

# Public read-only link
db.public_link_set("selection", T, True)
check("Public read-only link: anyone sees creators and cards, no prices", opens(T, {}, public=True))
db.public_link_set("selection", T, False)
check("Public link switched off: anonymous refused again", refused(T, {}))

# Assign the selection itself to another client (Selection > Share > Assign to client)
s2sel = fresh_selection("E2E cycle assign")
r = next(R)
s, _, loc = call("POST", "/selections/assign", ADMIN, {"id": s2sel["id"], "client": r["code_id"], "confirmed": "1", "move_campaigns": "1", "tell": "1"}, form=True)
check("Assign to client (selection moves to them)", opens(s2sel["token"], client(r["code_id"])) if "ok=" in loc else "assign answered %s %s" % (s, loc))
nk = db.effective_kam("selection", s2sel["id"])
check("After the move its KAM follows the NEW company", "" if nk == db.company_kam(r["code_id"]) else "KAM %r, new company's %r" % (nk, db.company_kam(r["code_id"])))

# Negative and take-back
stranger = next(R)
check("Unrelated client is refused", refused(T, client(stranger["code_id"])))
first = pool[0]
s, b, _ = call("POST", "/api/selection/invite", ADMIN, {"token": T, "do": "remove", "email": first["email"]})
check("Invite removed: that person is refused again", refused(T, client(first["code_id"])) if s == 200 else "remove answered %s" % s)
check("Not signed in is refused", refused(T, {}))

bad = [x for x in results if x[1] and not x[1].startswith("SKIP")]
print("\n%d checks, %d failed, %d skipped" % (len(results), len(bad), sum(1 for x in results if x[1].startswith("SKIP"))))
