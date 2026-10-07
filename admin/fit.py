"""Fit and campaign-role calls on a creator, and the suggestion for them.

A client reading a creator's analysis has to decide for themselves whether
the creator suits the campaign. The admin makes that call once, per creator in
a selection, with ready-made words: how well they fit, and the part they play
(awareness, engagement, conversion, UGC). `suggest` proposes both from the
creator's analysis of one platform, with the numbers behind it, so the admin
confirms or changes it rather than starting from nothing. Nothing reaches a
client until the admin saves it.
"""

FITS = ["Strong fit", "Good fit", "Possible fit", "Not recommended"]
ROLES = ["Awareness", "Engagement", "Conversion", "UGC content"]

# Engagement rate that counts as "healthy" / "strong" on each platform. TikTok
# rates run well above Instagram's, so one bar would flatter one and punish
# the other.
ER_BARS = {"Instagram": (2.0, 3.5), "TikTok": (4.0, 7.0)}
ER_DEFAULT = (1.5, 3.0)
MARKET = "SA"                                 # the audience that matters for most of our work
MARKET_NAME = "KSA"


def _pct(v):
    return ("%g" % round(v, 1)) + "%"


def _k(n):
    n = float(n)
    return ("%gM" % round(n / 1e6, 1)) if n >= 1e6 else ("%gK" % round(n / 1e3, 1)) if n >= 1e3 else "%d" % n


def clean(fit, roles, reason):
    """What the admin typed, kept to the ready-made words."""
    fit = fit if fit in FITS else ""
    roles = [r for r in ROLES if r in (roles or [])]
    reason = " ".join(str(reason or "").split())[:160]
    return {"fit": fit, "roles": roles, "reason": reason} if (fit or roles or reason) else None


def suggest(doc, platform, followers=None):
    """{"fit", "roles", "reason", "evidence"} from one platform's analysis, or
    {"note": ...} when there is nothing to go on."""
    if not doc:
        return {"note": "No %s analysis on file yet — nothing to suggest from." % (platform or "platform")}
    low, high = ER_BARS.get(platform, ER_DEFAULT)
    f = doc.get("followers") or followers
    er = doc.get("er")
    fake = doc.get("fake_followers_pct")
    if fake is None and doc.get("credibility_pct") is not None:
        fake = round(100 - doc["credibility_pct"], 1)
    countries = (doc.get("audience") or {}).get("countries") or []
    home = next((c.get("pct") for c in countries if str(c.get("code", "")).upper() == MARKET), None)
    if home is None and countries:
        home = 0

    pts, signals, evidence = 0, 0, []
    if er is not None:
        signals += 1
        if er >= high:
            pts += 1; evidence.append("Strong engagement (%s)" % _pct(er))
        elif er >= low:
            evidence.append("Healthy engagement (%s)" % _pct(er))
        else:
            pts -= 1; evidence.append("Low engagement (%s)" % _pct(er))
    if fake is not None:
        signals += 1
        if fake <= 12:
            pts += 1; evidence.append("Only %s fake followers" % _pct(fake))
        elif fake >= 30:
            pts -= 2; evidence.append("High share of fake followers (%s)" % _pct(fake))
    if home is not None:
        signals += 1
        if home >= 60:
            pts += 1; evidence.append("%s of the audience is in %s" % (_pct(home), MARKET_NAME))
        elif home < 30:
            pts -= 1; evidence.append("Only %s of the audience is in %s" % (_pct(home), MARKET_NAME))
        else:
            evidence.append("%s of the audience is in %s" % (_pct(home), MARKET_NAME))

    roles = []
    local_ok = home is None or home >= 50
    real_ok = fake is None or fake <= 20
    if f and f >= 100000:
        roles.append("Awareness"); evidence.append("Reach: %s followers" % _k(f))
    if er is not None and er >= high:
        roles.append("Engagement")
        if f and f <= 500000 and local_ok and real_ok:
            roles.append("Conversion")
    if "Conversion" in roles:
        evidence.append("Engaged, real, local audience suits conversion")

    if signals < 2:
        fit = ""
    elif fake is not None and fake >= 30:
        fit = "Not recommended"
    else:
        fit = "Strong fit" if pts >= 3 else "Good fit" if pts == 2 else "Possible fit" if pts == 1 else "Not recommended"
    reason = " · ".join(evidence[:3])
    out = {"fit": fit, "roles": roles, "reason": reason, "evidence": evidence}
    if signals < 2:
        out["note"] = "Not enough numbers in this analysis to suggest a fit; roles are from what is there."
    return out
