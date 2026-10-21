"""Switches and monthly caps for the team's AI helpers (item 218, phase 1, 2026-10-21).

Staff never pay credits for these. Each helper has an on/off switch and a monthly USD cap, both kept in the
``ai_features`` setting and changed in the admin (Client portal → Settings & keys → Team AI). Spend is read back
from ``ai_audit`` by the helper's own ``kind``, so the cap is the real bill, and the shared monthly budget in
gemini.generate still applies on top. Every helper ships OFF: nothing is spent until Bido switches it on.

    compliance   the claim / brief check on each new post's caption               kind "post_check"
    nextstep     the wording of the daily next-step digest for each KAM           kind "next_step_ai"

The rule-based parts (missing disclosure, missing hashtags, overdue steps, the digest itself) are free and run
whether the switch is on or not.

Requirements: Portal Programme/BRIEF-ai-journey-2026-10-21.md.
"""
import db

FEATURES = {
    "compliance": {"label": "Post checks", "kind": "post_check", "cap": 15.0,
                   "hint": "Reads each new post's caption for health-claim risk and the brief's rules."},
    "nextstep": {"label": "Next-step digest", "kind": "next_step_ai", "cap": 5.0,
                 "hint": "Words the 9:00 digest of stuck and overdue work for each account manager."},
}
KEY = "ai_features"


def _saved():
    got = db.setting(KEY, {}) or {}
    return got if isinstance(got, dict) else {}


def conf(name):
    f = FEATURES[name]
    s = _saved().get(name) or {}
    try:
        cap = float(s.get("cap", f["cap"]))
    except (TypeError, ValueError):
        cap = f["cap"]
    return {"on": bool(s.get("on", False)), "cap": max(0.0, cap)}


def spent(name):
    """USD spent this calendar month by one helper."""
    import gemini
    with db.connect() as conn:
        r = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM ai_audit WHERE kind = ? AND at >= ?",
                         (FEATURES[name]["kind"], gemini.month_start())).fetchone()
    return round(float(r[0]), 4)


def allowed(name):
    """True when the helper may call Gemini now: switched on, Gemini set up, under its own cap."""
    import gemini
    c = conf(name)
    return c["on"] and gemini.configured() and spent(name) < c["cap"]


def why_not(name):
    """A short reason the AI part is not running, or "" when it is."""
    import gemini
    c = conf(name)
    if not c["on"]:
        return "switched off"
    if not gemini.configured():
        return "Gemini is not set up"
    if spent(name) >= c["cap"]:
        return "this month's cap is used"
    return ""


def status():
    """Rows for the admin's Team AI card."""
    out = []
    for name, f in FEATURES.items():
        c = conf(name)
        out.append({"key": name, "label": f["label"], "hint": f["hint"], "on": c["on"], "cap": c["cap"],
                    "spent": spent(name), "why_not": why_not(name)})
    return out


def save(name, on=None, cap=None, by=""):
    if name not in FEATURES:
        raise KeyError(name)
    all_ = dict(_saved())
    cur = dict(all_.get(name) or {})
    if on is not None:
        cur["on"] = bool(on)
    if cap is not None:
        cur["cap"] = max(0.0, min(500.0, float(cap)))
    all_[name] = cur
    db.set_setting(KEY, all_)
    return conf(name)
