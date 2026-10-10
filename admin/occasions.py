"""The occasions and congress calendar Helvy uses for timing advice (KSA first).

A small curated list, kept in Python so it ships with the admin code. Public
dates only: national days, health awareness days, retail seasons and the medical
congresses HelloVoice plans around. No client names and no figures.

Islamic dates follow the moon and are approximate (marked approx); congress
dates are confirmed by the organisers each year (marked confirm). Influencer
content needs about 6–8 weeks from brief to posting, so each entry also says
when to brief.

    upcoming(today=None, months=4, sector="")   the next occasions, soonest first
    advise(categories, market, timing, launch)   launch windows for a brief, with one line each
                                                 ("Saudi Derm Congress is in 14 weeks: cast now")
"""
import datetime as _dt

# (name, kind, start, end, flag, sectors, note)
#   kind: national | religious | health | retail | congress | season
#   flag: "" exact, "approx" moon-sighted, "confirm" organiser to confirm
#   sectors: who it suits (pharma, derma, beauty, fmcg, retail, auto, all)
CALENDAR = [
    ("Breast Cancer Awareness Month", "health", "2026-10-01", "2026-10-31", "", "pharma", "Pink October: screening and awareness content."),
    ("World Mental Health Day", "health", "2026-10-10", "2026-10-10", "", "pharma", ""),
    ("Global Health Exhibition, Riyadh", "congress", "2026-10-26", "2026-10-29", "confirm", "pharma", "Saudi Arabia's largest health exhibition."),
    ("World Psoriasis Day", "health", "2026-10-29", "2026-10-29", "", "pharma derma", ""),
    ("World Diabetes Day", "health", "2026-11-14", "2026-11-14", "", "pharma", "Blue circle; diabetes is a leading condition in KSA."),
    ("World Antimicrobial Resistance Awareness Week", "health", "2026-11-18", "2026-11-24", "", "pharma", ""),
    ("White Friday sales", "retail", "2026-11-20", "2026-11-30", "approx", "beauty fmcg retail derma", "The region's biggest online sales week."),
    ("Year-end and New Year", "season", "2026-12-15", "2027-01-05", "", "all", "Recaps and new-year launches."),
    ("Saudi Derm Congress", "congress", "2027-01-15", "2027-01-17", "confirm", "derma pharma", "Dermatology; HCP and brand content."),
    ("Automechanika Riyadh", "congress", "2027-01-11", "2027-01-13", "confirm", "auto", "Automotive trade show."),
    ("Cycle-meeting season (pharma plans of action)", "season", "2027-01-01", "2027-01-31", "", "pharma", "Brand teams plan the year: a good time for launch films and HCP content."),
    ("World Health Expo (formerly Arab Health), Dubai", "congress", "2027-01-25", "2027-01-28", "confirm", "pharma", "Late January each year."),
    ("Jeddah Dermatology meeting", "congress", "2027-02-01", "2027-02-28", "confirm", "derma pharma", "February; dates to confirm."),
    ("World Cancer Day", "health", "2027-02-04", "2027-02-04", "", "pharma", ""),
    ("Ramadan", "religious", "2027-02-08", "2027-03-09", "approx", "all", "Peak content and viewing month; plan creators early, they book fast."),
    ("Saudi Founding Day", "national", "2027-02-22", "2027-02-22", "", "all", "National pride content; green and heritage themes."),
    ("Eid al-Fitr", "religious", "2027-03-10", "2027-03-13", "approx", "all", "Gifting, family and beauty."),
    ("Saudi Flag Day", "national", "2027-03-11", "2027-03-11", "", "all", ""),
    ("World Kidney Day", "health", "2027-03-11", "2027-03-11", "", "pharma", ""),
    ("Dermatology congress season (SSDDSS and others)", "congress", "2027-04-01", "2027-04-30", "confirm", "derma pharma beauty", "April; dates to confirm."),
    ("World Health Day", "health", "2027-04-07", "2027-04-07", "", "pharma", ""),
    ("Summer and sun-care season", "season", "2027-04-15", "2027-06-30", "", "derma beauty pharma", "Sunscreen, hydration and travel."),
    ("Hajj season", "religious", "2027-05-10", "2027-05-19", "approx", "pharma fmcg", "Health and safety content for pilgrims."),
    ("Eid al-Adha", "religious", "2027-05-16", "2027-05-19", "approx", "all", ""),
    ("World Hypertension Day", "health", "2027-05-17", "2027-05-17", "", "pharma", ""),
    ("World No Tobacco Day", "health", "2027-05-31", "2027-05-31", "", "pharma", ""),
    ("Islamic New Year", "religious", "2027-06-06", "2027-06-06", "approx", "all", ""),
    ("Back to school and university", "season", "2027-08-10", "2027-09-05", "approx", "fmcg retail pharma", "Student-targeting brands."),
    ("World Alzheimer's Day", "health", "2027-09-21", "2027-09-21", "", "pharma", ""),
    ("Saudi National Day", "national", "2027-09-23", "2027-09-23", "", "all", "The year's biggest national moment; book creators early."),
    ("World Heart Day", "health", "2027-09-29", "2027-09-29", "", "pharma", ""),
    ("Breast Cancer Awareness Month", "health", "2027-10-01", "2027-10-31", "", "pharma", ""),
]
LEAD_WEEKS = (6, 8)


def _d(s):
    return _dt.date.fromisoformat(s)


def upcoming(today=None, months=4, sector=""):
    today = today or _dt.date.today()
    horizon = today + _dt.timedelta(days=int(max(1, min(months, 12)) * 31))
    sector = (sector or "").strip().lower()
    out = []
    for name, kind, start, end, flag, sectors, note in CALENDAR:
        s, e = _d(start), _d(end)
        if e < today or s > horizon:
            continue
        if sector and sector not in sectors.split() and "all" not in sectors.split():
            continue
        brief_by = s - _dt.timedelta(weeks=LEAD_WEEKS[1])
        weeks = max(0, (s - today).days // 7)
        out.append({"name": name, "kind": kind, "starts": start, "ends": end, "weeks_away": weeks,
                    "advice": line(name, s, e, today),
                    "dates": {"approx": "approximate (moon-sighted)", "confirm": "organiser to confirm"}.get(flag, "fixed"),
                    "suits": sectors, "note": note,
                    "brief_by": brief_by.isoformat(), "brief_late": brief_by < today})
    out.sort(key=lambda x: x["starts"])
    return out


# The product spaces of the brief questions -> the calendar's sectors.
SECTOR_OF = {"health care": "pharma", "skincare": "derma", "beauty": "beauty", "hair care": "beauty", "fragrance": "beauty",
             "mother & baby": "fmcg", "food": "fmcg", "fitness": "fmcg", "fashion": "retail", "lifestyle": "retail",
             "technology": "retail", "automotive": "auto", "travel": "retail", "finance": "retail", "gaming": "retail"}
READY_WEEKS = 3          # under this, a window is too close to cast for
CAST_NOW_WEEKS = 14      # up to this far out, the best creators are still free: cast now


def _short(d):
    return "%d %s" % (d.day, d.strftime("%b"))


def status(start, end, today):
    """now (cast now) | plan (brief by a date) | tight (brief this week) | on (running) | late."""
    if start <= today <= end:
        return "on"
    weeks = (start - today).days / 7.0
    if weeks < READY_WEEKS:
        return "late"
    if weeks < LEAD_WEEKS[0]:
        return "tight"
    if weeks <= CAST_NOW_WEEKS:
        return "now"
    return "plan"


def line(name, start, end, today):
    """One sentence a client can act on. No prices, ever."""
    st = status(start, end, today)
    weeks = max(0, (start - today).days // 7)
    if st == "on":
        return "%s is on now, until %s." % (name, _short(end))
    if st == "late":
        return "%s starts in under %d weeks: too close to cast for." % (name, READY_WEEKS)
    when = "%d week%s" % (weeks, "" if weeks == 1 else "s")
    if st == "tight":
        return "%s is in %s: brief this week to make it." % (name, when)
    if st == "now":
        return "%s is in %s: cast now." % (name, when)
    return "%s is in %s: brief by %s." % (name, when, _short(start - _dt.timedelta(weeks=LEAD_WEEKS[1])))


def advise(categories=(), market="SA", timing=None, launch="", today=None, limit=3):
    """The launch windows that suit a brief, best first. Sector-specific occasions (a
    dermatology congress for skincare) come before ones that suit everyone; a launch date
    pulls the windows around it forward. ``{"windows": [...], "headline": str or None}``."""
    today = today or _dt.date.today()
    sectors = {SECTOR_OF.get(c) for c in (categories or []) if SECTOR_OF.get(c)}
    target = None
    if launch:
        try:
            target = _dt.date.fromisoformat(launch if len(launch) == 10 else launch + "-15")
        except ValueError:
            target = None
    months = 6 if timing in (None, "", "later", "quarter") else 3
    horizon = today + _dt.timedelta(days=31 * months)
    if target and target > horizon:
        horizon = target + _dt.timedelta(days=45)
    picks = []
    for name, kind, start, end, flag, suits, note in CALENDAR:
        s, e = _d(start), _d(end)
        if e < today or s > horizon:
            continue
        tags = set(suits.split())
        if market not in (None, "", "SA") and kind == "national":
            continue                              # Saudi national days are for KSA briefs
        own = bool(sectors & tags)
        if sectors and not own and "all" not in tags:
            continue
        st = status(s, e, today)
        if st == "late":
            continue
        rank = (0 if own else 1) + (0 if kind in ("congress", "religious", "season", "retail") else 0.5)
        if target:
            rank += min(3.0, abs((s - target).days) / 21.0)
        else:
            rank += (s - today).days / 120.0
        picks.append((rank, {"name": name, "kind": kind, "starts": start, "ends": end, "status": st,
                             "weeks_away": max(0, (s - today).days // 7), "message": line(name, s, e, today),
                             "dates": {"approx": "approximate (moon-sighted)", "confirm": "organiser to confirm"}.get(flag, "fixed"),
                             "brief_by": (s - _dt.timedelta(weeks=LEAD_WEEKS[1])).isoformat()}))
    picks.sort(key=lambda x: x[0])
    windows = [p for _, p in picks[:limit]]
    return {"windows": windows, "headline": windows[0]["message"] if windows else None,
            "rule": "Influencer content needs 6-8 weeks from brief to posting."}
