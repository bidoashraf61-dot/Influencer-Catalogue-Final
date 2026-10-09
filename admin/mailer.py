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
    user, host = (user or "").strip(), (host or "smtp.office365.com").strip()
    user = user.lower() if "@" in user else user          # SES / SendGrid log in with a key, not an address
    send_as = (send_as or "").strip().lower()
    if send_as and "@" not in send_as:
        raise ValueError("'Send as' must be an email address.")
    if not user or not password or len(password) < 6:
        raise ValueError("Enter the SMTP username and password.")
    if "@" not in user and not send_as:
        raise ValueError("This username is not an email address, so fill 'Send as' with the address to send from.")
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
    msg["Message-ID"] = make_msgid(domain=(c.get("send_as") or c["user"]).rsplit("@", 1)[-1])
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


# Client emails are drawn from images on the catalogue host: absolute https URLs
# (mail clients cannot reach relative paths) and PNG, because Outlook shows no WebP.
SITE = "https://influencer-catalogue.hellovoice.co.uk"
EMAIL_LOGO = SITE + "/assets/brand/helvy-connect/helvy-connect-email-480.png"        # on white
EMAIL_LOGO_INK = SITE + "/assets/brand/email/helvy-connect-on-ink-480.png"            # on the ink header
EMAIL_HELVY = SITE + "/assets/brand/email/helvy-still-192.png"                        # smile, transparent cut-out (no disc)
EMAIL_HV = SITE + "/assets/brand/email/hellovoice-white-240.png"                      # Powered by

# The sign-in code email (HELVY Connect, phase C, v2). Built for the inbox, not the
# browser: one 600px table, inline styles, system fonts, every image with width,
# height and alt, a VML button for Outlook, and dark-mode rules that only recolour
# (the code panel is ink with lime digits in both modes). The code is real text,
# six digits with no spaces between them, so a long-press copies "482913" whole.
OTP_HTML = """<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>Your HELVY Connect sign-in code</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
  body { margin: 0 !important; padding: 0 !important; width: 100% !important; -webkit-text-size-adjust: 100%; }
  img { border: 0; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }
  a { color: #121212; }
  .code { -webkit-user-select: all; user-select: all; }
  @media (max-width: 620px) {
    .wrap { width: 100% !important; }
    .px { padding-left: 22px !important; padding-right: 22px !important; }
    .code { font-size: 40px !important; letter-spacing: 8px !important; }
    .hi { font-size: 22px !important; line-height: 28px !important; }
    .tag { display: none !important; }
    .btn a { display: block !important; }
  }
  @media (prefers-color-scheme: dark) {
    .bg { background-color: #0b0b0b !important; }
    .card { background-color: #1b1b1b !important; }
    .tx { color: #f2f2f2 !important; }
    .mu { color: #b9b9b9 !important; }
    .rule { border-color: #333333 !important; }
    .trust { background-color: #242424 !important; }
  }
  [data-ogsc] .bg { background-color: #0b0b0b !important; }
  [data-ogsc] .card { background-color: #1b1b1b !important; }
  [data-ogsc] .tx { color: #f2f2f2 !important; }
  [data-ogsc] .mu { color: #b9b9b9 !important; }
  [data-ogsc] .trust { background-color: #242424 !important; }
</style>
</head>
<body class="bg" style="margin:0;padding:0;background-color:#efede8;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;color:#efede8;opacity:0;">Your HELVY Connect code is {CODE}. It expires in {MIN} minutes.&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;&#847;&zwnj;&nbsp;</div>
<table role="presentation" class="bg" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#efede8;">
<tr><td align="center" style="padding:32px 12px 40px;">
<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table role="presentation" class="wrap" width="600" cellpadding="0" cellspacing="0" border="0" style="width:600px;max-width:600px;">

  <tr><td style="background-color:#121212;border-radius:24px 24px 0 0;padding:22px 32px 20px;" class="px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td valign="middle"><img src="{LOGO}" width="168" height="84" alt="HELVY Connect" style="display:block;width:168px;height:84px;border:0;"></td>
      <td class="tag" align="right" valign="middle" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:17px;color:#a9a9a9;letter-spacing:.02em;">Connecting Brands<br>with the Right Voices</td>
    </tr></table>
  </td></tr>
  <tr><td style="background-color:#e8ff76;height:5px;line-height:5px;font-size:5px;">&nbsp;</td></tr>

  <tr><td class="card px" style="background-color:#ffffff;padding:34px 40px 6px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td width="92" valign="middle" style="width:92px;padding-right:18px;">
        <img src="{HELVY}" width="92" height="92" alt="Helvy, smiling" style="display:block;width:92px;height:92px;border:0;outline:none;text-decoration:none;">
      </td>
      <td valign="middle">
        <p class="tx hi" style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:26px;line-height:32px;font-weight:700;color:#121212;">Hi, it&rsquo;s Helvy &#128075;</p>
        <p class="mu" style="margin:6px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:22px;color:#383838;">Here&rsquo;s your code to sign in to HELVY Connect.</p>
      </td>
    </tr></table>
  </td></tr>

  <tr><td class="card px" style="background-color:#ffffff;padding:24px 40px 4px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td align="center" style="background-color:#121212;border-radius:18px;padding:26px 12px 22px;border-bottom:4px solid #e8ff76;">
        <p class="code" style="margin:0;font-family:'SF Mono',Menlo,Consolas,'Courier New',monospace;font-size:50px;line-height:56px;font-weight:700;letter-spacing:14px;color:#e8ff76;mso-line-height-rule:exactly;">{CODE}</p>
        <p style="margin:12px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;color:#cfcfcf;"><span style="color:#e8ff76;">&#9679;</span>&nbsp; Expires in {MIN} minutes &middot; works once</p>
      </td>
    </tr></table>
    <p class="mu" style="margin:12px 0 0;text-align:center;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:19px;color:#5a5a5a;">Type it on the sign-in page, or press and hold to copy it.</p>
  </td></tr>

  <tr><td class="card px btn" align="center" style="background-color:#ffffff;padding:22px 40px 8px;">
    <!--[if mso]><v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" href="{SITE}/" style="height:52px;v-text-anchor:middle;width:300px;" arcsize="50%" stroke="f" fillcolor="#e8ff76"><w:anchorlock/><center style="color:#121212;font-family:Arial,sans-serif;font-size:16px;font-weight:bold;">Open HELVY Connect &rarr;</center></v:roundrect><![endif]-->
    <!--[if !mso]><!--><a href="{SITE}/" style="display:inline-block;background-color:#e8ff76;color:#121212;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:52px;font-weight:700;text-decoration:none;border-radius:26px;padding:0 34px;mso-hide:all;">Open HELVY Connect &rarr;</a><!--<![endif]-->
  </td></tr>

  <tr><td class="card px" style="background-color:#ffffff;padding:22px 40px 34px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td class="trust" style="background-color:#f6f3ee;border-radius:14px;padding:16px 18px;">
        <p class="tx" style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:21px;color:#121212;"><strong>Not you?</strong> Ignore this email. Nobody can sign in without this code, and it stops working on its own.</p>
        <p class="mu" style="margin:8px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:19px;color:#5a5a5a;">HelloVoice never asks for this code by phone or chat.{SENT}</p>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="background-color:#121212;border-radius:0 0 24px 24px;padding:22px 32px 24px;" class="px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td valign="middle" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#a9a9a9;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td valign="middle" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#a9a9a9;padding-right:8px;">Powered by</td>
          <td valign="middle"><img src="{HV}" width="104" height="23" alt="HelloVoice" style="display:block;width:104px;height:23px;border:0;"></td>
          <td valign="middle" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#a9a9a9;padding-left:8px;">&middot; A BlueHolding Company</td>
        </tr></table>
        <p style="margin:10px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#8a8a8a;">Al-Olaya, Riyadh &middot; <a href="{SITE}/" style="color:#e8ff76;text-decoration:underline;">influencer-catalogue.hellovoice.co.uk</a></p>
      </td>
    </tr></table>
  </td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr>
</table>
</body>
</html>"""


def otp_message(code, minutes=10, to=None):
    """(subject, text, html) for a sign-in code."""
    subject = "Your HELVY Connect sign-in code: %s" % code
    text = ("Your HELVY Connect sign-in code is %s.\n\n"
            "It works for %d minutes. If you did not ask for it, ignore this email.\n\n"
            "HELVY Connect · Powered by HelloVoice · A BlueHolding Company" % (code, minutes))
    sent = (" Sent to %s because someone asked to sign in to HELVY Connect." % _html.escape(to)) if to else ""
    page = OTP_HTML
    for k, v in (("{CODE}", _html.escape(str(code))), ("{MIN}", str(int(minutes))), ("{LOGO}", EMAIL_LOGO_INK),
                 ("{HELVY}", EMAIL_HELVY), ("{HV}", EMAIL_HV), ("{SITE}", SITE), ("{SENT}", sent)):
        page = page.replace(k, v)
    return subject, text, page
