"""Color handling, following com/hp/hpl/guess/ui/Colors.java.

GUESS stores colors as strings: a name ("red"), or "r,g,b" / "r,g,b,a".
Names are case-insensitive. We additionally accept "#rrggbb".
"""
import random as _random

from ._colortable import NAMED

COLORS = {}
for _name, _rgb in NAMED.items():
    COLORS[_name.lower()] = _rgb + (255,)


class Color(str):
    """A named color bound in the namespace (e.g. ``red``). Behaves as a string."""

    __slots__ = ()

    def __repr__(self):
        return str(self)


def parse(value, default=None):
    """Return (r, g, b, a) for a GUESS color value, or ``default`` if invalid."""
    if value is None:
        return default
    if isinstance(value, (tuple, list)) and len(value) in (3, 4):
        parts = [int(v) for v in value]
        return _clamp(parts + [255] * (4 - len(parts)))
    s = str(value).strip().lower()
    if s in COLORS:
        return COLORS[s]
    if s.startswith("#") and len(s) in (7, 9):
        try:
            parts = [int(s[i:i + 2], 16) for i in range(1, len(s), 2)]
        except ValueError:
            return default
        return _clamp(parts + [255] * (4 - len(parts)))
    toks = s.replace(",", " ").split()
    if len(toks) in (3, 4):
        try:
            parts = [int(float(t)) for t in toks]
        except ValueError:
            return default
        return _clamp(parts + [255] * (4 - len(parts)))
    return default


def _clamp(parts):
    return tuple(max(0, min(255, p)) for p in parts)


def is_color(value):
    return parse(value) is not None


def normalize(value):
    """Validate a color for storage; returns the stored string form."""
    if isinstance(value, (tuple, list)):
        return ",".join(str(v) for v in parse(value))
    if parse(value) is None:
        raise ValueError(f"invalid color: {value!r}")
    return str(value)


def to_rgba_int(value, default=(0, 0, 0, 255)):
    """Pack as 0xRRGGBB and alpha (0..1) for the renderer."""
    r, g, b, a = parse(value, default)
    return (r << 16) | (g << 8) | b, round(a / 255, 3)


def randomColor(alpha=None):
    r, g, b = (_random.randrange(255) for _ in range(3))
    if alpha is None:
        return f"{r},{g},{b}"
    return f"{r},{g},{b},{int(alpha)}"


def averageColor(c1, c2):
    a = parse(c1, (0, 0, 0, 255))
    b = parse(c2, (255, 255, 255, 255))
    return ",".join(str(int((x + y) / 2)) for x, y in zip(a, b))


def generateColors(*args):
    """generateColors(start, end, n) or generateColors(start, middle, end, n)."""
    if len(args) == 3:
        start, end, n = args
        return _gradient(parse(start, (255, 0, 0, 255)), parse(end, (0, 0, 255, 255)), int(n))
    if len(args) == 4:
        start, middle, end, n = args
        n = int(n)
        first = n // 2 + n % 2
        a = _gradient(parse(start, (255, 0, 0, 255)), parse(middle, (0, 255, 0, 255)), first)
        b = _gradient(parse(middle, (0, 255, 0, 255)), parse(end, (0, 0, 255, 255)), n - first + 1)
        return a + b[1:]
    raise TypeError("generateColors(start, [middle,] end, count)")


def _gradient(c1, c2, n):
    if n <= 0:
        return []
    if n == 1:
        return [",".join(str(v) for v in c1)]
    out = []
    for i in range(n):
        p = i / (n - 1)
        out.append(",".join(str(int(max(0, min(255, a + (b - a) * p)))) for a, b in zip(c1, c2)))
    return out


# --------------------------------------------------------------------------
# Distinct categorical palettes (after Gephi's PaletteGenerator / iWantHue):
# k-means in CIE Lab over in-gamut colours of moderate chroma and lightness,
# then ordered so each next colour is as far as possible from the ones before.
# --------------------------------------------------------------------------

_PALETTE_CACHE = {}


def _lab_candidates():
    import numpy as np
    L, A, B = np.meshgrid(np.arange(35, 81, 2.5), np.arange(-90, 91, 3.0),
                          np.arange(-90, 91, 3.0), indexing="ij")
    L, A, B = L.ravel(), A.ravel(), B.ravel()
    C = np.hypot(A, B)
    keep = (C >= 30) & (C <= 85)
    L, A, B = L[keep], A[keep], B[keep]
    rgb = _lab_to_rgb(L, A, B)
    ok = ((rgb >= 0) & (rgb <= 1)).all(1)
    return np.stack([L[ok], A[ok], B[ok]], 1), rgb[ok]


def _lab_to_rgb(L, A, B):
    import numpy as np
    fy = (L + 16) / 116
    fx = fy + A / 500
    fz = fy - B / 200

    def finv(t):
        t3 = t ** 3
        return np.where(t3 > 0.008856, t3, (t - 16 / 116) / 7.787)

    X, Y, Z = 0.95047 * finv(fx), finv(fy), 1.08883 * finv(fz)
    lin = np.stack([3.2406 * X - 1.5372 * Y - 0.4986 * Z,
                    -0.9689 * X + 1.8758 * Y + 0.0415 * Z,
                    0.0557 * X - 0.2040 * Y + 1.0570 * Z], 1)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.abs(lin) ** (1 / 2.4) - 0.055)


def distinctColors(n, seed=1):
    """distinctColors(n): n clearly different colours (as "r,g,b" strings), the
    most different first — the categorical palette colorize(field) uses."""
    import numpy as np
    n = int(n)
    if n <= 0:
        return []
    key = (n, seed)
    if key in _PALETTE_CACHE:
        return list(_PALETTE_CACHE[key])
    if "cand" not in _PALETTE_CACHE:
        _PALETTE_CACHE["cand"] = _lab_candidates()
    lab, rgb = _PALETTE_CACHE["cand"]
    rng = np.random.default_rng(seed)
    k = min(n, len(lab))
    # k-means++ seeding, then Lloyd iterations
    cent = [lab[rng.integers(len(lab))]]
    d2 = ((lab - cent[0]) ** 2).sum(1)
    for _ in range(1, k):
        cent.append(lab[rng.choice(len(lab), p=d2 / d2.sum())] if d2.sum() > 0 else lab[rng.integers(len(lab))])
        d2 = np.minimum(d2, ((lab - cent[-1]) ** 2).sum(1))
    cent = np.array(cent)
    for _ in range(25):
        lab_c = ((lab[:, None, :] - cent[None, :, :]) ** 2).sum(2).argmin(1)
        new = cent.copy()
        for j in range(k):
            members = lab[lab_c == j]
            if len(members):
                new[j] = members.mean(0)
        if np.allclose(new, cent):
            break
        cent = new
    # snap each centre to its nearest in-gamut candidate
    idx = ((lab[:, None, :] - cent[None, :, :]) ** 2).sum(2).argmin(0)
    cols, lab_sel = rgb[idx], lab[idx]
    # order: start from the most saturated, then farthest-first
    order = [int(np.hypot(lab_sel[:, 1], lab_sel[:, 2]).argmax())]
    dist = ((lab_sel - lab_sel[order[0]]) ** 2).sum(1)
    while len(order) < k:
        dist[order] = -1
        j = int(dist.argmax())
        order.append(j)
        dist = np.minimum(dist, ((lab_sel - lab_sel[j]) ** 2).sum(1))
    out = [",".join(str(int(round(v * 255))) for v in cols[j]) for j in order]
    # more groups than candidates (thousands): cycle
    out = [out[i % len(out)] for i in range(n)]
    _PALETTE_CACHE[key] = out
    return list(out)


def mix_stops(stops, t):
    """Colour at fraction t (0..1) along a gradient through the (r,g,b,a) stops."""
    t = min(max(float(t), 0.0), 1.0)
    seg = t * (len(stops) - 1)
    i = min(int(seg), len(stops) - 2)
    k = seg - i
    a, b = stops[i], stops[i + 1]
    return ",".join(str(int(round(x + (y - x) * k))) for x, y in zip(a, b))
