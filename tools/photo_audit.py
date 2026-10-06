#!/usr/bin/env python3
"""Grade every creator photo against the catalogue's quality bar.

Cards are ~330px wide, so anything under 320px on its shortest side is drawn
as the small soft circle rather than a full-bleed photo. This lists who falls
short, so better pictures can be fetched or asked for in priority order:
creators a client can see (on a selection or a campaign) first.

Reads catalogue.db read-only and the photo folder; writes CSV to stdout. The
output holds creator codes and handles, so it never goes in this repo.

    ssh AWS 'python3 - --db .../catalogue.db --photos .../assets/catalogue' \
        < tools/photo_audit.py > photo-audit.csv

Grades:
    good     shortest side >= 320px
    lowres   101-319px
    thumb    <= 100px
    missing  no photo set, file gone, or not a readable image
Flags (worth a look even when the grade is good):
    tiny     file under 1.5KB, usually a blank or default avatar
    dup      byte-identical to another creator's photo
"""

import argparse
import collections
import csv
import hashlib
import json
import sqlite3
import struct
import sys
from pathlib import Path

GOOD = 320
THUMB = 100
TINY_BYTES = 1500


def dims(data):
    """(width, height) of a JPEG or PNG, (0, 0) if neither."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] != b"\xff\xd8":
        return 0, 0
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        if m == 0xD8 or m == 0x01 or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return 0, 0


def grade(short):
    if short <= 0:
        return "missing"
    if short <= THUMB:
        return "thumb"
    if short < GOOD:
        return "lowres"
    return "good"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--photos", required=True)
    args = ap.parse_args()

    db = sqlite3.connect("file:" + args.db + "?mode=ro", uri=True)
    photos = Path(args.photos)

    on_selection = collections.Counter()
    for (codes,) in db.execute("select codes from selections"):
        for code in json.loads(codes or "[]"):
            on_selection[code] += 1
    on_campaign = collections.Counter(
        code for (code,) in db.execute("select code from campaign_creators"))

    rows = []
    hashes = collections.defaultdict(list)
    for code, platform, handle, photo, active in db.execute(
            "select code, platform, handle, photo, active from creators order by code"):
        name = (photo or "").split("?")[0]
        path = photos / name if name else None
        w = h = size = 0
        if path and path.is_file():
            data = path.read_bytes()
            size = len(data)
            w, h = dims(data)
            hashes[hashlib.md5(data).hexdigest()].append(code)
        rows.append({
            "code": code,
            "platform": platform or "",
            "handle": handle or "",
            "active": 1 if active else 0,
            "width": w,
            "height": h,
            "bytes": size,
            "grade": grade(min(w, h)),
            "flags": "tiny" if 0 < size < TINY_BYTES else "",
            "selections": on_selection.get(code, 0),
            "campaigns": on_campaign.get(code, 0),
        })

    dup = {c for codes in hashes.values() if len(codes) > 1 for c in codes}
    for r in rows:
        if r["code"] in dup:
            r["flags"] = (r["flags"] + " dup").strip()
        seen = r["selections"] or r["campaigns"]
        r["priority"] = "P1" if seen and r["active"] else "P2" if r["active"] else "P3"
        r["status"] = "ok" if r["grade"] == "good" and not r["flags"] else "to fix"

    rows.sort(key=lambda r: (r["priority"], r["status"] != "to fix",
                             r["width"], r["code"]))
    cols = ["code", "priority", "status", "grade", "flags", "width", "height",
            "bytes", "platform", "handle", "active", "selections", "campaigns"]
    out = csv.DictWriter(sys.stdout, fieldnames=cols, extrasaction="ignore")
    out.writeheader()
    out.writerows(rows)

    tally = collections.Counter((r["priority"], r["status"]) for r in rows)
    grades = collections.Counter(r["grade"] for r in rows if r["active"])
    print("active by grade: " + ", ".join(
        "%s %d" % (g, grades[g]) for g in ("good", "lowres", "thumb", "missing")),
        file=sys.stderr)
    for p in ("P1", "P2", "P3"):
        print("%s  to fix %d  ok %d" % (p, tally[(p, "to fix")], tally[(p, "ok")]),
              file=sys.stderr)


if __name__ == "__main__":
    main()
