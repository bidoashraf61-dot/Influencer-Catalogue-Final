"""Rename a selection (portal item 173).

One rule for every door (the selection page, the client's Selections list, the admin
selections list, the Clients hub and Helvi's ``rename_selection`` tool):

    who may      HelloVoice (admin, or a key account manager on her own client's selection),
                 the selection's owner (the account it is filed under, or a shared code
                 HelloVoice linked onto that account), and someone HelloVoice invited to it
                 (they get the client's own controls). A colleague who can only look may not.
    the name     trimmed, inner whitespace collapsed, no < or >, 1 to 80 characters.
    recorded     one History entry ("Renamed selection A to B"), so an admin can undo it.

Only ``selections.name`` changes: campaigns, emails and the bell read the selection's
current name when they draw, so the new one shows everywhere from the next look. A quote
request found by the OLD name (legacy rows without ``request_id``) is pinned to the selection
first, so the rename never loses the selection's lifecycle.
"""
import re

import db
import history

MAX = 80


def clean(raw):
    """(name, None) or (None, reason). Reasons: "empty", "long"."""
    name = re.sub(r"[<>]", "", " ".join(str(raw if raw is not None else "").split())).strip()
    if not name:
        return None, "empty"
    if len(name) > MAX:
        return None, "long"
    return name, None


MESSAGES = {"empty": "Give the selection a name.",
            "long": "Keep the name to %d characters or fewer." % MAX,
            "forbidden": "Only the selection's owner, its account manager or HelloVoice can rename it.",
            "missing": "That selection no longer exists."}


def client_may(reader, sel, admin_code_id=None):
    """The client-side rule (reader = the code acting on the selection page or /account/).
    ``admin_code_id`` stands for HelloVoice: the server passes it when an admin, or a key account
    manager on her own client's selection, is the reader (``selection_viewer``)."""
    import portal
    if reader is None or sel is None:
        return False
    if admin_code_id is not None and int(reader) == int(admin_code_id):
        return True
    if db.selection_granted(sel["id"], reader):
        return True                    # invited with the client's own controls (owner rule 2026-10-15; coordinator 2026-10-20)
    if sel["code_id"] is None:
        return False                   # unfiled: nobody to call owner, so only HelloVoice
    return portal.owns(int(reader), sel["code_id"])


def _pin_request(conn, sel):
    if sel["request_id"] or sel["code_id"] is None:
        return
    r = conn.execute("SELECT id FROM requests WHERE code_id = ? AND selection_name = ? ORDER BY at DESC LIMIT 1",
                     (sel["code_id"], sel["name"])).fetchone()
    if r is not None:
        conn.execute("UPDATE selections SET request_id = ? WHERE id = ?", (r["id"], sel["id"]))


def apply(sel, raw, who=None, allow_deleted=False):
    """Rename ``sel`` (a row). Returns (row after, None) or (None, reason).
    ``who`` names the actor in History when the request did not set one (client requests).
    A selection the client deleted can still be renamed from the admin (``allow_deleted``)."""
    if sel is None or (not allow_deleted and "deleted_at" in sel.keys() and sel["deleted_at"]):
        return None, "missing"
    name, err = clean(raw)
    if err:
        return None, err
    if name == sel["name"]:
        return sel, None
    if who:
        history.set_actor(who)
    with history.tracked("selection", str(sel["id"]), "Renamed selection %s to %s" % (sel["name"], name)):
        with db.connect() as conn:
            _pin_request(conn, sel)
            conn.execute("UPDATE selections SET name = ?, updated_at = ? WHERE id = ?", (name, db.now(), sel["id"]))
    return db.selection(sel["id"]), None


# ------------------------------------------------------------- admin inline edit --
# The admin lists (Selections, the Clients hub panel) draw a selection's name with
# ``admin_name(...)``; /shell.js turns its pencil into an inline field that posts to
# /selections/rename with X-HV-Rename: 1 (JSON back). Without JavaScript the name is a plain link.

def admin_name(sid, name, href, url, link_cls=""):
    """The name as a link, plus a Rename control for everyone but a read-only viewer."""
    import ui
    from html import escape as e
    link = "<a href='%s'%s>%s</a>" % (e(href), (" class='%s'" % e(link_cls)) if link_cls else "", e(name))
    if getattr(ui._role, "value", "owner") == "viewer":
        return link
    return ("<span class='hv-arn' data-hv-rename='%d' data-url='%s' data-name=\"%s\">%s"
            "<button type='button' class='hv-arn-btn' aria-label=\"Rename %s\" title='Rename'>%s</button></span>") % (
        int(sid), e(url), e(name), link, e(name), ui.icon("edit", 15))


ADMIN_JS = r"""
(function(){
  if (window.__hvArn) return; window.__hvArn = 1;
  var MAX = %d;
  var css = ".hv-arn{display:inline-flex;align-items:center;gap:4px;max-width:100%%;flex-wrap:wrap}"
    + ".hv-arn-btn{display:inline-grid;place-items:center;width:32px;height:32px;padding:0;border:1px solid transparent;border-radius:999px;background:none;color:inherit;opacity:.55;cursor:pointer;flex:none}"
    + ".hv-arn-btn:hover{opacity:1;border-color:rgba(18,18,18,.2);background:#f3eee8}.hv-arn-btn:focus-visible{opacity:1;outline:3px solid #ee1515;outline-offset:2px}"
    + "@media (hover:none){.hv-arn-btn{width:44px;height:44px;opacity:.8}}"
    + ".hv-arn-btn[hidden],.hv-arn a[hidden]{display:none}"
    + ".hv-arn-f{display:flex;flex-wrap:wrap;align-items:center;gap:6px;flex:1 0 100%%;width:100%%;min-width:240px;margin:2px 0}"
    + ".hv-arn-f input{flex:1 1 200px;min-width:0;font:inherit;font-weight:600;font-size:16px;padding:7px 10px;border:1.5px solid #121212;border-radius:10px;background:#fff;color:#121212}"
    + ".hv-arn-f input:focus{outline:none;box-shadow:0 0 0 3px #e8ff76}.hv-arn-f input[aria-invalid=true]{border-color:#c01010}"
    + ".hv-arn-f .hv-arn-n{font-size:12px;color:#5c5c5c;font-variant-numeric:tabular-nums}.hv-arn-f .hv-arn-n.over{color:#c01010;font-weight:700}"
    + ".hv-arn-e{flex:1 0 100%%;margin:0;color:#c01010;font-size:13px;font-weight:600}.hv-arn-e[hidden]{display:none}"
    + ".hv-arn-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}";
  var st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
  function say(t){ var l=document.getElementById("hv-arn-live"); if(!l){l=document.createElement("p");l.id="hv-arn-live";l.className="hv-arn-sr";l.setAttribute("role","status");document.body.appendChild(l);} l.textContent=""; setTimeout(function(){l.textContent=t;},30); }
  function open(box){
    if (box.querySelector(".hv-arn-f")) return;
    var a = box.querySelector("a"), btn = box.querySelector(".hv-arn-btn"), was = box.getAttribute("data-name") || (a ? a.textContent : "");
    var f = document.createElement("form"); f.className = "hv-arn-f"; f.noValidate = true;
    f.innerHTML = "<input type='text' autocomplete='off' enterkeyhint='done' aria-label='Selection name'>"
      + "<button type='submit' class='btn small lime'>Save</button><button type='button' class='btn small ghost'>Cancel</button>"
      + "<span class='hv-arn-n' aria-hidden='true'></span><p class='hv-arn-e' role='alert' hidden></p>";
    var inp = f.querySelector("input"), save = f.querySelector("[type=submit]"), cancel = f.querySelector("[type=button]"),
        n = f.querySelector(".hv-arn-n"), err = f.querySelector(".hv-arn-e");
    inp.value = was; inp.maxLength = MAX + 20;
    function tick(){ var k = MAX - inp.value.trim().replace(/\s+/g," ").length; n.textContent = k < 0 ? (-k) + " too many" : k + " left"; n.classList.toggle("over", k < 0); err.hidden = true; inp.removeAttribute("aria-invalid"); }
    function close(back){ f.remove(); if (a) a.hidden = false; btn.hidden = false; document.removeEventListener("keydown", key, true); if (back) btn.focus(); }
    function fail(m){ err.textContent = m; err.hidden = false; inp.setAttribute("aria-invalid","true"); inp.disabled = save.disabled = cancel.disabled = false; save.textContent = "Save"; inp.focus(); }
    function key(e){ if (e.key === "Escape" && f.contains(document.activeElement)) { e.preventDefault(); e.stopImmediatePropagation(); close(true); } }
    f.addEventListener("submit", function(e){
      e.preventDefault();
      var name = inp.value.trim().replace(/\s+/g," ");
      if (!name) return fail("Give the selection a name.");
      if (name.length > MAX) return fail("Keep the name to " + MAX + " characters or fewer.");
      if (name === was) return close(true);
      inp.disabled = save.disabled = cancel.disabled = true; save.textContent = "Saving";
      fetch(box.getAttribute("data-url"), { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-HV-Rename": "1" },
        body: "id=" + encodeURIComponent(box.getAttribute("data-hv-rename")) + "&name=" + encodeURIComponent(name) })
      .then(function(r){ return r.json().catch(function(){ return { ok: false, message: r.status === 403 ? "You can't rename this selection." : "Couldn't rename it. Reload the page and try again." }; }); },
            function(){ return { ok: false, message: "Could not reach the server. Please try again." }; })
      .then(function(b){
        if (!b || !b.ok) return fail((b && b.message) || "Couldn't rename it.");
        box.setAttribute("data-name", b.name); if (a) a.textContent = b.name; btn.setAttribute("aria-label", "Rename " + b.name);
        document.querySelectorAll("[data-hv-rename='" + box.getAttribute("data-hv-rename") + "']").forEach(function(o){
          if (o === box) return; o.setAttribute("data-name", b.name); var oa = o.querySelector("a"); if (oa) oa.textContent = b.name; });
        close(true); say("Renamed to " + b.name + ". You can undo it from History.");
      });
    });
    cancel.addEventListener("click", function(){ close(true); });
    inp.addEventListener("input", tick);
    document.addEventListener("keydown", key, true);
    if (a) a.hidden = true; btn.hidden = true;
    box.appendChild(f); tick(); inp.focus(); inp.select();
  }
  document.addEventListener("click", function(e){
    var b = e.target.closest && e.target.closest(".hv-arn-btn");
    if (!b) return; e.preventDefault(); e.stopPropagation(); open(b.closest(".hv-arn"));
  });
})();
""" % MAX


def register_admin_js():
    import ui
    ui.add_shell_js(ADMIN_JS)
