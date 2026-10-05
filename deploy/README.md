# Deployment

How this repo actually runs at **influencer-catalogue.hellovoice.co.uk**. The
application is the rest of this repo; this directory is only the wiring, kept
here so it is not lore living on one server's filesystem.

Two containers behind nginx-proxy-manager, both on the same hostname so the
catalogue's `/api/*` calls are same-origin and need no CORS:

| | |
|---|---|
| `catalogue/` | `nginx:alpine` serving the built pages, `127.0.0.1:1012` |
| `admin/` | the stdlib-Python dashboard and API, `127.0.0.1:8900`, at `/admin` |

`/admin` is an NPM **custom location** on the catalogue's proxy host, not a
second host — that is what makes the two same-origin.

## Three things that are load-bearing

Each is commented where it is set, because each has already broken once.

**1. The admin container is pinned to `172.18.0.240`.** nginx caches an
upstream's IP at config load. A restart that moved the container to a new IP
made `/admin` return 502 while the service itself was perfectly healthy, fixed
only by reloading NPM — and with `restart: always` that can happen unattended.

**2. `update.sh` must build with `CATALOGUE_API=/admin`.** Without it the build
silently reverts to the static page: 306KB with all 162 creator names and
handles in the source, and the roster gated by nothing but a client-side hash.
Same command, no error, completely different security posture.

**3. The asset tree is mounted read-only with `assets/catalogue` nested
writable.** `server.py` writes uploaded photos into the folder the live site
reads, so that one folder must be writable — but it also reads its own logo from
`site/assets/helv/`, so mounting *only* the photo folder leaves the dashboard's
logo 404ing while every page still renders.

## What is deliberately not here

- **`site/`** — the built document root, including 154 creator photos. Produced
  by `update.sh`; it is client data, not source.
- **`admin/catalogue.db`** and **`admin/.secret`** — every creator record and
  quote request, plus the HMAC signing key. Back the database up; never commit
  it.
- **`content/catalogue_private.json`** — the identity key, gitignored already.

## Standing one up

```bash
# catalogue
mkdir -p /home/ubuntu/influencer-catalogue/{conf,logs}
cp deploy/catalogue/docker-compose.yml  /home/ubuntu/influencer-catalogue/
cp deploy/catalogue/nginx-default.conf  /home/ubuntu/influencer-catalogue/conf/default.conf
cp deploy/catalogue/update.sh           /home/ubuntu/influencer-catalogue/
docker compose -f /home/ubuntu/influencer-catalogue/docker-compose.yml up -d

# admin — the code is copied from this repo, the database is created on first run
mkdir -p /home/ubuntu/influencer-catalogue-admin/{admin,content}
cp admin/*.py /home/ubuntu/influencer-catalogue-admin/admin/
cp deploy/admin/docker-compose.yml /home/ubuntu/influencer-catalogue-admin/
docker compose -f /home/ubuntu/influencer-catalogue-admin/docker-compose.yml up -d

# first admin, and the roster
docker exec -it influencer-catalogue-admin python3 /app/admin/seed.py --email you@hellovoice.co.uk
docker exec -i  influencer-catalogue-admin python3 /app/admin/seed.py --import-roster
```

`seed.py --import-roster` reads `content/catalogue_private.json`, which
`build/influencer_catalogue.py` regenerates from the workbook.


## Campaign tracker release (Oct 2026)

What changes on the server, in order:

1. **Admin code** — pull, then copy the Python files (new: `metrics.py`,
   `track.py`) and restart:

   ```bash
   git -C /home/ubuntu/influencer-catalogue-src pull
   cp /home/ubuntu/influencer-catalogue-src/admin/*.py /home/ubuntu/influencer-catalogue-admin/admin/
   sudo docker restart influencer-catalogue-admin
   ```

   The new tables are created on start; nothing existing is touched. Back up
   `catalogue.db` first anyway.
2. **nginx** — copy the updated `deploy/catalogue/nginx-default.conf` to
   `/home/ubuntu/influencer-catalogue/conf/default.conf`. It adds `/go/` and
   `/insights/`, proxied to the admin container at `172.18.0.240:8900`.
3. **Site** — run `update.sh`. It now also publishes `campaign/index.html` and
   stamps `campaign.js` / `campaign.css`. It ends with `nginx -s reload`,
   which picks up step 2.
4. **Check:** `https://influencer-catalogue.hellovoice.co.uk/go/nothing` shows
   "This link is not active" (served by the admin, so the proxy works);
   `/campaign/` shows the passcode gate; Admin shows Campaigns and Settings.
5. **Optional:** country lookup — `python3 admin/track.py --geo-build …`
   inside the admin folder (see `docs/ADMIN.md` §5b).
6. **Capture job:** Admin → Settings → Create token, then set up the Mac as in
   `docs/CAPTURE-AGENT.md`.
