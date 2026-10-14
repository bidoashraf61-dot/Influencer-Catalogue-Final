"""Pages for a creator's industry (Control Centre step 3): the review queue and the Industry section of the
creator form. Every value goes through e()."""
import json
import urllib.parse

import industry
import ui
from views import e, page, u

CSS = ("<style>"
       ".iv-chips{display:flex;flex-wrap:wrap;gap:6px}"
       ".iv-chip{position:relative;display:inline-flex}.iv-chip input{position:absolute;opacity:0;width:1px;height:1px}"
       ".iv-chip span{display:inline-flex;align-items:center;border:1px solid var(--line-strong);border-radius:999px;padding:7px 13px;font-weight:600;"
       "font-size:13.5px;background:#fff;cursor:pointer;user-select:none}"
       ".iv-chip input:checked+span{background:var(--ink);color:var(--lime);border-color:var(--ink)}"
       ".iv-chip.sub input:checked+span{background:var(--lime);color:var(--ink);border-color:var(--ink)}"
       ".iv-chip input:focus-visible+span{outline:2px solid var(--ink);outline-offset:2px}"
       ".iv-chip kbd{font:600 11px 'DM Sans',sans-serif;margin-left:7px;opacity:.55}"
       ".iv-l{display:block;font-weight:600;font-size:13px;margin:0 0 6px}.iv-l em{font-weight:400;font-style:normal;color:var(--muted)}"
       ".iv-tier{display:flex;gap:8px;flex-wrap:wrap}"
       ".iv-tier label{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--line-strong);border-radius:12px;padding:10px 12px;cursor:pointer;"
       "flex:1;min-width:170px;margin:0;font-weight:400}"
       ".iv-tier label:has(input:checked){border-color:var(--ink);background:var(--lime)}.iv-tier input{width:auto;margin-top:4px}"
       ".iv-tier small{display:block;color:var(--muted);font-size:12px}"
       ".iv-src{font-size:12.5px;color:var(--muted);margin:12px 0 0}"
       ".iv-sec{border:1px solid var(--line);border-radius:14px;padding:16px;margin:14px 0}"
       ".iv-sec h3{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:24px;margin:0 0 2px}"
       ".iv-sec>p{margin:0 0 12px;color:var(--muted);font-size:13px}"
       ".iv-subs[hidden]{display:none}"
       "</style>")

_SUB_JS = ("<script>(function(){var subs=%s;document.querySelectorAll('[data-iv-main]').forEach(function(sel){"
           "var box=sel.closest('form').querySelector('[data-iv-subs]');if(!box)return;var keep={};"
           "function draw(){box.querySelectorAll('input:checked').forEach(function(i){keep[i.value]=1});var list=subs[sel.value]||[];"
           "box.innerHTML=list.map(function(s){return '<label class=\"iv-chip sub\"><input type=\"checkbox\" name=\"ind_subs\" value=\"'+s.replace(/\"/g,'&quot;')+'\"'+(keep[s]?' checked':'')+'><span>'+s.replace(/</g,'&lt;')+'</span></label>'}).join('')||'<span class=\"muted\" style=\"font-size:13px\">No sub-niches for this industry.</span>'}"
           "sel.addEventListener('change',function(){keep={};draw()});});})();</script>")


def _chips(name, options, chosen, sub=False, multi=True, keys=False):
    kind = "checkbox" if multi else "radio"
    return "<div class='iv-chips'>" + "".join(
        "<label class='iv-chip%s'><input type='%s' name='%s' value='%s'%s%s><span>%s%s</span></label>" % (
            " sub" if sub else "", kind, name, e(o), " checked" if o in chosen else "", (" data-key='%d'" % (i + 1)) if keys and i < 9 else "",
            e(o), ("<kbd>%d</kbd>" % (i + 1)) if keys and i < 9 else "")
        for i, o in enumerate(options)) + "</div>"


def form_section(c):
    """The Industry section of the creator form (fields ind_*; saved with the rest of the form)."""
    cur = industry.current(c) if c is not None else {"industry": None, "subs": [], "also": [], "tier": None, "conf": None, "source": None}
    main = cur["industry"] or ""
    opts = "<option value=''>Not set</option>" + "".join(
        "<option%s>%s</option>" % (" selected" if i == main else "", e(i)) for i in industry.INDUSTRIES)
    tier = cur["tier"] if cur["tier"] in industry.TIERS else "Review"
    tiers = "".join(
        "<label><input type='radio' name='ind_tier' value='%s'%s><span><b>%s</b><small>%s</small></span></label>" % (
            t, " checked" if t == tier else "", t, d) for t, d in (
            ("Confirmed", "Shown first in the filter"), ("Probable", "Shown under “Probable”"),
            ("Review", "Hidden from industry filters until checked")))
    src = cur["source"] or ""
    if src.startswith("Claude"):
        src = "Set by the AI classification (%s)" % (("%d%% sure" % cur["conf"]) if cur["conf"] is not None else "no score")
    return (CSS + "<div class='iv-sec'><h3>Industry</h3><p>Decides which Industry filter this creator appears in on the catalogue. "
            "A choice saved here by hand counts as Confirmed unless you pick otherwise.</p>"
            "<div class='row'><div><label for='ind-main' class='iv-l'>Main industry</label><select id='ind-main' name='ind_main' data-iv-main>" + opts + "</select></div>"
            "<div><span class='iv-l'>Also covers <em>(up to 2)</em></span>"
            "<select name='ind_also' multiple size='3' aria-label='Also covers'>" + "".join(
                "<option%s>%s</option>" % (" selected" if i in cur["also"] else "", e(i)) for i in industry.INDUSTRIES if i != "Unclassifiable") + "</select></div></div>"
            "<div style='margin-top:12px'><span class='iv-l'>Sub-niches <em>(up to 3)</em></span><div data-iv-subs>"
            + (_chips("ind_subs", industry.SUBS.get(main, []), cur["subs"], sub=True) if industry.SUBS.get(main) else
               "<span class='muted' style='font-size:13px'>No sub-niches for this industry.</span>") + "</div></div>"
            "<div style='margin-top:14px'><span class='iv-l'>How sure are we?</span><div class='iv-tier'>" + tiers + "</div></div>"
            + ("<p class='iv-src'>" + e(src) + "</p>" if src else "")
            + "<input type='hidden' name='ind_was' value='" + e(json.dumps([main, cur["tier"]])) + "'></div>"
            + _SUB_JS % json.dumps(industry.SUBS, ensure_ascii=False))


def review_page(card, counts, country=None, ok=None, err=None):
    filt = "".join("<a class='pill%s' href='%s'>%s</a>" % (" live" if (k or None) == country else "", u("/roster/review") + ("?country=" + k if k else ""), lab)
                   for k, lab in (("", "All"), ("KSA", "KSA"), ("UAE", "UAE"), ("Egypt", "Egypt")))
    total = counts["left"] + counts["done"]
    pct = int(round(counts["done"] * 100.0 / total)) if total else 100
    head = ("<div class='rv-top'><div><h1>Industry review</h1><p>Creators where the AI was not sure. Pick their main industry once and they "
            "appear in the right filter for every client. Biggest creators first.</p></div><div class='rv-f'>" + filt + "</div></div>"
            "<div class='rv-prog'><div class='rv-bar'><i style='width:%d%%'></i></div><b>%s left</b><span>%s done</span></div>" % (
                pct, "{:,}".format(counts["left"]), "{:,}".format(counts["done"])))
    banner = (("<div class='ok'>" + e(ok) + "</div>") if ok else "") + (("<div class='err'>" + e(err) + "</div>") if err else "")
    if card is None:
        body = ui.empty("check", "Nothing left to review", "Every creator here has a main industry. New ones the AI is unsure about will appear here.",
                        "<a class='btn small' href='" + u("/roster") + "'>Back to creators</a>")
        return page("Industry review", RV_CSS + head + banner + body, "/roster")
    ai = card["ai"]
    fol = "{:,}".format(card["followers"] or 0)
    where = " · ".join(x for x in (card["city"], card["nationality"]) if x)
    posts = "".join("<a href='%s' target='_blank' rel='noopener'><img src='%s' alt='' loading='lazy' referrerpolicy='no-referrer'></a>" % (
        e(p["url"] or "#"), e(p["pic"])) for p in card["posts"]) or "<p class='rv-none'>No post pictures on file.</p>"
    options = [ai["industry"]] + [a for a in ai["also"]] if ai["industry"] else []
    options += [i for i in industry.INDUSTRIES if i not in options]
    top, rest = options[:4], options[4:]
    main = ai["industry"] or ""
    after = "%d:%s" % (card["followers"] or 0, card["code"])
    hid = lambda n, v: "<input type='hidden' name='%s' value='%s'>" % (n, e(v))
    form = (
        "<form method='post' action='" + u("/roster/review") + "' class='rv-decide' id='rv-form'>"
        + hid("code", card["code"]) + hid("after", after) + hid("country", country or "")
        + "<div class='rv-ai'><b>AI suggestion: %s</b><span class='rv-conf'>%s</span><p>%s%s</p></div>" % (
            e(main or "none"), ("%d%% sure" % ai["conf"]) if ai["conf"] is not None else "not scored", e(card["why"]),
            (" Also mentions " + e(", ".join(ai["also"])) + ".") if ai["also"] else "")
        + "<div><span class='iv-l'>Main industry</span>" + _chips("ind_main", top, [main], multi=False, keys=True)
        + "<details class='rv-more'><summary>All industries</summary>" + _chips("ind_main", rest, [main], multi=False) + "</details></div>"
        + "<div><span class='iv-l'>Sub-niches <em>(optional)</em></span><div data-iv-subs>" + (
            _chips("ind_subs", industry.SUBS.get(main, []), ai["subs"], sub=True) if industry.SUBS.get(main) else
            "<span class='muted' style='font-size:13px'>No sub-niches for this industry.</span>") + "</div></div>"
        + "<div><span class='iv-l'>Also covers <em>(shows as Probable in those filters)</em></span>"
        + _chips("ind_also", ai["also"], ai["also"])
        + "<details class='rv-more'><summary>More industries</summary>"
        + _chips("ind_also", [i for i in industry.INDUSTRIES if i not in ai["also"] and i not in ("Unclassifiable",)], []) + "</details></div>"
        + "<div class='rv-acts'><button class='btn lime' name='do' value='confirm'>Confirm and next</button>"
          "<button class='btn ghost' name='do' value='skip' formnovalidate>Skip</button>"
          "<button class='btn ghost' name='do' value='unfit' formnovalidate onclick=\"return confirm('Hide this creator from clients? Nothing is deleted.')\">Not a fit for the catalogue</button>"
          "<span class='rv-k'><kbd>1</kbd>–<kbd>4</kbd> pick · <kbd>Enter</kbd> confirm · <kbd>S</kbd> skip</span></div></form>")
    who = ("<div class='rv-who'>" + (("<img class='rv-p' src='%s' alt=''>" % e(card["photo"])) if card["photo"] else "<div class='rv-p'></div>")
           + "<h2>%s</h2><div class='rv-m'>@%s · %s · %s%s</div>" % (e(card["name"] or card["code"]), e(card["handle"] or ""), e(card["platform"] or ""), fol,
                                                                   (" · " + e(where)) if where else "")
           + (("<p class='rv-bio'>" + e(card["bio"]) + "</p>") if card["bio"] else "")
           + "<div class='rv-posts'>" + posts + "</div>"
           + "<a class='rv-open' href='" + u("/roster") + "?q=" + urllib.parse.quote(card["code"]) + "'>Open full profile</a></div>")
    js = ("<script>(function(){var f=document.getElementById('rv-form');if(!f)return;"
          "var subs=%s;var box=f.querySelector('[data-iv-subs]');"
          "function draw(v){var list=subs[v]||[];box.innerHTML=list.map(function(s){return '<label class=\"iv-chip sub\"><input type=\"checkbox\" name=\"ind_subs\" value=\"'+s.replace(/\"/g,'&quot;')+'\"><span>'+s.replace(/</g,'&lt;')+'</span></label>'}).join('')||'<span class=\"muted\" style=\"font-size:13px\">No sub-niches for this industry.</span>'}"
          "f.addEventListener('change',function(ev){if(ev.target.name==='ind_main')draw(ev.target.value)});"
          "document.addEventListener('keydown',function(ev){var t=ev.target;if(t&&(t.tagName==='INPUT'&&t.type==='text'||t.tagName==='TEXTAREA'||t.isContentEditable))return;"
          "if(ev.metaKey||ev.ctrlKey||ev.altKey)return;var k=ev.key;"
          "if(k>='1'&&k<='4'){var r=f.querySelector('input[data-key=\"'+k+'\"]');if(r){r.checked=true;draw(r.value);ev.preventDefault()}}"
          "else if(k==='s'||k==='S'){f.querySelector('button[value=skip]').click();ev.preventDefault()}"
          "else if(k==='Enter'&&t.tagName!=='BUTTON'){f.querySelector('button[value=confirm]').click();ev.preventDefault()}});})();</script>"
          % json.dumps(industry.SUBS, ensure_ascii=False))
    return page("Industry review", CSS + RV_CSS + head + banner + "<div class='rv-card'>" + who + form + "</div>" + js, "/roster")


RV_CSS = ("<style>"
          ".rv-top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}"
          ".rv-top h1{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:clamp(38px,4.6vw,54px);line-height:.92;margin:0}"
          ".rv-top p{margin:8px 0 0;color:var(--gray);max-width:60ch}.rv-f{display:flex;gap:6px;flex-wrap:wrap}.rv-f .pill{text-decoration:none}"
          ".rv-prog{margin:18px 0 20px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}"
          ".rv-bar{flex:1;min-width:160px;height:10px;border-radius:999px;background:#e6e1d8;overflow:hidden}.rv-bar i{display:block;height:100%;background:var(--ink)}"
          ".rv-prog b{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:22px}.rv-prog span{color:var(--muted);font-size:13px}"
          ".rv-card{display:grid;grid-template-columns:330px minmax(0,1fr);background:var(--white);border:1px solid var(--line);border-radius:22px;overflow:hidden}"
          ".rv-who{background:var(--ink);color:#fff;padding:22px}"
          ".rv-p{width:96px;height:96px;border-radius:50%;object-fit:cover;border:3px solid var(--lime);background:var(--ink-3);display:block}"
          ".rv-who h2{font-family:'Bebas Neue',sans-serif;font-weight:400;font-size:34px;line-height:1;margin:14px 0 2px;color:#fff}"
          ".rv-m{color:rgba(255,255,255,.72);font-size:13px}.rv-bio{margin:14px 0;font-size:13.5px;color:rgba(255,255,255,.9);line-height:1.5}"
          ".rv-posts{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:14px}.rv-posts img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;display:block;background:var(--ink-3)}"
          ".rv-none{color:rgba(255,255,255,.6);font-size:13px;grid-column:1/-1}"
          ".rv-open{display:inline-block;margin-top:14px;color:var(--lime);font-size:13px}"
          ".rv-decide{padding:24px;display:flex;flex-direction:column;gap:18px;margin:0}"
          ".rv-ai{background:var(--paper);border-radius:14px;padding:14px 16px}.rv-ai p{margin:4px 0 0;font-size:13.5px;color:var(--gray)}"
          ".rv-conf{display:inline-flex;font-size:12px;font-weight:700;border-radius:999px;padding:2px 9px;background:var(--amber-soft);color:var(--amber);margin-left:8px}"
          ".rv-more{margin-top:8px}.rv-more summary{cursor:pointer;font-size:13px;color:var(--gray);margin-bottom:8px}"
          ".rv-acts{margin-top:auto;display:flex;gap:10px;flex-wrap:wrap;align-items:center;border-top:1px solid var(--line);padding-top:16px}"
          ".rv-k{font-size:12px;color:var(--muted);margin-left:auto}.rv-k kbd{font:600 11.5px 'DM Sans',sans-serif;border:1px solid var(--line-strong);border-radius:5px;padding:1px 5px;background:#fff}"
          "@media (max-width:900px){.rv-card{grid-template-columns:1fr}.rv-k{display:none}}"
          "</style>")
