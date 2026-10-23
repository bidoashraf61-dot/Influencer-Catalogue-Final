"""Activity log for one client account (item 237, owner 2026-10-23): every dated thing the person did, or that was
done to their account, newest first, with the IP and the device. Owners and admins only: the Control Centre's
person menu (Companies) and the admin's Client accounts page. KAMs never see it.

Sources: events (by the account's code), sign-in code emails (otp, by email), credit movements, staff changes to the
account (history), and the sign-up itself. Repeats of the same thing from the same device within 30 minutes (a
dashboard left open records a view on every refresh) are folded into one line with a count.
"""
import re

import db

PAGE = 100
FOLD = 30 * 60
RAW = 3000                     # raw rows read per source and page (folding turns many views into one line)

GROUPS = [("signin", "Sign-ins"), ("browse", "Browsing"), ("ai", "AI"), ("work", "Work"), ("account", "Account")]
# event kind -> (group, what the line says)
KINDS = {
    "signup": ("signin", "Signed up"),
    "unlock_ok": ("signin", "Signed in"),
    "unlock_fail": ("signin", "Sign-in refused"),
    "view": ("browse", "Opened"),
    "shortlist": ("browse", "Added a creator to a selection"),
    "unlock_toggle": ("browse", "Turned names on or off"),
    "brief": ("ai", "Wrote a brief with Helvi"),
    "chat": ("ai", "Asked Helvi"),
    "chat_action": ("ai", "Helvi made a change"),
    "ideas": ("ai", "Asked for content ideas"),
    "request": ("work", "Asked for a quote"),
    "selection_deleted": ("work", "Deleted a selection"),
    "brief_deleted": ("work", "Deleted a brief"),
    "mail_sent": ("work", "Emailed a report"),
    "mail_failed": ("work", "A report email failed"),
}
FAIL = {"unknown": "unknown link or code", "device_limit": "too many devices", "revoked": "access revoked",
        "expired": "access expired", "other link": "link belongs to someone else"}
VIEW = {"campaign": "campaign dashboard", "analysis": "creator analysis", "public": "shared link", "selection": "selection"}


def device(ua):
    """'iPhone · Safari' from a user agent; '' when there is none."""
    ua = ua or ""
    if not ua:
        return ""
    if "curl/" in ua or "python" in ua.lower():
        return "Script"
    os_ = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua
           else "Windows" if "Windows" in ua else "Mac" if "Mac OS X" in ua else "Linux" if "Linux" in ua else "Other")
    br = ("Edge" if "Edg/" in ua else "Samsung" if "SamsungBrowser" in ua else "Firefox" if ("Firefox/" in ua or "FxiOS" in ua)
          else "Chrome" if ("Chrome/" in ua or "CriOS" in ua) else "Safari" if "Safari/" in ua else "App")
    return os_ + " · " + br


def _event_line(r):
    group, what = KINDS[r["kind"]]
    d = (r["detail"] or "").strip()
    if r["kind"] == "view":
        m = re.match(r"(\w+):(.*)", d)
        what, d = ("Opened " + VIEW.get(m.group(1), m.group(1)), m.group(2).strip()) if m else ("Opened a page", d)
    elif r["kind"] == "unlock_fail":
        d = FAIL.get(d, d)
    elif r["kind"] == "unlock_ok":
        d = {"sign-in": "", "new device": "new device", "qr hand-off": "phone QR hand-off"}.get(d, d)
    elif r["kind"] == "unlock_toggle":
        what, d = ("Turned creator names " + ("on" if d == "on" else "off")), ""
    elif r["kind"] == "request":
        d = ""
    return {"at": r["at"], "g": group, "k": r["kind"], "what": what, "detail": d[:160], "ip": r["ip"] or "",
            "device": device(r["user_agent"]), "bad": r["kind"] in ("unlock_fail", "mail_failed")}


def _rows(u, before, g):
    """Raw lines older than `before` (or all), newest first, from every source of group `g` (or all)."""
    cid, out = u["code_id"], []
    want = lambda grp: not g or g == grp
    b = before or 2 ** 40
    with db.connect() as conn:
        kinds = [k for k, v in KINDS.items() if want(v[0])]
        if cid is not None and kinds:
            q = ",".join("?" * len(kinds))
            out += [_event_line(r) for r in conn.execute(
                "SELECT kind, at, ip, user_agent, detail FROM events WHERE code_id = ? AND at < ? AND kind IN (%s) "
                "ORDER BY at DESC LIMIT ?" % q, [cid, b] + kinds + [RAW])]
        if want("signin") and u["email"]:
            for r in conn.execute("SELECT created_at, used_at, attempts, ip FROM otp WHERE email = ? AND created_at < ? "
                                  "ORDER BY created_at DESC LIMIT ?", (u["email"].lower(), b, RAW)):
                note = "used" if r["used_at"] else ("%d wrong tries" % r["attempts"]) if r["attempts"] else "not used"
                out.append({"at": r["created_at"], "g": "signin", "k": "otp", "what": "Asked for a sign-in code", "detail": note,
                            "ip": r["ip"] or "", "device": "", "bad": bool(r["attempts"] and not r["used_at"])})
        if want("account"):
            if cid is not None:
                for r in conn.execute("SELECT delta, balance_after, reason, actor, at FROM credit_ledger WHERE code_id = ? AND at < ? "
                                      "ORDER BY at DESC LIMIT ?", (cid, b, RAW)):
                    who = r["actor"] if r["actor"] and r["actor"] not in ("system", "client") else ""
                    out.append({"at": r["at"], "g": "account", "k": "credits", "what": "Credits %+d" % r["delta"],
                                "detail": " · ".join(x for x in (r["reason"] or "", "balance %d" % r["balance_after"]) if x),
                                "ip": "", "device": "", "by": who, "bad": False})
            for r in conn.execute("SELECT at, who, label, action FROM history WHERE entity = 'user' AND key = ? AND at < ? "
                                  "ORDER BY at DESC LIMIT ?", (str(u["id"]), b, RAW)):
                out.append({"at": r["at"], "g": "account", "k": "staff", "what": r["label"] or ("Account " + r["action"]),
                            "detail": "", "ip": "", "device": "", "by": r["who"] or "", "bad": "Suspend" in (r["label"] or "")})
            if u["created_at"] and u["created_at"] < b:
                out.append({"at": u["created_at"], "g": "account", "k": "created", "what": "Account created",
                            "detail": u["domain"] or "", "ip": u["signup_ip"] or "", "device": "", "bad": False})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out


def _fold(rows):
    """Fold repeats (same thing, detail, device and IP, within FOLD seconds of the previous one) into one line."""
    lines = []
    for r in rows:
        last = lines[-1] if lines else None
        if (last and r["k"] in ("view", "shortlist") and last["k"] == r["k"] and (r["k"] == "shortlist" or last["detail"] == r["detail"])
                and last["device"] == r["device"] and last["ip"] == r["ip"] and last["first"] - r["at"] <= FOLD):
            last["n"] += 1
            last["first"] = r["at"]
            if r["k"] == "shortlist":         # a burst of adds is one line naming the creators
                last["codes"].append(r["detail"])
                last["what"] = "Added %d creators to selections" % last["n"]
                last["detail"] = ", ".join(last["codes"][:6]) + (" and %d more" % (len(last["codes"]) - 6) if len(last["codes"]) > 6 else "")
            continue
        lines.append(dict(r, n=1, first=r["at"], codes=[r["detail"]]))
    for x in lines:
        if x["k"] == "shortlist" and x["n"] > 1:
            x["n"] = 1                        # the count is in the words already
        x.pop("codes", None)
    return lines


def timeline(u, before=None, g=None):
    """{lines, more, before}: one page of folded lines older than `before`."""
    g = g if g in dict(GROUPS) else None
    raw = _rows(u, before, g)
    lines = _fold(raw)
    if len(lines) > PAGE:
        cut = lines[PAGE]["at"]
        lines = [x for x in lines[:PAGE] if x["first"] > cut] or lines[:PAGE]
        return {"lines": lines, "more": True, "before": lines[-1]["first"]}
    # a full raw read may stop mid-history even when it folds to fewer than PAGE lines
    more = len(raw) >= RAW
    return {"lines": lines, "more": more, "before": lines[-1]["first"] if lines and more else None}


def summary(u):
    """The strip at the top: last seen, sign-ins and refusals in 30 days, devices and IPs in 30 days."""
    cid, since = u["code_id"], db.now() - 30 * 86400
    if cid is None:
        return {"last_at": u["last_login_at"], "signins": 0, "refused": 0, "devices": [], "ips": 0}
    with db.connect() as conn:
        last = conn.execute("SELECT MAX(at) FROM events WHERE code_id = ?", (cid,)).fetchone()[0]
        n = dict(conn.execute("SELECT kind, COUNT(*) FROM events WHERE code_id = ? AND at >= ? AND kind IN ('unlock_ok','unlock_fail') "
                              "GROUP BY kind", (cid, since)).fetchall())
        seen = {}
        for r in conn.execute("SELECT user_agent, ip, MAX(at) at FROM events WHERE code_id = ? AND at >= ? AND user_agent IS NOT NULL "
                              "GROUP BY user_agent, ip", (cid, since)):
            d = device(r["user_agent"])
            x = seen.setdefault(d, {"device": d, "last_at": 0, "ips": set()})
            x["last_at"] = max(x["last_at"], r["at"])
            if r["ip"]:
                x["ips"].add(r["ip"])
    ips = set().union(*[x["ips"] for x in seen.values()]) if seen else set()
    devs = sorted(({"device": x["device"], "last_at": x["last_at"], "ips": len(x["ips"])} for x in seen.values()),
                  key=lambda x: x["last_at"], reverse=True)
    return {"last_at": max(last or 0, u["last_login_at"] or 0) or None, "signins": n.get("unlock_ok", 0),
            "refused": n.get("unlock_fail", 0), "devices": devs, "ips": len(ips)}


def for_viewer(role, uid, before=None, g=None, first=True):
    """(status, body) for the API. Only owners and admins (hub.viewer's "admin") may read it."""
    import portal
    if role != "admin":
        return 403, {"ok": False, "message": "Only owners and admins can see activity logs."}
    u = portal.user_by_id(int(uid or 0))
    if u is None:
        return 404, {"ok": False, "message": "That account is gone."}
    body = dict(timeline(u, before, g), ok=True, groups=[{"k": k, "label": v} for k, v in GROUPS])
    if first:
        body["summary"] = summary(u)
        body["person"] = {"id": u["id"], "email": u["email"], "name": u["name"] or "", "company": u["company"] or "",
                          "status": u["status"], "created_at": u["created_at"]}
    return 200, body
