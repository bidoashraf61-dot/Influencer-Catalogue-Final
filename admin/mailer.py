"""Outbound email through the Resend HTTP API (stdlib only).

The server could not mail before: the browser used to post quote requests to a
third-party form service because Cloudflare refuses that service from this
host. Resend is reached over plain HTTPS from the container.

The API key lives in ``.mail-key`` (mode 600, gitignored) or ``MAIL_API_KEY``;
the From address is the ``mail_from`` setting and its domain must be verified
in Resend. ``OUTBOX`` captures messages when ``CAPTURE`` is on (tests, demo).
"""
import html as _html
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import db

KEY_FILE = Path(__file__).resolve().parent / ".mail-key"
API = "https://api.resend.com/emails"
DEFAULT_FROM = "HelloVoice <portal@hellovoice.co.uk>"

CAPTURE = False
OUTBOX = []


class MailError(Exception):
    pass


def key():
    k = os.environ.get("MAIL_API_KEY", "").strip()
    if k:
        return k
    try:
        return KEY_FILE.read_text().strip()
    except OSError:
        return ""


def key_hint():
    k = key()
    return ("…" + k[-4:]) if k else ""


def save_key(value):
    value = (value or "").strip()
    if not value or any(c.isspace() for c in value) or len(value) < 16:
        raise ValueError("That does not look like an API key.")
    KEY_FILE.write_text(value)
    os.chmod(KEY_FILE, 0o600)


def clear_key():
    try:
        KEY_FILE.unlink()
    except OSError:
        pass


def configured():
    return CAPTURE or bool(key())


def sender():
    return db.setting("mail_from", DEFAULT_FROM) or DEFAULT_FROM


def send(to, subject, text, html=None, reply_to=None):
    """Send one message. Raises MailError when it cannot be sent."""
    if CAPTURE:
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html})
        return True
    k = key()
    if not k:
        raise MailError("Email is not set up yet.")
    body = {"from": sender(), "to": [to], "subject": subject, "text": text}
    if html:
        body["html"] = html
    if reply_to:
        body["reply_to"] = reply_to
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": "Bearer " + k, "Content-Type": "application/json",
        "User-Agent": "hellovoice-catalogue/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        return True
    except urllib.error.HTTPError as exc:
        raise MailError("Mail provider refused the message (%s)." % exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise MailError("Could not reach the mail provider.")


def otp_message(code, minutes=10):
    """(subject, text, html) for a sign-in code."""
    subject = "Your HelloVoice sign-in code: %s" % code
    text = ("Your HelloVoice Influencer Catalogue sign-in code is %s.\n\n"
            "It works for %d minutes. If you did not ask for it, ignore this email.\n\n"
            "HelloVoice · Riyadh" % (code, minutes))
    page = (
        "<div style='font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px;color:#111'>"
        "<p style='font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#666;margin:0 0 8px'>HelloVoice</p>"
        "<h1 style='font-size:22px;margin:0 0 16px'>Your sign-in code</h1>"
        "<p style='font-size:34px;letter-spacing:.3em;font-weight:700;background:#f4f4ee;padding:16px;"
        "text-align:center;border-radius:8px;margin:0 0 16px'>%s</p>"
        "<p style='font-size:14px;color:#444;margin:0 0 8px'>It works for %d minutes. "
        "If you did not ask for it, you can ignore this email.</p></div>" % (_html.escape(code), minutes))
    return subject, text, page
