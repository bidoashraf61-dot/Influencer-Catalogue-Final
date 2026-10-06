"""What the Home page shows: the things that need a person today, where every
selection and campaign stands, how the live campaigns are getting on, and how
busy the catalogue has been. Plain data in, plain data out; the page only draws."""

import time

import db


def _count(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchone()[0] or 0
    except Exception:
        return 0


def _live_clients():
    """Access codes that are switched on and not expired."""
    try:
        return db.stats(days=1)["live_codes"]
    except Exception:
        return 0


def home():
    now = db.now()
    out = {"queue": [], "pipeline": {}, "live": [], "series": [], "labels": [], "feed": [], "totals": {}}
    pulse = db.request_pulse()
    with db.connect() as conn:
        sel_total = _count(conn, "SELECT COUNT(*) FROM selections WHERE archived_at IS NULL")
        sel_free = _count(conn, "SELECT COUNT(*) FROM selections WHERE archived_at IS NULL AND code_id IS NULL")
        sel_unlinked = _count(
            conn, "SELECT COUNT(*) FROM selections s WHERE s.archived_at IS NULL AND s.id NOT IN "
                  "(SELECT selection_id FROM campaigns WHERE selection_id IS NOT NULL)")
        camps = conn.execute("SELECT id, name, client, status, starts_at, ends_at FROM campaigns ORDER BY id DESC").fetchall()
        planned = {r[0]: r[1] or 0 for r in conn.execute(
            "SELECT campaign_id, SUM(planned) FROM campaign_creators GROUP BY campaign_id")}
        live_posts = {r[0]: r[1] for r in conn.execute(
            "SELECT campaign_id, COUNT(*) FROM content WHERE hidden = 0 AND section = 'campaign' GROUP BY campaign_id")}
        insights_wait = _count(conn, "SELECT COUNT(*) FROM insights WHERE status IN ('pending','extracted')")
        creators = _count(conn, "SELECT COUNT(*) FROM creators WHERE active = 1")
        analysed = _count(conn, "SELECT COUNT(*) FROM creator_analysis")
        days = 14
        start = now - (days - 1) * 86400
        per_day = {r[0]: r[1] for r in conn.execute(
            "SELECT date(at,'unixepoch') d, COUNT(*) FROM events WHERE kind != 'unlock_fail' AND at >= ? GROUP BY d", (start - 86400,))}
    for i in range(days):
        t = start + i * 86400
        key = time.strftime("%Y-%m-%d", time.gmtime(t))
        out["series"].append(per_day.get(key, 0))
        out["labels"].append(time.strftime("%d %b", time.gmtime(t)))
    by_status = {"draft": 0, "live": 0, "ended": 0}
    for k in camps:
        by_status[k["status"]] = by_status.get(k["status"], 0) + 1
        if k["status"] == "live":
            n_plan, n_live = planned.get(k["id"], 0), live_posts.get(k["id"], 0)
            span = (k["ends_at"] - k["starts_at"]) if (k["starts_at"] and k["ends_at"] and k["ends_at"] > k["starts_at"]) else 0
            elapsed = max(0.0, min(1.0, (now - k["starts_at"]) / float(span))) if span else None
            out["live"].append({"id": k["id"], "name": k["name"], "client": k["client"], "planned": n_plan, "posts": n_live,
                                "elapsed": elapsed, "ends_at": k["ends_at"]})
    out["pipeline"] = {"selections": sel_total, "draft": by_status["draft"], "live": by_status["live"], "ended": by_status["ended"]}
    out["totals"] = {"creators": creators, "analysed": analysed, "clients": _live_clients()}
    out["feed"] = db.recent_events(8)

    q = out["queue"]
    if pulse["open"]:
        q.append(("inbox", "%d quote request%s waiting" % (pulse["open"], "" if pulse["open"] == 1 else "s"),
                  "A client sent a shortlist. Price it and send it back.", "/requests", "Open inbox", "alert"))
    if pulse.get("a_open"):
        n = pulse["a_open"]
        q.append(("profile", "%d analysis request%s from clients" % (n, "" if n == 1 else "s"),
                  "Clients asked for a creator's full analysis. Import it from the report PDF.", "/analysis", "Open requests", "alert"))
    if insights_wait:
        q.append(("check", "%d insight%s to review" % (insights_wait, "" if insights_wait == 1 else "s"),
                  "Creators sent insight screenshots. Approving them replaces estimates with real numbers.", "/campaigns", "Review", "alert"))
    for c in out["live"]:
        if c["planned"] and c["posts"] < c["planned"]:
            gap = c["planned"] - c["posts"]
            q.append(("flag", "%s: %d post%s still to come" % (c["name"], gap, "" if gap == 1 else "s"),
                      "%d of %d posts are live. Add the links or set a date and status for the rest." % (c["posts"], c["planned"]),
                      "/campaigns/content?id=%d" % c["id"], "Open posts", "warn"))
    for k in camps:
        if k["status"] == "draft":
            q.append(("flag", "%s is still a draft" % k["name"], "Finish the setup, then press Go live so the client can see it.",
                      "/campaigns/edit?id=%d" % k["id"], "Finish setup", "warn"))
    if sel_free:
        q.append(("list", "%d selection%s without a client" % (sel_free, "" if sel_free == 1 else "s"),
                  "A selection needs a client passcode before the client can open it.", "/selections", "Assign", "warn"))
    return out
