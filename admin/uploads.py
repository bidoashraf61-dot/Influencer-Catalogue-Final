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


def parse_multipart(body: bytes, content_type: str):
    """Return {field: value} where a file part becomes
    {"filename": str, "data": bytes}. Non-file parts decode to str."""
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
        if filename:
            out[name.group(1)] = {"filename": filename.group(1), "data": payload}
        else:
            out[name.group(1)] = payload.decode("utf-8", "replace")
    return out


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
    if len(data) > MAX_UPLOAD:
        return None, "That image is over 6MB."
    kind = image_kind(data)
    if not kind:
        return None, "That file is not a JPEG, PNG, WebP or GIF."

    safe = re.sub(r"[^A-Za-z0-9._-]", "", code).strip(".") or "creator"
    photo_dir.mkdir(parents=True, exist_ok=True)
    (photo_dir / (safe + ".jpg")).write_bytes(data)
    return safe + ".jpg", None
