#!/usr/bin/env python3
"""Generate assets/demo/demo-roster.json: the tour's fixed demo roster (tour v3, item 40).

The onboarding tour plays the real portal pages on demo data. The demo creators are INVENTED
people with REALISTIC numbers: follower counts, engagement, audience splits and score parts are
drawn from the shape of the real roster (the distributions the catalogue's own benchmarks
describe: nano under 20K, micro 20-100K, mid 100-500K, macro 500K-1M; Instagram reel view rate
10-20 %; engagement 3-8 % on small accounts falling to 1.5-4 % on large ones; Saudi audiences
70-85 % in KSA). Nothing here is read from the database or from any private catalogue file, and
this repository is public: no real creator name, handle or photo appears.

The generator is deterministic (fixed seed) so the file is reviewable; the photos are the eight
AI-generated portraits in assets/demo/ (not real people).

    python3 tools/gen_demo_roster.py          # rewrites assets/demo/demo-roster.json
    python3 tools/gen_demo_roster.py --check  # exits 1 when the committed file is out of date
"""
import json
import random
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "demo" / "demo-roster.json"
SEED = 20261011

# The only names the demo may use. The test suite asserts the generated roster stays inside these sets.
INVENTED_NAMES = ("Lulwa R.", "Dr. Adel K.", "Maha S.", "Tariq B.", "Nada H.", "Dr. Ghada M.", "Yousef O.", "Rana A.")
BRANDS = ("Velora Skin", "Sahar Beauty", "Dune Café", "Oasis Pharmacy", "Mira Home", "Nimbus Gym", "Zaha Kids", "Qamar Wear")

# code, name, handle, catalogue tier, city, interest, photo, platforms [(platform, base followers, post ER %)],
# licence countries, price band (SAR, the roster shape), audience women %, KSA share %, posts measured,
# score parts (engagement, reach, audience) 0..1, objective-fit notes
PEOPLE = [
    ("DEMO-01", "Lulwa R.", "lulwa.r.glow27", "Macro", "Riyadh", "Beauty & skincare", 1,
     [("Instagram", 612000, 4.1), ("TikTok", 241000, 6.3)], ["SA"], (6500, 9000), 71, 78, 24, (0.88, 0.95, 0.92)),
    ("DEMO-02", "Dr. Adel K.", "dr.adel.k.clinic", "HCP - Mid-Tier", "Jeddah", "Health", 2,
     [("Instagram", 188000, 5.2), ("Snapchat", 64000, 3.4)], ["SA"], (5000, 7000), 48, 81, 22, (0.90, 0.70, 0.74)),
    ("DEMO-03", "Maha S.", "maha.s.sips44", "Mid-Tier", "Riyadh", "Food & cafés", 3,
     [("TikTok", 204000, 3.7), ("Snapchat", 120000, 2.9)], ["SA"], (3000, 4500), 64, 74, 7, (0.74, 0.74, 0.64)),
    ("DEMO-04", "Tariq B.", "tariq.b.move19", "Nano", "Dammam", "Fitness", 4,
     [("Instagram", 14800, 7.9), ("TikTok", 9400, 6.1)], [], (600, 900), 38, 83, 21, (0.93, 0.50, 0.46)),
    ("DEMO-05", "Nada H.", "nada.h.noor08", "Mid-Tier", "Riyadh", "Parenting", 5,
     [("Instagram", 151000, 4.4), ("Snapchat", 88000, 3.1)], ["SA", "AE"], (3500, 5000), 68, 70, 19, (0.82, 0.72, 0.80)),
    ("DEMO-06", "Dr. Ghada M.", "dr.ghada.m.derm", "HCP - Mid-Tier", "Riyadh", "Dermatology", 6,
     [("Instagram", 273000, 5.6), ("TikTok", 96000, 4.8)], ["SA"], (6000, 8000), 74, 83, 26, (0.90, 0.78, 0.93)),
    ("DEMO-07", "Yousef O.", "yousef.o.drive31", "Macro", "Riyadh", "Cars", 7,
     [("Snapchat", 530000, 2.9), ("YouTube", 210000, 2.2)], ["SA"], (7000, 10000), 22, 76, 18, (0.55, 0.96, 0.18)),
    ("DEMO-08", "Rana A.", "rana.a.palette52", "Micro", "Jeddah", "Makeup", 8,
     [("Instagram", 39200, 8.1), ("TikTok", 52400, 6.7)], [], (1000, 1600), 83, 72, 6, (0.88, 0.62, 0.80)),
]
OBJECTIVE_W = (0.40, 0.25, 0.35)       # the engagement-led brief: engagement, reach, measured audience
AGES = ("13-17", "18-24", "25-34", "35-44", "45-64")
SKINCARE_FIT = {"DEMO-01": 1.0, "DEMO-02": 0.6, "DEMO-03": 0.2, "DEMO-04": 0.1, "DEMO-05": 0.5, "DEMO-06": 1.0, "DEMO-07": 0.0, "DEMO-08": 0.8}


def jitter(rng, base, spread):
    return int(round(base * (1 + rng.uniform(-spread, spread))))


def build():
    rng = random.Random(SEED)
    people = []
    for (code, name, handle, tier, city, interest, photo, plats, lic, price, women, ksa, posts, parts) in PEOPLE:
        eng, reach, aud = parts
        score = int(round(100 * (OBJECTIVE_W[0] * eng + OBJECTIVE_W[1] * reach + OBJECTIVE_W[2] * aud)))
        platforms = []
        for p, f0, er in plats:
            f = jitter(rng, f0, 0.012)
            er_p = round(er + rng.uniform(-0.15, 0.15), 1)
            views_rate = {"Instagram": 0.24, "TikTok": 0.42, "Snapchat": 0.16, "YouTube": 0.09}[p] * rng.uniform(0.85, 1.15)
            avg_views = int(round(f * views_rate))
            platforms.append({"platform": p, "followers": f, "er": er_p, "avg_views": avg_views,
                              "median_views": int(round(avg_views * rng.uniform(0.74, 0.86))), "posts": posts})
        top = platforms[0]
        # ages in the order of AGES: 13-17 small, 18-24, 25-34 largest, 35-44, 45-64
        raw = [rng.uniform(1.5, 4.0), rng.uniform(22, 32), rng.uniform(36, 48), rng.uniform(13, 21), rng.uniform(3, 9)]
        tot = sum(raw)
        ages = [round(x / tot * 100, 1) for x in raw]
        other = [("AE", 6.4), ("KW", 3.9), ("EG", 3.1), ("BH", 1.8), ("QA", 1.5)]
        rest = 100.0 - ksa
        countries = [{"code": "SA", "pct": float(ksa)}] + [{"code": c, "pct": round(rest * w / sum(x[1] for x in other), 1)} for c, w in other]
        fake = round(rng.uniform(3.5, 9.5), 1)
        spend_note = "above" if top["er"] >= 3.5 else "near"
        strengths, watchouts, checks = [], [], []
        strengths.append("%.1f%% engagement, %s the typical for creators this size" % (top["er"], spend_note))
        if women >= 65:
            strengths.append("%d%% of the measured audience are women" % women)
        if "HCP" in tier:
            strengths.append("A doctor: a trusted voice for health claims")
        if SKINCARE_FIT[code] >= 0.8:
            strengths.append("Works in the skincare space")
        if women < 50:
            watchouts.append("Audience is %d%% men" % (100 - women))
        if SKINCARE_FIT[code] <= 0.2:
            watchouts.append("Little sign of skincare content or audience interest")
        if women < 30:
            watchouts.append("Only %d%% of the audience are women" % women)
        if posts < 10:
            watchouts.append("Only %d recent posts to read: treat the numbers as a first look" % posts)
        checks.append({"label": "Measured audience", "text": "%d%% of the measured audience is in Saudi Arabia" % ksa,
                       "level": "ok" if ksa >= 70 else "warn"})
        checks.append({"label": "Gender", "text": "%d%% of the audience are women" % women,
                       "level": "ok" if women >= 60 else "warn" if women >= 40 else "bad"})
        level = "high" if posts >= 20 else "medium" if posts >= 10 else "low"
        people.append({
            "code": code, "name": name, "handle": handle, "tier": tier, "city": city, "interest": interest, "photo": photo,
            "nationality": "Saudi", "platforms": platforms, "licences": lic, "price": list(price),
            "score": {"overall": score, "parts": {"engagement": eng, "reach": reach, "audience": aud},
                      "confidence": {"level": level, "posts": posts, "peers_n": 40 if level != "low" else 9, "source": "peers" if level != "low" else "global"},
                      "limited_data": level == "low", "strengths": strengths[:3], "watchouts": watchouts[:2], "checks": checks},
            "audience": {"female": women, "male": 100 - women, "ages": [{"name": a, "pct": v} for a, v in zip(AGES, ages)],
                         "countries": countries,
                         "cities": [{"name": city, "pct": round(rng.uniform(28, 38), 1)}, {"name": "Jeddah" if city != "Jeddah" else "Riyadh", "pct": round(rng.uniform(14, 20), 1)},
                                    {"name": "Dammam", "pct": round(rng.uniform(6, 10), 1)}, {"name": "Mecca", "pct": round(rng.uniform(3, 5), 1)},
                                    {"name": "Medina", "pct": round(rng.uniform(2, 4), 1)}],
                         "languages": [{"name": "Arabic", "pct": 74.5}, {"name": "English", "pct": 22.8}, {"name": "Other", "pct": 2.7}]},
            "authenticity": {"fake_followers_pct": fake, "fake_likers_pct": round(fake * 0.75, 1), "real_people_pct": round(100 - fake * 2.6, 1),
                             "mass_followers_pct": round(rng.uniform(7, 13), 1), "suspicious_pct": fake, "notable_followers_pct": round(rng.uniform(1.4, 3.2), 1)},
            "growth_pct": round(rng.uniform(1.2, 4.1), 1), "posts_per_week": round(rng.uniform(3.2, 6.1), 1),
            "brands": [BRANDS[(int(code[-2:]) + k) % len(BRANDS)] for k in range(3)],
        })
    return {"version": "t3a", "brand": "Northwind Pharma", "campaign": "Ramadan Skincare", "invented_names": list(INVENTED_NAMES),
            "brands": list(BRANDS), "people": people}


def main(argv):
    text = json.dumps(build(), ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    if "--check" in argv:
        return 0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1
    OUT.write_text(text, encoding="utf-8")
    print("wrote", OUT.relative_to(OUT.parents[2]), len(text), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
