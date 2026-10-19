"""The app's own API (HELVi Connect PWA, item 168), under /api/push/.

    GET  /api/push/key          the VAPID public key for pushManager.subscribe()
    GET  /api/push/state        {phone: master switch, devices: active subscriptions here}
    POST /api/push/event        {k, e, p, os, br, sa, perm}: install / permission tracking
    POST /api/push/subscribe    {sub, k, sa, old}: store this browser's subscription
    POST /api/push/unsubscribe  {endpoint}
    POST /api/push/phone        {on}: the person's "Phone alerts" switch
    POST /api/push/ack|click    {d, k}: from the service worker, delivered / tapped

Anyone who can open a portal page may report events and subscribe (account holders,
access-code guests, the team); a subscription is filed under whoever is signed in.
ack/click carry their own per-delivery token, so they need no session.
"""
import push
import webpush


def ident(h):
    out = {}
    try:
        cid, user, kind = h._identity()
    except Exception:
        cid, user, kind = None, None, None
    if user is not None:
        out.update(user_id=user["id"], email=(user["email"] or "").lower())
    if cid is not None and kind != "admin":
        out["code_id"] = cid
    try:
        a = h.admin()
    except Exception:
        a = None
    if a is not None:
        out["admin_id"] = a["admin_id"]
        out.setdefault("email", (a["email"] or "").lower())
    return out


def handle(h, method, path, query=None):
    """True when the path was ours."""
    if not path.startswith("/api/push/"):
        return False
    op = path[len("/api/push/"):]
    ua = h.headers.get("User-Agent") or ""
    if method == "GET":
        if op == "key":
            h.send_json(200, {"ok": True, "key": webpush.public_key()}, h.cors())
        elif op == "state":
            who = ident(h)
            h.send_json(200, {"ok": True, "phone": push.phone_on(who.get("user_id")), "signed": bool(who),
                              "account": bool(who.get("user_id"))}, h.cors())
        else:
            return False
        return True
    body = h.json_body()
    if op in ("ack", "click"):
        ok = push.ack(body.get("d"), body.get("k"), clicked=(op == "click"))
        h.send_json(200 if ok else 404, {"ok": ok}, h.cors())
        return True
    who = ident(h)
    if op == "event":
        ok = push.track(who, body, ua)
        h.send_json(200 if ok else 400, {"ok": ok}, h.cors())
    elif op == "subscribe":
        if not who:
            h.send_json(401, {"ok": False, "reason": "locked"}, h.cors())
            return True
        ok = push.subscribe(who, body.get("sub") or {}, body.get("k") or "", ua, bool(body.get("sa")), body.get("old"))
        if ok and body.get("k"):
            push.track(who, {"k": body.get("k"), "e": "granted", "perm": "granted", "sa": body.get("sa")}, ua)
        h.send_json(200 if ok else 400, {"ok": ok}, h.cors())
    elif op == "unsubscribe":
        n = push.unsubscribe(body.get("endpoint") or "")
        h.send_json(200, {"ok": True, "n": n}, h.cors())
    elif op == "phone":
        if not who.get("user_id"):
            h.send_json(403, {"ok": False, "reason": "no_profile"}, h.cors())
            return True
        h.send_json(200, {"ok": True, "phone": push.set_phone(who["user_id"], bool(body.get("on")))}, h.cors())
    else:
        return False
    return True
