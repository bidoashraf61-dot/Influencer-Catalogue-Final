"""The app's own API (HELVi Connect PWA, item 168), under /api/push/.

    GET  /api/push/key          the VAPID public key for pushManager.subscribe()
    GET  /api/push/state        {phone: master switch, devices: active subscriptions here}
    POST /api/push/event        {k, e, p, os, br, sa, perm}: install / permission tracking
    POST /api/push/subscribe    {sub, k, sa, old}: store this browser's subscription
    POST /api/push/unsubscribe  {endpoint}
    POST /api/push/phone        {on}: the person's "Phone alerts" switch
    POST /api/push/ack|click    {d, k}: from the service worker, delivered / tapped
    POST /api/push/handoff      account holders: {url, svg} — a QR that signs their phone in (one use, 15 min)
    GET  /api/push/qr?h=        the phone lands here from the QR: signs in, then /account/?src=qr
    POST /api/push/welcome      the one-time desktop welcome was shown

Anyone who can open a portal page may report events and subscribe (account holders,
access-code guests, the team); a subscription is filed under whoever is signed in.
ack/click carry their own per-delivery token, so they need no session.
"""
import secrets

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
            uid = who.get("user_id")
            h.send_json(200, {"ok": True, "phone": push.phone_on(uid), "signed": bool(who), "account": bool(uid),
                              "welcome_seen": push.welcome_seen(uid), "phone_app": push.phone_app(uid)}, h.cors())
        elif op == "qr":
            return qr_landing(h, (query or {}).get("h", ""))
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
    elif op == "handoff":
        if not who.get("user_id"):
            h.send_json(403, {"ok": False, "reason": "no_profile"}, h.cors())
            return True
        token = push.handoff(who["user_id"])
        if not token:
            h.send_json(429, {"ok": False, "reason": "too_many"}, h.cors())
            return True
        import qr
        url = site_origin(h) + api_base(h) + "/api/push/qr?h=" + token
        h.send_json(200, {"ok": True, "url": url, "svg": qr.svg(url), "expires_in": push.HANDOFF_TTL}, h.cors())
    elif op == "welcome":
        if who.get("user_id"):
            push.mark_welcome(who["user_id"])
        push.track(who, {"k": body.get("k") or "", "e": "welcome", "p": "desktop"}, ua)
        h.send_json(200, {"ok": True}, h.cors())
    elif op == "phone":
        if not who.get("user_id"):
            h.send_json(403, {"ok": False, "reason": "no_profile"}, h.cors())
            return True
        h.send_json(200, {"ok": True, "phone": push.set_phone(who["user_id"], bool(body.get("on")))}, h.cors())
    else:
        return False
    return True


def site_origin(h):
    srv = h._srv()
    allowed = sorted(getattr(srv, "ALLOWED_ORIGINS", ()) or ())
    if allowed:
        return allowed[0].rstrip("/")
    return "http://" + (h.headers.get("Host") or "127.0.0.1")


def api_base(h):
    return getattr(h._srv(), "BASE", "") or ""


def qr_landing(h, token):
    """The phone scanned the code: sign it in as that person, then open the app's start page,
    where the Home Screen guide opens at once. A used or expired code just opens the sign-in."""
    import portal
    srv = h._srv()
    dest = "/account/?src=qr"
    uid = push.redeem(token, h.client_ip())
    user = portal.user_by_id(uid) if uid else None
    if user is None or user["status"] != "active" or user["deleted_at"]:
        return redirect(h, dest + "&qr=expired#overview")
    import auth
    import db
    row = h._code_row(user["code_id"])
    ok, _why = db.code_state(row) if row is not None else (False, "")
    if not ok:
        return redirect(h, dest + "&qr=expired#overview")
    device_token = h.cookies().get(srv.DEVICE_COOKIE, "")
    if len(device_token) < 20:
        device_token = secrets.token_urlsafe(24)
    device = db.device_hash(device_token)
    admitted, why = db.admit_device(row, device, h.client_ip(), h.headers.get("User-Agent"))
    if not admitted:
        return redirect(h, dest + "&qr=devices#overview")
    db.bump_code_use(row["id"])
    db.log("unlock_ok", row["id"], h.client_ip(), h.headers.get("User-Agent"), "qr hand-off")
    expiry = db.now() + srv.VIEWER_TTL
    ticket = auth.sign("%d:%d:%s:e" % (row["id"], expiry, device), srv.SECRET)
    policy = "SameSite=None; Secure" if srv.ALLOWED_ORIGINS else "SameSite=Lax"
    cookies = ["%s=%s; Path=/; HttpOnly; %s; Max-Age=%d" % (srv.VIEWER_COOKIE, ticket, policy, srv.VIEWER_TTL),
               "%s=%s; Path=/; HttpOnly; %s; Max-Age=%d" % (srv.DEVICE_COOKIE, device_token, policy, srv.DEVICE_TTL)]
    return redirect(h, dest + "#overview", cookies)


def redirect(h, to, cookies=()):
    h.send_response(302)
    h.send_header("Location", to)
    h.send_header("Cache-Control", "no-store")
    h.send_header("Referrer-Policy", "no-referrer")
    for c in cookies:
        h.send_header("Set-Cookie", c)
    h.send_header("Content-Length", "0")
    h.end_headers()
    return True
