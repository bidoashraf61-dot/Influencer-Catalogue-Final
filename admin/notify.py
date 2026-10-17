"""Emails to the HelloVoice team when something needs a person: a new client, a brief, a quote
request, a request for credits. Sent through the same mailer as the sign-in codes, to the
account's KAM when one is assigned and to the addresses in the ``notify_emails`` setting.

Never raises: a notification that cannot be sent must not break the client's action. Runs in a
background thread so the client's request does not wait on the mail provider.
"""
import threading

import db
import mailer

EVENTS = {"signup": "New client", "brief": "New brief", "quote": "Quote request", "credits": "Credits requested",
          "status": "Selection feedback", "analysis": "Analysis requested", "handoff": "Account manager request",
          "quote_changed": "Quote request changed", "quote_approved": "Quote approved",
          "creator_request": "Creator requested", "access_request": "Access requested",
          "kam_assign": "Handed to you", "campaign_started": "Campaign started by a client"}


def recipients(kam=None):
    raw = db.setting("notify_emails", []) or []
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    out = [str(x).strip().lower() for x in raw if "@" in str(x)]
    kam_email = kam_address(kam)
    if kam_email:
        out.insert(0, kam_email)
    return list(dict.fromkeys(out))


def kams():
    """[(name, email)] from the ``kams`` setting: one "Name <email>" per entry."""
    out = []
    for line in db.setting("kams", []) or []:
        line = str(line).strip()
        if "<" in line and line.endswith(">"):
            name, _, email = line[:-1].partition("<")
            out.append((name.strip(), email.strip().lower()))
        elif "@" in line:
            out.append((line, line.lower()))
    return out


def kam_address(kam):
    if not kam:
        return None
    for name, email in kams():
        if kam in (name, email):
            return email
    return kam if "@" in str(kam) else None


def send(event, lines, kam=None, link=None, also=None):
    """Fire and forget. ``also``: extra addresses for this one message (e.g. the owner)."""
    on = db.setting("notify_events", list(EVENTS)) or []
    # A hand-off from Helvy follows "quote" for teams that saved an event list before it existed.
    if event not in on and event not in ("kam_assign", "campaign_started") and not (event == "handoff" and "quote" in on):
        return
    to = list(dict.fromkeys(recipients(kam) + [str(a).strip().lower() for a in (also or []) if "@" in str(a)]))
    if not to or not mailer.configured():
        return
    subject = "HelloVoice catalogue · %s" % EVENTS.get(event, event)
    text = "\n".join(str(x) for x in lines if x) + (("\n\nOpen: " + link) if link else "")

    def run():
        for addr in to[:10]:
            try:
                mailer.send(addr, subject, text)
            except Exception:
                pass
    threading.Thread(target=run, daemon=True).start()
