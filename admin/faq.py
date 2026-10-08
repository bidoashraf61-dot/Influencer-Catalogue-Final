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
        # Helvy never quotes prices (phase C + D): the account manager does.
        return {"reply": "I don't quote prices: your account manager will prepare a quote for exactly the creators and content you want, "
                         "usually within one working day. I can send the request now, or show what your own budget can reach.",
                "next": ["Get a quote", "What can my budget reach?"]}
    if intent == "credits":
        return {"reply": "Tapping options in this chat is always free. A typed question uses **%d credit**, and building a scored shortlist uses **%d**. "
                         "Everything AI is free while you have an active campaign. You can earn or request more from your profile."
                         % (costs.get("chat", 1), costs.get("brief", 5)),
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
