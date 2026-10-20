#!/usr/bin/env python3
"""Cache-busting stamps for the published catalogue site (item 175).

    python3 stamp_assets.py <site-root>            # rewrite the stamps in place (update.sh runs this)
    python3 stamp_assets.py <site-root> --check    # report stale stamps, change nothing, exit 1 if any

Why it matters: a js/css URL that carries ?v= is served "immutable" for a year (nginx
$hv_asset_cache) and the HELVi Connect service worker answers it from its own cache first.
So a stamp that is not bumped when the file changes pins every browser and every installed
app to the old file. The stamp must be the file's content hash, on every page, every time.

What it stamps:
  1. Inside the js files, only the URLs that already carry a ?v= (a script that loads another
     script or style this way). Repeated until nothing changes, so a file's own hash includes its children's.
  2. Every src= / href= in every .html page under the root (assets/ is skipped) that points
     at an existing assets/js/*.js or assets/css/*.css: any page, any file, no list to keep.
  3. sw.js: VERSION becomes "hca-<hash of the app shell>", so any release that changes a
     script, a style, the offline page, the manifest or an app icon installs a new worker,
     which drops the old caches and takes over the open app at once.

The stamp is md5[:8] of the file, the same scheme update.sh has used since 2026-09-08.
Stdlib only; the server runs it with the system python3.
"""
import hashlib
import re
import sys
from pathlib import Path

ASSET = r"assets/(?:js|css)/[A-Za-z0-9_.-]+\.(?:js|css)"
# A URL inside a js file that already carries a stamp: "assets/js/hv-drag.js?v=6a87b52e".
JS_REF = re.compile(r"((?:\.\./|/)*(" + ASSET + r"))\?v=([0-9A-Za-z]+)")
# A src/href attribute in a page, stamped or not.
HTML_REF = re.compile(r"""((?:src|href)=["'])([^"'?#]*?(""" + ASSET + r"""))(?:\?v=([0-9A-Za-z]+))?(["'])""")
SW_VERSION = re.compile(r'const VERSION = "hca-[0-9A-Za-z-]*";')


def md5(p):
    return hashlib.md5(p.read_bytes()).hexdigest()[:8]


def stamp_js(root, write, stale):
    js_dir = root / "assets" / "js"
    if not js_dir.is_dir():
        return
    for _ in range(6):                      # nested references settle in a pass or two
        changed = False
        for f in sorted(js_dir.glob("*.js")):
            text = f.read_text(encoding="utf-8")

            def sub(m):
                target = root / m.group(2)
                if not target.is_file():
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
        if rel and rel[0] in ("assets", "admin", "node_modules", ".git"):
            continue
        if any(p.startswith(".") for p in rel):     # ._index.html (macOS copy junk) and dotfiles
            continue
        yield f


def stamp_html(root, write, stale):
    for f in pages(root):
        text = f.read_text(encoding="utf-8")

        def sub(m):
            target = root / m.group(3)
            if not target.is_file():
                return m.group(0)
            h = md5(target)
            if h != m.group(4):
                stale.append("%s -> %s (%s, now %s)" % (f.relative_to(root), m.group(3), m.group(4) or "unstamped", h))
            return m.group(1) + m.group(2) + "?v=" + h + m.group(5)

        new = HTML_REF.sub(sub, text)
        if new != text and write:
            f.write_text(new, encoding="utf-8")


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


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    check = "--check" in argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    root = Path(args[0]).resolve()
    stale = []
    stamp_js(root, not check, stale)
    stamp_html(root, not check, stale)
    sw = stamp_sw(root, not check, stale)          # last: the shell hash reads the stamped js
    if check:
        for s in stale:
            print("stale: " + s)
        print("%d stale stamp(s)" % len(stale) if stale else "all stamps current")
        return 1 if stale else 0
    print("stamped %d reference(s); %s" % (len(stale), sw or "no sw.js"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
