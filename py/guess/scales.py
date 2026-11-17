"""Built-in colour scales: ColorBrewer, viridis and friends, turbo, rainbow,
Tableau and d3's categorical schemes (data in _colorscales.py, made by
py/tools/gen_colorscales.mjs from d3-scale-chromatic and Vega).

A scale is named by a string anywhere GUESS takes one: colorBy(degree,
"viridis"), colorize(dept, "Set2"), generateColors("RdBu", 7),
GradientLegend("magma", 0, 10). Names ignore case, spaces, dashes and
underscores; a trailing "_r" reverses the scale ("viridis_r").
"""
import difflib
import re

from . import colors
from ._colorscales import DISCRETE, SCALES
from .model import GuessError

# other names for the same scales (Vega's long names, matplotlib's)
ALIASES = {
    "bluegreen": "BuGn", "bluepurple": "BuPu", "greenblue": "GnBu", "orangered": "OrRd",
    "purplebluegreen": "PuBuGn", "purpleblue": "PuBu", "purplered": "PuRd", "redpurple": "RdPu",
    "yellowgreenblue": "YlGnBu", "yellowgreen": "YlGn", "yelloworangebrown": "YlOrBr",
    "yelloworangered": "YlOrRd", "brownbluegreen": "BrBG", "purplegreen": "PRGn",
    "pinkyellowgreen": "PiYG", "purpleorange": "PuOr", "redblue": "RdBu", "redgrey": "RdGy",
    "redgray": "RdGy", "redyellowblue": "RdYlBu", "redyellowgreen": "RdYlGn",
    "grays": "Greys", "greys": "Greys", "cubehelixdefault": "cubehelix",
    "tab10": "category10", "tab20": "category20", "d3": "category10",
}


def _key(name):
    return re.sub(r"[\s_\-]", "", str(name)).lower()


_BY_KEY = {_key(n): n for n in SCALES}
_BY_KEY.update({_key(a): n for a, n in ALIASES.items()})


def _rgba(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)


class ColorScale:
    """A colour scale: scale.at(0.3) is the colour 30% of the way along,
    scale.colors(5) five colours from it (a categorical scheme's first five;
    for ColorBrewer scales, ColorBrewer's own 5-class scheme), and
    scale.reversed() runs the other way."""

    def __init__(self, name, kind, source, hexes, reverse=False):
        self.name, self.kind, self.source = name, kind, source
        self._hex = list(hexes)
        self.reverse = reverse
        self.stops = [_rgba(h) for h in (self._hex[::-1] if reverse else self._hex)]

    @property
    def categorical(self):
        return self.kind == "categorical"

    def at(self, t):
        """The colour at fraction t (0..1) along the scale."""
        if self.categorical:
            return colors.Color(_hex_to_text(self.stops[int(t * (len(self.stops) - 1) + 0.5)]))
        c = colors.mix_stops(self.stops, t)
        return colors.Color(c[:-4] if c.endswith(",255") and c.count(",") == 3 else c)

    def colors(self, n):
        """n colours from the scale: a categorical scheme's first n (repeating
        if it has fewer); ColorBrewer's n-class scheme when there is one;
        otherwise n evenly spaced along it."""
        n = int(n)
        if n <= 0:
            return []
        if self.categorical:
            return [colors.Color(_hex_to_text(self.stops[i % len(self.stops)])) for i in range(n)]
        brewer = DISCRETE.get(self.name, {}).get(n) if self.kind != "cyclical" else None
        if brewer:
            hexes = brewer.split()
            if self.reverse:
                hexes = hexes[::-1]
            return [colors.Color(_hex_to_text(_rgba(h))) for h in hexes]
        if n == 1:
            return [self.at(0.5)]
        if self.kind == "cyclical":           # the ends are the same colour: don't use both
            return [self.at(i / n) for i in range(n)]
        return [self.at(i / (n - 1)) for i in range(n)]

    def reversed(self):
        """The same scale, running the other way."""
        return ColorScale(self.name, self.kind, self.source, self._hex, not self.reverse)

    def __len__(self):
        return len(self.stops)

    def preview(self, n=None):
        """The colours shown when the scale is printed."""
        if self.categorical:
            return self.colors(len(self.stops) if n is None else n)
        return [self.at(i / 10) for i in range(11)] if n is None else self.colors(n)

    def __repr__(self):
        return f"<colour scale {self.label} ({self.kind})>"

    @property
    def label(self):
        return self.name + ("_r" if self.reverse else "")

    def __eq__(self, other):
        return isinstance(other, ColorScale) and (self.name, self.reverse) == (other.name, other.reverse)

    def __hash__(self):
        return hash((self.name, self.reverse))


def _hex_to_text(c):
    return ",".join(str(v) for v in c[:3])


def find(name):
    """The ColorScale called name, or None (not a scale name)."""
    if isinstance(name, ColorScale):
        return name
    if not isinstance(name, str):
        return None
    k = _key(name)
    rev = False
    if k not in _BY_KEY and k.endswith("r") and k[:-1] in _BY_KEY and re.search(r"[_\-\s.]r$", str(name), re.I):
        k, rev = k[:-1], True
    real = _BY_KEY.get(k)
    if real is None:
        return None
    kind, src, hexes = SCALES[real]
    return ColorScale(real, kind, src, hexes.split(), rev)


def get(name, what="colour scale"):
    """The ColorScale called name; an error with suggestions if there is none."""
    s = find(name)
    if s is not None:
        return s
    near = difflib.get_close_matches(_key(name), list(_BY_KEY), n=3, cutoff=0.6)
    hint = f"; did you mean {', '.join(repr(_BY_KEY[x]) for x in near)}?" if near else ""
    raise GuessError(f"no {what} called {name!r}{hint} (colorScales() lists them)")


def is_scale(x):
    return find(x) is not None


KIND_ORDER = ["sequential", "diverging", "cyclical", "categorical"]


def install(session):
    def cmd(fn):
        session.register_command(fn.__name__, fn)
        return fn

    @cmd
    def colorScale(name):
        """colorScale("viridis") is that colour scale: .at(0.3) is the colour 30%
        of the way along, .colors(5) five colours from it, .reversed() runs the
        other way. Anywhere a scale is taken, its name works too:
        colorBy(degree, "viridis"), colorize(dept, "Set2"),
        generateColors("RdBu", 7), GradientLegend("magma", 0, 10). Add "_r" to
        a name to reverse it ("viridis_r"). colorScales() lists them all."""
        return get(name)

    @cmd
    def colorScales(kind=None):
        """colorScales() lists the built-in colour scales with a preview of each:
        sequential (Blues, viridis, magma, turbo, …), diverging (RdBu, Spectral,
        …), cyclical (rainbow, sinebow) and categorical (Set2, tableau10, …).
        colorScales("diverging") lists one kind. From ColorBrewer, d3 and Vega."""
        if kind is not None and kind not in KIND_ORDER:
            raise GuessError(f"colorScales(kind): kind is one of {', '.join(KIND_ORDER)}")
        from .session import _color_seg
        rows = []
        names = sorted(SCALES, key=lambda n: (KIND_ORDER.index(SCALES[n][0]), SCALES[n][1] != "d3"))
        for n in names:
            k, src, _h = SCALES[n]
            if kind and k != kind:
                continue
            s = find(n)
            prev = []
            for c in s.preview():
                seg = _color_seg(c)
                if seg:
                    prev.append(seg)
            rows.append([n, k, {"g": prev}])
        session.emit({"type": "out", "gid": session.graph_gen,
                      "segs": [{"tbl": {"cols": ["name", "kind", "colours"], "rows": rows},
                                "a": f"{len(rows)} colour scales"}]})

    session.ns["ColorScale"] = ColorScale
