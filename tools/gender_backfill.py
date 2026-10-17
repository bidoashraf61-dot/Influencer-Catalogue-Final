"""Fill the creators' gender from name and handle with Gemini (owner, 2026-10-18).

No photos are sent: only each creator's display name and handle. The model answers male, female or unknown
with a confidence; the apply step only keeps confident answers. Run it against a COPY of the admin (code,
key and a copy of catalogue.db), never against the live service (see docs/GENDER.md):

    python3 tools/gender_backfill.py classify --db /tmp/gb/admin/catalogue.db --out /tmp/gb/genders.json [--limit N]
    python3 tools/gender_backfill.py apply --db <live catalogue.db> --in /tmp/gb/genders.json [--sheet names.json] [--min 0.75] [--dry]

``classify`` can be stopped and started again: codes already in the output file are skipped.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

ADMIN = Path(__file__).resolve().parent.parent / "admin"
sys.path.insert(0, str(ADMIN))

BATCH = 60
SYSTEM = (
    "You label the gender of social media creators in the Middle East and North Africa from ONLY their display name "
    "and handle. Answer 'male' or 'female' only when the first name makes it reasonably clear (Arabic names written in "
    "Arabic or Latin letters, and English names). Answer 'unknown' for brands, clinics, shops, groups, couples, "
    "initials, nicknames, ambiguous names, and anything you are not sure about. Give a confidence from 0 to 1. "
    "Never guess to be helpful: unknown is a good answer.")
SCHEMA = {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
    "i": {"type": "INTEGER"}, "g": {"type": "STRING", "enum": ["male", "female", "unknown"]}, "c": {"type": "NUMBER"}},
    "required": ["i", "g", "c"]}}


def classify(batch, gemini):
    """batch: [(code, name, handle)] -> {code: (gender, confidence)}"""
    lines = "\n".join("%d | %s | %s" % (i, (n or "").strip()[:80], (h or "").strip()[:60]) for i, (_, n, h) in enumerate(batch))
    out = gemini.generate_json("Label each creator. One line each: index | display name | handle\n" + lines, SCHEMA,
                               system=SYSTEM, temperature=0.0, max_tokens=4096, kind="gender", timeout=60)
    res = {}
    for row in out if isinstance(out, list) else []:
        try:
            i, g, c = int(row["i"]), str(row["g"]).lower(), float(row.get("c") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < len(batch) and g in ("male", "female", "unknown"):
            res[batch[i][0]] = (g, max(0.0, min(1.0, c)))
    return res


def cmd_classify(a):
    import db
    import gemini
    db.DB_PATH = Path(a.db)
    done = json.loads(Path(a.out).read_text()) if Path(a.out).exists() else {}
    with db.connect() as conn:
        rows = [(r["code"], r["name"], r["handle"]) for r in conn.execute(
            "SELECT code, name, handle FROM creators WHERE active = 1 AND (gender IS NULL OR gender = '') ORDER BY code")]
    todo = [r for r in rows if r[0] not in done]
    if a.limit:
        todo = todo[:a.limit]
    print("creators to read:", len(todo), "of", len(rows), "(already done: %d)" % len(done), flush=True)
    for s in range(0, len(todo), BATCH):
        part = todo[s:s + BATCH]
        try:
            got = classify(part, gemini)
        except Exception as exc:                 # keep what we have; run again to continue
            print("stopped at batch", s // BATCH, "->", exc, flush=True)
            break
        for code, (g, c) in got.items():
            done[code] = [g, round(c, 2)]
        Path(a.out).write_text(json.dumps(done))
        print("batch %d: %d read, %d total" % (s // BATCH, len(got), len(done)), flush=True)
    m = sum(1 for g, c in done.values() if g == "male"); f = sum(1 for g, c in done.values() if g == "female")
    print("male %d, female %d, unknown %d" % (m, f, len(done) - m - f))


def cmd_apply(a):
    import db
    db.DB_PATH = Path(a.db)
    sheet = json.loads(Path(a.sheet).read_text()) if a.sheet else {}
    results = json.loads(Path(a.inp).read_text()) if a.inp else {}
    n_sheet = n_ai = skipped = 0
    with db.connect() as conn:
        by_name = {}
        for r in conn.execute("SELECT code, name FROM creators WHERE active = 1"):
            by_name.setdefault((r["name"] or "").strip().lower(), []).append(r["code"])
    for name, g in sheet.items():
        codes = by_name.get(name.strip().lower()) or []
        if len(codes) == 1 and g in ("male", "female"):
            if not a.dry and db.set_gender(codes[0], g, "sheet", 1.0):
                n_sheet += 1
            elif a.dry:
                n_sheet += 1
    for code, (g, c) in results.items():
        if g in ("male", "female") and c >= a.min:
            if a.dry or db.set_gender(code, g, "ai", c):
                n_ai += 1
        else:
            skipped += 1
    print("%sfrom the sheets: %d, from the AI: %d, left unknown: %d" % ("(dry run) " if a.dry else "", n_sheet, n_ai, skipped))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("classify"); c.add_argument("--db", required=True); c.add_argument("--out", required=True); c.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("apply"); p.add_argument("--db", required=True); p.add_argument("--in", dest="inp"); p.add_argument("--sheet")
    p.add_argument("--min", type=float, default=0.75); p.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    {"classify": cmd_classify, "apply": cmd_apply}[a.cmd](a)
