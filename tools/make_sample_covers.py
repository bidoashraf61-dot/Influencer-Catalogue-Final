#!/usr/bin/env python3
"""Blurred popular-post covers for the sample full analysis (item 39).

    python3 tools/make_sample_covers.py HV-HCPG-003 [--media /path/to/admin/analysis_media]

Reads <media>/<CODE>/post-N.jpeg (the creator's real covers, never served through the sample) and
writes <media>/_sample/<CODE>/cover-<N-1>.jpg: shrunk to a few pixels and blurred, so faces, text and
branding cannot be read but colour and composition still look like a real post. Needs Pillow.
Run it again whenever the sample creator (Admin -> Client portal -> Settings) changes.
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageFilter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--media", default=str(Path(__file__).resolve().parent.parent / "admin" / "analysis_media"))
    a = ap.parse_args()
    code = re.sub(r"[^A-Z0-9-]", "", a.code.upper())
    src = Path(a.media) / code
    out = Path(a.media) / "_sample" / code
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("post-*.*")):
        m = re.match(r"post-(\d+)\.", f.name)
        if not m:
            continue
        i = int(m.group(1)) - 1
        im = Image.open(f).convert("RGB")
        im.thumbnail((14, 14), Image.LANCZOS)                      # almost nothing is left to read
        im = im.resize((360, 360), Image.BICUBIC).filter(ImageFilter.GaussianBlur(10))
        im.save(out / ("cover-%d.jpg" % i), "JPEG", quality=70)
        n += 1
    print("%d covers written to %s" % (n, out))
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
