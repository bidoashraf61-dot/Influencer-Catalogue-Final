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
import urllib.parse
import urllib.request
from pathlib import Path

import db

KEY_FILE = Path(__file__).resolve().parent / ".mail-key"
# A mailbox on the company's own email (Microsoft 365 by default): {"host", "port", "user", "password"}.
# Uses what hellovoice.co.uk already sends from, so no DNS change is needed. Takes priority over Resend.
SMTP_FILE = Path(__file__).resolve().parent / ".mail-smtp"
# Microsoft Graph with an app registration: {"tenant", "client_id", "secret", "sender"}. Sends as a
# shared mailbox with no password (OAuth client credentials). The preferred engine.
GRAPH_FILE = Path(__file__).resolve().parent / ".mail-graph"
_graph_token = {"value": None, "exp": 0}
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


def smtp_conf():
    try:
        c = json.loads(SMTP_FILE.read_text())
        return c if c.get("user") and c.get("password") else None
    except (OSError, ValueError):
        return None


def save_smtp(user, password, host="smtp.office365.com", port=587, send_as=""):
    user, host = (user or "").strip().lower(), (host or "smtp.office365.com").strip()
    send_as = (send_as or "").strip().lower()
    if send_as and "@" not in send_as:
        raise ValueError("'Send as' must be an email address (the shared mailbox).")
    if "@" not in user or not password or len(password) < 6:
        raise ValueError("Enter the mailbox address and its password (or app password).")
    if any(c.isspace() for c in host) or not host:
        raise ValueError("That is not a mail server name.")
    SMTP_FILE.write_text(json.dumps({"host": host, "port": int(port or 587), "user": user, "password": password,
                                     "send_as": send_as}))
    os.chmod(SMTP_FILE, 0o600)


def clear_smtp():
    try:
        SMTP_FILE.unlink()
    except OSError:
        pass


def graph_conf():
    try:
        c = json.loads(GRAPH_FILE.read_text())
        return c if all(c.get(k) for k in ("tenant", "client_id", "secret", "sender")) else None
    except (OSError, ValueError):
        return None


def save_graph(tenant, client_id, secret, sender_addr):
    import re
    tenant, client_id, sender_addr = (tenant or "").strip(), (client_id or "").strip(), (sender_addr or "").strip().lower()
    guid = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    if not (guid.match(tenant) or re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", tenant, re.I)):
        raise ValueError("Directory (tenant) ID should look like 1234abcd-…, or your domain.")
    if not guid.match(client_id):
        raise ValueError("Application (client) ID should look like 1234abcd-….")
    if not secret or len(secret.strip()) < 16:
        raise ValueError("Paste the client secret's Value (not its ID).")
    if "@" not in sender_addr:
        raise ValueError("Enter the shared mailbox address to send from.")
    GRAPH_FILE.write_text(json.dumps({"tenant": tenant, "client_id": client_id, "secret": secret.strip(), "sender": sender_addr}))
    os.chmod(GRAPH_FILE, 0o600)
    _graph_token.update(value=None, exp=0)


def clear_graph():
    try:
        GRAPH_FILE.unlink()
    except OSError:
        pass
    _graph_token.update(value=None, exp=0)


def graph_hint():
    c = graph_conf()
    return ("%s via Microsoft Graph" % c["sender"]) if c else ""


def engine():
    """'graph', 'smtp', 'resend' or '' — what send() will use."""
    if graph_conf():
        return "graph"
    if smtp_conf():
        return "smtp"
    return "resend" if key() else ""


def smtp_hint():
    c = smtp_conf()
    return ("%s%s via %s" % (c.get("send_as") + " as " if c.get("send_as") else "", c["user"], c["host"])) if c else ""


def configured():
    return CAPTURE or bool(engine())


def sender():
    g = graph_conf()
    if g:
        name = (db.setting("mail_from", DEFAULT_FROM) or DEFAULT_FROM).split("<")[0].strip() or "HelloVoice"
        return "%s <%s>" % (name, g["sender"])
    c = smtp_conf()
    if c:
        # Microsoft 365 only sends as the signed-in mailbox: keep the display name, force the address.
        name = (db.setting("mail_from", DEFAULT_FROM) or DEFAULT_FROM).split("<")[0].strip() or "HelloVoice"
        return "%s <%s>" % (name, c.get("send_as") or c["user"])
    return db.setting("mail_from", DEFAULT_FROM) or DEFAULT_FROM


DEFAULT_EMAIL_USD = 0.0004       # Resend Pro: $20 for 50,000 emails a month; the free plan is $0


def email_cost():
    try:
        return float(db.setting("email_cost_usd", DEFAULT_EMAIL_USD))
    except (TypeError, ValueError):
        return DEFAULT_EMAIL_USD


def _count(kind="email"):
    import gemini
    gemini.record(kind, None, "resend", 0, 0, 0, True, 0, "", email_cost())


def send(to, subject, text, html=None, reply_to=None):
    """Send one message. Raises MailError when it cannot be sent. Each sent email is
    counted, with its cost, in the platform's usage."""
    if CAPTURE:
        OUTBOX.append({"to": to, "subject": subject, "text": text, "html": html})
        _count()
        return True
    g = graph_conf()
    if g:
        _send_graph(g, to, subject, text, html, reply_to)
        _count()
        return True
    c = smtp_conf()
    if c:
        _send_smtp(c, to, subject, text, html, reply_to)
        _count()
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
        _count()
        return True
    except urllib.error.HTTPError as exc:
        raise MailError("Mail provider refused the message (%s)." % exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise MailError("Could not reach the mail provider.")


GRAPH_LOGIN = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_SEND = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"


def _graph_post(url, data, headers, timeout=15):
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return r.status, (json.loads(body) if body else {})


def _graph_access(c):
    import time
    if _graph_token["value"] and time.time() < _graph_token["exp"] - 120:
        return _graph_token["value"]
    form = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["secret"], "grant_type": "client_credentials",
                                   "scope": "https://graph.microsoft.com/.default"}).encode()
    try:
        _, tok = _graph_post(GRAPH_LOGIN.format(tenant=urllib.parse.quote(c["tenant"])), form,
                             {"Content-Type": "application/x-www-form-urlencoded"})
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode()).get("error", "")
        except Exception:
            pass
        raise MailError({"invalid_client": "Microsoft refused the app sign-in: check the client secret value and that it has not expired.",
                         "unauthorized_client": "Microsoft refused the app: check the application (client) ID.",
                         "invalid_request": "Microsoft refused the request: check the directory (tenant) ID."}.get(
                             detail, "Microsoft sign-in failed (%s %s)." % (exc.code, detail)))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise MailError("Could not reach Microsoft sign-in.")
    _graph_token.update(value=tok["access_token"], exp=time.time() + int(tok.get("expires_in", 3600)))
    return _graph_token["value"]


def _send_graph(c, to, subject, text, html=None, reply_to=None):
    message = {"subject": subject,
               "body": {"contentType": "HTML" if html else "Text", "content": html or text},
               "toRecipients": [{"emailAddress": {"address": to}}]}
    if reply_to:
        message["replyTo"] = [{"emailAddress": {"address": reply_to}}]
    payload = json.dumps({"message": message, "saveToSentItems": False}).encode()
    for attempt in (0, 1):
        tok = _graph_access(c)
        try:
            status, _ = _graph_post(GRAPH_SEND.format(sender=urllib.parse.quote(c["sender"])), payload,
                                    {"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
            if status in (200, 202):
                return
            raise MailError("Microsoft did not accept the message (%s)." % status)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and attempt == 0:
                _graph_token.update(value=None, exp=0)       # token expired early: get a new one once
                continue
            code = ""
            try:
                code = json.loads(exc.read().decode()).get("error", {}).get("code", "")
            except Exception:
                pass
            if exc.code == 403 or code in ("ErrorAccessDenied", "AccessDenied"):
                raise MailError("The app may not send as %s: grant it Mail.Send (application) with admin consent, "
                                "and include this mailbox in its access policy." % c["sender"])
            if exc.code == 404 or code in ("ErrorInvalidUser", "MailboxNotEnabledForRESTAPI", "ResourceNotFound"):
                raise MailError("Microsoft cannot find the mailbox %s." % c["sender"])
            raise MailError("Microsoft refused the message (%s %s)." % (exc.code, code))
        except (urllib.error.URLError, TimeoutError, OSError):
            raise MailError("Could not reach Microsoft Graph.")


def _send_smtp(c, to, subject, text, html=None, reply_to=None):
    import smtplib
    import ssl
    from email.message import EmailMessage
    from email.utils import make_msgid
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender(), to, subject
    msg["Message-ID"] = make_msgid(domain=c["user"].rsplit("@", 1)[1])
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    local = c["host"] in ("127.0.0.1", "localhost")
    try:
        with smtplib.SMTP(c["host"], int(c.get("port") or 587), timeout=20) as s:
            s.ehlo()
            if s.has_extn("starttls"):
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            elif not local:
                raise MailError("The mail server does not offer encryption; not sending the password in clear.")
            s.login(c["user"], c["password"])
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise MailError("The mailbox refused the sign-in. Check the password, and that SMTP sending is allowed for it.")
    except MailError:
        raise
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError("Could not send through the mailbox (%s)." % type(exc).__name__)


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
