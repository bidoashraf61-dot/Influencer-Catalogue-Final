"""The occasions and congress calendar Helvy uses for timing advice (KSA first).

A small curated list, kept in Python so it ships with the admin code. Public
dates only: national days, health awareness days, retail seasons and the medical
congresses HelloVoice plans around. No client names and no figures.

Islamic dates follow the moon and are approximate (marked approx); congress
dates are confirmed by the organisers each year (marked confirm). Influencer
content needs about 6–8 weeks from brief to posting, so each entry also says
when to brief.

    upcoming(today=None, months=4, sector="")   the next occasions, soonest first
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
        out.append({"name": name, "kind": kind, "starts": start, "ends": end,
                    "dates": {"approx": "approximate (moon-sighted)", "confirm": "organiser to confirm"}.get(flag, "fixed"),
                    "suits": sectors, "note": note,
                    "brief_by": brief_by.isoformat(), "brief_late": brief_by < today})
    out.sort(key=lambda x: x["starts"])
    return out
