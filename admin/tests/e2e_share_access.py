"""Share-access test: every role opens shared selections through the real HTTP handler.

Runs inside a throwaway container with no network, on a COPY of the database. Nothing live is touched:
no schedulers start (main() is never called), and every write goes to the copy.
"""
import json, os, sys, threading, time, urllib.request, urllib.error

sys.path.insert(0, "/app/admin")
os.chdir("/app")
import db
db.DB_PATH = "/work/catalogue.db"
import auth, server, portal
from http.server import ThreadingHTTPServer

server.BASE = ""
srv = ThreadingHTTPServer(("127.0.0.1", 8999), server.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)

EXP = db.now() + 3600


def staff(admin_id):
    return {"hv_admin": auth.sign(db.create_session(admin_id, 3600), server.SECRET)}


def client(code_id):
    """A pass as email sign-in issues it: code:expiry:device:e, on a device admitted to that code."""
    import secrets
    dev = secrets.token_urlsafe(24)
    dh = db.device_hash(dev)
    db.admit_device(db.get_code(code_id), dh, "127.0.0.1", "e2e")
    return {"hv_view": auth.sign("%d:%d:%s:e" % (code_id, EXP, dh), server.SECRET), "hv_dev": dev}


def get(path, cookies):
    req = urllib.request.Request("http://127.0.0.1:8999" + path)
    if cookies:
        req.add_header("Cookie", "; ".join("%s=%s" % kv for kv in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def open_sel(token, cookies):
    """(selection status, creators listed, prices given, cards status, cards returned)"""
    s, b = get("/api/selection?s=" + token, cookies)
    codes = b.get("codes") or [] if s == 200 else []
    if codes:
        cs, cb = get("/api/roster/cards?link=s:%s&codes=%s" % (token, ",".join(codes[:200])), cookies)
    else:
        cs, cb = get("/api/roster/cards?link=s:%s&codes=" % token, cookies)
    return s, len(codes), len(b.get("prices") or {}), cs, len(cb.get("cards") or [])


with db.connect() as c:
    sel = {r["id"]: r for r in c.execute("SELECT * FROM selections WHERE id IN (148, 26, 149)")}
    users = c.execute("SELECT * FROM users WHERE status = 'active' AND deleted_at IS NULL AND code_id IS NOT NULL").fetchall()
fak_owner = sel[26]["code_id"]
fak_dom = next((u["domain"] for u in users if u["code_id"] == fak_owner), "")
colleague = next((u["code_id"] for u in users if u["domain"] == fak_dom and u["code_id"] != fak_owner), None)
staffdoms = {"blueholding.co.uk", "hellovoice.co.uk", "sawata.com.eg", fak_dom}
others = [u["code_id"] for u in users if (u["domain"] or "") not in staffdoms
          and not db.selection_granted(148, u["code_id"]) and not db.selection_granted(149, u["code_id"])]
stranger, camp_client, invitee = others[0], others[1], others[2]
inv_email = next(u["email"] for u in users if u["code_id"] == invitee)

# Fresh shares made the way the portal makes them, on the copy:
cid = db.create_campaign("E2E share test", code_id=camp_client, selection_id=149)      # campaign assigned to a client
db.invite_add(149, inv_email, "e2e")                                                   # email invite, then that person signs in
db.invite_claim(inv_email, invitee)

T148, T26, T149 = sel[148]["token"], sel[26]["token"], sel[149]["token"]
cases = [
    # (who, cookies, token, should open?)
    ("Owner admin (Abdelrahman) - Indomie", staff(2), T148, True),
    ("Admin (Omnia) - Fakeeh", staff(3), T26, True),
    ("KAM Mariam - Indomie (her company)", staff(4), T148, True),
    ("KAM Salma - Fakeeh (her company)", staff(6), T26, True),
    ("KAM Salma - Fakeeh V2 (her company)", staff(6), T149, True),
    ("KAM Salma - Indomie (NOT hers)", staff(6), T148, False),
    ("Client owner - Fakeeh", client(fak_owner), T26, True),
    ("Colleague, same company - Fakeeh", client(colleague), T26, True) if colleague else None,
    ("Granted person (Hossam) - Indomie", client(61), T148, True),
    ("Campaign client, new assignment - Fakeeh V2", client(camp_client), T149, True),
    ("Invited by email, then signed in - Fakeeh V2", client(invitee), T149, True),
    ("Unrelated client - Indomie", client(stranger), T148, False),
    ("Not signed in - Indomie", {}, T148, False),
]
fails = 0
print("%-48s %-6s %s" % ("WHO / SELECTION", "RESULT", "selection: status, creators, prices | cards: status, cards"))
for case in filter(None, cases):
    who, ck, tok, want = case
    s, n, p, cs, cn = open_sel(tok, ck)
    opened = s == 200 and n > 0 and cs == 200 and cn == n
    ok = opened == want
    fails += not ok
    print("%-48s %-6s %s, %d creators, %d prices | %s, %d cards" % (who, "PASS" if ok else "FAIL", s, n, p, cs, cn))
print("\n%d failed" % fails)
