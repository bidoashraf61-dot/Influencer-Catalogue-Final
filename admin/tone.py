"""Creator tone tags (item 172, the "Tone" power-up).

The roster holds no tone, so a monthly batch (tools/tone_batch.py) asks Gemini to tag each
analysed creator from their bio and topics. The batch runs in a throwaway container on a COPY
of the database and writes a JSONL file; this module imports that file and serves the tags.

    python3 admin/tone.py import /path/tones.jsonl
"""

import json
import sys
import threading
import time

import db

TAGS = ("educational", "fun", "emotional", "premium", "everyday")
_lock = threading.Lock()
_cache = {"sig": None, "tags": {}}


def ensure():
    with db.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS creator_tone (code TEXT PRIMARY KEY, tones TEXT NOT NULL, "
                     "model TEXT, updated_at INTEGER NOT NULL)")


def all_tags():
    """{code: [tone, ...]}, cached until the table changes."""
    try:
        with db.connect() as conn:
            sig = tuple(conn.execute("SELECT COUNT(*), COALESCE(MAX(updated_at), 0) FROM creator_tone").fetchone())
            if sig == _cache["sig"]:
                return _cache["tags"]
            rows = conn.execute("SELECT code, tones FROM creator_tone").fetchall()
    except Exception:
        return {}
    out = {}
    for code, tones in rows:
        try:
            out[code] = [t for t in json.loads(tones) if t in TAGS]
        except ValueError:
            continue
    with _lock:
        _cache.update(sig=sig, tags=out)
    return out


def import_file(path):
    """Upsert tags from a tone_batch JSONL file. Returns the number of creators stored."""
    ensure()
    now = int(time.time())
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            tones = [t for t in (r.get("tones") or []) if t in TAGS][:2]
            if r.get("code") and tones:
                rows.append((str(r["code"]), json.dumps(tones), str(r.get("model") or "")[:40], now))
    with db.connect() as conn:
        conn.executemany("INSERT INTO creator_tone (code, tones, model, updated_at) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT(code) DO UPDATE SET tones = excluded.tones, model = excluded.model, "
                         "updated_at = excluded.updated_at", rows)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "import":
        print("stored", import_file(sys.argv[2]))
    else:
        print(__doc__)
