"""Abuse controls shared by the public and admin routes.

Three small things, all stdlib:

* ``limiter`` — a sliding-window rate limiter held in memory. One process serves
  the whole admin (ThreadingHTTPServer), so a lock is enough. A restart clears
  it, which is acceptable for throttling (it is not an audit trail; the
  ``events`` table is).
* ``origin_ok`` — a CSRF check for state-changing requests.
* ``company_email`` — email normalisation and the company-domain rule used by
  client sign-up.
"""
import re
import threading
import time
from urllib.parse import urlparse


# --------------------------------------------------------------- throttling --

class Limiter:
    """``allow(key, limit, window)`` is True while fewer than ``limit`` hits were
    recorded for ``key`` in the last ``window`` seconds. Call ``hit`` to record."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()
        self._last_sweep = time.time()

    def _prune(self, now):
        # Bounded memory: drop idle keys now and then.
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600]:
            del self._hits[k]

    def count(self, key, window, now=None):
        now = now or time.time()
        with self._lock:
            q = [t for t in self._hits.get(key, ()) if now - t < window]
            self._hits[key] = q
            return len(q)

    def hit(self, key, now=None):
        now = now or time.time()
        with self._lock:
            self._hits.setdefault(key, []).append(now)
            self._prune(now)

    def allow(self, key, limit, window, now=None):
        return self.count(key, window, now) < limit

    def retry_after(self, key, limit, window, now=None):
        """Seconds until ``allow`` would be True again (0 if it already is)."""
        now = now or time.time()
        with self._lock:
            q = [t for t in self._hits.get(key, ()) if now - t < window]
            if len(q) < limit:
                return 0
            return int(window - (now - q[len(q) - limit])) + 1

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


limiter = Limiter()


# ---------------------------------------------------------------------- CSRF --

def origin_ok(headers, allowed_origins):
    """True when a state-changing request plausibly came from our own pages.

    Browsers attach ``Origin`` (and ``Sec-Fetch-Site``) to every cross-site POST
    and a page script cannot forge them, so a mismatch is decisive. Requests
    with neither header (curl, the capture agent, server-to-server) carry no
    ambient browser credentials to abuse and are left to their own token auth.
    """
    origin = headers.get("Origin", "")
    if origin and origin != "null":
        if allowed_origins:
            return origin in allowed_origins
        host = urlparse(origin).netloc
        return host == headers.get("Host", "")
    if origin == "null":
        return False
    site = headers.get("Sec-Fetch-Site", "")
    if site:
        return site in ("same-origin", "same-site", "none")
    return True


# ------------------------------------------------------------ company email --

# Consumer mailbox providers. A client signing up must use a company address, so
# these never pass unless an admin allow-lists the exact domain.
FREE_DOMAINS = frozenset("""
gmail.com googlemail.com yahoo.com yahoo.co.uk yahoo.fr yahoo.de yahoo.es yahoo.it
yahoo.in yahoo.com.au yahoo.co.in yahoo.ca ymail.com rocketmail.com
hotmail.com hotmail.co.uk hotmail.fr hotmail.de hotmail.es hotmail.it
outlook.com outlook.sa live.com live.co.uk live.fr msn.com
icloud.com me.com mac.com aol.com aim.com
proton.me protonmail.com protonmail.ch pm.me tutanota.com tutanota.de tuta.io tutamail.com
gmx.com gmx.net gmx.de gmx.at gmx.ch web.de mail.com email.com usa.com
zoho.com zohomail.com yandex.com yandex.ru ya.ru mail.ru inbox.ru list.ru bk.ru
qq.com 163.com 126.com sina.com sohu.com naver.com daum.net hanmail.net
fastmail.com fastmail.fm hushmail.com mailfence.com rediffmail.com rediff.com
libero.it virgilio.it orange.fr free.fr wanadoo.fr laposte.net sfr.fr
t-online.de freenet.de arcor.de btinternet.com sky.com talktalk.net virginmedia.com
comcast.net verizon.net att.net sbcglobal.net bellsouth.net cox.net charter.net earthlink.net
optonline.net rogers.com shaw.ca sympatico.ca bell.net
stc.com.sa mobily.com.sa
mailinator.com guerrillamail.com guerrillamail.net sharklasers.com grr.la 10minutemail.com
tempmail.com temp-mail.org temp-mail.io throwawaymail.com yopmail.com yopmail.fr getnada.com
trashmail.com maildrop.cc dispostable.com fakeinbox.com mintemail.com mohmal.com
emailondeck.com spamgourmet.com tempail.com burnermail.io mailnesia.com moakt.com
discard.email anonaddy.com simplelogin.com duck.com
""".split())

_EMAIL_RE = re.compile(
    r"^[a-z0-9][a-z0-9._%+\-]{0,63}@([a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+)$"
)


def normalise_email(raw):
    """Lower-cased, trimmed address, or '' if it is not a plausible address."""
    s = (raw or "").strip().lower()
    if len(s) > 254 or s.count("@") != 1 or ".." in s:
        return ""
    local, _, dom = s.partition("@")
    s = local.split("+", 1)[0] + "@" + dom        # one mailbox, however many +tags: no free accounts per tag
    m = _EMAIL_RE.match(s)
    if not m:
        return ""
    tld = m.group(1).rsplit(".", 1)[-1]
    return s if re.fullmatch(r"[a-z]{2,24}|xn--[a-z0-9\-]{2,}", tld) else ""


def _matches(domain, listed):
    """``domain`` is listed, or is a subdomain of a listed entry."""
    parts = domain.split(".")
    return any(".".join(parts[i:]) in listed for i in range(len(parts) - 1))


def company_email(raw, allow=(), block=()):
    """Return ``(email, None)`` when ``raw`` may sign up, else ``('', reason)``.

    ``allow`` and ``block`` are admin-managed domain lists. Allow wins over the
    built-in free-provider list; block wins over everything.
    """
    email = normalise_email(raw)
    if not email:
        return "", "invalid"
    domain = email.rsplit("@", 1)[1]
    allow = {d.strip().lower() for d in allow if d and d.strip()}
    block = {d.strip().lower() for d in block if d and d.strip()}
    if _matches(domain, block):
        return "", "blocked"
    if _matches(domain, allow):
        return email, None
    if _matches(domain, FREE_DOMAINS):
        return "", "personal"
    return email, None
