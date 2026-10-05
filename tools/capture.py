#!/usr/bin/env python3
"""The capture job's side of the campaign tracker: talks to the admin service
from the team Mac. Claude (in Chrome) does the looking; this does the sending.

    python3 tools/capture.py jobs                 # what to capture today (JSON)
    python3 tools/capture.py push results.json    # send captured posts
    python3 tools/capture.py shots DIR            # download insight screenshots to read
    python3 tools/capture.py insight ID values.json   # send numbers read off one upload
    python3 tools/capture.py done --posts N --insights N [--error TEXT]   # log the run

Settings come from ~/.hv_capture (two lines, KEY=value), never from the repo:

    HV_CAPTURE_URL=https://influencer-catalogue.hellovoice.co.uk/admin
    HV_CAPTURE_TOKEN=hvcap_…        # Admin → Settings → Capture job

Stdlib only. Full procedure: docs/CAPTURE-AGENT.md.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def config():
    cfg = {}
    f = Path.home() / ".hv_capture"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    cfg.update({k: v for k, v in os.environ.items() if k.startswith("HV_CAPTURE_")})
    if not cfg.get("HV_CAPTURE_URL") or not cfg.get("HV_CAPTURE_TOKEN"):
        sys.exit("Set HV_CAPTURE_URL and HV_CAPTURE_TOKEN in ~/.hv_capture")
    return cfg["HV_CAPTURE_URL"].rstrip("/"), cfg["HV_CAPTURE_TOKEN"]


def call(path, payload=None, raw=False):
    base, token = config()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + "/api/capture/" + path, data,
                                 {"Authorization": "Bearer " + token,
                                  "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
    except urllib.error.HTTPError as ex:
        sys.exit("server said %d: %s" % (ex.code, ex.read()[:300].decode("utf-8", "replace")))
    return body if raw else json.loads(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("jobs")
    p = sub.add_parser("push"); p.add_argument("file")
    p = sub.add_parser("shots"); p.add_argument("dir")
    p = sub.add_parser("insight"); p.add_argument("id"); p.add_argument("file")
    p = sub.add_parser("done")
    p.add_argument("--posts", type=int, default=0)
    p.add_argument("--insights", type=int, default=0)
    p.add_argument("--error", action="append", default=[])
    a = ap.parse_args()

    if a.cmd == "jobs":
        print(json.dumps(call("jobs"), indent=2, ensure_ascii=False))
    elif a.cmd == "push":
        # One file may hold several campaigns: [{"campaign_id": 3, "items": [...]}, ...]
        data = json.loads(Path(a.file).read_text())
        batches = data if isinstance(data, list) else [data]
        for b in batches:
            res = call("content", b)
            print("campaign %s: saved %d (%d new)" % (b.get("campaign_id"), res["saved"], res["new"]))
            for r in res.get("refused", []):
                print("  refused %s — %s" % (r.get("url"), r.get("why")))
    elif a.cmd == "shots":
        out = Path(a.dir); out.mkdir(parents=True, exist_ok=True)
        jobs = call("jobs")
        for i in jobs.get("insights_pending", []):
            for n in i["files"]:
                q = urllib.parse.urlencode({"i": i["id"], "n": n})
                (out / ("%d__%s" % (i["id"], n))).write_bytes(call("insight-file?" + q, raw=True))
            print("insight %d (%s, %s) -> %d file(s)" % (i["id"], i["code"], i.get("post_url") or "post not named",
                                                        len(i["files"])))
    elif a.cmd == "insight":
        values = json.loads(Path(a.file).read_text())
        call("insight", {"id": int(a.id), "values": values})
        print("insight %s sent for approval" % a.id)
    elif a.cmd == "done":
        call("run", {"ok": not a.error, "posts": a.posts, "insights": a.insights,
                     "errors": "\n".join(a.error)})
        print("run logged")


if __name__ == "__main__":
    main()
