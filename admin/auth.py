"""Password hashing, access-code hashing and session cookies.

Stdlib only. `hashlib.scrypt` is unavailable on some Python builds — including
the macOS system Python this was written on — so PBKDF2-HMAC-SHA256 is used
instead: present everywhere, and at 240k iterations an entirely reasonable
choice for a handful of admin logins.
"""

import base64
import hashlib
import hmac
import os
import secrets
import string

ITERATIONS = 240_000
SALT_BYTES = 16


# ---------------------------------------------------------------- passwords --

def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt_b64, dk_b64 = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt_b64), int(iters)
        )
        # constant time: a timing difference here leaks whether a prefix matched
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def password_problems(password: str):
    """Returned to the user, so each item is a sentence they can act on."""
    out = []
    if len(password) < 12:
        out.append("Use at least 12 characters.")
    if password.lower() == password or password.upper() == password:
        out.append("Mix upper and lower case.")
    if not any(c.isdigit() for c in password):
        out.append("Include a digit.")
    if password.lower() in ("password", "hellovoice123", "catalogue123"):
        out.append("That one is guessable.")
    return out


# ------------------------------------------------------------- access codes --

# No look-alikes: 0/O and 1/I/l get misread when a code is read down the phone.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_code(groups=3, size=4) -> str:
    return "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(size)) for _ in range(groups)
    )


def hash_code(code: str) -> str:
    """Codes are looked up by hash on every unlock, so this is a plain fast
    digest rather than a slow KDF — but the code is normalised first so that
    'abcd efgh' and 'ABCD-EFGH' are the same code."""
    normalised = "".join(ch for ch in code.upper() if ch in ALPHABET)
    return hashlib.sha256(("hv-catalogue:" + normalised).encode()).hexdigest()


def code_hint(code: str) -> str:
    return code.strip().upper()[-4:]


# ----------------------------------------------------------------- cookies --

def sign(value: str, secret: bytes) -> str:
    mac = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{value}.{mac}"


def unsign(signed: str, secret: bytes):
    if not signed or "." not in signed:
        return None
    value, _, mac = signed.rpartition(".")
    expected = hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()[:32]
    return value if hmac.compare_digest(mac, expected) else None


def load_secret(path):
    """A stable server secret, created on first run. Sessions survive restarts
    because of it; deleting the file logs everybody out."""
    if path.exists():
        return path.read_bytes()
    secret = secrets.token_bytes(32)
    path.write_bytes(secret)
    os.chmod(path, 0o600)
    return secret
