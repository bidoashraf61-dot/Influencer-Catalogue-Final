"""Pages for the team and security: the Team & security page, two-step sign-in, the password
re-check and the "not allowed" page. Every value goes through e()."""
import team
import ui
from views import HEAD, ago, e, page, ts, u


def _banner(ok, err):
    return (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")


def _standalone(title, inner):
    """A small centred page before sign-in completes (no sidebar)."""
    return (HEAD + "<title>" + e(title) + " — HelloVoice Admin</title><link rel='stylesheet' href='" + u("/static/admin.css") + "'>"
            "<style>.solo{max-width:440px;margin:8vh auto;padding:0 16px}.solo .card{padding:26px}.code-in{font-size:var(--t-xl,28px);letter-spacing:.3em;"
            "text-align:center;font-variant-numeric:tabular-nums}.secret{font-family:ui-monospace,monospace;font-size:var(--t-md,14.5px);word-break:break-all;"
            "background:var(--paper);padding:10px 12px;border-radius:8px;display:block;margin:8px 0}</style></head><body>"
            "<main class='solo' id='main'><img src='" + u("/static/logo-knockout.webp") + "' alt='HelloVoice' height='26' "
            "style='filter:invert(1);margin-bottom:22px'>" + inner + "</main></body></html>")


def two_step_page(email, setup_secret=None, error=None):
    code_field = ("<label for='otp'>6-digit code from your authenticator app</label>"
                  "<input id='otp' class='code-in' name='code' inputmode='numeric' autocomplete='one-time-code' maxlength='6' pattern='[0-9]*' required autofocus>")
    if setup_secret:
        inner = ("<div class='card'><h1 style='font-size:var(--t-xl,28px);margin:0 0 6px'>Set up two-step sign-in</h1>"
                 "<p class='muted'>Your team requires it for your role. It takes a minute.</p><ol style='padding-left:18px;line-height:1.6'>"
                 "<li>Open Google Authenticator, Microsoft Authenticator or 1Password on your phone.</li>"
                 "<li>Add an account and choose <b>Enter a setup key</b> (or tap the link below on your phone).</li>"
                 "<li>Account: <b>HelloVoice Admin</b> · Key:<code class='secret'>" + e(" ".join(setup_secret[i:i + 4] for i in range(0, len(setup_secret), 4))) + "</code>"
                 "<a href='" + e(team.otpauth_uri(setup_secret, email)) + "'>Open in authenticator app</a></li>"
                 "<li>Type the 6-digit code it shows.</li></ol>"
                 + (("<div class='err'>" + e(error) + "</div>") if error else "")
                 + "<form method='post' action='" + u("/login/2fa") + "'>" + code_field + "<button class='btn lime' style='margin-top:14px;width:100%'>Turn on and sign in</button></form></div>")
    else:
        inner = ("<div class='card'><h1 style='font-size:var(--t-xl,28px);margin:0 0 6px'>Two-step sign-in</h1><p class='muted'>Signed in as " + e(email) + ".</p>"
                 + (("<div class='err'>" + e(error) + "</div>") if error else "")
                 + "<form method='post' action='" + u("/login/2fa") + "'>" + code_field + "<button class='btn lime' style='margin-top:14px;width:100%'>Sign in</button></form>"
                 "<p class='muted' style='font-size:var(--t-sm,13px);margin-top:14px'>Lost your phone? Ask an owner to reset your two-step sign-in.</p></div>")
    return _standalone("Two-step sign-in", inner)


def reauth_page(nxt, totp_on, again=False, error=None, mailed=False):
    totp = ("<label for='re-otp' style='margin-top:12px'>Code from your authenticator app</label>"
            "<input id='re-otp' name='code' inputmode='numeric' autocomplete='one-time-code' maxlength='6' required>" if totp_on else "")
    body = (ui.header("Confirm it is you", "For keys, deletes, credits and team changes we ask you to confirm again (once every 10 minutes).")
            + (("<div class='err'>" + e(error) + "</div>") if error else "")
            + ("<div class='note'>After confirming, press the button you pressed again; the change was not made yet.</div>" if again else "")
            + "<div class='card' style='max-width:460px'>"
            "<form method='post' action='" + u("/reauth") + "'><input type='hidden' name='next' value='" + e(nxt) + "'>"
            "<input type='hidden' name='send_code' value='1'><button class='btn' type='submit'>Email me a code</button></form>"
            "<form method='post' action='" + u("/reauth") + "' style='margin-top:14px'>"
            "<input type='hidden' name='next' value='" + e(nxt) + "'>"
            + ("<div class='note'>Code sent to your email.</div>" if mailed else "")
            + "<label for='re-mail'>6-digit code from your email</label>"
            "<input id='re-mail' name='mailcode' inputmode='numeric' autocomplete='one-time-code' maxlength='6'" + (" autofocus" if mailed else "") + ">"
            "<details style='margin-top:12px'><summary class='muted'>Use my password instead</summary>"
            "<label for='re-pw' style='margin-top:8px'>Password</label><input id='re-pw' name='password' type='password' autocomplete='current-password'></details>"
            + totp
            + "<button class='btn lime' style='margin-top:14px'>Confirm</button></form></div>")
    return page("Confirm it is you", body, "/team")


def forbidden_page(role):
    body = (ui.header("Not available for your role", "You are signed in as <b>%s</b>. %s" % (e(team.ROLE_LABEL.get(role, role)), e(team.ROLE_HELP.get(role, ""))))
            + ui.empty("key", "Ask an owner if you need this", "An owner can change your role on the People and access page.",
                       "<a class='btn small' href='" + u("/") + "'>Back to Home</a>"))
    return page("Not available", body, "/")


def team_page(who, ok=None, err=None, setup_secret=None, new_member=None):
    me_role = team.role_of(who)
    is_owner = me_role == "owner"
    hid = lambda n, v: "<input type='hidden' name='%s' value='%s'>" % (n, e(v))

    # ---- my account: two-step sign-in
    if who["totp_on"]:
        mine = ("<p><span class='pill live'>On</span> Two-step sign-in protects your account.</p>"
                + ("" if team.must_use_2fa(who) else
                   "<form method='post' action='" + u("/account/2fa/disable") + "' class='inline' data-confirm='Turn off two-step sign-in for your account?'>"
                   "<button class='btn small ghost'>Turn off</button></form>"))
    elif setup_secret:
        mine = ("<ol style='padding-left:18px;line-height:1.6'><li>In Google Authenticator, Microsoft Authenticator or 1Password choose <b>Enter a setup key</b>.</li>"
                "<li>Account <b>HelloVoice Admin</b>, key <code>" + e(" ".join(setup_secret[i:i + 4] for i in range(0, len(setup_secret), 4)))
                + "</code> (or <a href='" + e(team.otpauth_uri(setup_secret, who["email"])) + "'>open on your phone</a>).</li>"
                "<li>Type the code it shows:</li></ol><form method='post' action='" + u("/account/2fa/enable") + "' class='row'>"
                "<div><label for='en-otp'>6-digit code</label><input id='en-otp' name='code' inputmode='numeric' maxlength='6' required autofocus></div>"
                "<div><button class='btn lime'>Turn on</button></div></form>")
    else:
        mine = ("<p><span class='pill warn'>Off</span> Add a code from your phone at sign-in, so a stolen password is not enough.</p>"
                "<form method='post' action='" + u("/account/2fa/start") + "'><button class='btn lime'>Set up two-step sign-in</button></form>")
    account = ("<div class='card'><h2>My account</h2><p class='muted'>" + e(who["email"]) + " · " + e(team.ROLE_LABEL[me_role]) + "</p>"
               "<h3 style='font-size:var(--t-md,14.5px);margin:16px 0 6px'>Two-step sign-in</h3>" + mine + "</div>")
    if not is_owner:
        return page("My account", ui.header("My account", "Your sign-in and security.") + _banner(ok, err) + account, "/team")

    # ---- People and access (owners): one list, one Invite button, actions behind "..."
    LEVEL_HELP = {"owner": "Everything, including who has access.", "admin": "Everything except people and access.",
                  "kam": "Their own clients' selections, quotes and campaigns.", "viewer": "Can look at everything. Changes nothing."}
    LEVEL_SHORT = {"owner": "Owner", "admin": "Admin", "kam": "KAM", "viewer": "Viewer"}
    people = team.list_admins()
    rows = ""
    for a in people:
        r = team.role_of(a)
        nm = a["name"] or a["email"].split("@")[0].split(".")[0].capitalize()
        ini = "".join(w[0] for w in nm.split()[:2]).upper() or "?"
        mine = a["id"] == who["admin_id"]
        seen = a["active_at"] or a["last_login_at"]
        flag = ""
        if a["disabled_at"]:
            flag = "<em class='pa-flag dead'>Access removed</em>"
        elif not (a["last_login_at"] or a["active_at"]):
            flag = "<em class='pa-flag'>Invited · not signed in yet</em>"
        if mine:
            lvl = "<span class='pa-tag'>" + e(LEVEL_SHORT[r]) + " · you</span>"
        elif a["disabled_at"]:
            lvl = "<span class='pa-muted'>" + e(LEVEL_SHORT[r]) + "</span>"
        else:
            lvl = ("<form method='post' action='" + u("/team/role") + "'>" + hid("id", a["id"])
                   + "<select class='pa-level' name='role' aria-label='Level for " + e(a["email"]) + "' onchange='this.form.submit()'>"
                   + "".join("<option value='%s'%s>%s</option>" % (k, " selected" if k == r else "", e(LEVEL_SHORT[k])) for k in team.ROLES)
                   + "</select></form>")
        acts = ""
        if not mine:
            def act(path, label, confirm=None, cls=""):
                return ("<form method='post' action='" + u(path) + "'" + (" data-confirm='" + e(confirm) + "'" if confirm else "") + ">"
                        + hid("id", a["id"]) + "<button class='" + cls + "'>" + e(label) + "</button></form>")
            if a["disabled_at"]:
                acts = act("/team/enable", "Give access back")
            else:
                if not (a["last_login_at"] or a["active_at"]):
                    acts += act("/team/reinvite", "Send the invite again")
                else:
                    if a["totp_on"]:
                        acts += act("/team/reset2fa", "Reset two-step sign-in", "Reset two-step sign-in for %s? They set it up again next time." % a["email"])
                    acts += act("/team/signout", "Sign them out everywhere")
                acts += act("/team/disable", "Remove access", "Remove %s? They are signed out at once." % a["email"], "danger")
        more = ("<details class='pa-more'><summary aria-label='More for " + e(nm) + "'><svg viewBox='0 0 24 24' fill='currentColor' aria-hidden='true'>"
                "<circle cx='5' cy='12' r='1.8'/><circle cx='12' cy='12' r='1.8'/><circle cx='19' cy='12' r='1.8'/></svg></summary>"
                "<div class='pa-pop'>" + acts + "</div></details>") if acts else ""
        rows += ("<div class='pa-p" + (" off" if a["disabled_at"] else "") + "'><div class='pa-av" + (" own" if r == "owner" else "") + "'>" + e(ini) + "</div>"
                 "<div class='pa-who'><b>" + e(nm) + "</b><span>" + e(a["email"]) + "</span>" + flag + "</div>"
                 "<div class='pa-lvl'>" + lvl + "</div><div class='pa-seen'>" + ("Active now" if mine else e(ago(seen)) if seen else "Never") + "</div>"
                 "<div class='pa-m'>" + more + "</div></div>")
    invite = ("<details class='pa-inv' id='invite'" + (" open" if err else "") + "><summary class='btn lime'>"
              "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' aria-hidden='true'><path d='M12 5v14M5 12h14'/></svg>Invite someone</summary>"
              "<form method='post' action='" + u("/team/invite") + "' class='pa-card'><h2>Invite someone</h2>"
              "<div class='pa-two'><div><label for='in-email'>Work email</label><input id='in-email' name='email' type='email' required placeholder='name@blueholding.co.uk'></div>"
              "<div><label for='in-name'>Name <span class='muted'>(optional)</span></label><input id='in-name' name='name'></div></div>"
              "<label style='margin-top:14px'>What can they do?</label><div class='pa-levels' role='radiogroup'>"
              + "".join("<label class='pa-lv'><input type='radio' name='role' value='%s'%s><b>%s</b><span>%s</span></label>"
                        % (k, " checked" if k == "kam" else "", e(LEVEL_SHORT[k]), e(LEVEL_HELP[k])) for k in team.ROLES)
              + "</div><div class='pa-foot'><p>They get an email with a link to sign in. You can change their level any time.</p>"
              "<button class='btn'>Send invite</button></div></form></details>")
    n = len([a for a in people if not a["disabled_at"]])
    team_card = ("<div class='pa-list'><div class='pa-lh'><h2>Team</h2><small>%d %s</small></div>%s</div>" % (n, "person" if n == 1 else "people", rows))
    PA_CSS = ("<style>.pa-top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}"
              ".pa-top h1{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:clamp(38px,4.6vw,54px);line-height:.92;margin:0}"
              ".pa-top p{margin:8px 0 0;color:var(--gray);max-width:52ch}"
              ".pa-inv>summary{list-style:none;display:inline-flex;align-items:center;gap:8px;cursor:pointer}.pa-inv>summary::-webkit-details-marker{display:none}"
              ".pa-inv>summary svg{width:18px;height:18px}.pa-inv[open]>summary{display:none}"
              ".pa-card{background:var(--white);border:1px solid var(--ink);border-radius:var(--r-lg);padding:22px;margin:0 0 20px;box-shadow:0 14px 34px -18px rgba(18,18,18,.35)}"
              ".pa-card h2{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:26px;margin:0 0 14px}"
              ".pa-two{display:grid;grid-template-columns:2fr 1fr;gap:12px}"
              ".pa-levels{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:6px}"
              ".pa-lv{position:relative;border:1px solid var(--line-strong);border-radius:12px;padding:12px;cursor:pointer;background:#fff;margin:0;font-weight:400}"
              ".pa-lv input{position:absolute;opacity:0}.pa-lv b{display:block}.pa-lv span{display:block;font-size:12.5px;color:var(--muted);line-height:1.4;margin-top:3px}"
              ".pa-lv:has(input:checked){border-color:var(--ink);background:var(--lime)}.pa-lv:has(input:checked) span{color:#3d4500}"
              ".pa-lv:has(input:focus-visible){outline:2px solid var(--ink);outline-offset:2px}"
              ".pa-foot{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:16px}.pa-foot p{margin:0;font-size:13px;color:var(--muted)}"
              ".pa-head-row{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap}"
              ".pa-list{background:var(--white);border:1px solid var(--line);border-radius:var(--r-lg);margin-bottom:18px}"
              ".pa-lh{display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid var(--line)}"
              ".pa-lh h2{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:24px;margin:0}.pa-lh small{color:var(--muted);font-size:13px}"
              ".pa-p{display:grid;grid-template-columns:44px minmax(0,1fr) 150px 110px 40px;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid var(--line)}"
              ".pa-p:last-child{border-bottom:0}.pa-p.off{opacity:.6}"
              ".pa-av{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font-family:'Bebas Neue',sans-serif;font-size:18px;background:var(--linen)}"
              ".pa-av.own{background:var(--lime);box-shadow:inset 0 0 0 1.5px var(--ink)}"
              ".pa-who b{display:block;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
              ".pa-who span{display:block;font-size:13px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
              ".pa-flag{font-style:normal;font-size:12px;color:var(--amber);background:var(--amber-soft);border-radius:999px;padding:1px 8px;display:inline-block;margin-top:3px}"
              ".pa-flag.dead{color:var(--red);background:var(--red-soft)}"
              ".pa-level{font-weight:600;font-size:13.5px;border-radius:999px;min-height:38px;width:100%;margin:0}"
              ".pa-tag{display:inline-flex;font-weight:600;font-size:13.5px;padding:8px 12px;border-radius:999px;background:var(--ink);color:var(--lime)}"
              ".pa-muted,.pa-seen{font-size:13px;color:var(--muted)}"
              ".pa-more{position:relative}.pa-more>summary{list-style:none;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;cursor:pointer;border:1px solid transparent}"
              ".pa-more>summary::-webkit-details-marker{display:none}.pa-more>summary svg{width:18px;height:18px}"
              ".pa-more>summary:hover,.pa-more[open]>summary{border-color:var(--line-strong);background:var(--paper)}"
              ".pa-pop{position:absolute;right:0;top:44px;background:#fff;border:1px solid var(--line-strong);border-radius:12px;min-width:220px;padding:6px;"
              "box-shadow:0 18px 40px -16px rgba(18,18,18,.35);z-index:6}.pa-pop form{margin:0}"
              ".pa-pop button{display:block;width:100%;text-align:left;font:500 14px 'DM Sans',sans-serif;padding:10px 12px;border:0;background:transparent;border-radius:8px;cursor:pointer;color:var(--ink)}"
              ".pa-pop button:hover{background:rgba(232,255,118,.5)}.pa-pop button.danger{color:var(--red)}.pa-pop button.danger:hover{background:var(--red-soft)}"
              ".pa-fold{background:var(--white);border:1px solid var(--line);border-radius:var(--r-lg);margin-bottom:12px}"
              ".pa-fold>summary{list-style:none;cursor:pointer;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px}"
              ".pa-fold>summary::-webkit-details-marker{display:none}.pa-fold>summary b{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:22px}"
              ".pa-fold>summary span{font-size:13px;color:var(--muted)}.pa-fold>div{padding:0 20px 16px}.pa-fold .card{border:0;padding:0;box-shadow:none;margin:0 0 14px}"
              ".pa-note{font-size:13px;color:var(--muted);margin:6px 2px 0}"
              "@media (max-width:760px){.pa-levels{grid-template-columns:1fr 1fr}.pa-two{grid-template-columns:1fr}"
              ".pa-p{grid-template-columns:40px minmax(0,1fr) 40px;grid-template-areas:'av who m' 'av lvl lvl';row-gap:10px}"
              ".pa-av{grid-area:av;align-self:start}.pa-who{grid-area:who}.pa-lvl{grid-area:lvl}.pa-seen{display:none}.pa-m{grid-area:m}}</style>"
              "<script>document.addEventListener('click',function(ev){document.querySelectorAll('.pa-more[open]').forEach(function(d){if(!d.contains(ev.target))d.removeAttribute('open')})});"
              "document.addEventListener('keydown',function(ev){if(ev.key==='Escape')document.querySelectorAll('.pa-more[open]').forEach(function(d){d.removeAttribute('open')})});</script>")
    header = ("<div class='pa-top'><div><h1>People and access</h1><p>Who can control HELVY Connect. Everyone signs in with a code sent to their work email, "
              "so there are no passwords to share.</p></div></div>")
    req = team.required_roles()
    policy = ("<div class='card'><h2>Sign-in rules</h2><form method='post' action='" + u("/team/policy") + "'>"
              "<p class='muted'>Two-step sign-in is required for:</p><div style='display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px'>" + "".join(
                  "<label style='display:flex;gap:8px;align-items:center;font-weight:500'><input type='checkbox' name='req' value='%s'%s> %s</label>"
                  % (k, " checked" if k in req else "", e(team.ROLE_LABEL[k])) for k in team.ROLES) + "</div>"
              "<label for='idle'>Sign out after this many minutes without activity</label>"
              "<input id='idle' name='idle' type='number' min='5' max='1440' value='" + str(team.idle_minutes()) + "' style='max-width:140px'>"
              "<div style='margin-top:14px'><button class='btn lime'>Save rules</button></div></form>"
              "<p class='muted' style='font-size:var(--t-sm,13px);margin-top:10px'>People without two-step sign-in in a required role set it up at their next sign-in.</p></div>")
    labels = {"login": "Signed in", "login_code": "Asked for a sign-in code", "login_fail": "Failed sign-in", "signout": "Signed someone out", "reinvite": "Sent an invite again", "2fa_fail": "Wrong two-step code", "2fa_on": "Turned on two-step sign-in",
              "2fa_off": "Turned off two-step sign-in", "2fa_reset": "Reset two-step sign-in", "role": "Changed a role", "invite": "Added a team member",
              "disable": "Removed access", "enable": "Re-enabled access", "key": "Saved or removed a key", "export": "Exported data",
              "policy": "Changed sign-in rules", "reauth_fail": "Wrong password at re-check", "idle": "Signed out for inactivity"}
    log_rows = "".join("<tr><td class='muted'>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>" % (
        e(ts(r["at"])), e(r["actor"]), e(labels.get(r["kind"], r["kind"])), e(r["detail"] or "")) for r in team.recent_log(150))
    log_list = "".join("<tr><td class='muted'>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>" % (
        e(ts(r["at"])), e(r["actor"]), e(labels.get(r["kind"], r["kind"])), e(r["detail"] or "")) for r in team.recent_log(150))
    activity = ("<details class='pa-fold'><summary><b>Activity</b><span>Sign-ins and access changes · show</span></summary><div>"
                "<p class='muted' style='margin-top:0'>Nothing here can be edited or deleted.</p><table><thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead><tbody>"
                + (log_list or "<tr><td colspan='4' class='muted'>Nothing yet.</td></tr>") + "</tbody></table></div></details>")
    rules = ("<details class='pa-fold'><summary><b>Sign-in rules and your two-step</b><span>Optional extra protection · show</span></summary><div>"
             + account + policy + "</div></details>")
    return page("People and access", PA_CSS + header + _banner(ok, err)
                + "<div class='pa-head-row'>" + invite + "</div>" + team_card + activity + rules
                + "<p class='pa-note'>Changing a level or removing someone asks you to confirm with an emailed code. There is always at least one Owner.</p>", "/team")
