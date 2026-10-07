"""Admin pages for the client portal: accounts, briefs, AI usage, settings, and the copilot.

Server-rendered like the rest of the dashboard: every value goes through ``e()``,
every change is a plain form posting to ``/portal/...``.
"""
import json

import db
import gemini
import mailer
import portal
import ui
from views import ago, e, page, ts, u

TABS = [("accounts", "Client accounts"), ("briefs", "Briefs"), ("usage", "AI usage"), ("settings", "Settings & keys")]


def _banner(ok, err):
    return (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")


def _tabs(current):
    return [(u("/portal?tab=" + k), label, None, k == current) for k, label in TABS]


def _stat(label, value, sub=""):
    return ("<div class='stat'><span class='k'>%s</span><b class='v'>%s</b>%s</div>"
            % (e(label), e(value), ("<span class='muted'>" + e(sub) + "</span>") if sub else ""))


STAT_CSS = ("<style>.pstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 18px}"
            ".pstats .stat{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;display:flex;flex-direction:column;gap:2px}"
            ".pstats .k{font-size:12px;color:var(--gray);text-transform:uppercase;letter-spacing:.06em}"
            ".pstats .v{font-size:26px;font-family:'Bebas Neue',sans-serif;letter-spacing:.02em}"
            ".fgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}"
            "textarea.mono{font-family:ui-monospace,monospace;font-size:13px;min-height:90px;width:100%}</style>")


def _status_pill(s):
    cls = {"active": "live", "pending": "warn", "suspended": "dead"}.get(s, "")
    return "<span class='pill %s'>%s</span>" % (cls, e(s))


# ---------------------------------------------------------------- accounts --

def _accounts_tab():
    users = portal.list_users()
    week = db.now() - 7 * 86400
    pending = [x for x in users if x["status"] == "pending"]
    outstanding = sum((x["credits"] or 0) for x in users)
    stats = ("<div class='pstats'>" + _stat("Clients", len(users)) + _stat("Awaiting approval", len(pending))
             + _stat("Joined this week", sum(1 for x in users if x["created_at"] >= week))
             + _stat("Credits outstanding", outstanding) + "</div>")
    rows = []
    for x in users:
        approve = ""
        if x["status"] == "pending":
            approve = ("<form method='post' action='" + u("/portal/user/status") + "' class='inline'><input type='hidden' name='id' value='%d'>"
                       "<input type='hidden' name='status' value='active'><input type='hidden' name='back' value='/portal'>"
                       "<button class='btn small lime'>Approve</button></form> " % x["id"])
        rows.append(
            "<tr><td><strong>%s</strong><br><span class='muted'>%s · %s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td>"
            "<td class='right'>%s<a class='btn small ghost' href='%s'>Manage</a></td></tr>"
            % (e(x["name"] or "—"), e(x["company"] or "—"), e(x["email"]), _status_pill(x["status"]),
               e(x["credits"] if x["credits"] is not None else 0), e(x["selections"]), e(x["briefs"]),
               e(ago(x["last_login_at"]) if x["last_login_at"] else "never"), approve, u("/portal/user?id=%d" % x["id"])))
    table = ("<table><thead><tr><th>Client</th><th>Status</th><th>Credits</th><th>Selections</th><th>Briefs</th><th>Last in</th><th></th></tr></thead><tbody>"
             + ("".join(rows) or "<tr><td colspan='7'>" + ui.empty("users", "No sign-ups yet",
                "Clients appear here when they sign in with a company email on the catalogue.") + "</td></tr>") + "</tbody></table>")
    return stats + "<div class='card'>" + table + "</div>"


def _briefs_tab():
    rows = []
    for b in portal.briefs_for(None, 100):
        usr = portal.user_for_code(b["code_id"])
        who = (usr["company"] or usr["email"]) if usr else "Guest code #%d" % b["code_id"]
        rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>"
                    % (e(who), e(b["summary"]), e(b["objective"] or ""),
                       ("selection #%d" % b["selection_id"]) if b["selection_id"] else "—", e(ago(b["created_at"]))))
    return ("<div class='card'><p class='sec-desc'>Every brief a client answered. The selection it produced is on the Selections page, "
            "already scored against the brief.</p><table><thead><tr><th>Client</th><th>Brief</th><th>Objective</th><th>Result</th><th>When</th></tr></thead><tbody>"
            + ("".join(rows) or "<tr><td colspan='5'>" + ui.empty("list", "No briefs yet", "They appear when a client uses Find creators.") + "</td></tr>")
            + "</tbody></table></div>")


def _usage_tab():
    used, cap = gemini.tokens_this_month(), gemini.monthly_cap()
    since = gemini.month_start()
    with db.connect() as conn:
        by_kind = conn.execute("SELECT kind, COUNT(*) n, SUM(ok) good, SUM(prompt_tokens+out_tokens) tok, SUM(credits) cr "
                               "FROM ai_audit WHERE at >= ? GROUP BY kind ORDER BY n DESC", (since,)).fetchall()
        recent = conn.execute("SELECT a.*, u.email FROM ai_audit a LEFT JOIN users u ON u.code_id = a.code_id "
                              "ORDER BY a.id DESC LIMIT 25").fetchall()
        spent = conn.execute("SELECT COALESCE(-SUM(delta),0) FROM credit_ledger WHERE delta < 0 AND at >= ?", (since,)).fetchone()[0]
        granted = conn.execute("SELECT COALESCE(SUM(delta),0) FROM credit_ledger WHERE delta > 0 AND at >= ?", (since,)).fetchone()[0]
    pct = int(round(used * 100.0 / cap)) if cap else 0
    stats = ("<div class='pstats'>" + _stat("Tokens this month", "{:,}".format(used), "of {:,} ({}%)".format(cap, pct))
             + _stat("Calls", sum(r["n"] for r in by_kind)) + _stat("Failed", sum(r["n"] - (r["good"] or 0) for r in by_kind))
             + _stat("Credits spent", spent, "granted %d" % granted) + "</div>")
    kind_rows = "".join("<tr><td>%s</td><td>%d</td><td>%d</td><td>{:,}</td></tr>".format(r["tok"] or 0) % (e(r["kind"]), r["n"], r["good"] or 0)
                        for r in by_kind)
    recent_rows = "".join(
        "<tr><td class='muted'>%s</td><td>%s</td><td>%s</td><td>%s</td><td>{:,}</td><td>%s</td></tr>".format((r["prompt_tokens"] or 0) + (r["out_tokens"] or 0))
        % (e(ago(r["at"])), e(r["kind"]), e(r["email"] or ("code #%s" % r["code_id"] if r["code_id"] else "admin")),
           "ok" if r["ok"] else "<span class='pill dead'>failed</span>", e(r["latency_ms"] or ""), e(r["detail"] or ""))
        for r in recent)
    return (stats + "<div class='card'><h2>This month by action</h2><table><thead><tr><th>Action</th><th>Calls</th><th>OK</th><th>Tokens</th></tr></thead><tbody>"
            + (kind_rows or "<tr><td colspan='4' class='muted'>No AI calls yet.</td></tr>") + "</tbody></table></div>"
            + "<div class='card'><h2>Latest calls</h2><table><thead><tr><th>When</th><th>Action</th><th>Who</th><th>Result</th><th>Tokens</th><th>ms / note</th></tr></thead><tbody>"
            + (recent_rows or "<tr><td colspan='6' class='muted'>Nothing yet.</td></tr>") + "</tbody></table></div>")


def _settings_tab():
    allow, block = portal.domain_lists()
    costs = portal.costs()
    mode = portal.signup_mode()
    opts = "".join("<option value='%s'%s>%s</option>" % (k, " selected" if k == mode else "", lbl) for k, lbl in (
        ("open", "Open — any company email can sign up"), ("approval", "Approval — I approve each new client"),
        ("allowlist", "Invite only — only allow-listed domains"), ("closed", "Closed — no new sign-ups")))
    cost_inputs = "".join("<div><label>%s</label><input type='number' min='0' max='1000' name='cost_%s' value='%d'></div>"
                          % (lbl, k, costs[k]) for k, lbl in (("brief", "AI shortlist with reasons"), ("search", "Shortlist without AI text"),
                                                              ("parse", "Read a free-text brief"), ("chat", "Chat message")))

    def key_card(which, title, mod, help_):
        hint = mod.key_hint()
        return ("<div class='card'><h2>%s</h2><p class='sec-desc'>%s The key stays on the server in a private file and is never shown again, only its last four characters.</p>%s"
                "<form method='post' action='%s' autocomplete='off'><input type='hidden' name='which' value='%s'><input type='hidden' name='back' value='/portal?tab=settings'>"
                "<label>%s</label><input type='password' name='key' autocomplete='off' placeholder='Paste the key' required> "
                "<button class='btn lime' name='action' value='save'>Save key</button></form>%s</div>"
                % (e(title), help_, ("<p>Saved key: <code>%s</code></p>" % e(hint)) if hint else "<p class='muted'>No key saved.</p>",
                   u("/portal/keys"), which, "Replace key" if hint else "API key",
                   ("<form method='post' action='%s' class='inline' style='margin-top:10px'><input type='hidden' name='which' value='%s'>"
                    "<input type='hidden' name='back' value='/portal?tab=settings'><button class='btn small danger' name='action' value='clear' "
                    "onclick=\"return confirm('Remove the key?')\">Remove key</button></form>" % (u("/portal/keys"), which)) if hint else ""))

    form = (
        "<form method='post' action='%s'><input type='hidden' name='back' value='/portal?tab=settings'>" % u("/portal/settings")
        + "<div class='card'><h2>Sign-up</h2><p class='sec-desc'>Clients sign in with a one-time code sent to a company email. "
          "Personal providers (Gmail, Outlook, iCloud…) are always refused unless you allow-list that exact domain.</p>"
          "<div class='fgrid'><div><label>Who can sign up</label><select name='signup_mode'>" + opts + "</select></div>"
          "<div><label>Welcome credits</label><input type='number' min='0' name='signup_credits' value='%d'></div>" % portal.signup_credits()
        + "<div><label>Guest passcode allowance</label><input type='number' min='0' name='guest_credits' value='%d'>"
          "<div class='price-hint'>One-off credits for clients still using an access code.</div></div>" % portal.guest_credits()
        + "<div><label>Devices per account</label><input type='number' min='1' max='50' name='user_max_devices' value='%s'></div></div>"
          % e(db.setting("user_max_devices", 5))
        + "<div class='fgrid' style='margin-top:14px'><div><label>Allow-listed domains</label><textarea class='mono' name='domain_allow' placeholder='one per line'>%s</textarea></div>"
          % e("\n".join(allow))
        + "<div><label>Blocked domains</label><textarea class='mono' name='domain_block' placeholder='one per line'>%s</textarea></div></div></div>" % e("\n".join(block))
        + "<div class='card'><h2>AI credits</h2><p class='sec-desc'>What each action costs a client. A failed AI call is refunded automatically. The admin is never charged.</p>"
          "<div class='fgrid'>" + cost_inputs + "</div></div>"
        + "<div class='card'><h2>AI &amp; email</h2><div class='fgrid'>"
          "<div><label>Gemini model</label><input name='gemini_model' value='%s'><div class='price-hint'>Default %s. If a model is retired the next one in line is tried automatically.</div></div>" % (e(gemini.model()), e(gemini.DEFAULT_MODEL))
        + "<div><label>Monthly token ceiling</label><input type='number' min='10000' name='ai_monthly_tokens' value='%d'>"
          "<div class='price-hint'>AI stops for everyone when this is reached.</div></div>" % gemini.monthly_cap()
        + "<div><label>Send email from</label><input name='mail_from' value='%s'><div class='price-hint'>Its domain must be verified in Resend.</div></div></div>" % e(mailer.sender())
        + "<label style='margin-top:14px'>What the assistant knows about HelloVoice</label>"
          "<textarea class='mono' name='kb_text' rows='6'>%s</textarea></div>" % e(db.setting("kb_text", None) or __import__("assistant").DEFAULT_KB)
        + "<button class='btn lime'>Save settings</button></form>")
    keys = (key_card("gemini", "Gemini API key", gemini, "Powers the shortlist reasons, the chat and the copilot.")
            + key_card("mail", "Email (Resend) API key", mailer, "Sends the sign-in codes."))
    return form + "<div style='margin-top:20px'>" + keys + "</div>"


def portal_page(tab="accounts", ok=None, err=None, query=None):
    tab = tab if tab in dict(TABS) else "accounts"
    body = {"accounts": _accounts_tab, "briefs": _briefs_tab, "usage": _usage_tab, "settings": _settings_tab}[tab]()
    status = ("<span class='pill %s'>Gemini %s</span> <span class='pill %s'>Email %s</span>" % (
        "live" if gemini.configured() else "warn", "ready" if gemini.configured() else "not set up",
        "live" if mailer.configured() else "warn", "ready" if mailer.configured() else "not set up"))
    return page("Client portal", STAT_CSS + ui.header("Client portal", "Company-email accounts, AI credits, briefs and AI settings. " + status,
                tabs=_tabs(tab)) + _banner(ok, err) + body, "/portal")


# ------------------------------------------------------------- one client --

def user_page(usr, ok=None, err=None):
    cid = usr["code_id"]
    bal = portal.balance(cid)
    ledger = portal.ledger(cid, 25)
    with db.connect() as conn:
        sels = conn.execute("SELECT id, name, updated_at FROM selections WHERE code_id = ? ORDER BY updated_at DESC LIMIT 20", (cid,)).fetchall()
        ev = conn.execute("SELECT kind, COUNT(*) n, MAX(at) last FROM events WHERE code_id = ? GROUP BY kind ORDER BY n DESC", (cid,)).fetchall()
    hid = lambda name, val: "<input type='hidden' name='%s' value='%s'>" % (name, e(val))
    back = hid("back", "/portal/user?id=%d" % usr["id"])
    status_btns = "".join(
        "<form method='post' action='%s' class='inline'>%s%s%s<button class='btn small %s'>%s</button></form> " % (
            u("/portal/user/status"), hid("id", usr["id"]), hid("status", s), back, cls, lbl)
        for s, lbl, cls in (("active", "Activate", "lime"), ("pending", "Put on hold", "ghost"), ("suspended", "Suspend", "danger"))
        if s != usr["status"])
    profile = (
        "<div class='card'><h2>Profile</h2><form method='post' action='%s'>%s%s<div class='fgrid'>"
        "<div><label>Name</label><input name='name' value='%s'></div><div><label>Company</label><input name='company' value='%s'></div>"
        "<div><label>Job title</label><input name='job_title' value='%s'></div><div><label>Phone</label><input name='phone' value='%s'></div></div>"
        "<label style='margin-top:12px'>Internal notes</label><textarea name='notes' rows='3'>%s</textarea>"
        "<p class='muted'>%s · joined %s · domain %s</p><button class='btn lime'>Save</button></form></div>"
        % (u("/portal/user/save"), hid("id", usr["id"]), back, e(usr["name"]), e(usr["company"]), e(usr["job_title"]), e(usr["phone"]),
           e(usr["notes"]), e(usr["email"]), e(ts(usr["created_at"])), e(usr["domain"])))
    credits = (
        "<div class='card'><h2>AI credits: %d</h2><form method='post' action='%s' class='row'>%s%s"
        "<div><label>Add or remove</label><input type='number' name='amount' placeholder='e.g. 50 or -10' required></div>"
        "<div><label>Reason</label><input name='reason' placeholder='Top-up for Q4 campaign'></div><div><button class='btn lime'>Apply</button></div></form>"
        "<table><thead><tr><th>When</th><th>Change</th><th>Balance</th><th>Reason</th></tr></thead><tbody>%s</tbody></table></div>"
        % (bal, u("/portal/user/credits"), hid("id", usr["id"]), back,
           "".join("<tr><td class='muted'>%s</td><td>%+d</td><td>%d</td><td>%s</td></tr>" % (e(ago(r["at"])), r["delta"], r["balance_after"], e(r["reason"]))
                   for r in ledger) or "<tr><td colspan='4' class='muted'>No movements.</td></tr>"))
    work = (
        "<div class='card'><h2>Work</h2><p><strong>Selections</strong></p><ul>%s</ul><p><strong>Briefs</strong></p><ul>%s</ul><p><strong>Activity</strong></p><ul>%s</ul></div>"
        % ("".join("<li>%s <span class='muted'>%s</span></li>" % (e(s["name"]), e(ago(s["updated_at"]))) for s in sels) or "<li class='muted'>none</li>",
           "".join("<li>%s <span class='muted'>%s</span></li>" % (e(b["summary"]), e(ago(b["created_at"]))) for b in portal.briefs_for(cid, 10)) or "<li class='muted'>none</li>",
           "".join("<li>%s × %d <span class='muted'>last %s</span></li>" % (e(r["kind"]), r["n"], e(ago(r["last"]))) for r in ev) or "<li class='muted'>none</li>"))
    return page(usr["email"], STAT_CSS + ui.header(usr["name"] or usr["email"], "%s · %s" % (usr["company"] or "no company", usr["email"]),
                crumbs=[("Client portal", u("/portal")), (usr["email"], None)], actions=status_btns + _status_pill(usr["status"]))
                + _banner(ok, err) + profile + credits + work, "/portal")


# ----------------------------------------------------------------- copilot --

SUGGESTIONS = [
    "Which creators are missing a city, tier or photo?",
    "What are clients asking for that our roster can't supply?",
    "Who signed up this week and what did they ask for?",
    "Find 10 skincare creators in Riyadh on Instagram with 50k–300k followers",
    "How many credits has each client used this month?",
]

COPILOT_JS = r"""
(function(){
  var log=document.getElementById('cp-log'), box=document.getElementById('cp-text'), form=document.getElementById('cp-form'),
      thread=null, busy=false, URL_CHAT=%(chat)s, URL_OK=%(ok)s, URL_NO=%(no)s;
  function esc(s){return s.replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function md(t){ var h=esc(t).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>');
    var out=[],inl=false; h.split('\n').forEach(function(l){ if(/^\s*[-*] /.test(l)){ if(!inl){out.push('<ul>');inl=true;} out.push('<li>'+l.replace(/^\s*[-*] /,'')+'</li>'); }
      else { if(inl){out.push('</ul>');inl=false;} out.push(l?'<p>'+l+'</p>':''); } }); if(inl) out.push('</ul>'); return out.join(''); }
  function add(role,html){ var d=document.createElement('div'); d.className='cp-m cp-'+role; d.innerHTML=html; log.appendChild(d); log.scrollTop=log.scrollHeight; return d; }
  function post(url,body){ return fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(r){return r.json();}); }
  function queued(list){ (list||[]).forEach(function(q){
    var d=add('act','<div><b>Waiting for you</b><p>'+esc(q.text)+'</p></div><div class="cp-btns"><button class="btn small lime">Confirm</button> <button class="btn small ghost">Dismiss</button></div>');
    var b=d.querySelectorAll('button');
    b[0].onclick=function(){ b[0].disabled=b[1].disabled=true; post(URL_OK,{token:q.token}).then(function(r){ d.innerHTML=r.ok?'<b>Done.</b> '+esc(q.text)+' <span class="muted">Undo it from History &amp; undo.</span>':'<b>Not done.</b> '+esc(r.error||'Unknown error'); }); };
    b[1].onclick=function(){ post(URL_NO,{token:q.token}).then(function(){ d.innerHTML='<span class="muted">Dismissed: '+esc(q.text)+'</span>'; }); }; }); }
  function send(t){ if(busy||!t.trim())return; busy=true; add('me',esc(t)); var w=add('bot','<span class="muted">Thinking…</span>');
    post(URL_CHAT,{message:t,thread:thread}).then(function(r){ busy=false; if(!r.ok){ w.innerHTML='<span class="cp-err">'+esc(r.error||'Something went wrong')+'</span>'; return; }
      thread=r.thread; w.innerHTML=md(r.reply||''); queued(r.queued); }).catch(function(){ busy=false; w.innerHTML='<span class="cp-err">Could not reach the server.</span>'; }); }
  form.addEventListener('submit',function(e){ e.preventDefault(); var t=box.value; box.value=''; send(t); });
  box.addEventListener('keydown',function(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); form.requestSubmit(); } });
  document.querySelectorAll('.cp-chip').forEach(function(c){ c.onclick=function(){ send(c.textContent); }; });
})();
"""


def copilot_page(email, configured):
    chips = "".join("<button type='button' class='cp-chip'>%s</button>" % e(s) for s in SUGGESTIONS)
    off = "" if configured else ("<div class='note'>The copilot needs a Gemini key. <a href='%s'>Add it in Client portal → Settings &amp; keys</a>.</div>"
                                 % u("/portal?tab=settings"))
    css = ("<style>.cp{display:flex;flex-direction:column;height:calc(100vh - 250px);min-height:420px}"
           "#cp-log{flex:1;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:10px}"
           ".cp-m{max-width:78%;padding:10px 14px;border-radius:14px;line-height:1.5;font-size:14px}.cp-m p{margin:0 0 6px}.cp-m ul{margin:4px 0 6px 18px;padding:0}"
           ".cp-me{align-self:flex-end;background:var(--ink);color:#fff}.cp-bot{align-self:flex-start;background:#f3f1ec}"
           ".cp-act{align-self:flex-start;background:var(--amber-soft);border:1px solid var(--amber);width:78%}.cp-btns{margin-top:8px}"
           ".cp-err{color:var(--red)}#cp-form{display:flex;gap:10px;margin-top:12px}#cp-text{flex:1;min-height:46px;max-height:140px;border-radius:14px;padding:10px 14px;font:inherit;border:1px solid var(--line-strong)}"
           ".cp-chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}.cp-chip{border:1px solid var(--line-strong);background:#fff;border-radius:999px;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer}"
           ".cp-chip:hover{border-color:var(--ink)}</style>")
    js = COPILOT_JS % {"chat": json.dumps(u("/ai/chat")), "ok": json.dumps(u("/ai/confirm")), "no": json.dumps(u("/ai/dismiss"))}
    body = (css + ui.header("AI copilot", "Ask about your data, build selections, check client activity, or ask it to make a change. "
                            "Changes are never made until you press Confirm, and each one appears in History so you can undo it.")
            + off + "<div class='cp'><div class='cp-chips'>" + chips + "</div><div id='cp-log'><div class='cp-m cp-bot'>Hi. What would you like to look at or change?</div></div>"
            "<form id='cp-form'><textarea id='cp-text' placeholder='Ask anything about creators, clients, briefs or credits…' rows='1'></textarea>"
            "<button class='btn lime'>Send</button></form></div><script>" + js + "</script>")
    return page("AI copilot", body, "/ai")
