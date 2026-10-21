"""Edit mode on the campaign dashboard (item 209, slice c, 2026-10-21): the team fixes a campaign's posts where
they see the numbers. The same rules and the same db calls as the admin's campaign content page
(/campaigns/content: add a post, paste many links, type numbers, hide or delete, who is still to post, review
creator insights), behind JSON routes for the profile session. Owners and admins edit any campaign; a KAM her own
clients' (board.campaign_for decides who may see it). Clients and view-only team logins never get these routes.

Every change is recorded in History against the campaign, as in the admin.
"""
import re

import db

HOSTS = [("instagram.com", "Instagram"), ("tiktok.com", "TikTok"), ("snapchat.com", "Snapchat"), ("youtube.com", "YouTube"),
         ("youtu.be", "YouTube"), ("facebook.com", "Facebook"), ("fb.watch", "Facebook"), ("threads.net", "Threads"),
         ("threads.com", "Threads"), ("twitter.com", "X"), ("x.com", "X")]
URL = re.compile(r"^https://[^\s/]+\.[^\s]+$")


def platform_of(url):
    host = re.sub(r"^https?://(www\.|m\.|vm\.)?", "", (url or "").lower()).split("/")[0]
    for h, p in HOSTS:
        if host == h or host.endswith("." + h):
            return p
    return None


def _counts(src):
    out = {}
    for m in db.METRICS:
        v = src.get(m)
        v = "".join(ch for ch in str(v) if ch.isdigit()) if v not in (None, "") else ""
        out[m] = int(v) if v else None
    return out


def view(k):
    """Everything the Edit panel draws for one campaign."""
    creators = db.campaign_creators(k["id"])
    posts = db.campaign_content(k["id"])
    by = {}
    for p in posts:
        by.setdefault(p["code"], []).append({
            "id": p["id"], "platform": p["platform"], "kind": p["kind"], "url": p["url"], "posted_at": p["posted_at"],
            "section": p["section"], "hidden": bool(p["hidden"]), "source": p["source"], "metrics_at": p["metrics_at"],
            "likes": p["likes"], "comments": p["comments"], "views": p["views"], "shares": p["shares"], "saves": p["saves"],
            "has_insights": bool(p["insights"])})
    out = []
    for c in creators:
        code = c["cc_code"]
        out.append({"code": code, "name": (c["name"] if "name" in c.keys() else None) or code,
                    "planned": c["planned"], "pending_status": c["pending_status"] or "", "pending_date": c["pending_date"] or "",
                    "platforms": db.platforms_of(code), "posts": by.get(code, [])})
    names = {c["code"]: c["name"] for c in out}
    ins = []
    for i in db.campaign_insights(k["id"]):
        if i["status"] == "rejected":
            continue
        import json
        try:
            ext = json.loads(i["extracted"] or "{}")
        except ValueError:
            ext = {}
        ins.append({"id": i["id"], "code": i["code"], "name": names.get(i["code"]) or i["code"], "status": i["status"],
                    "values": ext, "content_id": i["content_id"], "post_url": i["post_url"] or i["content_url"] or "",
                    "uploaded_at": i["uploaded_at"], "note": i["note"] or ""})
    import postcheck
    checks = postcheck.of_campaign(k["id"])                 # item 218: each post's check
    for c in out:
        for p in c["posts"]:
            p["check"] = checks.get(p["id"])
    return {"campaign": {"id": k["id"], "name": k["name"], "token": k["token"], "status": k["status"]}, "creators": out,
            "checks_on": postcheck_on(),
            "insights": ins, "statuses": db.PENDING_STATUSES, "platforms": db.PLATFORMS, "kinds": db.KINDS,
            "metrics": db.METRICS, "insight_fields": db.INSIGHT_FIELDS}


def postcheck_on():
    import aifeatures
    return {"ai": aifeatures.allowed("compliance"), "why_not": aifeatures.why_not("compliance")}


def _creator_codes(k):
    return {m["cc_code"] for m in db.campaign_creators(k["id"])}


def _tracked(k, actor, label):
    import history
    history.set_actor(actor)
    return history.tracked("campaign", k["id"], label)


def add_post(k, actor, code, url, platform="", kind="", caption="", posted="", counts=None):
    import thumbs
    code = (code or "").strip().upper()
    url = (url or "").strip()
    if not URL.match(url):
        return 400, {"ok": False, "message": "The post link must start with https://"}
    if code not in _creator_codes(k):
        return 400, {"ok": False, "message": "Pick a creator in this campaign."}
    plat = platform if platform in db.PLATFORMS else (platform_of(url) or "Instagram")
    kind = kind if kind in db.KINDS else "post"
    item = {"code": code, "platform": plat, "kind": kind, "url": url, "posted_at": db.day_bounds(posted or "", None),
            "caption": (caption or "").strip() or None, "followers": db.platform_followers(code, plat), **_counts(counts or {})}
    with _tracked(k, actor, "Added a post"):
        _, created = db.add_content(k["id"], item, source="manual")
    thumbs.fill_later(k["id"])
    return 200, {"ok": True, "created": created, "platform": plat,
                 "message": "Post added." if created else "That post was already here. Its numbers were updated."}


def bulk_links(k, actor, code, text, platform=""):
    import thumbs
    code = (code or "").strip().upper()
    if code not in _creator_codes(k):
        return 400, {"ok": False, "message": "Pick a creator in this campaign."}
    added = seen = 0
    with _tracked(k, actor, "Bulk-added posts"):
        for line in (text or "").splitlines():
            m = re.search(r"https://[^\s,;]+\.[^\s,;]+", line)
            if not m:
                continue
            url = m.group(0)
            plat = platform if platform in db.PLATFORMS else (platform_of(url) or "Instagram")
            item = {"code": code, "platform": plat, "kind": "post", "url": url, "posted_at": None, "caption": None,
                    "followers": db.platform_followers(code, plat)}
            _, created = db.add_content(k["id"], item, source="manual")
            added += 1 if created else 0
            seen += 0 if created else 1
    if added:
        thumbs.fill_later(k["id"])
    if not added and not seen:
        return 400, {"ok": False, "message": "No links found. Paste one https:// link per line."}
    return 200, {"ok": True, "message": "%d post%s added.%s" % (added, "" if added == 1 else "s", " %d already here." % seen if seen else "")}


def _post(k, pid):
    item = db.content_item(int(pid)) if str(pid or "").isdigit() else None
    return item if item is not None and item["campaign_id"] == k["id"] else None


def set_numbers(k, actor, pid, values):
    item = _post(k, pid)
    if item is None:
        return 404, {"ok": False, "message": "That post is gone."}
    vals = _counts(values or {})
    if all(v is None for v in vals.values()):
        return 400, {"ok": False, "message": "Type at least one number."}
    with _tracked(k, actor, "Changed a post"):
        db.add_snapshot(item["id"], vals, "manual")
    return 200, {"ok": True, "message": "Numbers saved."}


def update_post(k, actor, pid, do):
    item = _post(k, pid)
    if item is None:
        return 404, {"ok": False, "message": "That post is gone."}
    if do not in ("hide", "unhide", "delete", "campaign", "other"):
        return 400, {"ok": False, "message": "Unknown action."}
    with _tracked(k, actor, "Changed a post"):
        if do in ("campaign", "other"):
            db.update_content(item["id"], section=do)
        elif do in ("hide", "unhide"):
            db.update_content(item["id"], hidden=1 if do == "hide" else 0)
        else:
            db.delete_content(item["id"])
    return 200, {"ok": True, "message": "Saved."}


def set_pending(k, actor, code, status, date):
    code = (code or "").strip().upper()
    if code not in _creator_codes(k):
        return 400, {"ok": False, "message": "Pick a creator in this campaign."}
    status = status if status in db.PENDING_STATUSES else None
    date = date if date and db.day_bounds(date, None) is not None else None
    with _tracked(k, actor, "Updated who is still to post"):
        db.set_pending(k["id"], {code: (status, date)})
    return 200, {"ok": True, "message": "Saved."}


def decide_insight(k, actor, iid, do, post=None, values=None):
    row = db.insight(int(iid)) if str(iid or "").isdigit() else None
    if row is None or row["campaign_id"] != k["id"]:
        return 404, {"ok": False, "message": "That insight is gone."}
    with _tracked(k, actor, "Reviewed insights"):
        if do == "reject":
            db.decide_insight(row["id"], False)
            return 200, {"ok": True, "message": "Rejected."}
        item = _post(k, post) if post else (db.content_item(row["content_id"]) if row["content_id"] else None)
        if item is None or item["campaign_id"] != k["id"]:
            return 400, {"ok": False, "message": "Choose which post these numbers belong to before approving."}
        vals = {f: (values or {}).get(f) for f in db.INSIGHT_FIELDS}
        if not db.clean_insight_values(vals):
            return 400, {"ok": False, "message": "Enter at least one number to approve."}
        db.decide_insight(row["id"], True, vals, item["id"])
    return 200, {"ok": True, "message": "Approved. The report now uses these numbers."}
