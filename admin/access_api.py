"""The two calls the locked pages make (docs/SAAS-MODEL.md, owner 2026-10-28).

    GET  /api/access/state?module=helvi-track   what this person meets there, to draw the right locked page
    POST /api/access/request  {module, kind: module|role, note}   ask for the module (HelloVoice) or a role (the company's admin)

A request goes through tenant_requests.file_request, so it lands in the Tenants inbox; a second identical open
one is folded into the first. Neither call leaks anything about a module's data: the state names the module,
the reason and who to ask, nothing else.
"""
import modules

KINDS = ("module", "role")


def _person(h):
    try:
        return modules.person_of(h)
    except Exception:
        return None


def state(h, query):
    p = _person(h)
    if p is None:
        return 401, {"ok": False, "reason": "signin"}
    keys = [query["module"]] if query.get("module") in modules.BY_KEY else [m["key"] for m in modules.MODULES]
    out = []
    for k in keys:
        s = modules.state_for(p, k)
        m = modules.BY_KEY[k]
        out.append({"module": k, "name": m["name"], "what": m["what"], "logo": m["logo"], "open": s["code"] is None,
                    "code": s["code"], "role": s["role"], "level": s["level"],
                    "ask": modules.company_admin(s["company"], k) if s["code"] == "no_role" else None})
    return 200, {"ok": True, "modules": out}


def request(h, b):
    p = _person(h)
    if p is None:
        return 401, {"ok": False, "reason": "signin"}
    key, kind = str(b.get("module") or ""), str(b.get("kind") or "")
    if key not in modules.BY_KEY or kind not in KINDS:
        return 400, {"ok": False, "message": "Pick a module and what you are asking for."}
    import tenant_requests
    company = modules.company_of(p)
    detail = {"module": key, "level": "view"} if kind == "module" else {"module": key, "role": "viewer", "user_id": p["id"]}
    rid = tenant_requests.file_request(company, p["id"], key, kind, str(b.get("note") or "")[:500], detail)
    return 200, {"ok": True, "id": rid, "to": "your company's admin" if kind == "role" else "HelloVoice",
                 "message": "Request sent."}
