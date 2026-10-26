#!/usr/bin/env python3
"""Cache-busting stamps for the published catalogue site (item 175).

    python3 stamp_assets.py <site-root>              # rewrite the stamps in place (update.sh runs this)
    python3 stamp_assets.py <site-root> --check      # report stale stamps, change nothing, exit 1 if any
    python3 stamp_assets.py <site-root> --links-only # only refuse broken links, no stamping at all

Exit codes: 0 clean, 1 stale stamps (--check only), 2 a broken link, 64 bad arguments.

Why it matters: a js/css URL that carries ?v= is served "immutable" for a year (nginx
$hv_asset_cache) and the HELVi Connect service worker answers it from its own cache first.
So a stamp that is not bumped when the file changes pins every browser and every installed
app to the old file. The stamp must be the file's content hash, on every page, every time.

What it stamps:
  1. Inside the js files, only the URLs that already carry a ?v= (a script that loads another
     script or style this way). Repeated until nothing changes, so a file's own hash includes its children's.
  2. Every src= / href= / poster= / data-src= in every .html page under the root (assets/ is
     skipped) that points at an existing assets/js/*.js, assets/css/*.css or assets/welcome/ film
     file: any page, any file, no list to keep.
  3. sw.js: VERSION becomes "hca-<hash of the app shell>", so any release that changes a
     script, a style, the offline page, the manifest or an app icon installs a new worker,
     which drops the old caches and takes over the open app at once.

What it refuses (exit 2, in --check and when writing alike):
  1. A src/href/poster/data-src that names an assets/js, assets/css or assets/welcome file
     which is not there. This used to pass silently: with nothing to hash, the reference was
     simply left alone and the publish carried on.
  2. A <link rel="stylesheet"> whose href is not a .css, or a <script src> that is not a .js.
     Caught even when the named file does exist, which (1) cannot see. Only local URLs are
     judged, so a CDN stylesheet or a Google Fonts css2?family=... URL is never flagged.
Both come from the same accident: on 2026-10-26 a publish stamped by hand pasted
"dashboard.js?v=626f6b2f" over the dashboard's stylesheet link, and the page went live with
no CSS at all. The stamper rewrites the ?v= and never the path, so a path that does not line
up with its tag was typed or pasted wrong, and is an error rather than a warning.

The stamp is md5[:8] of the file, the same scheme update.sh has used since 2026-09-08.
Stdlib only; the server runs it with the system python3.
"""
import hashlib
import re
import sys
from pathlib import Path

# Scripts and styles, plus the onboarding film and its poster (assets/welcome/, item 179): nginx serves
# everything under /assets/ "immutable" for 30 days, so replacing the placeholder film at the same
# path would not reach anyone who had already seen it without a stamp that changes with the file.
ASSET = r"assets/(?:(?:js|css)/[A-Za-z0-9_.-]+\.(?:js|css)|welcome/[A-Za-z0-9_.-]+\.(?:mp4|jpe?g|png|webp))"
# A URL inside a js file that already carries a stamp: "assets/js/hv-drag.js?v=6a87b52e".
JS_REF = re.compile(r"((?:\.\./|/)*(" + ASSET + r"))\?v=([0-9A-Za-z]+)")
# A src/href attribute in a page, stamped or not.
HTML_REF = re.compile(r"""((?:src|href|poster|data-src)=["'])([^"'?#]*?(""" + ASSET + r"""))(?:\?v=([0-9A-Za-z]+))?(["'])""")
SW_VERSION = re.compile(r'const VERSION = "hca-[0-9A-Za-z-]*";')
# Whole tags, so a stylesheet pointing at a script (or the other way round) is caught even
# when the file it names exists and therefore hashes perfectly well.
LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
SCRIPT_TAG = re.compile(r"<script\b[^>]*>", re.I)
REL_STYLESHEET = re.compile(r"""\brel\s*=\s*["']?stylesheet\b""", re.I)
HREF_ATTR = re.compile(r"""\bhref\s*=\s*["']([^"']*)["']""", re.I)
SRC_ATTR = re.compile(r"""\bsrc\s*=\s*["']([^"']*)["']""", re.I)
# A URL with a scheme ("https:", "data:") or a protocol-relative "//cdn...": someone else's
# file, whose name we do not get to judge.
REMOTE = re.compile(r"(?:[A-Za-z][A-Za-z0-9+.-]*:|//)")


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()[:8]


def stamp_js(root, write, stale, broken):
    js_dir = root / "assets" / "js"
    if not js_dir.is_dir():
        return
    for _ in range(6):                      # nested references settle in a pass or two
        changed = False
        for f in sorted(js_dir.glob("*.js")):
            if f.name.startswith("."):          # macOS ._ copies are binary, not scripts
                continue
            text = f.read_text(encoding="utf-8")

            def sub(m):
                target = root / m.group(2)
                if not target.is_file():
                    broken.append("%s -> %s (no such file)" % (f.relative_to(root), m.group(2)))
                    return m.group(0)
                h = md5(target)
                if h != m.group(3):
                    stale.append("%s -> %s (%s, now %s)" % (f.relative_to(root), m.group(2), m.group(3), h))
                return m.group(1) + "?v=" + h

            new = JS_REF.sub(sub, text)
            if new != text:
                changed = True
                if write:
                    f.write_text(new, encoding="utf-8")
        if not (changed and write):
            return


def pages(root):
    for f in sorted(root.rglob("*.html")):
        rel = f.relative_to(root).parts
        # "site/" only exists in the source tree: it is the HelloVoice homepage fetched from
        # Influencer-Catalogue-2 so the build can scrape its logo carousel, and it is never
        # published here, so a link of theirs must not be able to stop a publish of ours.
        if rel and rel[0] in ("assets", "admin", "node_modules", "site", ".git"):
            continue
        if f.name.startswith("."):
            continue
        if any(p.startswith(".") for p in rel):     # ._index.html (macOS copy junk) and dotfiles
            continue
        yield f


def stamp_html(root, write, stale, broken):
    for f in pages(root):
        text = f.read_text(encoding="utf-8")

        def sub(m):
            target = root / m.group(3)
            if not target.is_file():
                broken.append("%s -> %s (no such file)" % (f.relative_to(root), m.group(3)))
                return m.group(0)
            h = md5(target)
            if h != m.group(4):
                stale.append("%s -> %s (%s, now %s)" % (f.relative_to(root), m.group(3), m.group(4) or "unstamped", h))
            return m.group(1) + m.group(2) + "?v=" + h + m.group(5)

        new = HTML_REF.sub(sub, text)
        if new != text and write:
            f.write_text(new, encoding="utf-8")


def _local(url):
    """A reference this repository controls, rather than a CDN, a data: URI or //cdn..."""
    return bool(url) and not REMOTE.match(url)


def _bare(url):
    """The path, without the ?v= stamp or a #fragment."""
    return url.split("?")[0].split("#")[0]


def check_links(root, broken):
    """A stylesheet must name a style and a script must name a script. The file it points at
    may well exist and hash cleanly, so only the tag it sits in can tell these apart."""
    for f in pages(root):
        text = f.read_text(encoding="utf-8", errors="replace")
        page = f.relative_to(root)
        for tag in (m.group(0) for m in LINK_TAG.finditer(text)):
            if not REL_STYLESHEET.search(tag):
                continue                       # preload, icon, manifest: not a stylesheet
            href = HREF_ATTR.search(tag)
            if href is None or not _local(href.group(1)):
                continue
            if not _bare(href.group(1)).lower().endswith(".css"):
                broken.append("%s: stylesheet link points at %s" % (page, href.group(1)))
        for tag in (m.group(0) for m in SCRIPT_TAG.finditer(text)):
            src = SRC_ATTR.search(tag)
            if src is None or not _local(src.group(1)):
                continue                       # inline <script> has no src
            if not _bare(src.group(1)).lower().endswith((".js", ".mjs")):
                broken.append("%s: script src points at %s" % (page, src.group(1)))


def shell_hash(root):
    """One hash over everything the installed app keeps or runs: scripts, styles, the
    offline page, the manifest, the app icons and sw.js itself (minus its VERSION line)."""
    h = hashlib.md5()
    files = []
    for d in ("assets/js", "assets/css"):
        p = root / d
        if p.is_dir():
            files += [f for f in p.iterdir() if f.suffix in (".js", ".css") and not f.name.startswith(".")]
    app = root / "assets" / "app"
    if app.is_dir():
        files += [f for f in app.iterdir() if f.is_file() and not f.name.startswith(".")]
    files += [root / n for n in ("offline.html", "manifest.webmanifest")]
    for f in sorted(x for x in files if x.is_file()):
        h.update(str(f.relative_to(root)).encode())
        h.update(f.read_bytes())
    sw = root / "sw.js"
    if sw.is_file():
        h.update(SW_VERSION.sub("", sw.read_text(encoding="utf-8")).encode())
    return h.hexdigest()[:10]


def stamp_sw(root, write, stale):
    sw = root / "sw.js"
    if not sw.is_file():
        return None
    text = sw.read_text(encoding="utf-8")
    want = 'const VERSION = "hca-%s";' % shell_hash(root)
    m = SW_VERSION.search(text)
    if not m:
        stale.append("sw.js has no VERSION line to stamp")
        return None
    if m.group(0) != want:
        stale.append("sw.js VERSION (%s, now %s)" % (m.group(0), want))
        if write:
            sw.write_text(text.replace(m.group(0), want, 1), encoding="utf-8")
    return want


def _report(broken):
    """Broken links go to stderr: they stop a publish, and update.sh is read in a terminal."""
    for b in broken:
        print("BROKEN LINK: " + b, file=sys.stderr)
    print("%d broken link(s)" % len(broken), file=sys.stderr)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    check = "--check" in argv
    links_only = "--links-only" in argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 64
    root = Path(args[0]).resolve()
    broken = []
    if links_only:                                 # run against the source, before a publish copies it
        check_links(root, broken)
        if broken:
            _report(broken)
            return 2
        print("every stylesheet and script link is the right kind")
        return 0
    stale = []
    stamp_js(root, not check, stale, broken)
    stamp_html(root, not check, stale, broken)
    check_links(root, broken)
    sw = stamp_sw(root, not check, stale)          # last: the shell hash reads the stamped js
    if broken:                                     # an error either way: never stamp around one
        _report(broken)
        return 2
    if check:
        for s in stale:
            print("stale: " + s)
        print("%d stale stamp(s)" % len(stale) if stale else "all stamps current")
        return 1 if stale else 0
    print("stamped %d reference(s); %s" % (len(stale), sw or "no sw.js"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
