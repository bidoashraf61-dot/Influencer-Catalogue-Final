#!/usr/bin/env python3
"""What a tracking-link click can tell us: which app it came from, what
device, which country, whether it was a person at all — and where to send it.

Stdlib only, like the rest of the service. Nothing here touches the database;
server.py records what these functions return.

Country lookup reads an optional `geo.db` beside this file, built once from the
free DB-IP "IP to Country Lite" CSV (CC BY 4.0 — the report credits DB-IP):

    python3 admin/track.py --geo-build dbip-country-lite-2026-10.csv.gz

Without it every click is simply country "unknown"; nothing else changes. A
proxy that already knows the country (Cloudflare's CF-IPCountry) is preferred
over the file.
"""

import gzip
import hashlib
import ipaddress
import re
import sqlite3
import sys
import urllib.parse
from pathlib import Path

GEO_DB = Path(__file__).resolve().parent / "geo.db"

# ------------------------------------------------------------------- apps --

# The in-app browsers mark themselves in the user-agent. Order matters: the
# Instagram and Facebook browsers both carry "FBAN"/"FBAV"-style markers, and
# TikTok's carries several names over its versions.
APP_MARKERS = [
    ("Instagram", re.compile(r"Instagram", re.I)),
    ("TikTok", re.compile(r"musical_ly|BytedanceWebview|TikTok|trill_|ByteLocale", re.I)),
    ("Snapchat", re.compile(r"Snapchat", re.I)),
    ("Facebook", re.compile(r"FBAN|FBAV|FB_IAB|FBIOS", re.I)),
    ("X", re.compile(r"Twitter(?!bot)", re.I)),
    ("LinkedIn", re.compile(r"LinkedInApp", re.I)),
    ("Telegram", re.compile(r"Telegram(?!Bot)", re.I)),
]

# When the user-agent says nothing (WhatsApp and YouTube open links in the
# phone's own browser), the referrer sometimes does.
REFERRER_APPS = [
    ("YouTube", ("youtube.com", "youtu.be")),
    ("Instagram", ("instagram.com",)),
    ("TikTok", ("tiktok.com",)),
    ("Snapchat", ("snapchat.com",)),
    ("Facebook", ("facebook.com", "fb.com", "fb.me")),
    ("X", ("t.co", "twitter.com", "x.com")),
    ("WhatsApp", ("whatsapp.com", "wa.me")),
    ("Google", ("google.",)),
]

# Link-preview fetchers and crawlers: they fetch the link to draw a card, not
# because anybody tapped it. Logged, never counted. WhatsApp's own fetcher
# announces itself as "WhatsApp/2.x" — a person tapping a link in WhatsApp
# arrives in their phone browser with an ordinary user-agent instead.
BOTS = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|facebookexternalhit|facebookcatalog|WhatsApp/|"
    r"Snap URL Preview|SkypeUriPreview|Embedly|preview|curl/|wget/|python-|"
    r"httpclient|okhttp|Go-http-client|axios|node-fetch|HeadlessChrome|Lighthouse",
    re.I)


def app_of(ua, referrer=""):
    for name, pattern in APP_MARKERS:
        if pattern.search(ua or ""):
            return name
    host = urllib.parse.urlparse(referrer or "").netloc.lower()
    if host:
        for name, hosts in REFERRER_APPS:
            if any(h in host for h in hosts):
                return name
        return "Other website"
    return "Browser / direct"


def is_bot(ua, method="GET"):
    return method != "GET" or not ua or bool(BOTS.search(ua))


def device_of(ua):
    """(device, os). Tablet before mobile: an iPad says "Mobile" too."""
    ua = ua or ""
    if re.search(r"iPad|Tablet|SM-T\d|Nexus (7|9|10)", ua) or (
            "Android" in ua and "Mobile" not in ua):
        device = "Tablet"
    elif re.search(r"Mobile|iPhone|iPod|Android|Windows Phone", ua):
        device = "Mobile"
    else:
        device = "Desktop"
    if re.search(r"iPhone|iPad|iPod", ua):
        os_ = "iOS"
    elif "Android" in ua:
        os_ = "Android"
    elif "Windows" in ua:
        os_ = "Windows"
    elif re.search(r"Mac OS X|Macintosh", ua):
        os_ = "macOS"
    elif "Linux" in ua:
        os_ = "Linux"
    else:
        os_ = "Other"
    return device, os_


def visitor(ip, ua, salt):
    """A device fingerprint that cannot be turned back into an IP address:
    the IP is only ever stored hashed, with a salt kept on the server."""
    return hashlib.sha256((salt + "|" + (ip or "") + "|" + (ua or "")).encode()).hexdigest()[:24]


# ------------------------------------------------------------ destination --

def with_utm(destination, campaign_slug, creator_code, app):
    """The destination with UTM tags added, so the client's own analytics can
    tell this creator's visitors apart. Tags the client already put on the URL
    win: we never overwrite theirs."""
    parts = urllib.parse.urlsplit(destination)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    have = {k for k, _ in query}
    ours = [("utm_source", re.sub(r"[^a-z0-9]+", "_", (app or "link").lower()).strip("_")),
            ("utm_medium", "influencer"),
            ("utm_campaign", campaign_slug),
            ("utm_content", creator_code.lower())]
    query += [(k, v) for k, v in ours if k not in have]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


# ---------------------------------------------------------------- country --

def _key(ip):
    """An address as 16 big-endian bytes, IPv4 mapped into IPv6, so one
    byte-wise ordered table holds both."""
    a = ipaddress.ip_address(ip.strip())
    if a.version == 4:
        a = ipaddress.IPv6Address("::ffff:" + str(a))
    return a.packed


def country_of(ip, header_country=None):
    """Two-letter country code, or None when it cannot be known."""
    cc = (header_country or "").strip().upper()
    if re.fullmatch(r"[A-Z]{2}", cc) and cc not in ("XX", "T1"):
        return cc
    if not GEO_DB.exists() or not ip:
        return None
    try:
        key = _key(ip)
    except ValueError:
        return None
    conn = sqlite3.connect("file:%s?mode=ro" % GEO_DB, uri=True)
    try:
        row = conn.execute("SELECT stop, cc FROM ranges WHERE start <= ? "
                           "ORDER BY start DESC LIMIT 1", (key,)).fetchone()
    finally:
        conn.close()
    if row and key <= row[0] and row[1] not in ("ZZ", ""):
        return row[1]
    return None


def geo_build(csv_path, out=GEO_DB):
    """Turn the DB-IP Lite CSV (start,end,country) into the lookup table."""
    opener = gzip.open if str(csv_path).endswith(".gz") else open
    tmp = Path(str(out) + ".tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    conn.execute("CREATE TABLE ranges (start BLOB PRIMARY KEY, stop BLOB NOT NULL, cc TEXT) "
                 "WITHOUT ROWID")
    n = 0
    with opener(csv_path, "rt", encoding="utf-8") as fh:
        rows = []
        for line in fh:
            parts = line.strip().strip('"').replace('"', "").split(",")
            if len(parts) < 3:
                continue
            try:
                rows.append((_key(parts[0]), _key(parts[1]), parts[2][:2].upper()))
            except ValueError:
                continue
            if len(rows) >= 50000:
                conn.executemany("INSERT OR REPLACE INTO ranges VALUES (?,?,?)", rows)
                n += len(rows); rows = []
        conn.executemany("INSERT OR REPLACE INTO ranges VALUES (?,?,?)", rows)
        n += len(rows)
    conn.commit()
    conn.close()
    tmp.replace(out)
    return n


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--geo-build":
        print("ranges:", geo_build(sys.argv[2]))
    else:
        print(__doc__)
