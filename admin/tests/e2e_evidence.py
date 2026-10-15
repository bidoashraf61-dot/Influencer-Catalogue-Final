"""Competitor evidence packs (admin/evidence.py): import, roster matching, adding creators to the
selection, the client's view (only once shared) and KAM scope. All names below are invented.

    python3 admin/tests/e2e_evidence.py
"""
import json
import shutil
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e2e_portal as base  # noqa: E402

import db, evidence, gemini, guard, mailer, portal, server, views  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

KAM, OTHER = "mariam.k@hvkam.com", "omar.k@hvkam.com"


def post(url, comp, brand, handle, views_, likes, rel="match", paid=False, er=None):
    return {"url": url, "platform": "instagram", "handle": handle, "name": handle.title(), "followers": 40000,
            "date": "2026-03-01", "collab_type": "co_author", "product_tags": "x", "relevance": rel,
            "views": views_, "likes": likes, "comments": 10,
            "er_views": er if er is not None else (None if likes is None else (likes + 10) / views_),
            "likely_paid_boost": paid, "likes_hidden": likes is None, "performance_read": "internal note"}


PACK = {"generated": "2026-10-14", "source": "study.xlsx", "platforms": ["instagram"], "objective": "awareness",
        "brands": [{"brand": "Glow Serum", "product": "Vitamin C serum", "competitors": [
            {"competitor": "RivalSkin", "fit": "direct", "posts_detail": [
                post("https://www.instagram.com/reel/A1/", "RivalSkin", "Glow Serum", "noha", 90000, 2000),
                post("https://www.instagram.com/reel/A2/", "RivalSkin", "Glow Serum", "noha", 50000, 1500),
                post("https://www.instagram.com/reel/A3/", "RivalSkin", "Glow Serum", "sara", 30000, None),
                post("https://www.instagram.com/reel/A4/", "RivalSkin", "Glow Serum", "bought", 2000000, 30, paid=True),
                post("https://www.instagram.com/reel/A5/", "RivalSkin", "Glow Serum", "lina", 70000, 900, rel="other"),
                post("https://www.instagram.com/reel/A6/", "RivalSkin", "Glow Serum", "newface", 64000, 3000)]}]}],
        "creators": {"newface": {"name": "New Face", "followers": 64000, "city": "Jeddah", "type": "hcp",
                                 "links": {"Instagram": "https://www.instagram.com/newface/",
                                           "TikTok": "https://www.tiktok.com/@newface"}}}}
TIKTOK = {"platforms": ["tiktok"], "source": "tiktok study",
          "brands": [{"brand": "Glow Serum", "competitors": [{"competitor": "RivalSkin", "fit": "direct", "posts_detail": [
              dict(post("https://www.tiktok.com/@khalid/video/9", "RivalSkin", "Glow Serum", "khalid", 400000, 20000), platform="tiktok")]}]}]}


def upload(c, path, fields, payload):
    """multipart/form-data POST with one JSON file (the test Client only speaks JSON and forms)."""
    b = "----hvtest"
    parts = []
    for k, v in fields.items():
        parts.append('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v))
    head = "".join(parts) + '--%s\r\nContent-Disposition: form-data; name="file"; filename="pack.json"\r\nContent-Type: application/json\r\n\r\n' % b
    body = head.encode() + json.dumps(payload).encode() + ("\r\n--%s--\r\n" % b).encode()
    req = urllib.request.Request(c.base + path, data=body, method="POST",
                                 headers={"Origin": c.base, "Content-Type": "multipart/form-data; boundary=" + b})
    try:
        r = c.op.open(req)
    except urllib.error.HTTPError as exc:
        r = exc
    return (r.status if hasattr(r, "status") else r.code), r


class Evidence(unittest.TestCase):
    signup = base.Portal.signup
    admin = base.Portal.admin
    member = base.Portal.member

    @classmethod
    def setUpClass(cls):
        base.seed()
        db.set_setting("signup_mode", "open")
        db.set_setting("signups_per_ip_day", 1000)
        mailer.CAPTURE = True
        gemini.STUB = base.stub
        views.set_base("")
        db.set_setting("domain_kam", {"polyco.com": KAM, "rivalco.com": OTHER})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.ready = False

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(base.TMP, ignore_errors=True)

    def setUp(self):
        guard.limiter._hits.clear()
        mailer.OUTBOX.clear()
        if not Evidence.ready:
            W = Evidence
            W.client, _ = self.signup("lead@polyco.com")
            W.stranger, _ = self.signup("buyer@rivalco.com")
            W.mine = portal.user_by_email("lead@polyco.com")
            W.theirs = portal.user_by_email("buyer@rivalco.com")
            W.sel = db.save_selection(None, "Polyco glow", ["HV-MI-005"], {}, None, None, code_id=W.mine["code_id"])
            W.sel_other = db.save_selection(None, "Rival list", ["HV-MD-004"], {}, None, None, code_id=W.theirs["code_id"])
            W.token = db.selection(W.sel)["token"]
            self.member(KAM, "kam")
            self.member(OTHER, "kam")
            Evidence.ready = True

    def pack_id(self):
        with db.connect() as conn:
            return conn.execute("SELECT MAX(id) FROM evidence_packs WHERE deleted_at IS NULL").fetchone()[0]

    def test_1_import_matches_roster_and_ranks_organic(self):
        a = self.admin()
        s, r = upload(a, "/evidence/import", {"title": "Polyco competitors", "code_id": self.mine["code_id"],
                                              "selection_id": self.sel}, PACK)
        self.assertEqual(s, 303)
        self.assertIn("matched", r.headers["Location"])
        pid = self.pack_id()
        rows = evidence.posts(pid)
        self.assertEqual(len(rows), 6)
        self.assertEqual({r["handle"]: r["code"] for r in rows}["noha"], "HV-MI-001")      # matched by handle
        comp = evidence.summary(evidence.pack(pid))[0]["competitors"][0]
        handles = [t["handle"] for t in comp["top"]]
        self.assertEqual(handles[0], "noha")                      # median 70K beats sara's 30K
        self.assertNotIn("bought", handles)                       # paid-boosted only: not evidence
        self.assertNotIn("lina", handles)                         # other product
        self.assertEqual(comp["paid_boost"], 1)
        s, body, _ = a.get("/evidence/view?id=%d" % pid)
        self.assertEqual(s, 200)
        self.assertIn("RivalSkin", body)
        self.assertIn("internal note", body)                      # admins see the analyst's read
        self.assertIn("Open selection: Polyco glow", body)       # back to the selection
        self.assertIn("/market/#s=", body)                         # and to the Market Intelligence page
        s2, sbody, _ = a.get("/selections/edit?id=%d" % self.sel)
        self.assertIn("Market Intelligence", sbody)               # and from the selection to the pack
        self.assertIn("/evidence/view?id=%d" % pid, sbody)
        self.assertEqual(a.get("/evidence")[0], 200)

    def test_2_add_creators_to_the_selection(self):
        a = self.admin()
        pid = self.pack_id()
        s, _, _ = a.req("POST", "/evidence/add", form={"id": str(pid), "codes": "HV-MI-001"})
        self.assertEqual(s, 303)
        self.assertIn("HV-MI-001", json.loads(db.selection(self.sel)["codes"]))

    def test_3_client_sees_it_only_once_shared(self):
        pid = self.pack_id()
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual((s, b["evidence"]), (200, None))         # not shared yet
        a = self.admin()
        a.req("POST", "/evidence/save", form={"id": str(pid), "title": "Polyco competitors",
                                              "selection_id": str(self.sel), "client_visible": "1"})
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual(s, 200)
        ev = b["evidence"]
        comp = ev["brands"][0]["competitors"][0]
        self.assertEqual(comp["competitor"], "RivalSkin")
        self.assertTrue(comp["top"][0]["in_selection"])           # added in test 2
        raw = json.dumps(ev)
        self.assertNotIn("internal note", raw)                    # no analyst notes
        self.assertNotIn("HV-MI-002", raw)                        # no roster code outside this selection
        self.assertEqual(ev["by_code"]["HV-MI-001"], {"brands": 1, "posts": 2})   # Track record count on the card
        self.assertNotIn("/reel/A5/", raw)                        # other-product posts left out
        s, b, _ = self.stranger.get("/api/evidence?s=" + self.token)
        self.assertEqual(s, 401)                                  # another company's account

    def test_3a_track_record_for_one_creator(self):
        s, b, _ = self.client.get("/api/evidence/creator?s=%s&c=HV-MI-001" % self.token)
        self.assertEqual(s, 200, b)
        self.assertIn("creator", b, b)
        c = b["creator"]
        self.assertEqual((c["handle"], c["kpis"]["posts"], c["kpis"]["median_views"]), ("noha", 2, 70000))
        self.assertEqual(c["competitors"], [{"name": "RivalSkin", "posts": 2}])
        self.assertNotIn("internal note", json.dumps(b))
        self.assertEqual(self.client.get("/api/evidence/creator?s=%s&c=HV-MI-002" % self.token)[0], 404)   # not in the selection
        self.assertEqual(self.stranger.get("/api/evidence/creator?s=%s&c=HV-MI-001" % self.token)[0], 401)
        a = self.admin()
        s, body, _ = a.get("/selections/edit?id=%d" % self.sel)
        self.assertIn("/evidence/view?id=%d&amp;c=HV-MI-001#tr" % self.pack_id(), body)   # row link
        s, body, _ = a.get("/evidence/view?id=%d&c=HV-MI-001" % self.pack_id())
        self.assertIn("Track record: Noha", body)

    def test_3b_post_pictures_come_from_our_server(self):
        import thumbs
        jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
        seen = []
        thumbs.candidates = lambda url, plat, hint=None: seen.append(url) or ["https://cdn.example/x.jpg"]
        thumbs._image = lambda u: (jpg, "jpg")
        c = self.client.get("/api/evidence/creator?s=%s&c=HV-MI-001" % self.token)[1]["creator"]
        pid = c["posts"][0]["id"]
        r = self.client.op.open(urllib.request.Request(self.base + "/api/evidence/thumb?s=%s&p=%d" % (self.token, pid), headers={"Origin": self.base}))
        self.assertEqual((r.status, r.headers["Content-Type"], r.read()), (200, "image/jpeg", jpg))
        self.client.op.open(urllib.request.Request(self.base + "/api/evidence/thumb?s=%s&p=%d" % (self.token, pid)))
        self.assertEqual(len(seen), 1)                                     # fetched once, then kept
        with db.connect() as conn:
            other = conn.execute("SELECT id FROM evidence_posts WHERE relevance = 'other' AND pack_id = ?", (self.pack_id(),)).fetchone()[0]
        self.assertEqual(self.client.get("/api/evidence/thumb?s=%s&p=%d" % (self.token, other))[0], 404)   # not shown
        self.assertEqual(self.stranger.get("/api/evidence/thumb?s=%s&p=%d" % (self.token, pid))[0], 401)

    def test_3c_market_intelligence_map_is_this_selection_only(self):
        s, b, _ = self.client.get("/api/evidence/map?s=" + self.token)
        self.assertEqual(s, 200, b)
        m = b["map"]
        self.assertEqual(m["brand"], "Glow Serum")
        self.assertEqual([c["handle"] for c in m["creators"]], ["noha"])      # only the selection's creators
        self.assertEqual([(c["name"], c["creators"]) for c in m["competitors"]], [("RivalSkin", 1)])
        self.assertNotIn("internal note", json.dumps(b))
        self.assertEqual(self.stranger.get("/api/evidence/map?s=" + self.token)[0], 401)
        self.assertEqual(m["role"], "owner")                                   # the owner gets Approve / Reject
        self.assertIsNone(m["creators"][0]["status"])
        totals = [(c["posts"], c["views"], c["creators"]) for c in m["competitors"]]
        # Owner (2026-10-15): a rejected creator stays on the map, tagged, and in every total; nothing is hidden.
        self.assertEqual(self.client.post("/api/selection/status", {"token": self.token, "code": "HV-MI-001", "status": "rejected"})[0], 200)
        self.assertEqual(self.client.post("/api/selection/reason", {"token": self.token, "code": "HV-MI-001", "reason": "price"})[0], 200)
        m = self.client.get("/api/evidence/map?s=" + self.token)[1]["map"]
        self.assertEqual([(c["handle"], c["status"]) for c in m["creators"]], [("noha", "rejected")])
        self.assertEqual((m["rejected_on_map"], m["reasons"]), (1, {"HV-MI-001": "price"}))
        self.assertEqual([(c["posts"], c["views"], c["creators"]) for c in m["competitors"]], totals)
        self.client.post("/api/selection/status", {"token": self.token, "code": "HV-MI-001", "status": "approved"})
        self.assertEqual(self.client.get("/api/evidence/map?s=" + self.token)[1]["map"]["creators"][0]["status"], "approved")
        self.client.post("/api/selection/status", {"token": self.token, "code": "HV-MI-001", "status": "review"})
        self.assertIsNone(self.client.get("/api/evidence/map?s=" + self.token)[1]["map"]["creators"][0]["status"])

    def test_3d_logos_ranking_and_add_to_selection(self):
        svg_ok = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
        evidence.set_logo("RivalSkin", svg_ok, "svg", source="test")
        with self.assertRaises(ValueError):
            evidence.set_logo("Evil", b'<svg onload="alert(1)"></svg>', "svg")
        evidence.set_logo("Pending", svg_ok, "svg", approved=False)
        evidence.set_logo("Declared", b'<?xml version="1.0" encoding="UTF-8" standalone="no"?><svg xmlns="http://www.w3.org/2000/svg"/>', "svg")  # not an event attribute
        r = self.client.op.open(urllib.request.Request(self.base + "/api/brand-logo?n=RivalSkin"))
        self.assertEqual((r.status, r.headers["Content-Type"]), (200, "image/svg+xml"))
        self.assertEqual(self.client.get("/api/brand-logo?n=Pending")[0], 404)       # not approved: not served
        # sara is in the pack and on the roster but not in the selection: not on the map until added
        m = self.client.get("/api/evidence/map?s=" + self.token)[1]["map"]
        self.assertNotIn("sara", [c["handle"] for c in m["creators"]])
        s, b, _ = self.client.post("/api/evidence/add", {"token": self.token, "handle": "sara"})
        self.assertEqual((s, b.get("code")), (200, "HV-MI-002"), b)
        m = self.client.get("/api/evidence/map?s=" + self.token)[1]["map"]
        self.assertEqual(m["rank_by"], "views")
        self.assertTrue(m["competitors"][0]["logo"].startswith("/api/brand-logo?n=RivalSkin"))
        self.assertEqual([c["handle"] for c in m["creators"]], ["noha", "sara"])        # ranked by median views
        e = m["creators"][0]["estimate"]                                                # owner, 2026-10-15
        self.assertTrue(e and e["lo"] <= e["mid"] <= e["hi"] and e["n"] >= 1, e)
        s2, sel = self.client.get("/api/selection?s=" + self.token)[:2]
        self.assertEqual((s2, sel.get("metric")), (200, "views"), sel)                 # awareness projects views
        self.assertEqual(self.stranger.post("/api/evidence/add", {"token": self.token, "handle": "sara"})[0], 403)
        self.assertEqual(self.client.post("/api/evidence/add", {"token": self.token, "handle": "nobody"})[0], 404)

    def test_4_tiktok_adds_to_the_same_pack(self):
        a = self.admin()
        pid = self.pack_id()
        s, _ = upload(a, "/evidence/import", {"pack_id": pid}, TIKTOK)
        self.assertEqual(s, 303)
        pk = evidence.pack(pid)
        self.assertEqual(json.loads(pk["platforms"]), ["instagram", "tiktok"])
        comp = evidence.summary(pk)[0]["competitors"][0]
        self.assertEqual(comp["top"][0]["handle"], "khalid")
        self.assertEqual(comp["top"][0]["code"], "HV-MD-003")

    def test_5_kam_scope(self):
        pid = self.pack_id()
        mine, _, _ = self.member(KAM, "kam")
        other, _, _ = self.member(OTHER, "kam")
        self.assertEqual(mine.get("/evidence/view?id=%d" % pid)[0], 200)
        self.assertEqual(other.get("/evidence/view?id=%d" % pid)[0], 403)
        self.assertNotIn("Polyco competitors", other.get("/evidence")[1])
        self.assertEqual(other.req("POST", "/evidence/add", form={"id": str(pid), "codes": "HV-MI-002"})[0], 403)
        s, _ = upload(other, "/evidence/import", {"title": "x", "code_id": self.mine["code_id"]}, PACK)
        self.assertEqual(s, 403)                                  # not her client
        # her own client, but a selection of someone else's
        s, r = upload(other, "/evidence/import", {"title": "x", "code_id": self.theirs["code_id"],
                                                  "selection_id": self.sel}, PACK)
        self.assertEqual(s, 403)

    def test_6_bad_file_is_refused_readably(self):
        a = self.admin()
        s, r = upload(a, "/evidence/import", {"title": "x", "code_id": self.mine["code_id"]}, {"nope": 1})
        self.assertEqual(s, 303)
        self.assertIn("e=", r.headers["Location"])

    def test_65_missing_creators_go_on_the_roster_hidden_and_marked(self):
        import apify
        a = self.admin()
        pid = self.pack_id()
        st = evidence.roster_status(evidence.pack(pid))
        self.assertEqual((st["total"], st["missing"]), (6, 2))          # bought + newface are missing
        s, _, r = a.req("POST", "/evidence/roster", form={"id": str(pid)})
        self.assertEqual(s, 303)
        code = next(p["code"] for p in evidence.posts(pid) if p["handle"] == "newface")
        c = db.creator(code)
        self.assertEqual((c["name"], c["active"], c["city"]), ("New Face", 0, "Jeddah"))
        self.assertIn("TikTok", c["platform"])
        self.assertIn("competitor evidence", c["note"])
        st = evidence.roster_status(evidence.pack(pid))
        self.assertEqual((st["missing"], st["added"]), (0, 2))
        s, _, r = a.req("POST", "/evidence/roster", form={"id": str(pid)})   # nothing left: adds none twice
        self.assertEqual(len(evidence.roster_codes(pid)), 2)
        # The Apify target picks up exactly the marked creators, hidden or not (no run is started here).
        job = {"platform": "TikTok", "source": "evidence:%d" % pid, "max_handles": 100}
        self.assertEqual(apify.build_handles(job), [(code, "newface")])
        job["source"] = "all"
        self.assertNotIn(code, [c for c, _ in apify.build_handles(job)])  # hidden: not in ordinary jobs
        import apis_view
        self.assertIn("evidence:%d" % pid, apis_view._sources("sample20"))      # offered as a job target
        other, _, _ = self.member(OTHER, "kam")
        self.assertEqual(other.req("POST", "/evidence/roster", form={"id": str(pid)})[0], 403)

    def test_66_photos_and_apify_profile_update_the_added_creators_only(self):
        import tempfile, apify
        from pathlib import Path
        pid = self.pack_id()
        code = next(p["code"] for p in evidence.posts(pid) if p["handle"] == "newface")
        tmp = Path(tempfile.mkdtemp())
        photos, live = tmp / "study", tmp / "live"
        photos.mkdir()
        thumb = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x64\x00\x64" + b"\x00" * 200      # a 100x100 JPEG header
        (photos / "newface.jpg").write_bytes(thumb)
        (photos / "noha.jpg").write_bytes(thumb)                                       # on the roster before: untouched
        self.assertEqual(evidence.attach_photos(pid, photos, live), 1)
        self.assertEqual(db.creator(code)["photo"], code + ".jpg")
        # An Apify Instagram profile result: followers, tier and an HD photo replace the study's numbers.
        hd = b"\xff\xd8\xff\xc0\x00\x11\x08\x01\x40\x01\x40" + b"\x00" * 400      # 320x320
        evidence.PHOTO_DIR, fetched = live, []
        evidence._fetch_pic = lambda url: fetched.append(url) or hd
        job = {"kind": "profiles", "platform": "Instagram", "actor": "apify/instagram-profile-scraper"}
        run = {"id": 1, "handle_map": json.dumps({"newface": code, "noha": "HV-MI-001"})}
        items = [{"username": "newface", "followersCount": 260000, "profilePicUrlHD": "https://scontent.cdninstagram.com/x.jpg"},
                 {"username": "noha", "followersCount": 99999, "profilePicUrlHD": "https://scontent.cdninstagram.com/y.jpg"}]
        before = db.creator("HV-MI-001")
        apify.init()
        apify.ingest(run, job, items)
        c = db.creator(code)
        self.assertEqual(c["followers"], 260000)
        self.assertEqual(c["tier"], db.tier_for_reach(260000))
        self.assertEqual((live / (code + ".jpg")).read_bytes(), hd)
        self.assertEqual(len(fetched), 2)               # noha is in the study with no photo: photo only (2026-10-14)
        after = db.creator("HV-MI-001")
        self.assertEqual((after["followers"], after["tier"]), (before["followers"], before["tier"]))
        shutil.rmtree(tmp, ignore_errors=True)

    def test_665_gaps_target_and_photo_only_upgrade_for_existing_creators(self):
        import tempfile, apify
        from pathlib import Path
        pid = self.pack_id()
        live = Path(tempfile.mkdtemp())
        evidence.PHOTO_DIR = live
        gaps = evidence.gap_codes(pid, live)
        self.assertIn("HV-MI-001", gaps)                       # noha: on the roster before, no photo file here
        before = db.creator("HV-MI-001")
        hd = b"\xff\xd8\xff\xc0\x00\x11\x08\x01\x40\x01\x40" + b"\x00" * 400
        evidence._fetch_pic = lambda url: hd
        apify.init()
        apify.ingest({"id": 9, "handle_map": json.dumps({"noha": "HV-MI-001"})},
                     {"kind": "profiles", "platform": "Instagram", "actor": "apify/instagram-profile-scraper"},
                     [{"username": "noha", "followersCount": 1234567, "profilePicUrlHD": "https://scontent.cdninstagram.com/z.jpg"}])
        after = db.creator("HV-MI-001")
        self.assertEqual((live / "HV-MI-001.jpg").read_bytes(), hd)          # photo upgraded
        self.assertEqual((after["followers"], after["tier"]), (before["followers"], before["tier"]))   # numbers kept
        self.assertNotIn("HV-MI-001", evidence.gap_codes(pid, live))         # gap closed (has analysis + HD photo now)
        job = {"platform": "Instagram", "source": "evidence-gaps:%d" % pid, "max_handles": 100}
        self.assertNotIn("HV-MI-001", [c for c, _ in apify.build_handles(job)])
        shutil.rmtree(live, ignore_errors=True)

    def test_67_picture_fetch_only_from_instagram_hosts(self):
        import importlib
        ev = importlib.reload(evidence)
        self.assertIsNone(ev._fetch_pic("https://evil.example.com/a.jpg"))
        self.assertIsNone(ev._fetch_pic("http://scontent.cdninstagram.com/a.jpg"))
        self.assertIsNone(ev._fetch_pic("https://cdninstagram.com.evil.io/a.jpg"))

    def test_7_delete(self):
        a = self.admin()
        pid = self.pack_id()
        a.req("POST", "/evidence/delete", form={"id": str(pid)})
        self.assertIsNone(evidence.pack(pid))
        s, b, _ = self.client.get("/api/evidence?s=" + self.token)
        self.assertEqual(b["evidence"], None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
