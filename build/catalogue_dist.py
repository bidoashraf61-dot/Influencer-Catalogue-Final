#!/usr/bin/env python3
"""Assemble a standalone deployment tree containing only the catalogue.

The site build puts the catalogue at site/catalogue/, alongside the whole
HelloVoice site. Publishing site/ therefore serves the entire site, and a
visitor landing on the root gets the homepage rather than the roster — which
is exactly what happened on the first deployment.

This writes a tree that holds the catalogue and nothing else, with the roster
at the root so the shared link is just the domain:

    dist/index.html            the roster        (was catalogue/)
    dist/selection/index.html  one shortlist     (was catalogue/selection/)
    dist/assets/...            only the files those two pages reference

Assets are resolved by reading the built pages rather than by copying whole
directories, so nothing unreferenced is shipped and nothing referenced is
missed. Run after build/influencer_catalogue.py.

    python3 build/catalogue_dist.py
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DIST = ROOT / "dist"

CATALOGUE = SITE / "catalogue" / "index.html"
SELECTION = SITE / "catalogue" / "selection" / "index.html"


def referenced(page: Path, extra_css=True):
    """Every local file a page pulls in, resolved to real paths."""
    out = set()
    html = page.read_text(encoding="utf-8")

    def add(base: Path, url: str):
        if not url or url.startswith(("http", "mailto:", "#", "data:")):
            return
        out.add((base / url.split("?")[0]).resolve())

    for m in re.finditer(r'(?:href|src|poster)="([^"]+)"', html):
        add(page.parent, m.group(1))
    for m in re.finditer(r'srcset="([^"]+)"', html):
        for part in m.group(1).split(","):
            add(page.parent, part.strip().split(" ")[0])
    for m in re.finditer(r"url\(([^)]+)\)", html):
        add(page.parent, m.group(1).strip("'\""))

    if extra_css:
        for css in [p for p in out if p.suffix == ".css" and p.is_file()]:
            for m in re.finditer(r"url\(([^)]+)\)", css.read_text(encoding="utf-8")):
                add(css.parent, m.group(1).strip("'\""))
    return out


def main():
    for p in (CATALOGUE, SELECTION):
        if not p.exists():
            sys.exit(f"missing {p} — run build/influencer_catalogue.py first")

    needed = referenced(CATALOGUE) | referenced(SELECTION)
    site_root = SITE.resolve()
    assets = sorted(
        p for p in needed
        if p.is_file() and site_root in p.parents
        and p.relative_to(site_root).parts[0] == "assets"
    )

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    for src in assets:
        rel = src.relative_to(site_root)
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    # The pages were written for site/catalogue/ (one level down) and
    # site/catalogue/selection/ (two). At the root of dist they sit one level
    # higher, so every relative hop loses a step.
    roster = CATALOGUE.read_text(encoding="utf-8").replace("../assets/", "assets/")
    (DIST / "index.html").write_text(roster, encoding="utf-8")

    shortlist = (SELECTION.read_text(encoding="utf-8")
                 .replace("../../assets/", "../assets/")
                 .replace('href="../../catalogue/"', 'href="../"'))
    (DIST / "selection").mkdir()
    (DIST / "selection" / "index.html").write_text(shortlist, encoding="utf-8")

    # GitHub Pages runs Jekyll otherwise, which drops files it does not like.
    (DIST / ".nojekyll").write_text("")

    stray = [m.group(0) for m in re.finditer(r'(?:href|src|poster)="/[^"]*"', roster + shortlist)]
    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())

    print(f"assets copied   {len(assets)}")
    print(f"pages           index.html, selection/index.html")
    print(f"total size      {total / 1_048_576:.1f} MB")
    print(f"root-absolute   {len(stray)} (must be 0)")
    print(f"-> {DIST.relative_to(ROOT)}")
    if stray:
        sys.exit("root-absolute links would break under any base path")


if __name__ == "__main__":
    main()
