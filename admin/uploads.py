"""multipart/form-data parsing and photo handling.

`cgi.FieldStorage` would have done this, but `cgi` is deprecated since 3.11 and
gone in 3.13 — on a server we do not control that is a time bomb, so the
parsing is done here instead. It is a small format and we only need the parts
this dashboard posts.
"""

import re
from pathlib import Path

MAX_UPLOAD = 6 * 1024 * 1024  # 6MB — profile photos are tens of KB

# Magic bytes, because a filename tells you nothing about what a file is.
SIGNATURES = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp"),          # RIFF....WEBP, checked further below
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def image_kind(data: bytes):
    """The real format, or None if this is not an image we accept."""
    for sig, kind in SIGNATURES:
        if data.startswith(sig):
            if kind == "webp":
                return "webp" if data[8:12] == b"WEBP" else None
            return kind
    return None


def parse_multipart(body: bytes, content_type: str, multi=()):
    """Return {field: value} where a file part becomes
    {"filename": str, "data": bytes}. Non-file parts decode to str.

    Fields named in `multi` always come back as a list, even when the browser
    sent one part or none — <input multiple> posts one part per file under the
    same name, and the plain dict would keep only the last of them. Naming them
    explicitly means existing callers, none of which repeat a field, keep
    reading a single value.
    """
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not m:
        return {}
    boundary = ("--" + m.group(1)).encode()

    out = {}
    for chunk in body.split(boundary):
        if not chunk or chunk in (b"--\r\n", b"--", b"\r\n"):
            continue
        head, _, payload = chunk.partition(b"\r\n\r\n")
        if not _:
            continue
        payload = payload[:-2] if payload.endswith(b"\r\n") else payload

        headers = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]*)"', headers)
        if not name:
            continue
        filename = re.search(r'filename="([^"]*)"', headers)
        key = name.group(1)
        if filename:
            value = {"filename": filename.group(1), "data": payload}
        else:
            value = payload.decode("utf-8", "replace")
        if key in multi:
            out.setdefault(key, []).append(value)
        else:
            out[key] = value

    for key in multi:
        out.setdefault(key, [])
    return out


def photo_bytes(data: bytes):
    """(ok, error) for one image, without writing it. save_photo() and the bulk
    uploader apply the same two rules, so a file the roster form would reject
    is not quietly accepted in a batch of eighty."""
    if len(data) > MAX_UPLOAD:
        return False, "over 6MB"
    if not image_kind(data):
        return False, "not a JPEG, PNG, WebP or GIF"
    return True, None


def write_photo(data: bytes, code: str, photo_dir: Path):
    """Write bytes as <CODE>.jpg. Assumes photo_bytes() has passed."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "", code).strip(".") or "creator"
    photo_dir.mkdir(parents=True, exist_ok=True)
    (photo_dir / (safe + ".jpg")).write_bytes(data)
    return safe + ".jpg"


def save_photo(part, code: str, photo_dir: Path):
    """Write an uploaded photo as <CODE>.jpg. Returns (filename, error).

    The extension is always .jpg because the catalogue builds its URLs that
    way; the bytes are whatever was uploaded, and browsers sniff content, so a
    PNG served as .jpg still renders. Keeping one naming rule is worth more
    here than being pedantic about the extension.
    """
    if not part or not isinstance(part, dict) or not part.get("data"):
        return None, None
    data = part["data"]
    ok, why = photo_bytes(data)
    if not ok:
        return None, "That file is " + why + "."
    return write_photo(data, code, photo_dir), None
