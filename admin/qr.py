"""QR codes in the standard library, for the HELVi Connect app's "scan to get the app"
(item 169). Byte mode, error correction M, versions 1-10 (up to 213 bytes: plenty for a
sign-in link). Checked module for module against the `qrcode` package in tests/test_qr.py.

    matrix(text)   -> list of rows of 0/1 (no quiet zone)
    svg(text)      -> an SVG string, ink on transparent, with a 4-module quiet zone
"""

# (data codewords, ec codewords per block, blocks in group 1, data per block g1, blocks g2, data per block g2) for level M
_M = {1: (16, 10, 1, 16, 0, 0), 2: (28, 16, 1, 28, 0, 0), 3: (44, 26, 1, 44, 0, 0), 4: (64, 18, 2, 32, 0, 0),
      5: (86, 24, 2, 43, 0, 0), 6: (108, 16, 4, 27, 0, 0), 7: (124, 18, 4, 31, 0, 0), 8: (154, 22, 2, 38, 2, 39),
      9: (182, 22, 3, 36, 2, 37), 10: (216, 26, 4, 43, 1, 44)}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}

# GF(256) with polynomial 0x11d
_EXP, _LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11d
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _ec(data, n):
    gen = [1]
    for i in range(n):
        gen = [a ^ _gmul(b, _EXP[i]) for a, b in zip(gen + [0], [0] + gen)]
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j, g in enumerate(gen):
                rem[i + j] ^= _gmul(g, c)
    return rem[len(data):]


def _codewords(data, ver):
    total, ecn, b1, d1, b2, d2 = _M[ver]
    bits = [0, 1, 0, 0]                                              # byte mode
    cc = 8 if ver < 10 else 16
    bits += [(len(data) >> i) & 1 for i in range(cc - 1, -1, -1)]
    for byte in data:
        bits += [(byte >> i) & 1 for i in range(7, -1, -1)]
    cap = total * 8
    bits += [0] * min(4, cap - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    k = 0
    while len(words) < total:
        words.append(0xec if k % 2 == 0 else 0x11)
        k += 1
    blocks, i = [], 0
    for n, d in ((b1, d1), (b2, d2)):
        for _ in range(n):
            blocks.append(words[i:i + d])
            i += d
    ecs = [_ec(b, ecn) for b in blocks]
    out = []
    for k in range(max(len(b) for b in blocks)):
        out += [b[k] for b in blocks if k < len(b)]
    for k in range(ecn):
        out += [e[k] for e in ecs]
    return out


def _bch(value, poly, bits):
    v = value << bits
    top = poly.bit_length()
    while v.bit_length() >= top:
        v ^= poly << (v.bit_length() - top)
    return (value << bits) | v


MASKS = [lambda r, c: (r + c) % 2 == 0, lambda r, c: r % 2 == 0, lambda r, c: c % 3 == 0, lambda r, c: (r + c) % 3 == 0,
         lambda r, c: (r // 2 + c // 3) % 2 == 0, lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
         lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0, lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0]


def _base(ver):
    n = 17 + 4 * ver
    m = [[None] * n for _ in range(n)]

    def finder(r0, c0):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < n and 0 <= cc < n:
                    m[rr][cc] = 1 if (0 <= r <= 6 and 0 <= c <= 6 and (r in (0, 6) or c in (0, 6) or (2 <= r <= 4 and 2 <= c <= 4))) else 0
    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)
    pos = _ALIGN[ver]
    for r in pos:
        for c in pos:
            if m[r][c] is not None:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = 1 if max(abs(dr), abs(dc)) != 1 else 0
    for i in range(8, n - 8):                                         # timing, where alignment left room
        if m[6][i] is None:
            m[6][i] = 1 if i % 2 == 0 else 0
        if m[i][6] is None:
            m[i][6] = 1 if i % 2 == 0 else 0
    m[n - 8][8] = 1                                                   # dark module
    for i in range(9):                                                # reserve format areas
        if m[8][i] is None:
            m[8][i] = 0
        if m[i][8] is None:
            m[i][8] = 0
    for i in range(8):
        if m[8][n - 1 - i] is None:
            m[8][n - 1 - i] = 0
        if m[n - 1 - i][8] is None:
            m[n - 1 - i][8] = 0
    if ver >= 7:
        info = _bch(ver, 0x1f25, 12)
        for i in range(18):
            bit = (info >> i) & 1
            m[i // 3][n - 11 + i % 3] = bit
            m[n - 11 + i % 3][i // 3] = bit
    return m


def _place(m, words, mask):
    n = len(m)
    fixed = [[v is not None for v in row] for row in m]
    out = [list(row) for row in m]
    bits = [(w >> i) & 1 for w in words for i in range(7, -1, -1)]
    k, c, up = 0, n - 1, True
    while c > 0:
        if c == 6:
            c -= 1
        for i in range(n):
            r = n - 1 - i if up else i
            for cc in (c, c - 1):
                if not fixed[r][cc]:
                    b = bits[k] if k < len(bits) else 0
                    k += 1
                    out[r][cc] = b ^ (1 if MASKS[mask](r, cc) else 0)
        up = not up
        c -= 2
    fmt = _bch((0b00 << 3) | mask, 0x537, 10) ^ 0x5412            # level M = 00
    for i in range(15):
        bit = (fmt >> i) & 1
        if i < 6:
            out[i][8] = bit
        elif i < 8:
            out[i + 1][8] = bit
        else:
            out[n - 15 + i][8] = bit
        if i < 8:
            out[8][n - 1 - i] = bit
        elif i < 9:
            out[8][7] = bit
        else:
            out[8][14 - i] = bit
    out[n - 8][8] = 1
    return out


def _penalty(m):
    n = len(m)
    p = 0
    for grid in (m, [list(x) for x in zip(*m)]):
        for row in grid:
            run, prev = 0, None
            for v in row:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prev = 1, v
            if run >= 5:
                p += run - 2
            s = "".join(map(str, row))
            p += 40 * (s.count("10111010000") + s.count("00001011101"))
    for r in range(n - 1):
        for c in range(n - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                p += 3
    dark = sum(map(sum, m))
    p += 10 * (abs(dark * 20 - n * n * 10) // (n * n))
    return p


def matrix(text, mask=None):
    data = text.encode("utf-8")
    for ver in range(1, 11):
        total = _M[ver][0]
        need = 4 + (8 if ver < 10 else 16) + 8 * len(data)
        if need <= total * 8:
            break
    else:
        raise ValueError("too long for a QR code here")
    words = _codewords(data, ver)
    base = _base(ver)
    if mask is not None:
        return _place(base, words, mask)
    return min((_place(base, words, k) for k in range(8)), key=_penalty)


def svg(text, color="#121212"):
    m = matrix(text)
    n = len(m) + 8
    path = "".join("M%d %dh1v1h-1z" % (c + 4, r + 4) for r, row in enumerate(m) for c, v in enumerate(row) if v)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" shape-rendering="crispEdges" role="img" '
            'aria-label="QR code"><path fill="%s" d="%s"/></svg>' % (n, n, color, path))
