#!/usr/bin/env bash
# Publish the catalogue. The site is in API mode: the pages carry NO roster and
# fetch it from the admin service at /admin, so this only republishes the shell
# and the shared assets. Creator changes need no deploy at all — they are live
# the moment they are saved in the dashboard.
set -euo pipefail

SRC=/home/ubuntu/influencer-catalogue-src
DST=/home/ubuntu/influencer-catalogue/site

# The remote is SSH so this box can push as well as pull; the deploy key is
# repo-scoped and lives here. Without this git falls back to the agent and
# fails with "Permission denied (publickey)".
export GIT_SSH_COMMAND="ssh -o IdentitiesOnly=yes -i /home/ubuntu/.ssh/github_influencer_catalogue"

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

# The client logo carousel is not authored here: client_logos() scrapes the
# built HelloVoice homepage for its client_banner_section, and returns an EMPTY
# LIST if that file is absent — no error, the banner just silently disappears
# from the page. The homepage lives in Influencer-Catalogue-2, not this repo,
# so fetch it before every build.
mkdir -p "$SRC/site"
curl -sL -o "$SRC/site/index.html" \
  "https://raw.githubusercontent.com/bidoashraf61-dot/Influencer-Catalogue-2/main/site/index.html"

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

# The banner failing is silent by design upstream, so check it here.
LOGOS=$(grep -o 'cat-clients__logo' "$DST/index.html" | wc -l)
if [ "$LOGOS" -lt 2 ]; then
  echo "WARNING: client logo carousel is empty — site/index.html was probably not fetched" >&2
fi

sudo docker exec influencer-catalogue nginx -s reload

echo "published $(git -C "$SRC" rev-parse --short HEAD) (API mode)"
