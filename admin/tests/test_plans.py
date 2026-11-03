"""Check Helvy's plans (item 292) without touching the portal: what a plan may hold, and how ids carry forward.

    python3 admin/tests/test_plans.py
"""
import json
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import actions

ok = fail = 0


def t(label, got, want):
    global ok, fail
    if got == want:
        ok += 1
    else:
        fail += 1
        print("  FAIL %s\n    got  %r\n    want %r" % (label, got, want))


def raises(label, fn, must_say):
    global ok, fail
    try:
        fn()
    except ValueError as exc:
        if must_say.lower() in str(exc).lower():
            ok += 1
            return
        fail += 1
        print("  FAIL %s: said %r" % (label, str(exc)))
        return
    fail += 1
    print("  FAIL %s: did not refuse" % label)


raises("empty plan", lambda: actions.plan_check([]), "at least one step")
raises("not JSON", lambda: actions.plan_check("create it"), "JSON list")
raises("too long", lambda: actions.plan_check([{"action": "link.toggle", "fields": {"id": "2", "slug": "a-b-c"}}] * 16), "at most")
raises("unknown action", lambda: actions.plan_check([{"action": "campaign.nope"}]), "No such action")
raises("form.submit stays single", lambda: actions.plan_check([{"action": "form.submit", "fields": {}}]), "one at a time")
raises("forward ref", lambda: actions.plan_check([{"action": "campaign.status", "fields": {"id": "{{1.id}}", "status": "live"}}]),
       "earlier step")
raises("missing field after a ref", lambda: actions.plan_check([
    {"action": "link.toggle", "fields": {"id": "2", "slug": "a-b-c"}},
    {"action": "campaign.status", "fields": {"id": "{{1.id}}"}}]), "needs status")
raises("JSON field", lambda: actions.check("campaign.details", {"id": "2", "targets": "lots"}), "JSON object")

got = actions.plan_check(json.dumps([{"action": "link.toggle", "fields": {"id": "2", "slug": "a-b-c"}},
                                     {"action": "campaign.status", "fields": {"id": "{{1.id}}", "status": "live"}}]))
t("two steps", len(got), 2)
t("ref named on the card", got[1][2], "Set campaign the one from step 1 to live")
t("code fence tolerated", len(actions.plan_check("```json\n[{\"action\": \"campaign.status\", \"fields\": {\"id\": \"2\", \"status\": \"live\"}}]\n```")), 1)

t("id read back", actions._read_back(302, "/admin/campaigns/edit?id=41", "", "campaign.create", ("/campaigns/edit",)),
  {"ok": True, "message": "Done.", "action": "campaign.create", "id": "41"})
t("ok message keeps id", actions._read_back(302, "/admin/campaigns/edit?id=41&ok=Saved", "", "x").get("id"), "41")


# A run stops at the first refused step and reports the rest as not run; ids flow into later steps.
calls = []


def fake_run(action, fields, cookie):
    calls.append((action, dict(fields)))
    if action == "link.toggle":
        return {"ok": True, "message": "Switched.", "id": "77"}
    if fields.get("status") == "ended":
        return {"ok": False, "error": "Refused."}
    return {"ok": True, "message": "Done."}


real = actions.run
actions.run = fake_run
try:
    out = actions.run_plan([{"action": "link.toggle", "fields": {"id": "2", "slug": "a-b-c"}},
                            {"action": "campaign.status", "fields": {"id": "{{1.id}}", "status": "live"}},
                            {"action": "campaign.status", "fields": {"id": "{{1.id}}", "status": "ended"}},
                            {"action": "campaign.status", "fields": {"id": "2", "status": "draft"}}], "c=1")
finally:
    actions.run = real
t("states", [o["state"] for o in out], ["done", "done", "failed", "skipped"])
t("id carried", calls[1][1]["id"], "77")
t("nothing after the refusal", len(calls), 3)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
