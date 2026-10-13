"""Thumbnails for every post in every analysis (2026-10-13). Runs inside influencer-catalogue-admin.
   python3 post_thumbs.py Instagram|TikTok [--limit N]
Order: popular posts of everyone, then recent posts, then sponsored posts. Resumable (a post with a thumb is skipped).
Instagram: the post's own /media/ link (redirects to the picture, no login). TikTok: its public oEmbed lookup.
Gentle on both sites: a few requests a second, a long pause when one pushes back."""
import sys, os, re, json, time, threading, urllib.request, urllib.parse, urllib.error, concurrent.futures as cf
sys.path.insert(0, "/app/admin"); os.chdir("/app/admin")
import db, analysis
PLAT = sys.argv[1]; LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
MEDIA = analysis.MEDIA
IG = re.compile(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)"); TT = re.compile(r"tiktok\.com/@[^/]+/video/(\d+)")
RX, PREFIX = (IG, "ig") if PLAT == "Instagram" else (TT, "tt")
WORKERS, GAP = (2, 0.5) if PLAT == "Instagram" else (5, 0.2)
lock = threading.Lock(); pause_until = [0.0]; st = {"posts": 0, "ok": 0, "gone": 0, "err": 0, "pushback": 0}
def wait_turn():
    while time.time() < pause_until[0]: time.sleep(1)
def fetch(url):
    """bytes, None for gone, b'' for a failure worth retrying later"""
    for i in range(3):
        wait_turn()
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25)
            return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 400 and PLAT == 'Instagram': return None
            if e.code == 400 and i >= 1: return None
            if e.code in (429, 403, 401):
                with lock: st["pushback"] += 1; pause_until[0] = time.time() + 180
            time.sleep(3 * (i + 1))
        except Exception: time.sleep(3)
    return b""
def one(job):
    code, key, url = job
    if key in GONE: return "gone"
    dest = MEDIA / code / ("%s-%s.jpg" % (PREFIX, key))
    if dest.exists(): return dest.name
    if PLAT == "Instagram":
        img = fetch("https://www.instagram.com/p/%s/media/?size=m" % key); time.sleep(GAP)
    else:
        url = re.sub(r"^https?://(www\.)?tiktok\.com", "https://www.tiktok.com", url)     # oEmbed refuses the link without www
        raw = fetch("https://www.tiktok.com/oembed?url=" + urllib.parse.quote(url, safe="")); time.sleep(GAP)
        if raw is None: note_gone(key); return "gone"
        if raw == b"": return "err"
        try: th = json.loads(raw).get("thumbnail_url")
        except Exception: return "err"
        if not th: note_gone(key); return "gone"
        img = fetch(th)
    if img is None: note_gone(key); return "gone"
    if not img or len(img) < 1500: return "err"
    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(img); return dest.name
GONE_F = MEDIA / ("_gone_%s.txt" % PLAT)
GONE = set(GONE_F.read_text().split()) if GONE_F.exists() else set()
def note_gone(key):
    with lock:
        if key not in GONE:
            GONE.add(key)
            with open(GONE_F, "a") as fh: fh.write(key + chr(10))
t0 = time.time(); docs = 0
with db.connect() as conn:
    codes = [r["code"] for r in conn.execute("SELECT code FROM creator_analysis WHERE platform=? ORDER BY updated_at DESC", (PLAT,))]
if LIMIT: codes = codes[:LIMIT]
for kind in ("top_posts", "recent_posts", "sponsored_posts"):
    for code in codes:
        with db.connect() as conn:
            row = conn.execute("SELECT data FROM creator_analysis WHERE code=? AND platform=?", (code, PLAT)).fetchone()
        if not row: continue
        d = json.loads(row["data"]); jobs, refs = [], []
        for p in d.get(kind) or []:
            m = RX.search(p.get("url") or "")
            if m and not p.get("thumb"): jobs.append((code, m.group(1), p["url"])); refs.append(p)
        if not jobs: continue
        with cf.ThreadPoolExecutor(WORKERS) as ex: res = list(ex.map(one, jobs))
        changed = False
        for out, p in zip(res, refs):
            st["posts"] += 1
            if out.endswith(".jpg"): p["thumb"] = "media:" + out; st["ok"] += 1; changed = True
            elif out == "gone": st["gone"] += 1
            else: st["err"] += 1
        if changed:
            with db.connect() as conn:
                # re-read: a doc touched by another job meanwhile keeps its other thumbs
                cur = conn.execute("SELECT data FROM creator_analysis WHERE code=? AND platform=?", (code, PLAT)).fetchone()
                dd = json.loads(cur["data"])
                for k2 in ("top_posts", "recent_posts", "sponsored_posts"):
                    for p2 in dd.get(k2) or []:
                        for p in refs:
                            if p.get("thumb") and p2.get("url") == p.get("url") and not p2.get("thumb"): p2["thumb"] = p["thumb"]
                conn.execute("UPDATE creator_analysis SET data=? WHERE code=? AND platform=?", (json.dumps(dd, ensure_ascii=False), code, PLAT))
        docs += 1
        if docs % 100 == 0: print(kind, "docs", docs, st, "%.0fs" % (time.time() - t0), flush=True)
    print("PASS DONE", kind, st, "%.0fs" % (time.time() - t0), flush=True)
open("/tmp/thumbs_%s.done" % PLAT, "w").write("1"); print("ALL DONE", st, flush=True)
