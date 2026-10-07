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


def reauth_page(nxt, totp_on, again=False, error=None):
    body = (ui.header("Confirm it is you", "For keys, exports and team changes we ask for your password again (once every 10 minutes).")
            + (("<div class='err'>" + e(error) + "</div>") if error else "")
            + ("<div class='note'>After confirming, press the button you pressed again; the change was not made yet.</div>" if again else "")
            + "<div class='card' style='max-width:460px'><form method='post' action='" + u("/reauth") + "'>"
            "<input type='hidden' name='next' value='" + e(nxt) + "'>"
            "<label for='re-pw'>Password</label><input id='re-pw' name='password' type='password' autocomplete='current-password' required autofocus>"
            + ("<label for='re-otp' style='margin-top:12px'>Code from your authenticator app</label>"
               "<input id='re-otp' name='code' inputmode='numeric' autocomplete='one-time-code' maxlength='6' required>" if totp_on else "")
            + "<button class='btn lime' style='margin-top:14px'>Confirm</button></form></div>")
    return page("Confirm it is you", body, "/team")


def forbidden_page(role):
    body = (ui.header("Not available for your role", "You are signed in as <b>%s</b>. %s" % (e(team.ROLE_LABEL.get(role, role)), e(team.ROLE_HELP.get(role, ""))))
            + ui.empty("key", "Ask an owner if you need this", "An owner can change your role on the Team & security page.",
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

    # ---- team (owners)
    rows = ""
    for a in team.list_admins():
        r = team.role_of(a)
        role_sel = ("<form method='post' action='" + u("/team/role") + "' class='inline'>" + hid("id", a["id"])
                    + "<select name='role' aria-label='Role for " + e(a["email"]) + "' onchange='this.form.submit()'>"
                    + "".join("<option value='%s'%s>%s</option>" % (k, " selected" if k == r else "", e(team.ROLE_LABEL[k])) for k in team.ROLES)
                    + "</select></form>")
        actions = ""
        if a["id"] != who["admin_id"]:
            if a["disabled_at"]:
                actions += ("<form method='post' action='" + u("/team/enable") + "' class='inline'>" + hid("id", a["id"]) + "<button class='btn small'>Re-enable</button></form>")
            else:
                actions += ("<form method='post' action='" + u("/team/disable") + "' class='inline' data-confirm='Remove " + e(a["email"])
                            + " from the admin? They are signed out at once.'>" + hid("id", a["id"]) + "<button class='btn small danger'>Remove access</button></form>")
            if a["totp_on"]:
                actions += (" <form method='post' action='" + u("/team/reset2fa") + "' class='inline' data-confirm='Reset two-step sign-in for "
                            + e(a["email"]) + "? They set it up again at their next sign-in.'>" + hid("id", a["id"]) + "<button class='btn small ghost'>Reset two-step</button></form>")
        rows += ("<tr><td><strong>%s</strong><br><span class='muted'>%s</span></td><td>%s</td><td>%s</td><td class='muted'>%s</td><td class='right'>%s</td></tr>" % (
            e(a["name"] or a["email"].split("@")[0]), e(a["email"]), role_sel if a["id"] != who["admin_id"] else e(team.ROLE_LABEL[r]) + " (you)",
            ("<span class='pill live'>On</span>" if a["totp_on"] else "<span class='pill warn'>Off</span>") + (" <span class='pill dead'>removed</span>" if a["disabled_at"] else ""),
            e(ago(a["active_at"] or a["last_login_at"]) if (a["active_at"] or a["last_login_at"]) else "never"), actions))
    invited = ("<div class='note'><strong>" + e(new_member[0]) + " can now sign in.</strong> Give them this one-time password and ask them to change it "
               "(Home → Your account): <code>" + e(new_member[1]) + "</code></div>") if new_member else ""
    team_card = ("<div class='card'><h2>Team</h2>" + invited
                 + "<table><thead><tr><th>Person</th><th>Role</th><th>Two-step</th><th>Last active</th><th></th></tr></thead><tbody>" + rows + "</tbody></table>"
                 "<details style='margin-top:14px'><summary class='btn small'>Add a team member</summary><form method='post' action='" + u("/team/invite") + "' class='row' style='margin-top:12px'>"
                 "<div><label for='in-email'>Email</label><input id='in-email' name='email' type='email' required></div>"
                 "<div><label for='in-name'>Name</label><input id='in-name' name='name'></div>"
                 "<div><label for='in-role'>Role</label><select id='in-role' name='role'>" + "".join(
                     "<option value='%s'%s>%s</option>" % (k, " selected" if k == "kam" else "", e(team.ROLE_LABEL[k])) for k in team.ROLES) + "</select></div>"
                 "<div><button class='btn lime'>Add</button></div></form></details>"
                 "<dl class='roles' style='margin-top:16px;font-size:var(--t-sm,13px)'>" + "".join(
                     "<dt><b>%s</b></dt><dd class='muted' style='margin:0 0 6px'>%s</dd>" % (e(team.ROLE_LABEL[k]), e(team.ROLE_HELP[k])) for k in team.ROLES) + "</dl></div>")
    req = team.required_roles()
    policy = ("<div class='card'><h2>Sign-in rules</h2><form method='post' action='" + u("/team/policy") + "'>"
              "<p class='muted'>Two-step sign-in is required for:</p><div style='display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px'>" + "".join(
                  "<label style='display:flex;gap:8px;align-items:center;font-weight:500'><input type='checkbox' name='req' value='%s'%s> %s</label>"
                  % (k, " checked" if k in req else "", e(team.ROLE_LABEL[k])) for k in team.ROLES) + "</div>"
              "<label for='idle'>Sign out after this many minutes without activity</label>"
              "<input id='idle' name='idle' type='number' min='5' max='1440' value='" + str(team.idle_minutes()) + "' style='max-width:140px'>"
              "<div style='margin-top:14px'><button class='btn lime'>Save rules</button></div></form>"
              "<p class='muted' style='font-size:var(--t-sm,13px);margin-top:10px'>People without two-step sign-in in a required role set it up at their next sign-in.</p></div>")
    labels = {"login": "Signed in", "login_fail": "Wrong password", "2fa_fail": "Wrong two-step code", "2fa_on": "Turned on two-step sign-in",
              "2fa_off": "Turned off two-step sign-in", "2fa_reset": "Reset two-step sign-in", "role": "Changed a role", "invite": "Added a team member",
              "disable": "Removed access", "enable": "Re-enabled access", "key": "Saved or removed a key", "export": "Exported data",
              "policy": "Changed sign-in rules", "reauth_fail": "Wrong password at re-check", "idle": "Signed out for inactivity"}
    log_rows = "".join("<tr><td class='muted'>%s</td><td>%s</td><td>%s</td><td class='muted'>%s</td></tr>" % (
        e(ts(r["at"])), e(r["actor"]), e(labels.get(r["kind"], r["kind"])), e(r["detail"] or "")) for r in team.recent_log(150))
    log_card = ("<div class='card'><h2>Security log</h2><p class='sec-desc'>Sign-ins, failures, two-step changes, roles, keys and exports. Nothing here can be edited or deleted.</p>"
                "<table><thead><tr><th>When</th><th>Who</th><th>What</th><th>Detail</th></tr></thead><tbody>"
                + (log_rows or "<tr><td colspan='4' class='muted'>Nothing yet.</td></tr>") + "</tbody></table></div>")
    return page("Team & security", ui.header("Team & security", "Who can use the admin, what each role may do, and how sign-in is protected.")
                + _banner(ok, err) + account + team_card + policy + log_card, "/team")
