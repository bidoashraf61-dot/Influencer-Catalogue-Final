"""Signed photo links, checked by nginx instead of by this service.

The dashboard shows a thumbnail against every creator, and it served all 757 of
them from here. Python answers one request at a time, so a save that took 17ms
on a quiet server took three seconds behind a roster that was still loading its
pictures — the lag that was reported, measured, and traced to exactly this.

nginx serves them now. It also checks the link itself, with secure_link, so a
request for a photo never reaches this process at all. The signature below is
the one nginx computes for

    secure_link_md5 "$secure_link_expires$uri$photo_secret"

which means both sides have to agree on the secret and, to the second, on the
expiry. The secret lives in .photo-secret beside this file; update.sh copies it
into the nginx map. It is deliberately not the session secret: a signed photo
link travels in an <img> tag, through referrers and proxy logs, and must not be
able to say anything about a signed-in admin.
"""

import base64
import hashlib
import os
import time
from pathlib import Path

SECRET_FILE = Path(__file__).with_name(".photo-secret")

# A link is good until the end of the day after tomorrow.
WINDOW = 86400

_secret = None


def secret():
    """The shared signing key, made once and then only read.

    Generating it here rather than failing keeps a fresh install working, but
    on a running system this file is provisioned by the deploy: if this process
    invented a new key, nginx would still hold the old one and every photo on
    the site would turn into a 403.
    """
    global _secret
    if _secret is None:
        if not SECRET_FILE.exists():
            SECRET_FILE.write_text(os.urandom(24).hex())
            SECRET_FILE.chmod(0o600)
        _secret = SECRET_FILE.read_text().strip()
    return _secret


def forget_secret():
    """Drop the cached key, so a rotated .photo-secret is picked up."""
    global _secret
    _secret = None


def expires_at(now=None):
    """The same expiry for every link issued on the same day.

    Signing against the current second would put a different query string on
    every thumbnail on every page load, and a changed URL is a cache miss —
    the browser would re-fetch all 757 pictures each visit, which is the cost
    this whole change exists to remove. Rounding up to a day boundary keeps the
    URL stable while the link still stops working inside two days.
    """
    now = int(time.time() if now is None else now)
    return (now // WINDOW + 2) * WINDOW


def sign(uri, expires=None):
    exp = expires_at() if expires is None else expires
    raw = hashlib.md5(("%d%s%s" % (exp, uri, secret())).encode()).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def signed(uri, expires=None):
    exp = expires_at() if expires is None else expires
    return "%s?s=%s&e=%d" % (uri, sign(uri, exp), exp)


def thumb(photo, base=""):
    """A small copy for a list. nginx resizes it and caches the result."""
    if not photo:
        return None
    return base + signed("/thumb/" + str(photo).split("?")[0])


def photo(photo_name, base=""):
    """The picture at full size, for a card on the catalogue itself."""
    if not photo_name:
        return None
    return base + signed("/assets/catalogue/" + str(photo_name).split("?")[0])
