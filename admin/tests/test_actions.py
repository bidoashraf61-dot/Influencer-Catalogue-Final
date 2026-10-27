"""Check the bridge's guard rails without touching the portal.

    python3 admin/tests/test_actions.py
"""
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
        print("  FAIL %s: wrong message %r" % (label, str(exc)))
        return
    fail += 1
    print("  FAIL %s: did not refuse" % label)


print("actions in the registry:", len(actions.REGISTRY))
cat = actions.catalogue()
t("catalogue lists every action", len(cat["actions"]), len(actions.REGISTRY))
t("one area filters", [a["action"] for a in actions.catalogue("post")["actions"]],
  sorted(k for k in actions.REGISTRY if k.startswith("post.")))

raises("unknown action", lambda: actions.check("campaign.launch", {"id": 2}), "no such action")
raises("unknown field", lambda: actions.check("campaign.status", {"id": 2, "live": "yes"}), "does not take")
raises("missing required", lambda: actions.check("campaign.status", {"id": 2}), "needs status")
raises("empty required", lambda: actions.check("post.add", {"id": 2, "url": "", "code": "HV-1"}), "needs url")

t("sentence, simple", actions.describe("campaign.status", {"id": 2, "status": "live"}),
  "Set campaign 2 to live")
t("sentence, extras appended", actions.describe("post.add", {
    "id": 2, "url": "https://x.com/p/1", "code": "HV-MC-049", "platform": "TikTok", "kind": "reel", "likes": 10}),
  "Add the post https://x.com/p/1 to campaign 2 — code HV-MC-049, kind reel, likes 10, platform TikTok")
t("a link alone is enough to add a post", actions.check("post.add", {"id": 2, "url": "https://www.tiktok.com/@a/video/1"})[1],
  {"id": 2, "url": "https://www.tiktok.com/@a/video/1"})
t("delete is called out", actions.describe("campaign.delete", {"id": 7}),
  "DELETE campaign 7 and everything on it. This cannot be undone")

t("no cookie, no call", actions.run("campaign.status", {"id": 2, "status": "draft"}, "")["ok"], False)
t("a bad action never reaches the portal",
  [e for e in [None] if False] or isinstance(actions.REGISTRY.get("campaigns.save"), type(None)), True)

# The whole-page form must stay out of reach.
t("/campaigns/save is not exposed",
  [k for k, v in actions.REGISTRY.items() if v["path"] == "/campaigns/save"], [])

# --- how an answer is read back ---
R = actions._read_back
t("a message means done", R(303, "/admin/campaigns?ok=Jamjoom%20is%20live.", "", "x"),
  {"ok": True, "message": "Jamjoom is live.", "action": "x"})
t("an error comes back as the portal wrote it", R(303, "/admin/campaigns?e=Set%20the%20dates%20first", "", "x")["error"],
  "Set the dates first")
t("the sign-in page is never a success", R(303, "/admin/login", "", "x")["ok"], False)
t("a wordless list page is not a success", R(303, "/admin/campaigns", "", "x")["ok"], False)
t("a wordless page the action does land on is", R(303, "/admin/campaigns/edit?id=9", "", "x", ("/campaigns/edit",))["ok"], True)
t("403 is a refusal", R(403, "", "nope", "x")["ok"], False)

# --- codes, selections, team, roster ---
for area in ("code", "selection", "team", "roster"):
    t("area %s has actions" % area, bool(actions.catalogue(area)["actions"]), True)
    t("area %s is described" % area, area in actions.AREAS, True)
t("code.delete is high risk", actions.describe("code.delete", {"id": 3}), "DELETE client code 3. This cannot be undone")
t("team reset is high risk", actions.REGISTRY["team.reset_2fa"]["risk"], "high")
t("selection.create needs only a name", actions.check("selection.create", {"name": "Q4"})[1], {"name": "Q4"})
t("selection.create fills in the form's mode", actions.REGISTRY["selection.create"]["defaults"], {"mode": "scratch"})
raises("code.limits refuses a stray field", lambda: actions.check("code.limits", {"id": 1, "label": "x"}), "does not take")
raises("team.role needs a role", lambda: actions.check("team.role", {"id": 2}), "needs role")
# Whole-page saves stay out: they replace every field they are sent.
t("/roster/save is not exposed", [k for k, v in actions.REGISTRY.items() if v["path"] == "/roster/save"], [])
t("/settings, /portal/keys are not exposed",
  [k for k, v in actions.REGISTRY.items() if v["path"].startswith(("/settings", "/portal/keys", "/apis"))], [])
t("a step-up redirect says so, not 'sign in'", "confirm it is you" in R(303, "/admin/reauth?again=1", "", "x")["error"], True)

print("\n%d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
