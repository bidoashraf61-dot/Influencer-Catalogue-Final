#!/usr/bin/env python3
"""The review server.

`python3 -m http.server` sends no cache headers at all, so a browser is free to
hold a page for as long as it likes — and does. The stylesheet and the scripts
are versioned by content hash so they always come back fresh, but nothing can
version a page's own URL, so /service/technology-activations/ kept being served
from the browser's copy while the build on disk had moved on. That has now cost
two round trips: once over card aspect ratios that were already right, and once
over a showreel that was already installed.

The documents are sent no-store. The hashed assets keep a long cache, because
their URL changes whenever their bytes do.
"""
import functools
import http.server
import os
import re
import pathlib
import socketserver
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "site"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8811


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves byte ranges, which this server did not.

    SimpleHTTPRequestHandler answers a Range request with the whole file and a
    200, and never advertises Accept-Ranges. A browser will still play a video
    served that way, but it cannot reliably seek one — and the hero character is
    driven entirely by seeking. Setting currentTime did nothing: the value read
    back as 0 every time, so he stood still while the cursor moved, and the fault
    looked like the cursor code rather than the transport under it.

    Real hosting handles this already; this only matters for local review.
    """

    def do_GET(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().do_GET()

        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()

        m = re.match(r"bytes=(\d*)-(\d*)\s*$", rng.strip())
        if not m:
            return super().do_GET()

        size = os.path.getsize(path)
        first, last = m.group(1), m.group(2)
        if first == "":
            # a suffix range: the final N bytes, which is how players read the
            # moov atom when it sits at the end of a file
            if last == "":
                return super().do_GET()
            length = int(last)
            start, end = max(0, size - length), size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1

        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        end = min(end, size - 1)
        length = end - start + 1

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(length))
        self.end_headers()

        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return          # the player moved on; not an error
                remaining -= len(chunk)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        path = self.path.split("?", 1)[0]
        hashed = "v=" in self.path and path.endswith((".css", ".js"))
        if hashed:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        elif path.endswith((".mp4", ".webm", ".webp", ".jpg", ".png", ".glb", ".woff2")):
            # media is large and changes rarely; revalidate rather than refetch
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):        # one line per request is enough
        if "404" in (fmt % args):
            sys.stderr.write("  404  %s\n" % self.path)


if __name__ == "__main__":
    os.chdir(ROOT)
    # Threading, not the plain TCPServer.
    #
    # The plain server handles one request at a time, which a browser opening
    # six parallel connections will sit and wait on. It was survivable while
    # every asset was small; the hero film holds its connection open while it
    # streams, and behind it the rest of the page simply stopped arriving —
    # readyState stuck on "loading" with one script of many fetched.
    class Threaded(socketserver.ThreadingTCPServer):
        daemon_threads = True

    Threaded.allow_reuse_address = True
    with Threaded(("", PORT), Handler) as httpd:
        print(f"review server on http://localhost:{PORT}/  (documents are no-store)")
        httpd.serve_forever()
