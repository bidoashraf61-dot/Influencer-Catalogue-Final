"""The Tenants page: which modules each client company has, and at what level.

Owners only — admins run the business, owners configure the platform. Every change is
written to the security log with who, when and what it was before, so a tenant's own
settings and an owner's override are told apart later.

The page shows every client, not only the ones with a row in `tenant_modules`: a client
nobody has configured is on `view` for everything, which is exactly how the product
worked before any of this existed.
"""
import db
import modules


def page_html(query=None):
    import views
    e, u = views.e, views.u
    query = query or {}
    codes = db.list_codes()
    stored = modules.all_levels()

    def opts(cur, key, cid):
        return "".join(
            "<option value='%s'%s>%s</option>" % (lv, " selected" if lv == cur else "", e(modules.LEVEL_LABEL[lv]))
            for lv in modules.LEVELS)

    head = "".join("<th>" + e(m["name"]) + "</th>" for m in modules.MODULES)
    rows = []
    for c in codes:
        cid = c["id"]
        have = dict({m["key"]: modules.DEFAULT for m in modules.MODULES}, **(stored.get(cid) or {}))
        cells = "".join(
            "<td><select name='lvl:%d:%s'>%s</select></td>" % (cid, m["key"], opts(have.get(m["key"], modules.DEFAULT), m["key"], cid))
            for m in modules.MODULES)
        rows.append(
            "<tr><td><b>" + e(c["label"]) + "</b><div class='muted'>"
            + ("%d selection%s · %d campaign%s" % (c["n_selections"], "" if c["n_selections"] == 1 else "s",
                                                   c["n_campaigns"], "" if c["n_campaigns"] == 1 else "s"))
            + "</div></td>" + cells + "</tr>")

    # Limits and branding: one row per tenant, the platform default showing through as the
    # placeholder so an empty box plainly means "whatever everyone else gets".
    setn = modules.all_settings()

    def fields(group, cid):
        have = setn.get(cid) or {}
        return "".join(
            "<td><input name='set:%d:%s' value='%s' placeholder='%s' size='%d'%s></td>"
            % (cid, f["key"], e(have.get(f["key"]) or ""), e(_default_hint(f)), 8 if f["kind"] == "int" else 14,
               " inputmode='numeric'" if f["kind"] == "int" else "")
            for f in group)

    def table(group, title, intro):
        head2 = "".join("<th title='%s'>%s%s</th>" % (e(f["help"]), e(f["label"]),
                                                      "" if f["enforced"] else " <span class='muted'>*</span>")
                        for f in group)
        body2 = "".join("<tr><td><b>" + e(c["label"]) + "</b></td>" + fields(group, c["id"]) + "</tr>" for c in codes)
        starred = [f for f in group if not f["enforced"]]
        foot = ("<p class='price-hint'>* recorded, not enforced yet: "
                + e(", ".join(f["label"].lower() for f in starred)) + ".</p>") if starred else ""
        return ("<div class='card'><div class='hd'><h2>" + e(title) + "</h2></div>"
                "<p class='sec-desc'>" + intro + "</p>"
                "<table class='tbl'><thead><tr><th>Client</th>" + head2 + "</tr></thead><tbody>"
                + (body2 or "<tr><td>No clients yet.</td></tr>") + "</tbody></table>" + foot + "</div>")

    legend = "".join("<li><b>%s</b> — %s</li>" % (e(modules.LEVEL_LABEL[lv]), e(modules.LEVEL_HELP[lv]))
                     for lv in modules.LEVELS)
    what = "".join("<li><b>%s</b> — %s</li>" % (e(m["name"]), e(m["what"])) for m in modules.MODULES)

    note = ""
    if query.get("ok"):
        note = "<div class='ok'>" + e(query.get("ok")) + "</div>"
    elif query.get("e"):
        note = "<div class='err'>" + e(query.get("e")) + "</div>"

    body = (
        "<div class='card'><div class='hd'><h2>Tenants</h2></div>"
        + note +
        "<p class='sec-desc'>Each client company is a tenant. Set what each of them has; the core — "
        "the roster, selections and quotes — is always on and is not listed here. "
        "HelloVoice always sees everything, whatever is set below.</p>"
        "<div class='row' style='gap:28px;flex-wrap:wrap;margin-bottom:14px'>"
        "<ul class='muted' style='margin:0'>" + what + "</ul>"
        "<ul class='muted' style='margin:0'>" + legend + "</ul></div>"
        "<form method='post' action='" + u("/tenants/save") + "'>"
        "<table class='tbl'><thead><tr><th>Client</th>" + head + "</tr></thead>"
        "<tbody>" + ("".join(rows) or "<tr><td colspan='9'>No clients yet.</td></tr>") + "</tbody></table>"
        "<p class='price-hint'>Manage is stored but still behaves as view: the screens a tenant would "
        "add their own posts and competitors with are the next slice.</p>"
        "</div>"
        + table(modules.LIMITS, "Limits and credits",
                "Empty means the platform default. A cap counts what they have now and refuses the next one.")
        + table(modules.BRAND, "Branding",
                "What a tenant is called and coloured on their own report and app.")
        + "<div style='margin:14px 0 40px'><button class='btn'>Save everything</button></div></form>")
    return views.page("Tenants", body, "/tenants")


def _default_hint(f):
    """What shows through an empty box: the platform default, in words."""
    if f["key"] == "credits_month":
        import db as _db
        return str(_db.setting("monthly_credits", 0) or 0)
    return "no limit" if f["kind"] == "int" else "default"


def save(form, by, ip=None):
    """Apply the posted levels. Returns a sentence for the page."""
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
