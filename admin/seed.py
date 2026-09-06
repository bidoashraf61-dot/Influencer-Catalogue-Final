#!/usr/bin/env python3
"""Create the first admin and import the roster.

    python3 admin/seed.py --email you@hellovoice.co.uk
    python3 admin/seed.py --import-roster

The password is never passed as an argument — it would sit in your shell
history. It is prompted for, hidden, and checked before anything is written.
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import auth  # noqa: E402
import db  # noqa: E402

PRIVATE_KEY = ROOT / "content" / "catalogue_private.json"
PHOTO_DIR = ROOT / "site" / "assets" / "catalogue"


def add_admin(email):
    db.init()
    if db.admin_by_email(email):
        sys.exit("An admin with that email already exists.")

    while True:
        pw = getpass.getpass("New password: ")
        problems = auth.password_problems(pw)
        if problems:
            print("  " + "\n  ".join(problems))
            continue
        if pw != getpass.getpass("Confirm: "):
            print("  They do not match.")
            continue
        break

    db.create_admin(email, auth.hash_password(pw))
    print("Admin created: " + email)


def import_roster():
    """Load the roster from the private key file the static build already
    writes. That file holds the identity fields the public pages never carried,
    which is exactly what the database needs."""
    db.init()
    if not PRIVATE_KEY.exists():
        sys.exit("Missing " + str(PRIVATE_KEY) + " — run build/influencer_catalogue.py first.")

    data = json.loads(PRIVATE_KEY.read_text())
    order = {"Nano": 1, "Micro": 2, "Mid-Tier": 3, "Macro": 4}
    n = 0
    for i, (code, v) in enumerate(sorted(
            data.items(), key=lambda kv: (order.get(kv[1]["tier"], 9), -(kv[1]["followers"] or 0)))):
        photo = code + ".jpg"
        db.upsert_creator({
            "code": code,
            "name": v["name"],
            "handle": v.get("handle") or None,
            "platform": v["platform"],
            "followers": v.get("followers"),
            "city": v.get("city"),
            "tier": v["tier"],
            "interest": None,
            "photo": photo if (PHOTO_DIR / photo).exists() else None,
            "active": 1,
            "note": None,
            "sort": i,
        })
        n += 1

    have = sum(1 for c in db.list_creators() if c["photo"])
    print("Imported " + str(n) + " creators (" + str(have) + " with a photo).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", help="create an admin with this email")
    ap.add_argument("--import-roster", action="store_true",
                    help="load creators from content/catalogue_private.json")
    args = ap.parse_args()

    if not args.email and not args.import_roster:
        ap.print_help()
        return
    if args.email:
        add_admin(args.email.strip().lower())
    if args.import_roster:
        import_roster()


if __name__ == "__main__":
    main()
