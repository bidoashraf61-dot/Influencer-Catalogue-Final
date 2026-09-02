#!/usr/bin/env python3
"""Install harvested profile photos into the catalogue asset folder.

The browser pass writes files named <handle>.jpg. This maps handle -> code
through the private key file and copies them to
site/assets/catalogue/<CODE>.jpg, which is what the page reads.

Why a folder and not a URL list: Instagram's CDN URLs are signed and
short-lived, and instagram.com's CSP blocks posting them anywhere useful, so
the bytes come out of the browser rather than the links.

    python3 build/catalogue_photos.py <source-dir>
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "content" / "catalogue_private.json"
OUT = ROOT / "site" / "assets" / "catalogue"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    if not src.is_dir():
        sys.exit(f"not a directory: {src}")
    if not PRIVATE.exists():
        sys.exit("run build/influencer_catalogue.py first — no private key file")

    private = json.loads(PRIVATE.read_text())
    by_handle = {v["handle"].lower(): code for code, v in private.items() if v.get("handle")}

    OUT.mkdir(parents=True, exist_ok=True)
    installed, unmatched = 0, []

    for f in sorted(src.glob("*.jpg")):
        handle = f.stem.lower()
        code = by_handle.get(handle)
        if not code:
            unmatched.append(f.stem)
            continue
        if f.stat().st_size < 500:
            unmatched.append(f.stem + " (too small)")
            continue
        shutil.copy2(f, OUT / f"{code}.jpg")
        installed += 1

    total = len(private)
    have = len(list(OUT.glob("*.jpg")))
    print(f"installed {installed}")
    print(f"coverage  {have}/{total}  ({have * 100 // total}%)")
    if unmatched:
        print(f"unmatched {len(unmatched)}: {', '.join(unmatched[:8])}")
    print("\nnow re-run: python3 build/influencer_catalogue.py")


if __name__ == "__main__":
    main()
