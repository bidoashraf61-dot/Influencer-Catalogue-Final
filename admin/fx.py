"""Currencies: prices are kept in SAR and shown in the currency a selection
(or the client) picks, at fixed rates set in Settings.

Rates are "1 SAR = x <currency>". AED and USD start from their official pegs
to the dollar (1 USD = 3.75 SAR, 1 USD = 3.6725 AED); EGP floats, so it has
no default and is offered only once a rate is entered.
"""

import math

import db

CURRENCIES = ["SAR", "AED", "USD", "EGP"]
DEFAULTS = {"AED": round(3.6725 / 3.75, 4), "USD": round(1 / 3.75, 4), "EGP": None}
NAMES = {"SAR": "Saudi riyal", "AED": "UAE dirham", "USD": "US dollar", "EGP": "Egyptian pound"}


def rates():
    """{currency: units per 1 SAR} for every currency that can be used."""
    saved = db.setting("fx_rates") or {}
    out = {"SAR": 1.0}
    for c in CURRENCIES[1:]:
        v = saved.get(c, DEFAULTS.get(c)) if isinstance(saved, dict) else DEFAULTS.get(c)
        if isinstance(v, (int, float)) and v > 0:
            out[c] = float(v)
    return out


def usable(cur):
    return cur in rates()


def nice(n, cur):
    """Round a converted price the way a quote reads: whole riyals/dirhams to
    the nearest 10, dollars to the nearest 5, pounds to the nearest 50."""
    step = {"USD": 5, "EGP": 50}.get(cur, 10)
    return int(round(n / step) * step) if n >= step else int(math.ceil(n))


def from_sar(amount, cur):
    if amount is None:
        return None
    r = rates().get(cur)
    return amount if not r or cur == "SAR" else nice(amount * r, cur)


def to_sar(amount, cur):
    """A price typed in `cur`, kept in SAR (whole riyals)."""
    if amount is None:
        return None
    r = rates().get(cur)
    return amount if not r or cur == "SAR" else int(round(amount / r))
