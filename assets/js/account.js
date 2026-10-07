/* The client's own space (/account/): drawn from /api/account.
 *
 * Tabs by hash: #home (default), #selections, #campaigns, #settings, and
 * #settings/<section> for profile, team, notifications or privacy.
 *
 * Home leads with the live campaign as a scorebug, in the campaign report's
 * own vocabulary (verdict stamp, red LIVE dot, scoreline, Strong / Fair / Low
 * signals), so the account and the report read as one product.
 *
 * Everything from the server goes on the page with textContent, never HTML.
 */
(function () {
  "use strict";

  var CFG = window.CATALOGUE_CONFIG || {};
  var API = (CFG.api != null ? CFG.api : "/admin").replace(/\/$/, "");
  var ROOT = "../";
  var DATA = null;
  var FLASH = null;           // a message that must survive the next re-render

  function $(id) { return document.getElementById(id); }
  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v == null || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "html") el.innerHTML = v;           // only our own static strings
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
  }
  function api(method, path, body) {
    return fetch(API + path, {
      method: method, credentials: "include", cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (b) { return { s: r.status, b: b }; });
    }, function () { return { s: 0, b: {} }; });
  }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  /* ------------------------------------------------------------ formatting */

  function big(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function day(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  }
  function ago(ts) {
    if (!ts) return "";
    var s = Date.now() / 1000 - ts;
    if (s < 3600) return "just now";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
    return day(ts);
  }
  function initials(name) {
    return String(name || "").trim().split(/\s+/).slice(0, 2).map(function (w) { return w.charAt(0); }).join("").toUpperCase() || "?";
  }
  // The report's words: a signal is Strong / Fair / Low, a campaign is On track / Close to target / Behind target.
  var SIG = { good: "Strong", moderate: "Fair", low: "Low" };
  function sig(grade, label) {
    return h("span", { class: "ac-sig ac-sig--" + (grade || "none") }, label || SIG[grade] || "Too early");
  }
  function stamp(v) {
    return h("span", { class: "ac-verdict ac-verdict--" + (v.grade || "none") }, v.label || "Getting started");
  }
  // Posts against the calendar: how much of the plan is live versus how much of the campaign has run.
  function pace(c) {
    if (!c.planned || !c.starts_at || !c.ends_at) return null;
    var span = c.ends_at - c.starts_at;
    if (span <= 0) return null;
    var ran = Math.max(0, Math.min(1, (Date.now() / 1000 - c.starts_at) / span));
    var done = c.delivered / c.planned;
    if (done >= ran - .1) return { grade: "good", label: "On pace" };
    if (done >= ran - .3) return { grade: "moderate", label: "Slightly behind" };
    return { grade: "low", label: "Behind plan" };
  }
  function imgUrl(kind, v) { return API + "/api/me/image?k=" + kind + "&v=" + encodeURIComponent(v || ""); }
  function note(el, text, bad) { el.textContent = text || ""; el.className = "ac-note" + (bad ? " ac-note--bad" : ""); }

  /* ------------------------------------------------------------------ head */

  function face(el, u) {
    el.textContent = "";
    if (u.photo) el.appendChild(h("img", { src: imgUrl("photo", u.photo), alt: "" }));
    else el.appendChild(h("span", null, initials(u.name)));
  }

  // The header names the page and holds the tabs; who the client is lives on Home.
  function renderHead() {
    var ins = DATA.insights;
    $("ac-face").hidden = true;
    $("ac-logo").hidden = true;
    $("ac-name").textContent = "My account";
    $("ac-role").textContent = DATA.user.name || DATA.user.email;
    var bits = [];
    bits.push(ins.live_campaigns ? ins.live_campaigns + " campaign" + (ins.live_campaigns === 1 ? "" : "s") + " live" : "No live campaigns");
    bits.push(DATA.selections.length + " selection" + (DATA.selections.length === 1 ? "" : "s"));
    $("ac-status").textContent = bits.join(" · ");
    $("ac-who").hidden = false;
    $("ac-tabs").hidden = false;
  }

  /* ------------------------------------------------------------------ home */

  function scoreline(items) {
    var dl = h("dl", { class: "ac-scoreline" });
    items.forEach(function (it) {
      dl.appendChild(h("div", null, h("dt", null, it[0]), h("dd", null, it[1], it[2] ? h("small", null, it[2]) : null),
        it[3] ? h("div", { class: "ac-scoreline__sig" }, it[3]) : null));
    });
    return dl;
  }

  // The live campaign, as the report's scorebug: brands, LIVE, name, verdict, scoreline, one way in.
  function scorebug(c, more) {
    var u = DATA.user, p = pace(c);
    var brands = h("div", { class: "ac-bug__brands" });
    if (u.logo) { brands.appendChild(h("img", { src: imgUrl("logo", u.logo), alt: u.company || "" })); brands.appendChild(h("span", { class: "ac-bug__x", "aria-hidden": "true" }, "×")); }
    brands.appendChild(h("img", { class: "ac-bug__hv", src: ROOT + "assets/brand/logo.png", alt: "HelloVoice" }));
    return h("section", { class: "ac-bug", "aria-labelledby": "ac-bug-title" },
      h("div", { class: "ac-bug__top" }, brands,
        h("span", { class: "ac-live" }, "Live"),
        h("span", { class: "ac-muted" }, [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – "))),
      h("div", { class: "ac-bug__row" },
        h("h2", { class: "ac-bug__title", id: "ac-bug-title" }, c.name),
        stamp(c.verdict)),
      scoreline([
        ["Views", big(c.views), null, null],
        ["Reach", big(c.reach), null, h("span", { class: "ac-muted" }, "people reached")],
        ["Engagement", c.er != null ? c.er.toFixed(1) : "—", c.er != null ? "%" : null, c.er_grade ? sig(c.er_grade) : null],
        ["Posts live", String(c.delivered), c.planned ? "/" + c.planned : null, p ? sig(p.grade, p.label) : null]
      ]),
      h("div", { class: "ac-bug__go" },
        h("a", { class: "cat-btn cat-btn--lime", href: ROOT + "campaign/#t=" + encodeURIComponent(c.token) }, "Open the full report"),
        more ? h("a", { class: "ac-more", href: "#campaigns" }, more) : null));
  }

  function completionStrip() {
    var c = DATA.completion;
    if (!c || c.pct >= 100) return null;
    var key = "ac-strip:" + DATA.user.email;
    if (store(key) === String(c.missing.length)) return null;   // dismissed at this many steps
    var strip = h("div", { class: "ac-strip", role: "note" },
      h("span", { class: "ac-strip__meter", "aria-hidden": "true" }, h("i", { style: "width:" + c.pct + "%" })),
      h("span", null, h("b", null, c.missing.length + " step" + (c.missing.length === 1 ? "" : "s") + " to finish your profile"),
        " · " + c.missing.map(function (m) { return m.label.replace(/^Add (a |an |your )?/, ""); }).join(", ")),
      h("a", { href: "#settings/profile", "data-focus": c.missing[0].key }, "Finish →"),
      h("button", { class: "ac-strip__x", type: "button", "aria-label": "Hide this reminder", onclick: function () { store(key, String(c.missing.length)); strip.remove(); } }, "×"));
    return strip;
  }

  function attentionCard() {
    if (!DATA.attention.length) return null;
    var list = h("ul", { class: "ac-attn" });
    DATA.attention.forEach(function (a) {
      var label = h("span", null, a.text);
      list.appendChild(h("li", { class: "ac-attn__" + a.kind },
        h("span", { class: "ac-attn__dot", "aria-hidden": "true" }),
        a.href ? h("a", { href: ROOT + a.href }, label, h("span", { "aria-hidden": "true" }, " →")) : label));
    });
    return h("div", { class: "ac-card ac-card--attn" }, h("h2", { class: "ac-h2" }, "Needs your attention"), list);
  }

  function explainer() {
    return h("details", { class: "ac-explain" }, h("summary", null, "What these numbers mean"),
      h("dl", null,
        h("dt", null, "Views"), h("dd", null, "How many times the campaign's videos and posts were played or seen."),
        h("dt", null, "Reach"), h("dd", null, "How many different people saw them at least once."),
        h("dt", null, "Engagement"), h("dd", null, "Likes, comments, shares and saves as a share of views, graded against HelloVoice's benchmark for creators of the same size: Strong, Fair or Low."),
        h("dt", null, "Posts live"), h("dd", null, "Posts published so far against the plan, compared with how far into the campaign we are."),
        h("dt", null, "AI credits"), h("dd", null, "Used by the HELV Assistant for written shortlists and chat answers. Browsing, selections and reports never use credits.")));
  }

  function campaignCard(c) {
    var href = ROOT + "campaign/#t=" + encodeURIComponent(c.token);
    var dates = [day(c.starts_at), day(c.ends_at)].filter(Boolean).join(" – ");
    var p = pace(c);
    return h("a", { class: "ac-item ac-item--camp", href: href },
      h("div", { class: "ac-item__top" },
        c.status === "live" ? h("span", { class: "ac-live" }, "Live") : h("span", { class: "ac-status" }, c.status === "ended" ? "Ended" : c.status),
        h("span", { class: "ac-item__verdict ac-item__verdict--" + (c.verdict.grade || "none") }, c.verdict.label || "Getting started")),
      h("b", { class: "ac-item__name" }, c.name),
      h("span", { class: "ac-muted" }, dates),
      h("div", { class: "ac-item__nums" },
        h("span", null, h("b", null, big(c.views)), " views"),
        h("span", null, h("b", null, c.delivered + (c.planned ? "/" + c.planned : "")), " posts"),
        p && c.status === "live" ? sig(p.grade, p.label) : null),
      h("span", { class: "ac-item__go" }, "Open report →"));
  }

  function selectionCard(s) {
    return h("a", { class: "ac-item", href: ROOT + "selection/#s=" + encodeURIComponent(s.token) },
      h("span", { class: "ac-item__kicker" }, s.creators + " creator" + (s.creators === 1 ? "" : "s")),
      h("b", { class: "ac-item__name" }, s.name),
      h("span", { class: "ac-muted" }, "Updated " + ago(s.updated_at)),
      h("span", { class: "ac-item__go" }, "Open selection →"));
  }

  function empty(title, line, cta, href, go) {
    return h("div", { class: "ac-empty" }, h("b", null, title), h("p", null, line),
      cta ? (go ? h("button", { class: "cat-btn cat-btn--lime", type: "button", onclick: go }, cta)
                : h("a", { class: "cat-btn cat-btn--lime", href: href }, cta)) : null);
  }

  function section(title, link, items, emptyEl, sub) {
    return h("div", { class: "ac-sec" },
      h("div", { class: "ac-sec__hd" }, h("div", null, h("h2", { class: "ac-h2" }, title), sub ? h("p", { class: "ac-muted ac-sec__sub" }, sub) : null), link),
      items.length ? h("div", { class: "ac-grid" }, items) : emptyEl);
  }

  function talk() { if (window.hvPortal && window.hvPortal.talk) window.hvPortal.talk(); else location.href = ROOT; }

  function shortlistLine() {
    var i = DATA.insights;
    if (!i.shortlisted) return null;
    var tiers = Object.keys(i.tiers || {}).sort(function (a, b) { return i.tiers[b] - i.tiers[a]; })
      .slice(0, 3).map(function (t) { return t + ": " + i.tiers[t]; }).join(" · ");
    return i.shortlisted + " creators shortlisted" + (tiers ? " — " + tiers : "");
  }

  function contactCard() {
    var who = DATA.kam || "Your HelloVoice team";
    return h("div", { class: "ac-card ac-contact" },
      h("div", null, h("span", { class: "ac-label" }, DATA.kam ? "Your account manager" : "Your contact"),
        h("b", { class: "ac-contact__name" }, who),
        h("p", { class: "ac-muted" }, "Questions about a selection, a quote or a campaign? Message here and it reaches " + (DATA.kam ? DATA.kam.split(" ")[0] : "the team") + " with the context.")),
      h("button", { class: "cat-btn cat-btn--lime", type: "button", onclick: talk }, "Message " + (DATA.kam ? DATA.kam.split(" ")[0] : "the team")));
  }

  // Home is the client's own profile, nothing else: who they are, how to
  // reach them, their contact at HelloVoice, their credits and team.
  function renderHome() {
    var p = $("tab-home");
    p.textContent = "";
    var u = DATA.user;
    add(p, completionStrip());
    var facts = [["Email", u.email], ["Phone", u.phone], ["Job title", u.job_title], ["Company", u.company],
                 ["Member since", u.created_at ? day(u.created_at) : null],
                 ["Account manager", DATA.kam || "Your HelloVoice team"],
                 ["AI credits", DATA.credits != null ? DATA.credits + " left" + (DATA.monthly_credits ? " · " + DATA.monthly_credits + " added monthly" : "") : null]];
    var dl = h("dl", { class: "ac-facts" });
    facts.forEach(function (f) {
      dl.appendChild(h("div", null, h("dt", null, f[0]), h("dd", { class: f[1] ? null : "is-empty" }, f[1] || "Not added yet")));
    });
    var faceEl = h("div", { class: "ac-profile__face", "aria-hidden": "true" });
    face(faceEl, u);
    add(p, h("section", { class: "ac-profile", "aria-labelledby": "ac-profile-name" },
      h("div", { class: "ac-profile__who" }, faceEl,
        h("div", null, h("h2", { class: "ac-profile__name", id: "ac-profile-name" }, u.name || u.email),
          h("p", { class: "ac-muted" }, [u.job_title, u.company].filter(Boolean).join(" · ") || u.email)),
        u.logo ? h("div", { class: "ac-profile__logo" }, h("img", { src: imgUrl("logo", u.logo), alt: u.company || "Company logo" })) : null),
      dl,
      h("div", { class: "ac-row" },
        h("a", { class: "cat-btn cat-btn--lime", href: "#settings/profile" }, "Edit profile"),
        h("button", { class: "ac-btn-line", type: "button", onclick: talk }, "Message " + (DATA.kam ? DATA.kam.split(" ")[0] : "the team")))));
    if (DATA.team.length) {
      var list = h("ul", { class: "ac-people" });
      DATA.team.forEach(function (t) {
        list.appendChild(h("li", null, h("span", { class: "ac-people__ini", "aria-hidden": "true" }, initials(t.name)),
          h("div", null, h("b", null, t.name), t.job_title ? h("span", { class: "ac-muted" }, t.job_title) : null)));
      });
      add(p, h("div", { class: "ac-sec" }, h("div", { class: "ac-sec__hd" }, h("h2", { class: "ac-h2" }, "Your team"),
        h("a", { class: "ac-more", href: "#settings/team" }, "Invite a colleague →")), list));
    }
  }

  function renderSelections() {
    var p = $("tab-selections");
    p.textContent = "";
    add(p, section("My selections", h("a", { class: "ac-more", href: ROOT + "#cat-roster" }, "Browse creators →"),
      DATA.selections.map(selectionCard),
      empty("No selections yet", "Pick creators in the catalogue and review them as a selection.", "Browse creators", ROOT + "#cat-roster"),
      shortlistLine()));
  }

  // Campaigns: each live campaign as the report's scorebug, then the rest.
  function renderCampaigns() {
    var p = $("tab-campaigns");
    p.textContent = "";
    var live = DATA.campaigns.filter(function (c) { return c.status === "live"; });
    var rest = DATA.campaigns.filter(function (c) { return c.status !== "live"; });
    live.forEach(function (c) { add(p, scorebug(c, null)); });
    if (live.length) add(p, explainer());
    add(p, attentionCard());
    if (!live.length || rest.length) {
      add(p, section(live.length ? "Earlier campaigns" : "My campaigns", null, rest.map(campaignCard),
        empty("No campaigns yet", "When we run a campaign for you, its live results and report appear here.", "Ask for a proposal", null, talk)));
    }
  }

  /* -------------------------------------------------------------- settings */

  var SET_TABS = [["profile", "Profile & company"], ["team", "Team"], ["notifications", "Notifications"], ["privacy", "Privacy & data"]];

  function readImage(file, kind) {
    // The photo is cropped to a centred square; the logo keeps its shape.
    return new Promise(function (resolve, reject) {
      if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { reject("Please choose a JPG, PNG or WebP image."); return; }
      var img = new Image();
      img.onload = function () {
        var max = kind === "photo" ? 512 : 600;
        var sw = img.naturalWidth, sh = img.naturalHeight, sx = 0, sy = 0, w, hgt;
        if (kind === "photo") { var side = Math.min(sw, sh); sx = (sw - side) / 2; sy = (sh - side) / 2; sw = sh = side; w = hgt = Math.min(max, side); }
        else { var k = Math.min(1, max / Math.max(sw, sh)); w = Math.round(sw * k); hgt = Math.round(sh * k); }
        var cv = document.createElement("canvas"); cv.width = w; cv.height = hgt;
        cv.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, w, hgt);
        URL.revokeObjectURL(img.src);
        resolve(kind === "photo" ? cv.toDataURL("image/jpeg", .9) : cv.toDataURL("image/png"));
      };
      img.onerror = function () { reject("That file couldn't be read as an image."); };
      img.src = URL.createObjectURL(file);
    });
  }

  function flashFor(key) {
    var f = FLASH && FLASH.key === key ? FLASH : null;
    if (f) FLASH = null;
    var el = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    if (f) note(el, f.text, f.bad);
    return el;
  }

  function imageField(kind, label, hint) {
    var u = DATA.user, has = !!u[kind];
    var prev = h("div", { class: "ac-img ac-img--" + kind });
    if (has) prev.appendChild(h("img", { src: imgUrl(kind, u[kind]), alt: "" }));
    else prev.appendChild(h("span", null, kind === "photo" ? initials(u.name) : "Logo"));
    var msg = flashFor(kind);
    var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "ac-file" });
    var pick = h("label", { class: "ac-upload" }, input, h("span", null, has ? "Change" : "Upload " + (kind === "photo" ? "a photo" : "a logo")));
    var remove = null;
    if (has) {
      var armed = false;
      remove = h("button", { class: "ac-link", type: "button", onclick: function () {
        if (!armed) { armed = true; remove.textContent = "Confirm remove"; remove.classList.add("is-armed"); return; }
        api("POST", "/api/me/image", { kind: kind, remove: true }).then(function (r) {
          if (!r.b.ok) { note(msg, "Couldn't remove it. Please try again.", true); return; }
          DATA.user[kind] = null;
          FLASH = { key: kind, text: (kind === "photo" ? "Photo" : "Logo") + " removed." };
          if (kind === "photo" && window.hvPortal && window.hvPortal.setPhoto) window.hvPortal.setPhoto(null);
          refreshCompletion(); renderHead(); route();
        });
      } }, "Remove");
    }
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) return;
      note(msg, "Uploading…");
      readImage(f, kind).then(function (dataUrl) {
        return api("POST", "/api/me/image", { kind: kind, data: dataUrl });
      }).then(function (r) {
        if (!r.b.ok) { note(msg, r.b.message || "Couldn't save that image. Please try again.", true); return; }
        DATA.user[kind] = r.b.version;
        if (r.b.completion) DATA.completion = r.b.completion;
        if (kind === "photo" && window.hvPortal && window.hvPortal.setPhoto) window.hvPortal.setPhoto(r.b.version);
        FLASH = { key: kind, text: (kind === "photo" ? "Photo" : "Logo") + " saved." };
        renderHead(); route();
      }, function (err) { note(msg, typeof err === "string" ? err : "Couldn't read that image.", true); });
    });
    return h("div", { class: "ac-imgfield", "data-key": kind }, prev,
      h("div", null, h("b", null, label), h("p", { class: "ac-muted" }, hint), h("div", { class: "ac-row" }, pick, remove, msg)));
  }

  function refreshCompletion() {
    api("GET", "/api/account").then(function (r) { if (r.b && r.b.ok) { DATA.completion = r.b.completion; } });
  }

  function settingsProfile() {
    var u = DATA.user, f = {};
    var form = h("form", { class: "ac-form" });
    [["name", "Name", "name"], ["job_title", "Job title", "organization-title"], ["company", "Company", "organization"], ["phone", "Phone", "tel"]].forEach(function (x) {
      f[x[0]] = h("input", { class: "ac-input", id: "ac-f-" + x[0], name: x[0], value: u[x[0]] || "", autocomplete: x[2], "data-key": x[0], required: x[0] === "name" ? true : null });
      form.appendChild(h("div", { class: "ac-field" }, h("label", { for: "ac-f-" + x[0] }, x[1]), f[x[0]]));
    });
    form.appendChild(h("div", { class: "ac-field" }, h("span", { class: "ac-field__label" }, "Email"), h("p", { class: "ac-static" }, u.email)));
    var msg = flashFor("profile");
    form.appendChild(h("div", { class: "ac-row" }, h("button", { class: "cat-btn cat-btn--lime", type: "submit" }, "Save changes"), msg));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      note(msg, "Saving…");
      api("POST", "/api/me/update", { name: f.name.value, company: f.company.value, job_title: f.job_title.value, phone: f.phone.value }).then(function (r) {
        if (!r.b.ok) { note(msg, r.b.message || "Couldn't save. Please try again.", true); return; }
        ["name", "company", "job_title", "phone"].forEach(function (k) { if (r.b.user && k in r.b.user) DATA.user[k] = r.b.user[k]; });
        renderHead();
        note(msg, "Saved.");
        refreshCompletion();
      });
    });
    return [h("h2", { class: "ac-h2" }, "Profile & company"),
      imageField("photo", "Profile photo", "Shown in the menu and on your account. A square crop is made for you."),
      imageField("logo", "Company logo", "Shown next to your name and on your live campaign's scoreboard."),
      form];
  }

  function settingsTeam() {
    var list = h("ul", { class: "ac-people" });
    DATA.team.forEach(function (t) {
      list.appendChild(h("li", null, h("span", { class: "ac-people__ini", "aria-hidden": "true" }, initials(t.name)),
        h("div", null, h("b", null, t.name), t.job_title ? h("span", { class: "ac-muted" }, t.job_title) : null)));
    });
    var name = h("input", { class: "ac-input", id: "ac-inv-name", autocomplete: "off", required: true });
    var email = h("input", { class: "ac-input", id: "ac-inv-email", type: "email", autocomplete: "off", required: true });
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var form = h("form", { class: "ac-form ac-form--inline" },
      h("div", { class: "ac-field" }, h("label", { for: "ac-inv-name" }, "Colleague's name"), name),
      h("div", { class: "ac-field" }, h("label", { for: "ac-inv-email" }, "Work email"), email),
      h("div", { class: "ac-row" }, h("button", { class: "cat-btn cat-btn--lime", type: "submit" }, "Ask for access"), msg));
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      note(msg, "Sending…");
      api("POST", "/api/team/invite", { name: name.value, email: email.value }).then(function (r) {
        if (r.s === 429) { note(msg, "You've sent enough requests today. Your account manager has them.", true); return; }
        note(msg, r.b.message || (r.b.ok ? "Sent." : "Couldn't send. Please try again."), !r.b.ok);
        if (r.b.ok) { name.value = ""; email.value = ""; }
      });
    });
    return [h("h2", { class: "ac-h2" }, "Team"),
      h("p", { class: "ac-muted" }, "Colleagues from your company with their own HelloVoice account. You see each other's selections."),
      DATA.team.length ? list : h("p", { class: "ac-empty-line" }, "No colleagues yet."),
      h("h3", { class: "ac-h3" }, "Invite a colleague"),
      h("p", { class: "ac-muted" }, "We'll set up their access and let them know. Access is always given by HelloVoice."),
      form];
  }

  function settingsNotifications() {
    var rows = [["quote", "A quote is ready", "When we answer a quote request."],
                ["live", "A campaign goes live", "The day the first posts are published."],
                ["report", "The report updates", "When new results are added to a live campaign."]];
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var box = h("div", { class: "ac-switches" });
    rows.forEach(function (r) {
      var id = "ac-n-" + r[0];
      var input = h("input", { type: "checkbox", id: id, role: "switch" });
      input.checked = !!DATA.notify[r[0]];
      input.addEventListener("change", function () {
        var body = {}; body[r[0]] = input.checked;
        api("POST", "/api/me/notify", body).then(function (res) {
          if (res.b.ok) { DATA.notify = res.b.notify; note(msg, r[1] + ": " + (input.checked ? "on" : "off") + ". Saved."); }
          else { input.checked = !input.checked; note(msg, "Couldn't save that. Please try again.", true); }
        });
      });
      box.appendChild(h("label", { class: "ac-switch", for: id }, h("span", null, h("b", null, r[1]), h("span", { class: "ac-muted" }, r[2])), input, h("i", { "aria-hidden": "true" })));
    });
    return [h("h2", { class: "ac-h2" }, "Notifications"),
      h("p", { class: "ac-muted" }, "Sent to " + DATA.user.email + ". Your choices are saved now; these emails are being switched on shortly."), box, msg];
  }

  function settingsPrivacy() {
    var msg = h("span", { class: "ac-note", role: "status", "aria-live": "polite" });
    var confirmBox = h("div", { class: "ac-confirm", hidden: true });
    var typed = h("input", { class: "ac-input", id: "ac-del", autocomplete: "off", placeholder: "DELETE" });
    var go = h("button", { class: "cat-btn ac-btn-danger", type: "button", disabled: true }, "Delete my account for good");
    typed.addEventListener("input", function () { go.disabled = typed.value.trim() !== "DELETE"; });
    go.addEventListener("click", function () {
      go.disabled = true;
      api("POST", "/api/me/delete", { confirm: "DELETE" }).then(function (r) {
        if (r.b && r.b.ok !== false && r.s < 400) { location.href = ROOT; return; }
        go.disabled = false; note(msg, (r.b && r.b.message) || "Couldn't delete the account. Please contact your account manager.", true);
      });
    });
    confirmBox.appendChild(h("label", { for: "ac-del" }, "Type DELETE to confirm. Your account and personal data are erased; this can't be undone."));
    confirmBox.appendChild(h("div", { class: "ac-row" }, typed, go,
      h("button", { class: "ac-link", type: "button", onclick: function () { confirmBox.hidden = true; typed.value = ""; go.disabled = true; } }, "Cancel")));
    return [h("h2", { class: "ac-h2" }, "Privacy & data"),
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Download my data"), h("p", { class: "ac-muted" }, "Your profile, briefs and credit history as a file.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: function () {
          note(msg, "Preparing your file…");
          fetch(API + "/api/me/export", { credentials: "include", cache: "no-store" }).then(function (r) {
            if (!r.ok) throw new Error("export");
            return r.blob();
          }).then(function (b) {
            var a = h("a", { href: URL.createObjectURL(b), download: "my-hellovoice-data.json" }); document.body.appendChild(a); a.click(); a.remove();
            note(msg, "Downloaded my-hellovoice-data.json.");
          }).catch(function () { note(msg, "Couldn't prepare the file. Please try again.", true); });
        } }, "Download")),
      h("div", { class: "ac-action" }, h("div", null, h("b", null, "Sign out of other devices"), h("p", { class: "ac-muted" }, "Every other browser loses access. You stay signed in here.")),
        h("button", { class: "ac-btn-line", type: "button", onclick: function () {
          api("POST", "/api/me/signout-others", {}).then(function (r) { note(msg, r.b.ok ? (r.b.removed ? "Signed out of " + r.b.removed + " other device" + (r.b.removed === 1 ? "" : "s") + "." : "No other devices were signed in.") : "Couldn't do that. Please try again.", !r.b.ok); });
        } }, "Sign out others")),
      msg,
      h("div", { class: "ac-action ac-action--danger" }, h("div", null, h("b", null, "Delete my account"), h("p", { class: "ac-muted" }, "Your account and personal data are erased. Selections and campaigns stay with your company.")),
        h("button", { class: "cat-btn ac-btn-danger", type: "button", onclick: function () { confirmBox.hidden = false; typed.focus(); } }, "Delete account")),
      confirmBox];
  }

  function renderSettings(sub) {
    var p = $("tab-settings");
    p.textContent = "";
    sub = SET_TABS.some(function (t) { return t[0] === sub; }) ? sub : "profile";
    var nav = h("nav", { class: "ac-subnav", "aria-label": "Settings" });
    var pick = h("select", { class: "ac-input ac-subnav__select", "aria-label": "Settings section" });
    SET_TABS.forEach(function (t) {
      nav.appendChild(h("a", { href: "#settings/" + t[0], "aria-current": t[0] === sub ? "page" : null }, t[1]));
      var o = h("option", { value: t[0] }, t[1]); if (t[0] === sub) o.selected = true; pick.appendChild(o);
    });
    pick.addEventListener("change", function () { location.hash = "#settings/" + pick.value; });
    var body = h("div", { class: "ac-setbody" });
    add(body, { profile: settingsProfile, team: settingsTeam, notifications: settingsNotifications, privacy: settingsPrivacy }[sub]());
    add(p, h("div", { class: "ac-settings" }, h("div", null, nav, pick), body));
  }

  /* ---------------------------------------------------------------- routing */

  function route() {
    if (!DATA) return;
    var hash = (location.hash || "#home").slice(1).split("/");
    var tab = ["home", "selections", "campaigns", "settings"].indexOf(hash[0]) >= 0 ? hash[0] : "home";
    document.querySelectorAll(".ac-panel").forEach(function (el) { el.hidden = el.getAttribute("data-panel") !== tab; });
    document.querySelectorAll(".ac-tabs a").forEach(function (a) {
      if (a.getAttribute("data-tab") === tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    ({ home: renderHome, selections: renderSelections, campaigns: renderCampaigns, settings: function () { renderSettings(hash[1]); } })[tab]();
    var want = null;
    try { want = sessionStorage.getItem("ac-focus"); sessionStorage.removeItem("ac-focus"); } catch (e) {}
    if (want) {
      var el = document.querySelector('[data-key="' + want + '"]');
      if (el) { el.scrollIntoView({ block: "center" }); var inp = el.matches("input") ? el : el.querySelector("input"); if (inp) inp.focus(); }
    }
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest("[data-focus]");
    if (a) { try { sessionStorage.setItem("ac-focus", a.getAttribute("data-focus")); } catch (err) {} }
  });

  function closed(title, line) {
    $("ac-loading").hidden = true;
    var c = $("ac-closed");
    c.textContent = "";
    c.appendChild(h("b", null, title));
    c.appendChild(h("p", null, line));
    c.appendChild(h("a", { class: "cat-btn cat-btn--lime", href: ROOT }, "Go to the catalogue"));
    c.hidden = false;
  }

  function load() {
    return api("GET", "/api/account").then(function (r) {
      if (r.s === 401) { closed("Please sign in", "Sign in on the catalogue to see your account."); return; }
      if (r.s === 403) { closed("Accounts are for signed-in clients", "You're using an access code. Your campaigns are in campaign tracking."); return; }
      if (!r.b.ok) { closed("Something went wrong", "Your account couldn't be loaded. Please try again shortly."); return; }
      DATA = r.b;
      $("ac-loading").hidden = true;
      renderHead();
      route();
    });
  }

  window.addEventListener("hashchange", route);
  load();
})();
