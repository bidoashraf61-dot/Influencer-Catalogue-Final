"""Web Push in the standard library: VAPID (RFC 8292) and aes128gcm payload
encryption (RFC 8291), so the admin can push to phones without pip packages.

    keys()                         the server's VAPID key pair (made once, kept in admin/.vapid-key)
    public_key()                   base64url of the public key, for the browser's subscribe()
    send(sub, payload, ttl=...)    POST one encrypted message; returns (status, gone)

``sub`` is the browser's PushSubscription JSON: {"endpoint", "keys": {"p256dh", "auth"}}.
``gone`` is True when the push service says the subscription no longer exists
(404/410) and the caller should delete it.

The crypto is plain Python integers: P-256 for ECDH and ES256, AES-128 + GHASH for
GCM. It is slow next to OpenSSL (a few ms per message) but pushes are a handful a
minute. Checked against RFC 8291's worked example and the GCM spec vectors in
tests/test_webpush.py.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".vapid-key")
SUBJECT = "mailto:no-reply@hellovoice.co.uk"


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64u(text):
    text = str(text).strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ------------------------------------------------------------------ P-256 --

P = 0xffffffff00000001000000000000000000000000ffffffffffffffffffffffff
A = P - 3
B = 0x5ac635d8aa3a93e7b3ebbd55769886bc651d06b0cc53b0f63bce3c3e27d2604b
N = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551
G = (0x6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296,
     0x4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5)


def _add(p1, p2):
    """Affine point addition; None is the point at infinity."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return x3, (lam * (x1 - x3) - y1) % P


def _jdouble(X, Y, Z):
    if Y == 0:
        return 0, 1, 0
    ysq = Y * Y % P
    S = 4 * X * ysq % P
    Z2 = Z * Z % P
    M = 3 * (X - Z2) * (X + Z2) % P          # a = -3
    X3 = (M * M - 2 * S) % P
    Y3 = (M * (S - X3) - 8 * ysq * ysq) % P
    return X3, Y3, 2 * Y * Z % P


def _jadd(X1, Y1, Z1, x2, y2):
    """Jacobian + affine."""
    if Z1 == 0:
        return x2, y2, 1
    Z1s = Z1 * Z1 % P
    U2 = x2 * Z1s % P
    S2 = y2 * Z1s * Z1 % P
    H = (U2 - X1) % P
    R = (S2 - Y1) % P
    if H == 0:
        return _jdouble(X1, Y1, Z1) if R == 0 else (0, 1, 0)
    H2 = H * H % P
    H3 = H * H2 % P
    U1H2 = X1 * H2 % P
    X3 = (R * R - H3 - 2 * U1H2) % P
    Y3 = (R * (U1H2 - X3) - Y1 * H3) % P
    return X3, Y3, H * Z1 % P


def mul(k, point=G):
    k %= N
    if k == 0 or point is None:
        return None
    X, Y, Z = 0, 1, 0
    for bit in bin(k)[2:]:
        X, Y, Z = _jdouble(X, Y, Z)
        if bit == "1":
            X, Y, Z = _jadd(X, Y, Z, point[0], point[1])
    if Z == 0:
        return None
    zi = pow(Z, -1, P)
    zi2 = zi * zi % P
    return X * zi2 % P, Y * zi2 * zi % P


def encode_point(pt):
    return b"\x04" + pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big")


def decode_point(raw):
    if len(raw) != 65 or raw[0] != 4:
        raise ValueError("bad public key")
    x, y = int.from_bytes(raw[1:33], "big"), int.from_bytes(raw[33:], "big")
    if (y * y - (x * x * x + A * x + B)) % P:
        raise ValueError("point not on curve")
    return x, y


def new_private():
    return secrets.randbelow(N - 1) + 1


def ecdh(private, public_point):
    shared = mul(private, public_point)
    if shared is None:
        raise ValueError("bad shared point")
    return shared[0].to_bytes(32, "big")


def sign(private, message):
    """ES256: raw r||s (64 bytes) over SHA-256(message)."""
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    while True:
        k = secrets.randbelow(N - 1) + 1
        r = mul(k)[0] % N
        if not r:
            continue
        s = pow(k, -1, N) * (z + r * private) % N
        if s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def verify(public_point, message, sig):
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if not (0 < r < N and 0 < s < N):
        return False
    z = int.from_bytes(hashlib.sha256(message).digest(), "big")
    w = pow(s, -1, N)
    pt = _add(mul(z * w % N), mul(r * w % N, public_point))
    return pt is not None and pt[0] % N == r


# -------------------------------------------------------------- AES-128-GCM --

def _sbox():
    box, p, q = [0] * 256, 1, 1
    while True:                                   # p walks GF(2^8) by 3, q by its inverse
        p = p ^ ((p << 1) & 0xff) ^ (0x1b if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xff
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1 | q >> 7) & 0xff) ^ ((q << 2 | q >> 6) & 0xff) ^ ((q << 3 | q >> 5) & 0xff) ^ ((q << 4 | q >> 4) & 0xff)
        box[p] = x ^ 0x63
        if p == 1:
            break
    box[0] = 0x63
    return box


SBOX = _sbox()


def _xt(b):
    return ((b << 1) ^ 0x1b) & 0xff if b & 0x80 else b << 1


def _expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xt(rcon)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[r * 4:r * 4 + 4], []) for r in range(11)]


def _encrypt_block(rk, block):
    s = [b ^ k for b, k in zip(block, rk[0])]
    for rnd in range(1, 11):
        s = [SBOX[b] for b in s]
        s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]         # ShiftRows (column-major)
        if rnd != 10:
            out = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                t = a[0] ^ a[1] ^ a[2] ^ a[3]
                out += [a[i] ^ t ^ _xt(a[i] ^ a[(i + 1) % 4]) for i in range(4)]
            s = out
        s = [b ^ k for b, k in zip(s, rk[rnd])]
    return bytes(s)


R_GCM = 0xe1 << 120


def _gmul(x, y):
    z, v = 0, y
    for i in range(127, -1, -1):
        if (x >> i) & 1:
            z ^= v
        v = (v >> 1) ^ R_GCM if v & 1 else v >> 1
    return z


def _ghash(h, aad, ct):
    def blocks(data):
        for i in range(0, len(data), 16):
            yield int.from_bytes(data[i:i + 16].ljust(16, b"\0"), "big")
    y = 0
    for blk in list(blocks(aad)) + list(blocks(ct)):
        y = _gmul(y ^ blk, h)
    return _gmul(y ^ ((len(aad) * 8) << 64 | len(ct) * 8), h)


def aes_gcm_encrypt(key, nonce, plaintext, aad=b""):
    """Ciphertext || 16-byte tag. 96-bit nonce only."""
    rk = _expand(key)
    h = int.from_bytes(_encrypt_block(rk, bytes(16)), "big")
    j0 = nonce + b"\0\0\0\1"
    out = bytearray()
    ctr = int.from_bytes(j0, "big")
    for i in range(0, len(plaintext), 16):
        ctr = (ctr & ~0xffffffff) | ((ctr + 1) & 0xffffffff)
        ks = _encrypt_block(rk, ctr.to_bytes(16, "big"))
        chunk = plaintext[i:i + 16]
        out += bytes(a ^ b for a, b in zip(chunk, ks))
    s = _ghash(h, aad, bytes(out))
    tag = (s ^ int.from_bytes(_encrypt_block(rk, j0), "big")).to_bytes(16, "big")
    return bytes(out) + tag


# ------------------------------------------------------------ RFC 8291 ----

def _hkdf(salt, ikm, info, length):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:length]


def encrypt(payload, ua_public_raw, auth_secret, as_private=None, salt=None, rs=4096):
    """The aes128gcm body for one push message (single record)."""
    as_private = as_private or new_private()
    salt = salt or os.urandom(16)
    as_public_raw = encode_point(mul(as_private))
    shared = ecdh(as_private, decode_point(ua_public_raw))
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\0" + ua_public_raw + as_public_raw, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\0", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\0", 12)
    if len(payload) > rs - 17:
        raise ValueError("payload too large")
    body = aes_gcm_encrypt(cek, nonce, payload + b"\x02")
    return salt + struct.pack("!IB", rs, 65) + as_public_raw + body


# --------------------------------------------------------------- VAPID ----

_KEY = None


def keys():
    """(private int, public point). Made on first use and kept in .vapid-key (mode 600)."""
    global _KEY
    if _KEY:
        return _KEY
    d = None
    try:
        with open(KEY_FILE) as fh:
            d = int.from_bytes(unb64u(fh.read().strip()), "big")
    except (OSError, ValueError):
        d = None
    if not d:
        d = new_private()
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(b64u(d.to_bytes(32, "big")))
    _KEY = (d, mul(d))
    return _KEY


def public_key():
    return b64u(encode_point(keys()[1]))


def vapid_header(endpoint, exp=None):
    d, pub = keys()
    u = urllib.parse.urlsplit(endpoint)
    claims = {"aud": "%s://%s" % (u.scheme, u.netloc), "exp": int(exp or time.time() + 12 * 3600), "sub": SUBJECT}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing = (head + "." + body).encode()
    token = head + "." + body + "." + b64u(sign(d, signing))
    return "vapid t=%s, k=%s" % (token, b64u(encode_point(pub)))


def send(sub, payload, ttl=24 * 3600, urgency="normal", topic=None, timeout=15):
    """POST one push. Returns (http status, gone). Never raises on HTTP errors."""
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if isinstance(payload, str):
        payload = payload.encode()
    endpoint = sub["endpoint"]
    if not endpoint.startswith("https://"):
        return 0, True
    body = encrypt(payload, unb64u(sub["keys"]["p256dh"]), unb64u(sub["keys"]["auth"]))
    headers = {"TTL": str(int(ttl)), "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
               "Urgency": urgency, "Authorization": vapid_header(endpoint)}
    if topic:
        headers["Topic"] = "".join(c for c in topic if c.isalnum() or c in "-_")[:32]
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, False
    except urllib.error.HTTPError as e:
        return e.code, e.code in (404, 410)
    except Exception:
        return 0, False
