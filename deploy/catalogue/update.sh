#!/usr/bin/env bash
# Publish the catalogue. The site is in API mode: the pages carry NO roster and
# fetch it from the admin service at /admin, so this only republishes the shell
# and the shared assets. Creator changes need no deploy at all — they are live
# the moment they are saved in the dashboard.
set -euo pipefail

SRC=/home/ubuntu/influencer-catalogue-src
DST=/home/ubuntu/influencer-catalogue/site

git -C "$SRC" fetch --depth 1 origin main
git -C "$SRC" reset --hard origin/main

# The builder needs the workbook to write content/catalogue_private.json. It is
# not in this repo — it lives in Influencer-Catalogue-2 — and is fetched once.
WB="$SRC/Influncer Proposal Catalogue/Alpha_Plus_influncers.xlsx"
if [ ! -f "$WB" ]; then
  mkdir -p "$SRC/Influncer Proposal Catalogue"
  curl -sL -o "$WB" \
    "https://raw.githubusercontent.com/bidoashraf61-dot/Influencer-Catalogue-2/main/Influncer%20Proposal%20Catalogue/Alpha_Plus_influncers.xlsx"
fi

# CATALOGUE_API is what strips the roster out of the pages. Without it the build
# silently reverts to the static one: 306KB with all 162 names in the source.
cd "$SRC"
CATALOGUE_API="/admin" python3 build/influencer_catalogue.py
python3 build/catalogue_dist.py

# Assets are rsynced from the repo; dist ships none, and the pages still point
# at assets/ for css, js, brand and the creator photos.
# NOTE: never --delete assets/catalogue — the dashboard writes uploaded photos
# straight into it, and they are not in git.
rsync -a --exclude 'catalogue' "$SRC/assets/" "$DST/assets/"
cp "$SRC/dist/index.html"           "$DST/index.html"
cp "$SRC/dist/selection/index.html" "$DST/selection/index.html"

sudo docker exec influencer-catalogue nginx -s reload

echo "published $(git -C "$SRC" rev-parse --short HEAD) (API mode)"
