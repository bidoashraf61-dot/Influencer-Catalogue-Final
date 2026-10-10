"""Admin pages for the quote lifecycle and for creating a campaign from a selection (fix batch 9).

    chip(key)                         the state pill
    quote_card(sel, back)             timeline + "Quote ready" form + "Create campaign" (selection page)
    request_strip(sel, back)          the compact version inside a request card (Requests inbox)
    setup_defaults(sel)               everything the campaign form is pre-filled with
    setup_page(sel, d, error)         the four-step "Create campaign" form

Internal tool: it follows the admin's own look (ink, lime, linen, pills) and stays quiet.
Everything the client sees about the quote comes from ``lifecycle.client_payload``.
"""
import json
import re

import db
import lifecycle
import ui
import views
from views import e, u, ts

PILL = {"draft": "", "requested": "warn", "ready": "own", "approved": "live", "live": "live", "completed": ""}

CSS = """<style>
.lc-pill{display:inline-flex;align-items:center;gap:6px}
.lc-pill.is-completed{background:#ece9e3;color:var(--ink);box-shadow:inset 0 0 0 1px var(--line-strong)}
.lc-line{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 14px}
.lc-tl{list-style:none;margin:0 0 4px;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.lc-tl li{border:1px solid var(--line);border-radius:var(--r-md);padding:10px 12px;background:var(--white);min-height:78px}
.lc-tl li.done{background:var(--green-soft);border-color:transparent}
.lc-tl li.current{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.lc-tl b{display:block;font-size:var(--t-sm)}
.lc-tl span{display:block;color:var(--muted);font-size:var(--t-xs);margin-top:2px}
.lc-form{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1.3fr) auto;gap:10px;align-items:end;margin-top:14px}
.lc-form label{display:block;font-size:var(--t-xs);font-weight:600;color:var(--gray);margin-bottom:4px}
.lc-form textarea{min-height:44px;height:44px;resize:vertical}
.lc-act{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.lc-strip{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}
.lc-strip details summary{cursor:pointer;font-weight:600;font-size:var(--t-sm)}
@media(max-width:760px){.lc-form{grid-template-columns:1fr}}
</style>"""


def chip(key):
    key = key if key in lifecycle.LABEL else "draft"
    return "<span class='pill dot lc-pill is-%s %s'>%s</span>" % (key, PILL[key], e(lifecycle.LABEL[key]))


def _timeline(lc):
    items = []
    for s in lc["steps"]:
        when = ts(s["at"]) if s["at"] else ("Now" if s["state"] == "current" else "Not yet")
        by = (" · " + e(s["by"])) if s["by"] and s["at"] else ""
        items.append("<li class='%s'><b>%s</b><span>%s%s</span></li>" % (s["state"], e(s["label"]), when, by))
    return "<ol class='lc-tl' aria-label='Quote timeline'>" + "".join(items) + "</ol>"


def _ready_form(sel, lc, back):
    if not lc["can_mark_ready"]:
        return ""
    ready = lc["key"] == "ready"
    return (
        "<form method='post' action='" + u("/quote/ready") + "' class='lc-form'>"
        "<input type='hidden' name='id' value='" + str(sel["id"]) + "'><input type='hidden' name='back' value='" + e(back) + "'>"
        "<div><label for='q-note-" + str(sel["id"]) + "'>Note the client sees (optional)</label>"
        "<textarea id='q-note-" + str(sel["id"]) + "' name='note' maxlength='500' placeholder='e.g. Includes 4 reels and usage rights for 3 months'>"
        + e(lc.get("note") or "") + "</textarea></div>"
        "<div><label for='q-link-" + str(sel["id"]) + "'>Quote PDF or link (optional, https)</label>"
        "<input id='q-link-" + str(sel["id"]) + "' name='link' type='url' maxlength='300' placeholder='https://…' value='" + e(lc.get("link") or "") + "'></div>"
        "<button class='btn small lime'>" + ("Update quote note" if ready else "Mark quote ready") + "</button></form>"
        "<p class='price-hint'>The client is told on their bell, never by email. They see only this note and link: "
        "no prices come from here unless you write them.</p>")


def quote_card(sel, back):
    lc = lifecycle.admin_payload(sel)
    warn = ("<div class='err' style='margin:0 0 12px'>The client changed the creators after the quote was marked ready. "
            "Check the quote still fits.</div>") if lc["changed_after_ready"] else ""
    changes = ""
    if lc["changes"]:
        changes = ("<p class='muted' style='margin:10px 0 0'>Changed after the request: " + "; ".join(
            "%s on %s (+%d, −%d)" % (e(c["by"] or "The client"), ts(c["at"]), c["added"], c["removed"]) for c in lc["changes"][:3]) + ".</p>")
    camps = "".join("<li><a href='" + u("/campaigns/edit") + "?id=%d'>%s</a> %s</li>" % (k["id"], e(k["name"]), views.status_pill(k["status"]))
                    for k in lc["campaigns"])
    actions = ""
    if lc["can_withdraw"]:
        actions += ("<form method='post' action='" + u("/quote/withdraw") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                    "<input type='hidden' name='back' value='%s'><button class='btn small ghost'>Take back “Quote ready”</button></form>" % (sel["id"], e(back)))
    if lc["can_create_campaign"]:
        label = "Create another campaign" if lc["campaigns"] else "Create campaign"
        actions += ("<a class='btn small' href='" + u("/campaigns/setup") + "?selection=%d'>" % sel["id"] + ui.icon("plus", 15) + " " + label + "</a>")
    return (CSS + "<div class='card'><div class='hd'><h2>Quote</h2></div>"
            "<div class='lc-line'>" + chip(lc["key"]) + "<span class='muted'>This is the chip the client sees on their selection, list and profile.</span></div>"
            + warn + _timeline(lc) + changes + _ready_form(sel, lc, back)
            + ("<div class='lc-act'>" + actions + "</div>" if actions else "")
            + ("<ul style='margin:12px 0 0'>" + camps + "</ul>" if camps else "")
            + ("" if lc["can_create_campaign"] else "<p class='muted' style='margin:12px 0 0'>Create campaign unlocks once a quote has been requested.</p>")
            + "</div>")


def request_strip(sel, back):
    """Inside a request card: the selection's state and a way to set Quote ready."""
    if sel is None:
        return ("<div class='lc-strip'><span class='muted'>Not priced yet. Use “Price &amp; send” first, then mark the quote ready here.</span></div>")
    lc = lifecycle.admin_payload(sel)
    link = u("/selections/edit") + "?id=%d#st=status" % sel["id"]
    inner = _ready_form(sel, lc, back) if lc["can_mark_ready"] else ""
    extra = ""
    if lc["can_withdraw"]:
        extra = ("<form method='post' action='" + u("/quote/withdraw") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                 "<input type='hidden' name='back' value='%s'><button class='btn small ghost'>Take back</button></form>" % (sel["id"], e(back)))
    return (CSS + "<div class='lc-strip'><div class='lc-line' style='margin:0'><strong>Quote status</strong> " + chip(lc["key"])
            + " <a class='btn small ghost' href='" + link + "'>Open selection</a> " + extra + "</div>"
            + ("<details style='margin-top:10px'" + (" open" if lc["key"] == "requested" else "") + "><summary>"
               + ("Update the note the client sees" if lc["key"] == "ready" else "Mark quote ready")
               + "</summary>" + inner + "</details>" if inner else "")
            + "</div>")


# --------------------------------------------------------- create campaign --

GOALS = [("awareness", "Awareness", "Views and reach"), ("engagement", "Engagement", "Likes, comments, saves"),
         ("traffic", "Traffic", "Clicks on a link")]


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())[:30]


def setup_defaults(sel):
    """Pre-fill for the form: the selection and its brief, nothing invented."""
    import metrics
    import selstatus
    with db.connect() as conn:
        br = conn.execute("SELECT answers FROM briefs WHERE selection_id = ? AND deleted_at IS NULL ORDER BY id DESC LIMIT 1",
                          (sel["id"],)).fetchone()
    try:
        ans = json.loads(br["answers"] or "{}") if br is not None else {}
    except ValueError:
        ans = {}
    goals = metrics.brief_goals(sel["id"])
    plats = ans.get("platforms") or []
    plats = [p for p in (plats if isinstance(plats, list) else [plats]) if p in db.PLATFORMS]
    if not plats and sel["platform"] in db.PLATFORMS:
        plats = [sel["platform"]]
    code = db.get_code(sel["code_id"]) if sel["code_id"] else None
    keys = sel.keys()
    import portal
    owner = portal.user_for_code(sel["code_id"]) if sel["code_id"] else None
    # The name HelloVoice set on the selection, else the owner's company (a portal account's access
    # code is labelled with their email), else the access code's label.
    client = ((sel["client_name"] if "client_name" in keys else None)
              or (owner["company"] if owner is not None and owner["company"] else None)
              or (code["label"] if code else "") or "")
    codes = json.loads(sel["codes"] or "[]")
    status = selstatus.of(sel["id"])
    approved = [c for c in codes if (status.get(c) or {}).get("s") == "approved"]
    usable = [c for c in codes if (status.get(c) or {}).get("s") not in ("rejected", "unavailable")]
    chosen = approved or usable
    slug = _slug(client or sel["name"])
    return {
        "name": sel["name"], "client": client, "code_label": code["label"] if code else "",
        "platforms": plats, "goals": goals, "objective": metrics.blend_key(goals) or "balanced",
        "codes": codes, "chosen": chosen, "approved_n": len(approved),
        "status": {c: (status.get(c) or {}).get("s", "review") for c in codes},
        "rules": ("#" + slug) if slug else "", "disclosure": "#ad #إعلان",
        "destination": "", "starts": "", "ends": "", "notes": "",
        "costs": {k: v for k, v in json.loads((sel["costs"] if "costs" in keys else None) or "{}").items() if isinstance(v, int)},
        "has_brief": br is not None,
    }


_CSS_SETUP = """<style>
.cc-steps{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px;padding:0;list-style:none}
.cc-steps button{display:flex;align-items:center;gap:10px;border:1px solid var(--line-strong);background:var(--white);border-radius:999px;
 padding:6px 16px 6px 6px;font:600 var(--t-sm) "DM Sans",sans-serif;cursor:pointer;color:var(--gray);transition:background .15s,color .15s,border-color .15s}
.cc-steps .dot{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#ece9e3;color:var(--gray);font-size:var(--t-sm)}
.cc-steps button.is-now{color:var(--ink);border-color:var(--ink)}.cc-steps button.is-now .dot{background:var(--ink);color:var(--lime)}
.cc-steps button.is-done .dot{background:var(--green);color:#fff}
.cc-form .cc-step{display:none}.cc-form .cc-step.is-now,.cc-form:not(.js) .cc-step{display:block}
.cc-opts{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.cc-opt{position:relative}.cc-opt input{position:absolute;opacity:0;inset:0;cursor:pointer}
.cc-opt span{display:flex;flex-direction:column;border:1px solid var(--line-strong);border-radius:var(--r-md);padding:10px 16px;min-width:150px;background:var(--white);
 transition:background .15s,border-color .15s,transform .15s}
.cc-opt b{font-size:var(--t-md)}.cc-opt small{color:var(--muted);font-size:var(--t-xs)}
.cc-opt input:checked+span{background:var(--lime);border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.cc-opt input:focus-visible+span{outline:2px solid var(--ink);outline-offset:2px}
.cc-opt.pl span{min-width:0;padding:8px 16px}
.cc-from{display:inline-flex;gap:6px;align-items:center;font-size:var(--t-xs);color:var(--muted);margin-top:8px}
.cc-people{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px;margin-top:10px}
.cc-who{position:relative;display:flex;gap:10px;align-items:center;border:1px solid var(--line);border-radius:var(--r-md);padding:8px 10px;background:var(--white)}
.cc-who input{position:absolute;opacity:0;inset:0;cursor:pointer;margin:0}
.cc-who:has(input:checked){background:var(--green-soft);border-color:transparent}
.cc-who:has(input:focus-visible){outline:2px solid var(--ink);outline-offset:2px}
.cc-who .tick{margin-left:auto;width:22px;height:22px;border-radius:50%;border:1.5px solid var(--line-strong);display:grid;place-items:center;flex:none}
.cc-who input:checked~.tick{background:var(--green);border-color:var(--green);color:#fff}
.cc-who small{display:block;color:var(--muted);font-size:var(--t-xs)}
.cc-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px}
.cc-nav{display:flex;justify-content:space-between;gap:10px;margin-top:18px;flex-wrap:wrap}
.cc-sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:6px}
.cc-sum div{border:1px solid var(--line);border-radius:var(--r-md);padding:10px 12px;background:var(--bg)}
.cc-sum dt{font-size:var(--t-xs);color:var(--muted);font-weight:600}.cc-sum dd{margin:2px 0 0;font-weight:600;overflow-wrap:anywhere}
.cc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
@media(prefers-reduced-motion:reduce){.cc-opt span,.cc-steps button{transition:none}}
</style>"""

_JS_SETUP = """<script>
(function(){
  var f=document.getElementById('cc-form'); if(!f) return;
  f.classList.add('js');
  var steps=[].slice.call(f.querySelectorAll('.cc-step')), tabs=[].slice.call(document.querySelectorAll('.cc-steps button')), at=0, seen={0:1};
  function val(n){var el=f.elements[n]; return el?el.value.trim():'';}
  function checked(n){return [].slice.call(f.querySelectorAll('input[name="'+n+'"]:checked'));}
  function lab(el){return el.getAttribute('data-label')||el.value;}
  function sum(){
    var goals=checked('goal').map(lab), pl=checked('platform').map(lab), n=checked('code').length;
    var o={name:val('name')||'—',client:val('client')||'—',pl:pl.length?pl.join(', '):'Every platform',
      goals:goals.length?goals.join(' + '):'Balanced',n:n+' creator'+(n===1?'':'s'),
      rules:[val('rules'),val('disclosure')].filter(Boolean).join('  ·  ')||'—',
      dates:(val('starts')||'No start yet')+' to '+(val('ends')||'no end yet')};
    [].forEach.call(document.querySelectorAll('[data-sum]'),function(el){el.textContent=o[el.getAttribute('data-sum')];});
    var c=document.getElementById('cc-count'); if(c) c.textContent=o.n;
  }
  function show(i){
    at=Math.max(0,Math.min(steps.length-1,i)); seen[at]=1;
    steps.forEach(function(s,k){s.classList.toggle('is-now',k===at);});
    tabs.forEach(function(t,k){t.classList.toggle('is-now',k===at);t.classList.toggle('is-done',k!==at&&!!seen[k]);t.setAttribute('aria-current',k===at?'step':'false');});
    sum(); var h=steps[at].querySelector('h2'); if(h){h.setAttribute('tabindex','-1');h.focus({preventScroll:true});}
    window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion:reduce)').matches?'auto':'smooth'});
  }
  document.addEventListener('click',function(ev){
    var t=ev.target.closest('[data-go],[data-pick]'); if(!t) return;
    if(t.hasAttribute('data-go')){ev.preventDefault();
      if(t.getAttribute('data-go')==='next'&&at===0&&!val('name')){f.elements.name.focus();f.elements.name.reportValidity&&f.elements.name.reportValidity();return;}
      show(t.getAttribute('data-go')==='next'?at+1:t.getAttribute('data-go')==='prev'?at-1:+t.getAttribute('data-go'));}
    else{ev.preventDefault();var m=t.getAttribute('data-pick'),boxes=[].slice.call(f.querySelectorAll('input[name="code"]'));
      boxes.forEach(function(b){b.checked=m==='all'?b.getAttribute('data-live')==='1':m==='approved'?b.getAttribute('data-st')==='approved':false;});sum();}
  });
  f.addEventListener('change',sum); f.addEventListener('input',sum);
  f.addEventListener('submit',function(ev){
    if(!checked('code').length){ev.preventDefault();show(1);var m=document.getElementById('cc-none');if(m){m.hidden=false;}}
  });
  show(0);
})();
</script>"""


def setup_page(sel, d, error=None):
    by = {c["code"]: c for c in db.list_creators()}
    st_label = {"approved": "Approved", "review": "Under review", "rejected": "Rejected", "unavailable": "Unavailable"}
    people = []
    for code in d["codes"]:
        c = by.get(code)
        if c is None:
            continue
        shot = ("<img class='thumb sm' src='" + e(__import__("links").thumb(c["photo"])) + "' alt='' width='40' height='40' loading='lazy'>"
                if c["photo"] else "<span class='thumb sm none'>—</span>")
        s = d["status"].get(code, "review")
        live = "0" if s in ("rejected", "unavailable") else "1"
        people.append(
            "<label class='cc-who'><input type='checkbox' name='code' value='" + e(code) + "' data-st='" + s + "' data-live='" + live + "'"
            + (" checked" if code in d["chosen"] else "") + ">" + shot
            + "<span><b>" + e(c["name"]) + "</b><small>" + e(c["tier"] or "—") + " · " + ui.compact(c["followers"]) + " · " + st_label.get(s, s) + "</small></span>"
            "<span class='tick' aria-hidden='true'>" + ui.icon("check", 14) + "</span></label>")
    goal_opts = "".join(
        "<label class='cc-opt'><input type='checkbox' name='goal' value='%s' data-label='%s'%s><span><b>%s</b><small>%s</small></span></label>"
        % (k, lbl, " checked" if k in d["goals"] else "", lbl, hint) for k, lbl, hint in GOALS)
    plat_opts = "".join(
        "<label class='cc-opt pl'><input type='checkbox' name='platform' value='%s' data-label='%s'%s><span><b>%s</b></span></label>"
        % (p, p, " checked" if p in d["platforms"] else "", p) for p in ("Instagram", "TikTok", "Snapchat", "YouTube"))
    src_goal = ("From the client's brief" if d["goals"] else "No goal in the brief yet: Balanced") if d["has_brief"] else "No brief on file: pick the goals"
    note = "<div class='err'>" + e(error) + "</div>" if error else ""
    nxt = "<button type='button' class='btn lime' data-go='next'>Next " + ui.icon("arrow", 16) + "</button>"
    prev = "<button type='button' class='btn ghost' data-go='prev'>Back</button>"
    body = (
        _CSS_SETUP
        + ui.header("Create campaign", "Pre-filled from “" + e(sel["name"]) + "” and its brief. It is saved as a draft: nothing is visible to the client until you set it live.",
                    crumbs=[("Selections", u("/selections")), (sel["name"], u("/selections/edit") + "?id=%d" % sel["id"]), ("Create campaign", None)])
        + note
        + "<ol class='cc-steps' aria-label='Steps'>"
        + "".join("<button type='button' data-go='%d'%s><span class='dot'>%d</span>%s</button>" % (i, "", i + 1, lbl)
                  for i, lbl in enumerate(("Basics", "Creators", "Tracking", "Review")))
        + "</ol>"
        + "<form method='post' action='" + u("/campaigns/setup") + "' id='cc-form' class='cc-form'>"
        + "<input type='hidden' name='selection' value='%d'>" % sel["id"]
        # 1 Basics
        + "<section class='card cc-step is-now'><h2>Basics</h2>"
          "<div class='row'><div style='flex:2'><label for='cc-name'>Campaign name</label><input id='cc-name' name='name' required maxlength='120' value='" + e(d["name"]) + "'></div>"
          "<div><label for='cc-client'>Client</label><input id='cc-client' name='client' maxlength='120' value='" + e(d["client"]) + "'></div></div>"
          "<p class='price-hint'>" + ("Filed under the client code <b>" + e(d["code_label"]) + "</b>, so their report opens under that code." if d["code_label"]
                                       else "<b>No client code is attached to this selection.</b> Attach one on the campaign before going live.") + "</p>"
          "<label style='margin-top:16px'>Platforms</label><div class='cc-opts'>" + plat_opts + "</div>"
          "<p class='price-hint'>Pick one to track a single platform, or several to track them all."
          + (" Taken from the brief." if d["platforms"] else "") + "</p>"
          "<label style='margin-top:16px'>What the campaign is for</label><div class='cc-opts'>" + goal_opts + "</div>"
          "<span class='cc-from'>" + ui.icon("check", 14) + e(src_goal) + ". Several goals become a blend the report scores against.</span>"
          "<div class='cc-nav'><span></span>" + nxt + "</div></section>"
        # 2 Creators
        + "<section class='card cc-step'><h2>Creators</h2>"
          "<p class='sec-desc'>" + (("%d approved by the client are ticked." % d["approved_n"]) if d["approved_n"]
                                    else "Nobody is approved yet, so everyone not rejected is ticked.")
          + " Their costs are carried over from the selection.</p>"
          "<div class='cc-bar'><button type='button' class='btn small ghost' data-pick='approved'>Approved only</button>"
          "<button type='button' class='btn small ghost' data-pick='all'>All not rejected</button>"
          "<button type='button' class='btn small ghost' data-pick='none'>None</button>"
          "<span class='muted' id='cc-count'></span></div>"
          "<p class='err' id='cc-none' hidden>Tick at least one creator.</p>"
          "<div class='cc-people'>" + ("".join(people) or "<p class='muted'>This selection has no creators.</p>") + "</div>"
          "<div class='cc-nav'>" + prev + nxt + "</div></section>"
        # 3 Tracking
        + "<section class='card cc-step'><h2>Tracking</h2>"
          "<p class='sec-desc'>How posts are found each day. A # word is a hashtag, an @ word a mention, anything else a keyword.</p>"
          "<div class='cc-grid'><div><label for='cc-rules'>Hashtags, mentions, keywords</label>"
          "<input id='cc-rules' name='rules' value='" + e(d["rules"]) + "' placeholder='#svr #suncare @svr_ksa sunscreen'>"
          "<div class='price-hint'>" + ("Suggested from the client name. Confirm the real campaign hashtag." if d["rules"] else "Add the campaign hashtag and the brand handle.") + "</div></div>"
          "<div><label for='cc-disc'>Required disclosure</label><input id='cc-disc' name='disclosure' value='" + e(d["disclosure"]) + "' placeholder='#ad #إعلان'>"
          "<div class='price-hint'>A post with none of these is flagged. Saudi rules ask for a clear ad label.</div></div></div>"
          "<div style='margin-top:14px'><label for='cc-dest'>Destination link (optional)</label>"
          "<input id='cc-dest' name='destination' type='url' placeholder='https://…'>"
          "<div class='price-hint'>A tracking link for each creator is created for you. Leave this empty if the campaign sends nobody anywhere.</div></div>"
          "<div class='cc-nav'>" + prev + nxt + "</div></section>"
        # 4 Dates and review
        + "<section class='card cc-step'><h2>Dates and review</h2>"
          "<div class='row'><div><label for='cc-start'>First day (optional)</label><input id='cc-start' name='starts' type='date'></div>"
          "<div><label for='cc-end'>Last day (optional)</label><input id='cc-end' name='ends' type='date'></div></div>"
          "<p class='price-hint'>Dates are needed before the campaign can go live. You can set them later on its Setup tab.</p>"
          "<div style='margin-top:14px'><label for='cc-notes'>Internal notes (optional)</label><textarea id='cc-notes' name='notes' maxlength='600' rows='2'></textarea></div>"
          "<h3 style='margin:20px 0 6px'>This is what will be created</h3>"
          "<dl class='cc-sum'><div><dt>Name</dt><dd data-sum='name'></dd></div><div><dt>Client</dt><dd data-sum='client'></dd></div>"
          "<div><dt>Platforms</dt><dd data-sum='pl'></dd></div><div><dt>Goals</dt><dd data-sum='goals'></dd></div>"
          "<div><dt>Creators</dt><dd data-sum='n'></dd></div><div><dt>Tracking</dt><dd data-sum='rules'></dd></div>"
          "<div><dt>Dates</dt><dd data-sum='dates'></dd></div><div><dt>Status</dt><dd>Draft, hidden from the client</dd></div></dl>"
          "<div class='cc-nav'>" + prev + "<button class='btn lime'>" + ui.icon("check", 16) + " Create draft campaign</button></div></section>"
        + "</form>" + _JS_SETUP
    )
    return views.page("Create campaign", body, "/campaigns")
