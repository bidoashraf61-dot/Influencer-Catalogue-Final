"""The goal formulas and benchmarks, as a read-only admin page (Scoring rules > Goal formulas and benchmarks).

The source is admin/reference/goal-formulas.md, a plain markdown file copied with the admin code. Staff only
(the /reference prefix is already refused to key account managers and viewers). It holds the value floor and
cost ratios, so it is never part of anything a client can reach."""
import html
import re
from pathlib import Path

import ui
import views as V

SRC = Path(__file__).resolve().parent / "reference" / "goal-formulas.md"
e, u = V.e, V.u

CSS = """<style>
.gf{max-width:980px}.gf h2{margin:34px 0 8px;font-size:22px}.gf h3{margin:24px 0 6px;font-size:17px}.gf h4{margin:18px 0 4px;font-size:15px}
.gf p,.gf li{line-height:1.55;font-size:14.5px}.gf code{background:#f1eee8;padding:1px 5px;border-radius:5px;font-size:13px}
.gf pre{background:#f6f4f0;border-radius:12px;padding:12px 14px;overflow:auto;font-size:12.5px;line-height:1.5}.gf pre code{background:none;padding:0}
.gf table{margin:10px 0 14px;font-size:13px}.gf th,.gf td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.gf blockquote{margin:10px 0;padding:8px 14px;border-left:4px solid #b9d400;background:#f8f9ee;border-radius:0 10px 10px 0}
.gf-toc{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 18px}.gf-toc a{padding:4px 10px;border-radius:999px;background:#f1eee8;font-size:12.5px;text-decoration:none;color:inherit}
.gf-tw{overflow-x:auto}
</style>"""


def _inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)


def render(md):
    """Small markdown reader: headings, tables, lists, quotes, code fences, rules, bold, italic, code, links."""
    out, toc, lines, i = [], [], md.split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"(#{1,4})\s+(.*)", ln)
        if m:
            lvl, text = len(m.group(1)), m.group(2)
            hid = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            if lvl == 2:
                toc.append((hid, text))
            if lvl > 1:
                out.append("<h%d id='%s'>%s</h%d>" % (lvl, hid, _inline(text), lvl))
            i += 1
            continue
        if ln.strip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                j += 1
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in lines[i:j]]
            body = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            if body:
                head, rest = body[0], body[1:]
                out.append("<div class='gf-tw'><table><thead><tr>" + "".join("<th>%s</th>" % _inline(c) for c in head) + "</tr></thead><tbody>"
                           + "".join("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in r) + "</tr>" for r in rest) + "</tbody></table></div>")
            i = j
            continue
        if re.match(r"\s*([-*]|\d+\.)\s+", ln):
            ordered = bool(re.match(r"\s*\d+\.", ln))
            items = []
            while i < len(lines) and re.match(r"\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % _inline(x) for x in items), tag))
            continue
        if ln.startswith(">"):
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i].lstrip("> "))
                i += 1
            out.append("<blockquote>" + _inline(" ".join(q)) + "</blockquote>")
            continue
        if re.fullmatch(r"\s*-{3,}\s*", ln):
            out.append("<hr>")
        elif ln.strip():
            out.append("<p>" + _inline(ln) + "</p>")
        i += 1
    return "".join(out), toc


def page_html():
    try:
        body, toc = render(SRC.read_text(encoding="utf-8"))
        inner = ("<div class='gf-toc'>" + "".join("<a href='#%s'>%s</a>" % (h, e(t)) for h, t in toc) + "</div>" + body)
    except OSError:
        inner = ("<div class='err'><strong>The formulas file could not be read.</strong> It lives in admin/reference/goal-formulas.md "
                 "and is copied with the admin code.</div>")
    page = (CSS + ui.header("Goal formulas and benchmarks", "How every campaign goal, benchmark and score is worked out. Staff only.",
                            crumbs=[("Scoring rules", u("/reference")), ("Goal formulas and benchmarks", None)])
            + "<div class='gf'>" + inner + "</div>")
    return V.page("Goal formulas and benchmarks", page, "/reference/goal-formulas")
