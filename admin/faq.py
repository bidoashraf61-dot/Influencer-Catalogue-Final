"""Instant answers for the catalogue chat: the questions clients ask most,
answered at once from facts the platform already holds. No AI call and no
credit. Anything that is not clearly one of these goes to the assistant.

``answer(text)`` returns ``{"reply", "next"}`` or ``None``.
"""
import re

import db
import portal

CONTACT = "info@hellovoice.co.uk · +966 11 463 4518"

# (intent, English and Arabic cues). Order matters: the first match wins.
INTENTS = [
    ("prices", r"\b(price|prices|pricing|rate card|cost|costs|how much|fee|fees|per video)\b|كم السعر|الأسعار|اسعار|سعر|تكلفة|بكم"),
    ("credits", r"\bcredits?\b|رصيد|نقاط|كريدت"),
    ("book", r"\b(book|booking|hire|order|quote|quotation|proceed|next step)\b|احجز|حجز|عرض سعر|طلب"),
    ("how", r"\b(how (does|do) (this|it|you) work|how it works|what (is|does) (this|helv|hellovoice))\b|كيف يعمل|كيف تعمل|ما هو"),
    ("analysis", r"\b(analysis|analytics|insights?|audience data|demographics?)\b|تحليل|إحصائيات|احصائيات"),
    ("report", r"\b(campaign report|report|results|tracking|track)\b|تقرير|نتائج|متابعة"),
    ("contact", r"\b(contact|phone|email|call|whatsapp|talk to (someone|a person)|reach you)\b|تواصل|رقم|ايميل|بريد|اتصال"),
]
# A creator request ("find me skincare creators under 5k") is not an FAQ even if it says "price".
# Questions about numbers (engagement, views, reach, averages…) need the creators' own figures: never an FAQ.
ANALYTIC = re.compile(r"\b(engagement|engage|er|views?|reach|impressions?|followers?|likes?|comments?|average|avg|mean|total|"
                      r"audience|demographic\w*|fake|selection|these creators|my list|compare|best|top|highest|lowest)\b|تفاعل|مشاهد|متابع|متوسط", re.I)
SEARCHY = re.compile(r"\b(find|show|suggest|recommend|looking for|shortlist|creators? (in|for|who)|influencers? (in|for|who))\b|ابحث|اقترح|أبحث", re.I)


def _money(v):
    return "SAR {:,}".format(int(round(v))) if v else "—"


def _prices():
    rows = [t for t in db.list_tiers() if t["price_from"]]
    if not rows:
        return "Prices depend on the creator's size and the deliverables. Ask for a quote and your account manager will price it."
    lines = ["• **%s**%s: %s–%s per video" % (t["name"], (" (" + t["reach"] + " followers)") if ("reach" in t.keys() and t["reach"]) else "",
                                               _money(t["price_from"]), "{:,}".format(int(round(t["price_to"] or t["price_from"]))))
             for t in rows]
    return ("Typical prices per video, before VAT:\n" + "\n".join(lines)
            + "\n\nA creator's own rate can differ, and bundles are priced together. A quote from your account manager is final.")


def answer(text):
    t = " ".join(str(text or "").split())
    if not t or len(t.split()) > 14 or SEARCHY.search(t) or ANALYTIC.search(t):
        return None
    for intent, cue in INTENTS:
        if re.search(cue, t, re.I):
            return _reply(intent)
    return None


def _reply(intent):
    costs = portal.costs()
    if intent == "prices":
        return {"reply": _prices(), "next": ["Get a quote", "Find creators within my budget"]}
    if intent == "credits":
        return {"reply": "Tapping options in this chat is always free. A typed question uses **%d credit**, and building a scored shortlist uses **%d**. "
                         "Your balance is shown under the chat; you can ask for more from your account." % (costs.get("chat", 1), costs.get("brief", 5)),
                "next": ["Find creators", "Talk to a person"]}
    if intent == "book":
        return {"reply": "Pick the creators you like on the catalogue (or let me build a shortlist), save them as a selection, "
                         "then press **Request a quote**. Your account manager confirms availability, deliverables and the final price, "
                         "usually within one working day.", "next": ["Get a quote", "Find creators"]}
    if intent == "how":
        return {"reply": "Browse vetted creators, filter by platform, size, city and topic, and open any creator's analysis. "
                         "Save the ones you like as a selection and request a quote; HelloVoice runs the campaign end to end "
                         "and you follow the results on your campaign report.", "next": ["Find creators", "Get a quote"]}
    if intent == "analysis":
        return {"reply": "Creators with a full analysis show their audience, engagement and reach on their page. "
                         "If a creator's analysis is locked, press **Request full analysis** on their page and the team adds it.",
                "next": ["Find creators", "Talk to a person"]}
    if intent == "report":
        return {"reply": "Each live campaign has a report link under your access code, with every post, reach and engagement "
                         "against the goals. The numbers refresh once every 24 hours.", "next": ["Talk to a person"]}
    if intent == "contact":
        return {"reply": "You can reach HelloVoice at " + CONTACT + ". Or I can send your message to your account manager now.",
                "next": ["Talk to a person"]}
    return None
