"""Build the trial template (item 271): the BlueHolding demo company, demo data only.

    python3 tools/trial_template.py SNAPSHOT.db OUT.db

SNAPSHOT.db is a COPY of the live catalogue.db (sqlite backup API, never the live file). The copy is
emptied table by table: a table named in KEEP keeps only its demo rows; every other table is emptied,
so a table added later never carries real data into a trial by default. What is kept:

* the demo selections (setting ``sample_selections``) and the demo campaigns (``pinned_campaigns``), with
  every table hanging off them, and the evidence packs made for those selections;
* the creators they name, with prices, costs and internal notes removed;
* a handful of harmless settings (``SETTINGS``).

Everything kept is refiled under one company, BlueHolding (code ``trial.DEMO_CODE``), with all three modules
at manage, one owner (``trial.DEMO_USER``) and three demo competitors. Run it in a throwaway container with
no network (docs/TRIAL-LINKS.md).
"""
import json
import sqlite3
import sys
import time

DEMO_CODE = 9001
DEMO_USER = 9001

SETTINGS = {"fx_rates", "tag_subs", "gating_migrated", "passcodes_off", "roster_plus_floor", "gemini_model"}


def main(src, out):
    import shutil
    shutil.copyfile(src, out)
    c = sqlite3.connect(out)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = OFF")

    def setting(k, d):
        r = c.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone()
        try:
            return json.loads(r[0]) if r else d
        except ValueError:
            return d

    SEL = [int(x) for x in setting("sample_selections", [])]
    CAMP = [int(x) for x in setting("pinned_campaigns", [])]
    assert SEL and CAMP, "no sample_selections / pinned_campaigns setting"
    for k in CAMP:
        row = c.execute("SELECT client, name FROM campaigns WHERE id = ?", (k,)).fetchone()
        assert row and ("demo" in (row["client"] or "").lower() or (row["name"] or "").lower().startswith("demo")), \
            "campaign %d is not a demo campaign" % k
    PACK = [r[0] for r in c.execute("SELECT id FROM evidence_packs WHERE deleted_at IS NULL AND selection_id IN (%s)"
                                    % ",".join(map(str, SEL)))]
    codes = set()
    for r in c.execute("SELECT codes FROM selections WHERE id IN (%s)" % ",".join(map(str, SEL))):
        codes.update(json.loads(r[0] or "[]"))
    codes.update(r[0] for r in c.execute("SELECT code FROM campaign_creators WHERE campaign_id IN (%s)"
                                         % ",".join(map(str, CAMP))))
    if PACK:
        p = ",".join(map(str, PACK))
        codes.update(r[0] for r in c.execute("SELECT code FROM evidence_posts WHERE pack_id IN (%s) AND code IS NOT NULL" % p))
        codes.update(r[0] for r in c.execute("SELECT code FROM evidence_roster WHERE pack_id IN (%s)" % p))
    codes.discard(None)
    content = [r[0] for r in c.execute("SELECT id FROM content WHERE campaign_id IN (%s)" % ",".join(map(str, CAMP)))]

    c.execute("CREATE TEMP TABLE k_sel (id INTEGER PRIMARY KEY)")
    c.executemany("INSERT INTO k_sel VALUES (?)", [(x,) for x in SEL])
    c.execute("CREATE TEMP TABLE k_camp (id INTEGER PRIMARY KEY)")
    c.executemany("INSERT INTO k_camp VALUES (?)", [(x,) for x in CAMP])
    c.execute("CREATE TEMP TABLE k_pack (id INTEGER PRIMARY KEY)")
    c.executemany("INSERT INTO k_pack VALUES (?)", [(x,) for x in PACK])
    c.execute("CREATE TEMP TABLE k_code (code TEXT PRIMARY KEY)")
    c.executemany("INSERT INTO k_code VALUES (?)", [(x,) for x in codes])
    c.execute("CREATE TEMP TABLE k_content (id INTEGER PRIMARY KEY)")
    c.executemany("INSERT INTO k_content VALUES (?)", [(x,) for x in content])

    by_camp = "campaign_id IN (SELECT id FROM k_camp)"
    by_sel = "selection_id IN (SELECT id FROM k_sel)"
    by_code = "code IN (SELECT code FROM k_code)"
    KEEP = {
        "campaigns": "id IN (SELECT id FROM k_camp)",
        "campaign_creators": by_camp, "campaign_next": by_camp, "campaign_weekly": by_camp,
        "campaign_updates": by_camp, "comment_reads": by_camp, "comments": by_camp, "content": by_camp,
        "content_checks": by_camp, "insights": by_camp, "links": by_camp, "clicks": by_camp, "score_log": by_camp,
        "push_camp_state": by_camp, "push_milestones": by_camp,
        "snapshots": "content_id IN (SELECT id FROM k_content)",
        "comment_labels": "1",
        "selections": "id IN (SELECT id FROM k_sel)",
        "selection_status": by_sel, "selection_alike": by_sel, "selection_quote": by_sel, "quote_changes": by_sel,
        "evidence_packs": "id IN (SELECT id FROM k_pack)",
        "evidence_posts": "pack_id IN (SELECT id FROM k_pack)", "evidence_roster": "pack_id IN (SELECT id FROM k_pack)",
        "creators": by_code, "creator_analysis": by_code, "creator_licences": by_code, "creator_tone": by_code,
        "profile_metrics": by_code, "profile_raw": by_code, "profile_snapshots": by_code, "post_samples": by_code,
        "content_ideas": by_code,
        "tiers": "1", "brand_logos": "1",
        "settings": "key IN (%s)" % ",".join("'%s'" % k for k in sorted(SETTINGS)),
    }
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    report = []
    for t in tables:
        before = c.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        rule = KEEP.get(t)
        if rule is None:
            c.execute('DELETE FROM "%s"' % t)
        else:
            c.execute('DELETE FROM "%s" WHERE NOT (%s)' % (t, rule))
        after = c.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        report.append((t, before, after))

    # Nothing internal: prices, costs, margins, notes.
    c.execute("UPDATE creators SET price_from = NULL, price_to = NULL, cost = NULL, note = NULL, owner_code_id = NULL")
    c.execute("UPDATE selections SET margin = NULL, margin_max = NULL, costs = '{}', total_from = 0, total_to = 0, "
              "code_id = ?, request_id = NULL", (DEMO_CODE,))
    sel_prices = {}
    for r in c.execute("SELECT id, prices FROM selections"):
        sel_prices[r["id"]] = json.dumps({k: [0, 0] for k in json.loads(r["prices"] or "{}")})
    for sid, pr in sel_prices.items():
        c.execute("UPDATE selections SET prices = ? WHERE id = ?", (pr, sid))
    tier_cols = [r[1] for r in c.execute("PRAGMA table_info(tiers)")]
    for col in ("price_from", "price_to"):
        if col in tier_cols:
            c.execute("UPDATE tiers SET %s = 0" % col)
    c.execute("UPDATE campaigns SET code_id = ?, cost = NULL, notes = NULL", (DEMO_CODE,))
    c.execute("UPDATE campaign_updates SET code_id = ?", (DEMO_CODE,))
    c.execute("UPDATE evidence_packs SET code_id = ?, created_by = 'HelloVoice'", (DEMO_CODE,))
    if "campaign_creators" in tables:
        cc_cols = [r[1] for r in c.execute("PRAGMA table_info(campaign_creators)")]
        for col in ("cost", "fee", "price"):
            if col in cc_cols:
                c.execute("UPDATE campaign_creators SET %s = NULL" % col)

    # Settings the demo needs, pointing at the kept objects only.
    for k, v in (("sample_selections", []), ("pinned_campaigns", []), ("selections_scored", SEL),
                 ("selections_unscored", []), ("selections_zero_price", SEL), ("workspace_invites", []),
                 ("post_profiles_auto", False), ("monthly_credits", 0), ("guest_credits", 0), ("signup_credits", 0),
                 ("signup_mode", "closed"), ("ai_features", {}), ("team_sharing", False)):
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))
    src_c = sqlite3.connect(src)
    r = src_c.execute("SELECT value FROM settings WHERE key = 'campaign_sales'").fetchone()
    if r:
        sales = json.loads(r[0] or "{}")
        keep = {str(k): sales[str(k)] for k in CAMP if str(k) in sales}
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('campaign_sales', ?)", (json.dumps(keep),))
    src_c.close()

    # The company and its owner.
    now = int(time.time())
    code_cols = [r[1] for r in c.execute("PRAGMA table_info(codes)")]
    vals = {"id": DEMO_CODE, "code_hash": "trial-demo-no-passcode", "hint": "", "code_plain": None,
            "label": "BlueHolding (demo)", "created_at": now, "max_uses": None, "uses": 0, "max_devices": None}
    vals = {k: v for k, v in vals.items() if k in code_cols}
    c.execute("INSERT INTO codes (%s) VALUES (%s)" % (",".join(vals), ",".join("?" * len(vals))), list(vals.values()))
    user_cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
    u = {"id": DEMO_USER, "email": "trial@demo.helvi.invalid", "name": "BlueHolding", "company": "BlueHolding",
         "job_title": "Marketing", "domain": "demo.helvi.invalid", "code_id": DEMO_CODE, "status": "active",
         "created_at": now, "last_login_at": now, "tour": "done", "notify": None, "language": "en"}
    u = {k: v for k, v in u.items() if k in user_cols}
    c.execute("INSERT INTO users (%s) VALUES (%s)" % (",".join(u), ",".join("?" * len(u))), list(u.values()))
    for m in ("helvi-selection", "helvi-track", "helvi-intelligence"):
        c.execute("INSERT INTO tenant_modules (code_id, module, level, changed_at, changed_by) VALUES (?,?,?,?,?)",
                  (DEMO_CODE, m, "manage", now, "trial template"))
    for k, v in (("brand_name", "BlueHolding"), ("seats", 5), ("campaigns_max", 6), ("selections_max", 10)):
        c.execute("INSERT INTO tenant_settings (code_id, key, value, changed_at, changed_by) VALUES (?,?,?,?,?)",
                  (DEMO_CODE, k, str(v), now, "trial template"))

    # Three named competitors, taken from the demo evidence so their posts are already collected.
    if PACK:
        comp = c.execute("SELECT competitor, COUNT(*) n FROM evidence_posts WHERE pack_id = ? AND competitor IS NOT NULL "
                         "AND competitor != '' GROUP BY competitor ORDER BY n DESC LIMIT 3", (PACK[0],)).fetchall()
        for r in comp:
            h = "".join(ch for ch in r["competitor"].lower() if ch.isalnum())
            c.execute("INSERT INTO competitors (code_id, name, handles, note, added_by, created_at, updated_at, pack_id, "
                      "last_run_at, last_note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (DEMO_CODE, r["competitor"], json.dumps({"Instagram": h}), "Sample competitor", "HelloVoice", now,
                       now, PACK[0], now, "%d posts on file (sample data)." % r["n"]))

    c.commit()
    c.execute("VACUUM")
    c.close()
    print("selections", SEL, "campaigns", CAMP, "packs", PACK, "creators", len(codes))
    for t, b, a in report:
        if b:
            print("%-22s %7d -> %d" % (t, b, a))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
