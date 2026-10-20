"""Merge two selections (item 207, owner 2026-10-20).

On a selection page, "Merge with..." picks another selection the reader may change. The other one's creators
join this one after this one's own; for a creator both hold, this one's approve / reject status, price, tags
and notes win. The other selection is archived (History brings it back) and every campaign that held it now
holds this one.

    candidates(reader, sel, admin_id)       the selections this reader may merge into ``sel``
    merge(reader, into, other, admin_id, by)   (ok, message, row)

``reader`` is the code acting on the page (selection_viewer); ``admin_id`` stands for HelloVoice, as in
selrename.client_may, which is the permission rule for both selections.
"""
import json

import db

# JSON columns keyed by creator code: the other selection's entries fill in what this one lacks.
KEYED = ("prices", "costs", "tags", "client_tags", "verdicts", "platforms", "segments")


def _may(reader, sel, admin_id):
    import selrename
    return sel is not None and not sel["deleted_at"] and selrename.client_may(reader, sel, admin_id)


def candidates(reader, sel, admin_id):
    """Other live selections of the same client the reader may change, newest first."""
    import portal
    if not _may(reader, sel, admin_id):
        return []
    owner = sel["code_id"]
    if owner is None:
        return []
    team = sorted(portal.team_codes(int(owner)))
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM selections WHERE code_id IN (%s) AND id != ? AND deleted_at IS NULL AND archived_at IS NULL "
                            "ORDER BY updated_at DESC LIMIT 60" % ",".join("?" * len(team)), team + [sel["id"]]).fetchall()
    out = []
    for r in rows:
        if _may(reader, r, admin_id):
            out.append({"token": r["token"], "name": r["name"], "creators": len(json.loads(r["codes"] or "[]")), "updated_at": r["updated_at"]})
    return out


def _load(v):
    try:
        got = json.loads(v or "{}")
    except (TypeError, ValueError):
        got = {}
    return got if isinstance(got, dict) else {}


def merge(reader, into, other, admin_id, by=""):
    import board
    import history
    if into is None or other is None or into["id"] == other["id"]:
        return False, "Pick another selection to merge.", None
    if not _may(reader, into, admin_id) or not _may(reader, other, admin_id):
        return False, "You can only merge selections you can change.", None
    if other["archived_at"]:
        return False, "%s is already archived." % other["name"], None
    a_codes = json.loads(into["codes"] or "[]")
    b_codes = json.loads(other["codes"] or "[]")
    new = [c for c in b_codes if c not in a_codes]
    codes = a_codes + new
    keys = set(into.keys())
    with history.tracked("selection", into["id"], "Merged %s into %s" % (other["name"], into["name"])):
        with db.connect() as conn:
            sets, vals = ["codes = ?", "updated_at = ?"], [json.dumps(codes), db.now()]
            for col in KEYED:
                if col not in keys:
                    continue
                mine, theirs = _load(into[col]), _load(other[col])
                if not theirs:
                    continue
                merged = dict(theirs)
                merged.update(mine)                                   # this selection's entries win
                sets.append(col + " = ?")
                vals.append(json.dumps({c: merged[c] for c in codes if c in merged} if col != "segments" else merged))
            conn.execute("UPDATE selections SET %s WHERE id = ?" % ", ".join(sets), vals + [into["id"]])
            # approve / reject statuses: the other one's fill in, this one's stay
            conn.execute("INSERT OR IGNORE INTO selection_status (selection_id, code, status, reason, note, by_kind, by_name, at, replacements) "
                         "SELECT ?, code, status, reason, note, by_kind, by_name, at, replacements FROM selection_status WHERE selection_id = ?",
                         (into["id"], other["id"]))
    # every campaign that held the other selection now holds this one
    for cid in board.campaigns_holding(other["id"]):
        board.link_selection(cid, into["id"], by)
        with db.connect() as conn:
            conn.execute("DELETE FROM campaign_selections WHERE campaign_id = ? AND selection_id = ?", (cid, other["id"]))
            k = conn.execute("SELECT selection_id FROM campaigns WHERE id = ?", (cid,)).fetchone()
            if k is not None and k["selection_id"] == other["id"]:
                conn.execute("UPDATE campaigns SET selection_id = ? WHERE id = ?", (into["id"], cid))
                conn.execute("DELETE FROM campaign_selections WHERE campaign_id = ? AND selection_id = ?", (cid, into["id"]))
    with history.tracked("selection", other["id"], "Archived %s: merged into %s" % (other["name"], into["name"])):
        with db.connect() as conn:
            conn.execute("UPDATE selections SET archived_at = ?, updated_at = ? WHERE id = ?", (db.now(), db.now(), other["id"]))
    row = db.selection(into["id"])
    return True, "Merged: %d creator%s from %s joined %s." % (len(new), "" if len(new) == 1 else "s", other["name"], into["name"]), row
