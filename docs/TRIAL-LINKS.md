# Trial share links (item 271)

Agreed with Bido by multiple choice on 28 October 2026. A prospect opens one link and walks through the whole
portal as the **BlueHolding demo company** (Helvi Selection, Track and Intelligence, all at manage), with no
sign-in and demo data only.

## What Bido decided

| Question | Answer |
|---|---|
| What a link opens | The whole demo workspace; free navigation across all three modules. `?to=/page` lands on one page first |
| Sign-in | None. Each link is named for its client; visits are counted per link |
| Lifetime | 14 days by default, extend / reset / end from the admin |
| Actions | Sandboxed: each link has its own copy of the demo; AI, Apify, email and push are off |
| Creators | Only those in the demo selection, campaign and evidence pack; no prices, costs, margins or notes; no roster total |
| Demo data | Demo Campaign (9), its selection (81), its evidence pack (5), three sample competitors |
| Name | The client named on the link greets the visitor and names the reports |
| Talk to HelloVoice | A short form; requests appear on Demo links and the team is emailed |

## How it works

- **Admin › Tenants › Demo links** (`/admin/tenants/trials`, owners): make, copy, +14 days, reset data, end now;
  visits, last seen, requests.
- **`/admin/try/<token>`** sets the signed `hv_trial` cookie (plus `hv_trial_on`, readable by the page so
  `app.js` loads `assets/js/trial.js`) and lands on `/workspace/`. HelloVoice staff signed in to the admin see a
  note instead: staff are never a trial visitor, so open the link in a private window.
- **The trial process.** `server.py` starts a second copy of itself (`--trial`, `HV_TRIAL=1`, 127.0.0.1:8901)
  and keeps it running. Every request carrying a valid trial cookie and no admin session is forwarded to it with
  the link id. That process opens only `admin/trial/` databases (`db.use_path`, inherited by threads it starts),
  refuses every outbound connection, has no admin session, sees the visitor as the demo company's owner, answers
  only `/api/*`, `/go/` and `/insights/`, and accepts only the POSTs in `trial.POST_OK` (the rest answer
  `403 {reason: "trial"}`, which the banner shows as a note).
- **Data.** `admin/trial/template.db` is built by `tools/trial_template.py` from a copy of the live database:
  a whitelist keeps the demo rows, every other table is emptied (a table added later starts empty in a trial).
  `admin/trial/links/<id>.db` is a link's copy, made on its first visit and deleted a day after it ends.
  Neither is in git.

## Rebuild the template (after the demo campaign or selection changes)

```bash
ssh AWS
W=/home/ubuntu/trial-build-$(date +%F); mkdir -p $W
A=/home/ubuntu/influencer-catalogue-admin/admin
cp /home/ubuntu/influencer-catalogue-src/tools/trial_template.py $W/
sudo docker run --rm --network none --memory 600m --user 1000:1000 -v $A:/src -v $W:/w python:3.11-alpine \
  python3 -c "import sqlite3;s=sqlite3.connect('file:/src/catalogue.db?mode=ro',uri=True);d=sqlite3.connect('/w/snap.db');s.backup(d)"
sudo docker run --rm --network none --memory 600m --user 1000:1000 -v $W:/w python:3.11-alpine \
  python3 /w/trial_template.py /w/snap.db /w/template.db
sudo cp $W/template.db $A/trial/template.db && rm -rf $W
```

New links use it at once. Existing links keep their copy until **Reset data**.

## Open

- A second, finished demo campaign (to show a closing report) is not built yet.
- A per-link logo is not offered yet (the name is).
