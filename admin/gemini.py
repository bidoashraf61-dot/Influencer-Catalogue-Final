"""Google Gemini over plain HTTPS (stdlib only, like the rest of the admin).

The key is read, in order, from the ``GEMINI_API_KEY`` environment variable or
the ``.gemini-key`` file next to this module (mode 600, gitignored, written from
the APIs page and never shown again). It is never sent to a browser.

Every call is audited in ``ai_audit`` (tokens, latency, credits, outcome) and
counted against a monthly token ceiling, so a bug or a busy client cannot run up
an open-ended bill. A bounded semaphore stops slow model calls from using up
every thread of the single-process server.

``STUB`` lets tests and the offline demo replace the network call.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import db

KEY_FILE = Path(__file__).resolve().parent / ".gemini-key"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MONTHLY_TOKENS = 5_000_000
MAX_CONCURRENT = 4

STUB = None            # callable(body: dict) -> response dict, set by tests
_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


class AIError(Exception):
    """Base class; ``reason`` is safe to show a user."""
    reason = "ai_error"


class NotConfigured(AIError):
    reason = "not_configured"


class OverBudget(AIError):
    reason = "budget"


class Upstream(AIError):
    reason = "upstream"


class Busy(AIError):
    reason = "busy"


# ---------------------------------------------------------------------- key --

def key():
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    try:
        return KEY_FILE.read_text().strip()
    except OSError:
        return ""


def key_hint():
    k = key()
    return ("…" + k[-4:]) if k else ""


def save_key(value):
    value = (value or "").strip()
    if not value or any(c.isspace() for c in value) or len(value) < 20:
        raise ValueError("That does not look like an API key.")
    KEY_FILE.write_text(value)
    os.chmod(KEY_FILE, 0o600)


def clear_key():
    try:
        KEY_FILE.unlink()
    except OSError:
        pass


def configured():
    return STUB is not None or bool(key())


def model():
    return db.setting("gemini_model", DEFAULT_MODEL) or DEFAULT_MODEL


# ------------------------------------------------------------------- budget --

def month_start():
    t = time.gmtime()
    return int(time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0))) - time.timezone


def tokens_this_month():
    with db.connect() as conn:
        r = conn.execute("SELECT COALESCE(SUM(prompt_tokens + out_tokens), 0) FROM ai_audit WHERE at >= ?",
                         (month_start(),)).fetchone()
    return int(r[0])


def monthly_cap():
    try:
        return int(db.setting("ai_monthly_tokens", DEFAULT_MONTHLY_TOKENS))
    except (TypeError, ValueError):
        return DEFAULT_MONTHLY_TOKENS


# --------------------------------------------------------------------- call --

def _audit(kind, code_id, mdl, usage, credits, ok, started, detail=""):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO ai_audit (at, code_id, kind, model, prompt_tokens, out_tokens, credits, ok, latency_ms, detail) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (db.now(), code_id, kind, mdl, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0),
             credits, 1 if ok else 0, int((time.time() - started) * 1000), (detail or "")[:300]))


def generate(contents, *, system=None, schema=None, tools=None, temperature=0.4, max_tokens=1500,
             kind="chat", code_id=None, credits=0, timeout=45):
    """One model call. Returns ``{"text", "calls", "parts", "usage"}``.

    ``contents`` is a list of Gemini content dicts (``{"role", "parts"}``) or a
    plain string. ``schema`` asks for JSON matching it (the text is then valid
    JSON). ``tools`` is a list of function declarations; any the model decides
    to call come back in ``calls`` as ``{"name", "args"}``.
    """
    if not configured():
        raise NotConfigured("Gemini is not set up yet.")
    if tokens_this_month() >= monthly_cap():
        raise OverBudget("The monthly AI allowance has been used.")
    if isinstance(contents, str):
        contents = [{"role": "user", "parts": [{"text": contents}]}]
    body = {"contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema
    if tools:
        body["tools"] = [{"functionDeclarations": tools}]

    mdl = model()
    started = time.time()
    if not _slots.acquire(timeout=8):
        raise Busy("The assistant is busy. Try again in a moment.")
    try:
        data = _post(mdl, body, timeout)
    except AIError as exc:
        _audit(kind, code_id, mdl, {}, 0, False, started, str(exc))
        raise
    finally:
        _slots.release()

    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
    calls = [{"name": p["functionCall"].get("name"), "args": p["functionCall"].get("args") or {}}
             for p in parts if "functionCall" in p]
    usage = data.get("usageMetadata") or {}
    if not text and not calls:
        _audit(kind, code_id, mdl, usage, 0, False, started, "empty:" + str(cand.get("finishReason")))
        raise Upstream("The assistant returned nothing. Try rephrasing.")
    _audit(kind, code_id, mdl, usage, credits, True, started)
    return {"text": text, "calls": calls, "parts": parts, "usage": usage}


def generate_json(contents, schema, **kw):
    out = generate(contents, schema=schema, **kw)
    try:
        return json.loads(out["text"])
    except ValueError:
        raise Upstream("The assistant answered in the wrong format. Try again.")


def _post(mdl, body, timeout):
    if STUB is not None:
        return STUB(body)
    req = urllib.request.Request(
        ENDPOINT.format(model=mdl), data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key()})
    last = None
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode()).get("error", {}).get("message", "")
            except Exception:
                pass
            if exc.code in (429, 500, 502, 503, 504) and attempt == 0:
                time.sleep(1.5)
                last = exc
                continue
            if exc.code in (400, 401, 403) and "key" in detail.lower():
                raise NotConfigured("The Gemini key was refused.")
            raise Upstream("Gemini error %s" % exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == 0:
                time.sleep(1.0)
                last = exc
                continue
            raise Upstream("Could not reach Gemini.")
    raise Upstream("Gemini is not responding (%s)." % (last,))
