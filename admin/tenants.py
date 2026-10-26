"""The Tenants page: which modules each client company has, at what level, and inside what caps.

Owners only — admins run the business, owners configure the platform. Every change is written to
the security log with who, when and the value it replaced.

One company, one block. A company usually signs in under several emails, and each of those is its
own `codes` row with its own selections and campaigns, so the controls stay per account; the block
simply gathers them under the company's name and keeps them folded away until wanted. Companies are
matched on a flattened name, so "Blue holding" and "Blueholding" are one company, and a passcode
with no account behind it is grouped by its own label.
"""
import re

import db
import modules


def _key(name):
    """What makes two spellings the same company."""
    return re.sub(r"[^a-z0-9]+", "", str(name or "").lower()) or "—"


def _groups(codes):
    """[(company, [code rows])], companies alphabetical, biggest account first inside."""
    import portal
    out, names = {}, {}
    for c in codes:
        u = portal.user_for_code(c["id"])
        raw = (u["company"] if u is not None and u["company"] else "") or c["label"]
        k = _key(raw)
        names.setdefault(k, {}).setdefault(raw, 0)
        names[k][raw] += 1
        out.setdefault(k, []).append((c, u))
    rows = []
    for k, members in out.items():
        best = sorted(names[k].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        members.sort(key=lambda m: -(m[0]["n_selections"] + m[0]["n_campaigns"]))
        rows.append((best, members))
    rows.sort(key=lambda r: r[0].lower())
    return rows


def _who(code, user):
    """How one account reads inside its company: the person, then what they hold."""
    import views
    e = views.e
    who = (user["email"] if user is not None else "") or code["label"]
    who = re.sub(r"^Client:\s*", "", who)
    n = "%d selection%s · %d campaign%s" % (code["n_selections"], "" if code["n_selections"] == 1 else "s",
                                            code["n_campaigns"], "" if code["n_campaigns"] == 1 else "s")
    return "<b>" + e(who) + "</b><div class='muted'>" + e(n) + "</div>"


def page_html(query=None):
    import views
    e, u = views.e, views.u
    query = query or {}
    groups = _groups(db.list_codes())
    stored, setn = modules.all_levels(), modules.all_settings()

    def mark(m, h):
        return ("<img src='" + e(m.get("logo") or "") + "' alt='" + e(m["name"]) + "' height='" + str(h) +
                "' style='display:block;margin:0 auto 2px;height:" + str(h) + "px;width:auto'>") if m.get("logo") else ""

    def spent(cid):
        try:
            import competitors
            v = competitors.spend_month(cid)
        except Exception:
            return ""
        return " <span class='muted'>$%.2f used</span>" % v if v else ""

    def level_cells(cid):
        have = dict({m["key"]: modules.DEFAULT for m in modules.MODULES}, **(stored.get(cid) or {}))
        out = ""
        for m in modules.MODULES:
            cur = have.get(m["key"], modules.DEFAULT)
            out += ("<td data-l=\"%s\"><select name='lvl:%d:%s'>%s</select></td>"
                    % (e(m["name"]), cid, m["key"], "".join(
                        "<option value='%s'%s>%s</option>" % (lv, " selected" if lv == cur else "", e(modules.LEVEL_LABEL[lv]))
                        for lv in modules.LEVELS)))
        return out

    def field_cells(group, cid):
        have = setn.get(cid) or {}
        return "".join(
            "<td data-l=\"%s\"><input name='set:%d:%s' value='%s' placeholder='%s' size='%d'%s>%s</td>"
            % (e(f["label"]), cid, f["key"], e(have.get(f["key"]) or ""), e(_default_hint(f)), 9 if f["kind"] == "int" else 14,
               " inputmode='numeric'" if f["kind"] == "int" else "",
               spent(cid) if f["key"] == "spend_month" else "")
            for f in group)

    def summary_of(members):
        """What the fold says without being opened: the levels inside, and how many accounts."""
        seen = []
        for code, _ in members:
            have = dict({m["key"]: modules.DEFAULT for m in modules.MODULES}, **(stored.get(code["id"]) or {}))
            seen.append(tuple(have[m["key"]] for m in modules.MODULES))
        n = len(members)
        who = "%d account%s" % (n, "" if n == 1 else "s")
        if len(set(seen)) == 1:
            lv = " · ".join("%s: %s" % (m["name"].replace("Helvi ", ""), modules.LEVEL_LABEL[l])
                            for m, l in zip(modules.MODULES, seen[0]))
            return who + " · " + lv
        return who + " · mixed levels"

    def block(title, intro, head, body_for):
        out = []
        for company, members in groups:
            rows = "".join("<tr><td>" + _who(c, usr) + "</td>" + body_for(c["id"]) + "</tr>" for c, usr in members)
            out.append(
                "<details class='tn-co'" + (" open" if len(members) == 1 and len(groups) < 4 else "") + ">"
                "<summary><b>" + e(company) + "</b> <span class='muted'>" + e(summary_of(members)) + "</span></summary>"
                "<table class='tbl'><thead><tr><th>Account</th>" + head + "</tr></thead><tbody>" + rows + "</tbody></table>"
                "</details>")
        return ("<div class='card'><div class='hd'><h2>" + e(title) + "</h2>"
                "<div><button type='button' class='btn tiny ghost' data-fold='open'>Expand all</button> "
                "<button type='button' class='btn tiny ghost' data-fold='close'>Collapse all</button></div></div>"
                "<p class='sec-desc'>" + intro + "</p>" + ("".join(out) or "<p>No clients yet.</p>") + "</div>")

    note = ""
    if query.get("ok"):
        note = "<div class='ok'>" + e(query.get("ok")) + "</div>"
    elif query.get("e"):
        note = "<div class='err'>" + e(query.get("e")) + "</div>"

    legend = "".join("<li><b>%s</b> — %s</li>" % (e(modules.LEVEL_LABEL[lv]), e(modules.LEVEL_HELP[lv]))
                     for lv in modules.LEVELS)
    what = "".join(
        "<li style='display:flex;align-items:center;gap:10px;margin-bottom:6px'>%s<span><b>%s</b> — %s</span></li>"
        % (mark(m, 28).replace("margin:0 auto 2px", "margin:0"), e(m["name"]), e(m["what"]))
        for m in modules.MODULES)
    mod_head = "".join("<th style='text-align:center'>" + mark(m, 30) + e(m["name"]) + "</th>" for m in modules.MODULES)

    body = (
        "<div class='card'><div class='hd'><h2>Tenants</h2></div>" + note +
        "<p class='sec-desc'>Each client company is a tenant, with every account they sign in under folded "
        "beneath it. The core — the roster, selections and quotes — is always on and is not listed here. "
        "HelloVoice always sees everything, whatever is set below.</p>"
        "<div class='row tn-key' style='gap:22px;flex-wrap:wrap'>"
        "<ul class='muted' style='margin:0;min-width:0'>" + what + "</ul>"
        "<ul class='muted' style='margin:0;min-width:0'>" + legend + "</ul></div></div>"
        "<form method='post' action='" + u("/tenants/save") + "'>"
        + block("Modules", "What each account has. Manage is stored but still behaves as view: the screens a "
                           "tenant would add their own posts and competitors with are the next slice.",
                mod_head, level_cells)
        + block("Limits and credits", "Empty means the platform default. A cap counts what they have now and "
                                      "refuses the next one.",
                "".join("<th title='%s'>%s%s</th>" % (e(f["help"]), e(f["label"]), "" if f["enforced"] else " <span class='muted'>*</span>")
                        for f in modules.LIMITS),
                lambda cid: field_cells(modules.LIMITS, cid))
        + "<p class='price-hint'>* recorded, not enforced yet: "
        + e(", ".join(f["label"].lower() for f in modules.LIMITS if not f["enforced"])) + ".</p>"
        + block("Branding", "What a tenant is called and coloured on their own report and app.",
                "".join("<th title='%s'>%s</th>" % (e(f["help"]), e(f["label"])) for f in modules.BRAND),
                lambda cid: field_cells(modules.BRAND, cid))
        + "<div style='margin:14px 0 40px'><button class='btn'>Save everything</button></div></form>"
        + """<style>
  .tn-co { border:1px solid var(--line,#e7e4dd); border-radius:12px; margin-bottom:8px; background:#fff }
  .tn-co > summary { cursor:pointer; padding:11px 14px; list-style:none; display:flex; gap:10px;
                     align-items:baseline; flex-wrap:wrap; border-radius:12px }
  .tn-co > summary::-webkit-details-marker { display:none }
  .tn-co > summary::before { content:'▸'; color:#9a9a9a; font-size:12px }
  .tn-co[open] > summary::before { content:'▾' }
  .tn-co > summary:hover { background:#faf8f3 }
  .tn-co table { margin:0 14px 12px }
  /* A phone cannot hold three columns of controls, so each account becomes a stacked block and
     every cell carries the column's name with it (Bido, 26 Oct 2026). */
  @media (max-width: 720px) {
    /* .row is a two-column grid at this width; the key reads better as one. */
    .tn-key { grid-template-columns: 1fr }
    .card { padding: 16px }
    .tn-co > summary { padding:10px 12px }
    .tn-co table, .tn-co tbody, .tn-co tr, .tn-co td { display:block; width:auto }
    .tn-co thead { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0) }
    .tn-co table { margin:0 12px 10px }
    .tn-co tr { padding:10px 0; border-bottom:1px solid var(--line,#e7e4dd) }
    .tn-co tr:last-child { border-bottom:0 }
    .tn-co td { padding:6px 0 0 }
    .tn-co td[data-l]::before { content:attr(data-l); display:block; font-size:11px; letter-spacing:.06em;
                                text-transform:uppercase; color:#8a8a8a; margin-bottom:3px }
    .tn-co td select, .tn-co td input { width:100%; max-width:none; box-sizing:border-box }
  }
</style>
<script>
  // Expand all / Collapse all, per card: the folds are plain <details>, so nothing else is needed.
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('[data-fold]');
    if (!b) return;
    var card = b.closest('.card');
    Array.prototype.forEach.call((card || document).querySelectorAll('details.tn-co'), function (d) {
      d.open = b.getAttribute('data-fold') === 'open';
    });
  });
</script>""")
    return views.page("Tenants", body, "/tenants")


def _default_hint(f):
    """What shows through an empty box: the platform default, in words."""
    if f["key"] == "credits_month":
        return str(db.setting("monthly_credits", 0) or 0)
    return "no limit" if f["kind"] == "int" else "default"


def save(form, by, ip=None):
    """Apply the posted levels and settings. Returns a sentence for the page."""
    import team
    changed = []
    for name, val in form.items():
        if name.startswith("set:"):
            try:
                _, cid, key = name.split(":", 2)
                cid = int(cid)
            except ValueError:
                continue
            v = val[0] if isinstance(val, list) else val
            was = (modules.settings(cid).get(key) or "")
            if (v or "").strip() == was:
                continue
            if modules.set_value(cid, key, v, by) is None:
                continue
            changed.append((cid, key, was or "default", (v or "").strip() or "default"))
            continue
        if not name.startswith("lvl:"):
            continue
        try:
            _, cid, key = name.split(":", 2)
            cid = int(cid)
        except ValueError:
            continue
        val = val[0] if isinstance(val, list) else val
        was = modules.level(cid, key)
        if val == was or modules.set_level(cid, key, val, by) is None:
            continue
        changed.append((cid, key, was, val))

    for cid, key, was, now_ in changed:
        team.log("tenant_config", by, "code %d · %s · %s -> %s" % (cid, key, was, now_), ip)
        if key == "credits_month":
            _apply_credits(cid, now_)
    if not changed:
        return "Nothing changed."
    return "Saved %d change%s." % (len(changed), "" if len(changed) == 1 else "s")


def _apply_credits(code_id, val):
    """Monthly credits are already a per-client field the refill reads (`users.monthly_credits`),
    so the panel writes there rather than growing a second allowance nobody enforces."""
    import portal
    u = portal.user_for_code(code_id)
    if u is None:
        return
    try:
        n = None if val in ("", "default", None) else max(0, int(val))
    except (TypeError, ValueError):
        return
    portal.update_profile(u["id"], monthly_credits=n)
