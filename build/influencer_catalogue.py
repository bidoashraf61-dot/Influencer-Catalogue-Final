#!/usr/bin/env python3
"""Build the HelloVoice influencer proposal catalogue.

Reads the roster workbook and emits two things:

  content/catalogue_private.json  — code -> name / handle / exact followers.
                                    NEVER deployed. Gitignored. This is the
                                    reveal key you use after the client signs.
  site/catalogue/index.html       — the client-facing portal. Carries the
                                    creator's name, exact follower count, city,
                                    platform, tier and price range. The only
                                    field still withheld is the @handle.

NOTE ON THE SECURITY MODEL. This started as an anonymised catalogue — code,
tier and a follower *band*, so a leaked copy was worthless. Names and exact
counts were added on request, and that changes things: "Noha Magdy, 697,000,
Jeddah, Instagram" identifies the account in one search, so withholding the
@handle no longer protects much. The passcode and the anti-copy layer are now
the real defence, and neither stops a determined technical user. Build with
CATALOGUE_ANON=1 to go back to codes and bands.

    python3 build/influencer_catalogue.py
"""

import hashlib
import html
import json
import os
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "Influncer Proposal Catalogue" / "Alpha_Plus_influncers.xlsx"
OUT_HTML = ROOT / "site" / "catalogue" / "index.html"
OUT_SELECTION = ROOT / "site" / "catalogue" / "selection" / "index.html"
OUT_PRIVATE = ROOT / "content" / "catalogue_private.json"
PHOTO_DIR = ROOT / "site" / "assets" / "catalogue"
HARVEST = ROOT / "content" / "_harvest.json"  # optional, from the photo pass

# ---------------------------------------------------------------- reference --

# Final client prices, SAR, straight out of the tier sheets. Cards show the
# full range.
# `reach` is the tier's follower range as defined in each tier sheet header
# (نطاق الفئة), not something inferred from the roster.
TIERS = {
    "Nano":     {"code": "NA", "label": "Nano",  "from": 435,  "to": 870,  "order": 1, "reach": "Under 10K"},
    "Micro":    {"code": "MI", "label": "Micro", "from": 870,  "to": 1740, "order": 2, "reach": "10K – 50K"},
    "Mid-Tier": {"code": "MD", "label": "Mid",   "from": 1450, "to": 2900, "order": 3, "reach": "50K – 500K"},
    "Macro":    {"code": "MC", "label": "Macro", "from": 2175, "to": 4350, "order": 4, "reach": "500K – 1M"},
}

# The workbook has no niche column, so interests are not per-creator data yet.
# Drop a {code: interest} map at content/interests.json and it is picked up.
INTERESTS = ["Beauty", "Skincare", "Hair Care", "Fragrance", "Make-up", "Lifestyle"]
DEFAULT_INTEREST = "Skincare"
HAS_INTERESTS = False

CITIES = {
    "الرياض": "Riyadh",
    "جدة": "Jeddah",
    "غير محددة": "Unspecified",
}

# Card code prefix. This is client-facing on every card, so it names the
# agency, not the client — the catalogue is a reusable HelloVoice asset.
PREFIX = os.environ.get("CATALOGUE_PREFIX", "HV")

PASSCODE = os.environ.get("CATALOGUE_PASSCODE", "Hellovoice123")
# Where the quote request is POSTed. Empty string = the page shows a clear
# "not configured yet" error instead of silently losing a submission.
# FormSubmit relays the request to this inbox with no backend of our own.
# The address must be activated once: the first POST triggers a confirmation
# email to it, and nothing is delivered until someone clicks that link.
REQUEST_EMAIL = os.environ.get("CATALOGUE_EMAIL", "info@hellovoice.co.uk")
ENDPOINT = os.environ.get(
    "CATALOGUE_ENDPOINT", f"https://formsubmit.co/ajax/{REQUEST_EMAIL}"
)

# CATALOGUE_ANON=1 restores the anonymised catalogue: code and follower band
# instead of name and exact count. Everything else is identical.
ANON = os.environ.get("CATALOGUE_ANON", "").lower() in ("1", "true", "yes")


def band(n):
    """Follower band, used only in anonymised mode."""
    if not n:
        return "—"
    if n < 10_000:
        return "Under 10K"
    if n < 50_000:
        return "10K – 50K"
    if n < 500_000:
        return "50K – 500K"
    return "500K+"


def read_roster():
    wb = openpyxl.load_workbook(WORKBOOK, data_only=True)
    ws = wb["المؤثرون"]
    rows = [r for r in ws.iter_rows(min_row=4, values_only=True) if r[0]]

    interests = {}
    imap = ROOT / "content" / "interests.json"
    if imap.exists():
        interests = json.loads(imap.read_text())
    # No map means every creator falls back to one default value. Rendering a
    # filter off that would tell the client all 162 are Skincare creators —
    # stating something untrue, not merely omitting data. The filter is only
    # rendered when there is real data behind it.
    global HAS_INTERESTS
    HAS_INTERESTS = bool(interests)

    harvest = {}
    if HARVEST.exists():
        for rec in json.loads(HARVEST.read_text()):
            harvest[rec["u"].lower()] = rec

    people, counters = [], {}
    for raw in sorted(rows, key=lambda r: (TIERS.get(r[6], {}).get("order", 9), -(r[5] or 0))):
        _, name, city, account, platform, followers, tier, _notes = raw[:8]
        meta = TIERS.get(tier)
        if not meta:
            continue

        counters[tier] = counters.get(tier, 0) + 1
        code = f"{PREFIX}-{meta['code']}-{counters[tier]:03d}"
        handle = (account or "").strip().lstrip("@")

        # Live follower count from the photo pass wins — the workbook is stale
        # (Ghalya read 570,730 live against 511,000 in the sheet).
        live = harvest.get(handle.lower(), {}).get("followers")
        effective = live or followers

        pf = PHOTO_DIR / f"{code}.jpg"
        # Photos get replaced in place as harvest passes improve them, and the
        # URL never changes — a cached image will happily render the old one and
        # send you hunting a data bug that is not there. Stamp them.
        photo = f"{code}.jpg?v={file_hash(pf)}" if pf.exists() else ""
        lowres = bool(photo) and jpeg_width(pf) <= 150

        people.append({
            "code": code,
            "tier": tier,
            "tier_label": meta["label"],
            "price_from": meta["from"],
            "price_to": meta["to"],
            "city": CITIES.get((city or "").strip(), "Unspecified"),
            "platform": platform,
            "interest": interests.get(code, DEFAULT_INTEREST),
            "photo": photo,
            "lowres": lowres,
            # private, stripped before the HTML is written
            "_name": name,
            "_handle": handle,
            "_followers": effective,
            "_sheet_followers": followers,
        })
    return people


def file_hash(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8]


def jpeg_width(path):
    """Source width, without a Pillow dependency. Instagram hands back either
    320px (API) or 100px (og:image), and a 100px source blown up to a 330px
    card is visibly mush — the card treatment branches on this."""
    b = path.read_bytes()
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            return (b[i + 7] << 8) | b[i + 8]
        i += 2 + ((b[i + 2] << 8) | b[i + 3])
    return 0


def client_logos():
    """The client banner, read from the built homepage rather than copied, so
    it cannot drift from the site. Returns unique (src, srcset, alt) in the
    order the site shows them; empty if the homepage is not built yet."""
    home = ROOT / "site" / "index.html"
    if not home.exists():
        return []
    import re
    page = home.read_text(encoding="utf-8")
    sec = re.search(r'<section[^>]*client_banner_section.*?</section>', page, re.S)
    if not sec:
        return []
    found = re.findall(
        r'src="(/assets/clients/[^"]+)"\s+srcset="([^"]+)"\s+alt="([^"]*)"', sec.group(0))
    seen, out = set(), []
    for src, srcset, alt in found:
        if src in seen:
            continue
        seen.add(src)
        out.append((src, srcset, alt))
    return out


def plate(code):
    """Fallback tile label — the code's own number."""
    return code.rsplit("-", 1)[-1]


def display_name(name):
    """Tidy the sheet's inconsistent casing without mangling real initialisms.
    'lilian hassanieh' and 'GHALIAH ALSHARIF' both need fixing; 'Ghalya MU'
    does not, so mixed-case names are left exactly as written."""
    s = str(name or "").strip()
    if not s:
        return "—"
    if s.islower() or s.isupper():
        return " ".join(w if (w.isupper() and len(w) <= 3) else w.capitalize()
                        for w in s.split())
    return s


# Drawn marks, one consistent stroke weight. Not emoji, not a font glyph.
PLATFORM_ICONS = {
    "Instagram": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
        '<rect x="3" y="3" width="18" height="18" rx="5"/>'
        '<circle cx="12" cy="12" r="4.1"/>'
        '<circle cx="17.3" cy="6.7" r="1.15" fill="currentColor" stroke="none"/></svg>'
    ),
    "TikTok": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M14.2 3v11.6a3.6 3.6 0 1 1-3.6-3.6"/>'
        '<path d="M14.2 3.2c.45 2.7 2.05 4.3 4.75 4.6"/></svg>'
    ),
}


def profile_url(platform, handle):
    if not handle:
        return ""
    if platform == "Instagram":
        return f"https://www.instagram.com/{handle}/"
    if platform == "TikTok":
        return f"https://www.tiktok.com/@{handle}"
    return ""


def card_html(p):
    """One card. Data attributes carry only non-identifying fields."""
    e = html.escape
    if p["photo"]:
        cls = "cat-card__photo cat-card__photo--soft" if p["lowres"] else "cat-card__photo"
        media = (
            f'<div class="{cls}" '
            f'style="background-image:url(/assets/catalogue/{e(p["photo"])})"></div>'
        )
    else:
        media = (
            f'<div class="cat-card__photo cat-card__photo--fallback" '
            f'data-plate="{e(plate(p["code"]))}"></div>'
        )

    icon = PLATFORM_ICONS.get(p["platform"], "")
    url = "" if ANON else profile_url(p["platform"], p["_handle"])
    if url:
        # data-noselect keeps the click from also toggling the card underneath.
        platform_html = (
            f'<a class="cat-card__platform" href="{e(url)}" target="_blank" '
            f'rel="noopener noreferrer nofollow" data-noselect '
            f'aria-label="Visit {e(p["platform"])} profile">'
            f'<span class="cat-card__platform-hint">Visit profile</span>{icon}</a>'
        )
    else:
        platform_html = (
            f'<span class="cat-card__platform" title="{e(p["platform"])}">{icon}</span>'
        )
    name = "" if ANON else display_name(p["_name"])
    reach_label = "Reach" if ANON else "Followers"
    reach = band(p["_followers"]) if ANON else (
        f"{p['_followers']:,}" if p["_followers"] else "—")
    name_html = "" if ANON else f'\n          <h3 class="cat-card__name">{e(name)}</h3>'
    label_who = e(p["code"]) if ANON else f"{e(name)}, {e(p['code'])}"

    return f"""      <article class="cat-card" data-tier="{e(p['tier'])}" data-platform="{e(p['platform'])}" data-city="{e(p['city'])}" data-interest="{e(p['interest'])}" data-code="{e(p['code'])}" data-price="{p['price_from']}" tabindex="0" role="button" aria-pressed="false" aria-label="{label_who}, {e(p['tier_label'])} tier, {e(p['city'])}, {e(p['platform'])}, {reach} followers">
        <div class="cat-card__media">
          {media}
          <span class="cat-card__shield" aria-hidden="true"></span>
          <span class="cat-card__tier">{e(p['tier_label'])}</span>
          {platform_html}
          <span class="cat-card__check" aria-hidden="true"></span>
        </div>
        <div class="cat-card__body">
          <p class="cat-card__code">{e(p['code'])}</p>{name_html}
          <ul class="cat-card__meta">
            <li><span>{reach_label}</span><strong>{reach}</strong></li>
            <li><span>City</span><strong>{e(p['city'])}</strong></li>
            <li><span>Tier</span><strong>{e(p['tier_label'])}</strong></li>
          </ul>
          <p class="cat-card__price"><strong>{p['price_from']:,} – {p['price_to']:,}</strong> SAR</p>
        </div>
      </article>"""


def chips(label, name, values):
    out = [f'<div class="cat-filter"><span class="cat-filter__label">{html.escape(label)}</span><div class="cat-filter__chips">']
    out.append(f'<button type="button" class="cat-chip is-active" data-filter="{name}" data-value="" aria-pressed="true">All</button>')
    for value, count in values:
        out.append(
            f'<button type="button" class="cat-chip" data-filter="{name}" '
            f'data-value="{html.escape(value)}" aria-pressed="false">'
            f'{html.escape(value)} <i>{count}</i></button>'
        )
    out.append("</div></div>")
    return "".join(out)


def stamp(rel):
    """Content-hash an asset URL. The browser will happily serve a stale
    stylesheet otherwise — the theme brief calls this out explicitly."""
    f = ROOT / "site" / rel.lstrip("/")
    if not f.exists():
        return rel
    h = hashlib.sha1(f.read_bytes()).hexdigest()[:8]
    return f"{rel}?v={h}"


def relativise(html, depth):
    """Rewrite root-absolute asset and page links to be relative to a page
    sitting `depth` directories below the site root.

    A static host that serves the site at the domain root is the easy case;
    GitHub Pages serves it under /<repo>/, where every "/assets/..." resolves
    against the wrong root and the page loads unstyled. Relative links work in
    both, and need no build-time knowledge of the base path.

    srcset matters as much as src and is easy to miss: it holds several
    comma-separated URLs, each possibly with a descriptor, and it is the one
    the browser actually uses on a retina screen. Missing it means the 1x
    fallback looks fine on a desktop check while every logo silently 404s on a
    phone."""
    prefix = "../" * depth

    def one(m):
        return f'{m.group(1)}="{prefix}{m.group(2)}"'

    # single-URL attributes
    html = re.sub(r'\b(href|src|poster)="/(?!/)([^"]*)"', one, html)

    # srcset: rewrite every candidate inside the attribute
    def srcset(m):
        out = []
        for cand in m.group(1).split(","):
            cand = cand.strip()
            if cand.startswith("/") and not cand.startswith("//"):
                cand = prefix + cand[1:]
            out.append(cand)
        return 'srcset="' + ", ".join(out) + '"'

    html = re.sub(r'srcset="([^"]*)"', srcset, html)

    html = html.replace("url(/assets/", f"url({prefix}assets/")
    return html


def build():
    people = read_roster()

    # ---- private key file, never deployed
    OUT_PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    OUT_PRIVATE.write_text(json.dumps({
        p["code"]: {
            "name": p["_name"],
            "handle": p["_handle"],
            "platform": p["platform"],
            "followers": p["_followers"],
            "sheet_followers": p["_sheet_followers"],
            "tier": p["tier"],
            "city": p["city"],
        } for p in people
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    def tally(key, order=None):
        counts = {}
        for p in people:
            counts[p[key]] = counts.get(p[key], 0) + 1
        items = sorted(counts.items(), key=lambda kv: -kv[1])
        if order:
            items = sorted(counts.items(), key=lambda kv: order.index(kv[0]))
        return items

    tier_order = ["Nano", "Micro", "Mid-Tier", "Macro"]
    tier_counts = [(TIERS[t]["label"], n) for t, n in tally("tier", tier_order)]

    filters = (
        chips("Tier", "tier", [(t, n) for t, n in tally("tier", tier_order)])
        + chips("Platform", "platform", tally("platform"))
        + chips("City", "city", tally("city"))
        + (chips("Interest", "interest", tally("interest")) if HAS_INTERESTS else "")
    )

    logos = client_logos()
    logo_row = "".join(
        f'<div class="cat-clients__logo">'
        f'<img src="{html.escape(src)}" srcset="{html.escape(srcset)}" '
        f'alt="{html.escape(alt)}" width="64" height="64" loading="lazy" decoding="async"/></div>'
        for src, srcset, alt in logos
    )
    clients_block = ("""
  <section class="cat-clients" aria-label="Clients">
    <div class="cat-pad"><div class="cat-container">
      <p class="cat-clients__caption">Trusted <em>(by)</em> Leading Multinational Brands</p>
    </div></div>
    <div class="cat-clients__track" aria-hidden="true">
      <div class="cat-clients__row">""" + logo_row + logo_row + """</div>
    </div>
  </section>""") if logos else ""

    cards = "\n".join(card_html(p) for p in people)
    with_photos = sum(1 for p in people if p["photo"])

    # The band is short phrases separated by the asterisk mark, per
    # THEME-BRIEF.md — not two long run-on strings.
    phrases = [f"{TIERS[t]['label']} {TIERS[t]['reach']}" for t in tier_order] + INTERESTS
    ASTERISK = (
        '<i class="cat-ticker__star" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" width="100%" height="100%">'
        '<g fill="currentColor">'
        '<rect x="10.3" y="1" width="3.4" height="22" rx="1.7"/>'
        '<rect x="10.3" y="1" width="3.4" height="22" rx="1.7" transform="rotate(45 12 12)"/>'
        '<rect x="10.3" y="1" width="3.4" height="22" rx="1.7" transform="rotate(90 12 12)"/>'
        '<rect x="10.3" y="1" width="3.4" height="22" rx="1.7" transform="rotate(135 12 12)"/>'
        '</g></svg></i>'
    )
    one_run = "".join(
        f'{ASTERISK}<span>{html.escape(phrase)}</span>' for phrase in phrases
    )
    # two identical runs so translateX(-50%) loops seamlessly
    ticker_track = one_run + one_run

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex, nofollow, noarchive, noimageindex"/>
<meta name="referrer" content="no-referrer"/>
<title>Influencer Catalogue — HelloVoice</title>
<link rel="icon" href="/assets/icons/icon-32.png" type="image/png"/>
<link rel="apple-touch-icon" href="/assets/icons/icon-180.png"/>
<link rel="stylesheet" href="{stamp('/assets/css/catalogue.css')}"/>
</head>
<body class="cat-locked" data-page="catalogue">

<div class="cat-gate" id="cat-gate">
  <div class="cat-gate__inner">
    <img class="cat-gate__logo" src="/assets/brand/logo-knockout.webp" alt="HelloVoice"/>
    <p class="cat-gate__eyebrow">Confidential</p>
    <h1 class="cat-gate__title">Influencer<br/>Catalogue</h1>
    <p class="cat-gate__note">Enter the access code you were given.</p>
    <form class="cat-gate__form" id="cat-gate-form" autocomplete="off">
      <input type="password" id="cat-code" class="cat-gate__input" placeholder="Access code"
             aria-label="Access code" autocomplete="off" spellcheck="false"/>
      <button type="submit" class="cat-btn cat-btn--lime">Unlock</button>
    </form>
    <p class="cat-gate__error" id="cat-gate-error" role="alert" hidden>That code is not right.</p>
  </div>
</div>

<main class="cat-app" id="cat-app" hidden>

  <header class="cat-hero">
    <div class="cat-pad"><div class="cat-container">
      <div class="cat-topbar">
        <img class="cat-hero__logo" src="/assets/brand/logo.png" alt="HelloVoice"/>
        <a class="cat-portfolio" href="https://hellovoice.co.uk" target="_blank" rel="noopener">
          Portfolio
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg>
        </a>
      </div>
      <div class="cat-hero__head">
        <div class="cat-pill">Creator Roster</div>
        <h1 class="cat-hero__title">Catalogue</h1>
      </div>
      <p class="cat-hero__lead">
        Creator campaigns run end to end — casting against the brief,
        per-creator scripts that protect the claim set, compliance before
        anything posts, and a post-by-post read afterwards.
      </p>

      <div class="cat-showreel">
        <video class="cat-showreel__video" autoplay muted loop playsinline
               preload="none" poster="/assets/video/hero-reel-poster.jpg"
               aria-label="Influencer campaign showreel">
          <source src="/assets/video/hero-reel.mp4" type="video/mp4"/>
        </video>
        <span class="cat-showreel__label">Showreel</span>
      </div>
    </div></div>
  </header>

  <div class="cat-ticker" aria-hidden="true">
    <div class="cat-ticker__track">{ticker_track}</div>
  </div>

  <section class="cat-controls" aria-label="Filters">
    <div class="cat-pad"><div class="cat-container">
      {filters}
      <p class="cat-count" id="cat-count" aria-live="polite">{len(people)} creators</p>
      <p class="cat-note">Prices are indicative ranges only. Final rates vary with campaign requirements, deliverables, exclusivity, seasonality and any special agreement, and are confirmed in the quote.</p>
    </div></div>
  </section>

  {clients_block}

  <section class="cat-grid-section">
    <div class="cat-pad"><div class="cat-container">
      <div class="cat-grid" id="cat-grid">
{cards}
      </div>
      <p class="cat-empty" id="cat-empty" hidden>Nothing matches those filters.</p>
    </div></div>
  </section>

  <footer class="cat-footer">
    <div class="cat-pad"><div class="cat-container">
      <img class="cat-footer__logo" src="/assets/helv/logo-knockout.webp"
           srcset="/assets/helv/logo-knockout@2x.webp 2x"
           alt="HelloVoice" width="760" height="166"/>
      <p class="cat-footer__note">
        Confidential and not for redistribution.
        Creator identities are released on agreement.
      </p>
      <a class="cat-footer__portfolio" href="https://hellovoice.co.uk" target="_blank" rel="noopener">
        See the portfolio at hellovoice.co.uk
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg>
      </a>
    </div></div>
  </footer>

  <div class="cat-tray" id="cat-tray" hidden>
    <div class="cat-tray__inner">
      <div class="cat-tray__count"><strong id="cat-tray-n">0</strong> selected</div>
      <div class="cat-tray__codes" id="cat-tray-codes"></div>
      <div class="cat-tray__actions">
        <button type="button" class="cat-btn cat-btn--ghost" id="cat-clear">Clear</button>
        <button type="button" class="cat-btn cat-btn--ghost" id="cat-save">Save selection</button>
        <button type="button" class="cat-btn cat-btn--lime" id="cat-request">Request a quote</button>
      </div>
    </div>
  </div>

  <div class="cat-modal" id="cat-modal" hidden role="dialog" aria-modal="true" aria-labelledby="cat-modal-title">
    <div class="cat-modal__panel">
      <button type="button" class="cat-modal__close" id="cat-modal-close" aria-label="Close">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>
      </button>
      <h2 class="cat-modal__title" id="cat-modal-title">Request a quote</h2>
      <p class="cat-modal__sub"><strong id="cat-modal-n">0</strong> creators selected</p>
        <p class="cat-note cat-note--modal">Prices are indicative ranges only. Final rates vary with campaign requirements, deliverables, exclusivity, seasonality and any special agreement, and are confirmed in the quote.</p>
      <form id="cat-form" class="cat-form" autocomplete="off">
        <label>Full name<input type="text" name="name" required/></label>
        <label>Company<input type="text" name="company" required/></label>
        <label>Email<input type="email" name="email" required/></label>
        <label>Phone<input type="tel" name="phone" required/></label>
        <button type="submit" class="cat-btn cat-btn--lime cat-form__submit">Send request</button>
        <p class="cat-form__status" id="cat-form-status" role="status"></p>
      </form>
    </div>
  </div>

  <div class="cat-modal" id="cat-save-modal" hidden role="dialog" aria-modal="true" aria-labelledby="cat-save-title">
    <div class="cat-modal__panel">
      <button type="button" class="cat-modal__close" id="cat-save-close" aria-label="Close">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>
      </button>
      <h2 class="cat-modal__title" id="cat-save-title">Save selection</h2>
      <p class="cat-modal__sub"><strong id="cat-save-n">0</strong> creators. Name it, then share the link.</p>
      <form id="cat-save-form" class="cat-form" autocomplete="off">
        <label>Selection name<input type="text" name="selname" placeholder="Ramadan skincare push" required/></label>
        <button type="submit" class="cat-btn cat-btn--lime cat-form__submit">Open selection</button>
      </form>
      <div id="cat-save-out" hidden>
        <p class="cat-note cat-note--modal">Anyone with this link and the access code sees this selection.</p>
        <div class="cat-share">
          <input type="text" id="cat-share-url" class="cat-share__url" readonly aria-label="Selection link"/>
          <button type="button" class="cat-btn cat-btn--lime" id="cat-share-copy">Copy</button>
        </div>
        <a class="cat-share__open" id="cat-share-open" href="#">Open the selection &rarr;</a>
      </div>
    </div>
  </div>

</main>

<script>
  window.CATALOGUE_CONFIG = {{
    passHash: "{simple_hash(PASSCODE)}",
    endpoint: {json.dumps(ENDPOINT)}
  }};
</script>
<script src="{stamp('/assets/js/catalogue.js')}"></script>
</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(relativise(page, 1), encoding="utf-8")

    # ---- the selection page ------------------------------------------------
    # A sibling of the catalogue that renders whichever creators the URL
    # fragment names. It carries the full set of cards because a static page
    # has to be able to draw ANY selection — see docs/CATALOGUE.md, this does
    # not hide the rest of the roster from whoever holds the link.
    selection = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="robots" content="noindex, nofollow, noarchive, noimageindex"/>
<meta name="referrer" content="no-referrer"/>
<title>Selection — HelloVoice</title>
<link rel="icon" href="/assets/icons/icon-32.png" type="image/png"/>
<link rel="apple-touch-icon" href="/assets/icons/icon-180.png"/>
<link rel="stylesheet" href="{stamp('/assets/css/catalogue.css')}"/>
</head>
<body class="cat-locked" data-page="selection">

<div class="cat-gate" id="cat-gate">
  <div class="cat-gate__inner">
    <img class="cat-gate__logo" src="/assets/brand/logo-knockout.webp" alt="HelloVoice"/>
    <p class="cat-gate__eyebrow">Confidential</p>
    <h1 class="cat-gate__title">Selection</h1>
    <p class="cat-gate__note">Enter the access code you were given.</p>
    <form class="cat-gate__form" id="cat-gate-form" autocomplete="off">
      <input type="password" id="cat-code" class="cat-gate__input" placeholder="Access code"
             aria-label="Access code" autocomplete="off" spellcheck="false"/>
      <button type="submit" class="cat-btn cat-btn--lime">Unlock</button>
    </form>
    <p class="cat-gate__error" id="cat-gate-error" role="alert" hidden>That code is not right.</p>
  </div>
</div>

<main class="cat-app" id="cat-app" hidden>

  <header class="cat-hero">
    <div class="cat-pad"><div class="cat-container">
      <div class="cat-topbar">
        <img class="cat-hero__logo" src="/assets/brand/logo.png" alt="HelloVoice"/>
        <a class="cat-portfolio" href="https://hellovoice.co.uk" target="_blank" rel="noopener">
          Portfolio
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg>
        </a>
      </div>
      <a class="cat-back" href="/catalogue/">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>
        Full catalogue
      </a>
      <div class="cat-hero__head">
        <div class="cat-pill">Selection</div>
        <h1 class="cat-hero__title" id="sel-title">Selection</h1>
      </div>
      <p class="cat-hero__lead">
        The creators shortlisted for this campaign. Remove anyone who does not
        fit, then send it back for a full quote.
      </p>
    </div></div>
  </header>

  <section class="cat-summary" aria-label="Summary">
    <div class="cat-pad"><div class="cat-container">
      <dl class="cat-summary__grid" id="sel-summary"></dl>
      <p class="cat-note">Prices are indicative ranges only. Final rates vary with campaign requirements, deliverables, exclusivity, seasonality and any special agreement, and are confirmed in the quote.</p>
    </div></div>
  </section>

  {{clients_block}}

  <section class="cat-grid-section">
    <div class="cat-pad"><div class="cat-container">
      <div class="cat-grid" id="cat-grid">
{{cards}}
      </div>
      <p class="cat-empty" id="cat-empty" hidden>This link does not name any creators.</p>
    </div></div>
  </section>

  <section class="cat-close" id="cat-close">
    <div class="cat-pad"><div class="cat-container">
      <h2 class="cat-close__title">Happy with this selection?</h2>
      <p class="cat-close__sub">
        Send it back and we will come back with a full quote, deliverables and
        availability for each creator.
      </p>
      <div class="cat-close__actions">
        <button type="button" class="cat-btn cat-btn--lime" id="cat-request-2">Request a quote</button>
        <button type="button" class="cat-btn cat-btn--ghost" id="cat-copy-link">Copy link</button>
        <a class="cat-btn cat-btn--ghost" href="/catalogue/">Back to the catalogue</a>
      </div>
      <p class="cat-close__copied" id="cat-copied" role="status"></p>
    </div></div>
  </section>

  <footer class="cat-footer">
    <div class="cat-pad"><div class="cat-container">
      <img class="cat-footer__logo" src="/assets/helv/logo-knockout.webp"
           srcset="/assets/helv/logo-knockout@2x.webp 2x"
           alt="HelloVoice" width="760" height="166"/>
      <p class="cat-footer__note">
        Confidential and not for redistribution.
        Creator identities are released on agreement.
      </p>
      <a class="cat-footer__portfolio" href="https://hellovoice.co.uk" target="_blank" rel="noopener">
        See the portfolio at hellovoice.co.uk
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg>
      </a>
    </div></div>
  </footer>

  <div class="cat-tray" id="cat-tray" hidden>
    <div class="cat-tray__inner">
      <div class="cat-tray__count"><strong id="cat-tray-n">0</strong> in this selection</div>
      <div class="cat-tray__codes" id="cat-tray-codes"></div>
      <div class="cat-tray__actions">
        <button type="button" class="cat-btn cat-btn--lime" id="cat-request">Request a quote</button>
      </div>
    </div>
  </div>

  <div class="cat-modal" id="cat-modal" hidden role="dialog" aria-modal="true" aria-labelledby="cat-modal-title">
    <div class="cat-modal__panel">
      <button type="button" class="cat-modal__close" id="cat-modal-close" aria-label="Close">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>
      </button>
      <h2 class="cat-modal__title" id="cat-modal-title">Request a quote</h2>
      <p class="cat-modal__sub"><strong id="cat-modal-n">0</strong> creators selected</p>
      <p class="cat-note cat-note--modal">Prices are indicative ranges only. Final rates vary with campaign requirements, deliverables, exclusivity, seasonality and any special agreement, and are confirmed in the quote.</p>
      <form id="cat-form" class="cat-form" autocomplete="off">
        <label>Full name<input type="text" name="name" required/></label>
        <label>Company<input type="text" name="company" required/></label>
        <label>Email<input type="email" name="email" required/></label>
        <label>Phone<input type="tel" name="phone" required/></label>
        <button type="submit" class="cat-btn cat-btn--lime cat-form__submit">Send request</button>
        <p class="cat-form__status" id="cat-form-status" role="status"></p>
      </form>
    </div>
  </div>

</main>

<script>
  window.CATALOGUE_CONFIG = {{
    passHash: "{simple_hash(PASSCODE)}",
    endpoint: {json.dumps(ENDPOINT)}
  }};
</script>
<script src="{stamp('/assets/js/catalogue.js')}"></script>
</body>
</html>
"""
    selection = (selection
                 .replace("{clients_block}", clients_block)
                 .replace("{cards}", cards))
    OUT_SELECTION.parent.mkdir(parents=True, exist_ok=True)
    OUT_SELECTION.write_text(relativise(selection, 2), encoding="utf-8")

    print(f"cards          {len(people)}")
    print(f"with photos    {with_photos}  ({with_photos * 100 // max(len(people),1)}%)")
    print(f"tiers          {tier_counts}")
    print(f"private key    {OUT_PRIVATE.relative_to(ROOT)}")
    print(f"page           {OUT_HTML.relative_to(ROOT)}")
    print(f"selection page {OUT_SELECTION.relative_to(ROOT)}")
    print(f"passcode       {PASSCODE}")
    print(f"endpoint       {ENDPOINT or '(not configured — set CATALOGUE_ENDPOINT)'}")
    print(f"request email  {REQUEST_EMAIL}")
    print(f"client logos   {len(logos)}")
    if HAS_INTERESTS:
        print(f"interests      {len(set(p['interest'] for p in people))} values, filter shown")
    else:
        print("interests      NO DATA — filter hidden. Add content/interests.json")
        print("               as {\"HV-MD-014\": \"Hair Care\"} to enable it.")


def simple_hash(s):
    """Small non-cryptographic hash so the passcode is not sitting in the page
    as plain text. This is a lock on a glass door and is documented as such —
    it stops the link being casually forwarded, nothing more."""
    h = 5381
    for ch in s:
        h = ((h * 33) ^ ord(ch)) & 0xFFFFFFFF
    return format(h, "08x")


if __name__ == "__main__":
    build()
